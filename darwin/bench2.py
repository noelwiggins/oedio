"""Benchmark series 2 (Phase 2b): one cycle every few hours.

Each cycle:
  * anchor   H1-H3, replicate 0, fixed seeds. Controls must repeat exactly
             (reproducibility check) and give a continuous line back to series 1.
  * fresh    FRESH_PER_CYCLE never-reused problems drawn from the series-2
             distribution, FRESH_REPLICATES replicates each, fresh seeds.
             All claims are judged on these cells only, so consecutive cycles
             are independent evidence and "robust" means it held on new problems.
Contestants at an equal evaluation budget:
    random, hillclimb, darwin (no memory), darwin_memory (rule, no failure
    weighting), darwin_memory_fw (rule + failure weighting),
    darwin_memory_learned (learned retrieval; identical to the rule until the
    model has enough transfer data). llm_direct is a reference on anchors only.
Benchmarks read memory frozen at the start of the cycle and never write to it.
"""
from __future__ import annotations

import json
import time

import numpy as np
import sqlalchemy as sa

from . import baselines, bench, core, costs, life, memory, store, suite

S = store
SERIES = 2
CONTESTANTS = {
    "random": bench.CONTESTANTS["random"],
    "hillclimb": bench.CONTESTANTS["hillclimb"],
    "darwin": bench.CONTESTANTS["darwin"],
    "darwin_memory": bench.CONTESTANTS["darwin_memory"],
    "darwin_memory_fw": bench.CONTESTANTS["darwin_memory_fw"],
    "darwin_memory_learned": "Darwin + Discovery Memory with learned retrieval (falls back to the rule until trained)",
    "llm_direct": bench.CONTESTANTS["llm_direct"] + "; anchors only",
}
MEMORY_VARIANTS = {"darwin_memory": ("rule", False), "darwin_memory_fw": ("rule", True),
                   "darwin_memory_learned": ("learned", True)}
PARAMS = {"max_evals": 500, "population": 30, "train_seeds": 2}
STANDING = {
    "memory": ("darwin_memory_fw", "darwin",
               "On never-seen problems at an equal budget, Darwin with Discovery Memory scores higher than "
               "Darwin without memory (series 2)."),
    "learned": ("darwin_memory_learned", "darwin_memory_fw",
                "Learned memory retrieval scores higher than rule-based retrieval on never-seen problems (series 2)."),
    "random": ("darwin", "random",
               "On never-seen problems at an equal budget, Darwin scores higher than random search (series 2)."),
    "hillclimb": ("darwin", "hillclimb",
                  "On never-seen problems at an equal budget, Darwin scores higher than a hill climber (series 2)."),
}
COMPARISONS = [("darwin_memory_fw", "darwin"), ("darwin_memory", "darwin"), ("darwin_memory_learned", "darwin"),
               ("darwin_memory_fw", "darwin_memory"), ("darwin_memory_learned", "darwin_memory_fw"),
               ("darwin", "random"), ("darwin", "hillclimb"), ("darwin_memory_fw", "hillclimb"),
               ("hillclimb", "random")]


def _cell(exp_id, prob, rep, seed, mem_head, r0, r1, spec, set_progress, label):
    base = core.Config.from_dict({
        "world": suite.WORLD, "objective": prob["objective"], "conditions": prob["conditions"],
        "population": PARAMS["population"], "generations": 400, "islands": 2, "train_seeds": PARAMS["train_seeds"],
        "holdout_seeds": 8, "ticks": suite.TICKS, "cohort": suite.COHORT, "max_evals": PARAMS["max_evals"],
        "stagnation": 400, "seed": int(seed)})
    seeds = base.train_seed_list()
    cond = life.Conditions(**prob["conditions"])
    results = {}

    def record(name, genome, train_best, evals, cpu, detail):
        sc = bench._score(genome, prob, spec)
        results[name] = {"genome": genome, "score": float(sc.mean()), "seeds": sc,
                         "normalized": bench._norm(float(sc.mean()), r0, r1), "evals": evals, "cpu": cpu,
                         "detail": detail, "train_best": train_best}

    for name in ("darwin",) + tuple(MEMORY_VARIANTS):
        set_progress({"phase": f"{label}: {name}"})
        t0 = time.process_time()
        c = core.Config.from_dict(base.to_dict())
        used = []
        if name != "darwin":
            mode, fw = MEMORY_VARIANTS[name]
            used = memory.retrieve(suite.WORLD, prob["objective"], prob["conditions"], failure_weighting=fw,
                                   upto_id=mem_head, mode=mode)
            c.memory, c.memory_failure_weighting = True, fw
            c.seed_genomes = [{"memory_id": e["memory_id"], "genome": e["genome"]} for e in used]
        ev = core.Evolution(c).run()
        record(name, ev.best.genome, ev.best.fitness, len(ev._cache), time.process_time() - t0, {
            "generations": len(ev.history), "stop_reason": ev.stop_reason, "digest": ev.digest(),
            "retrieval": used[0]["retrieval"] if used else None,
            "memory_seeds": [{"memory": S.fmt_mem(e["memory_id"]), "distance": e["distance"], "weight": e["weight"]}
                             for e in used],
            "winner_from_memory": S.fmt_mem(ev.winner_memory_id()) if ev.winner_memory_id() else None})
    n_budget = results["darwin"]["evals"]
    set_progress({"phase": f"{label}: baselines"})
    t0 = time.process_time()
    g, fb, n = baselines.random_search(spec, prob["objective"], cond, seeds, n_budget, base.seed + 1,
                                       suite.TICKS, suite.COHORT)
    record("random", g, fb, n, time.process_time() - t0, {})
    t0 = time.process_time()
    g, fb, n = baselines.hill_climb(spec, prob["objective"], cond, seeds, n_budget, base.seed + 2,
                                    suite.TICKS, suite.COHORT)
    record("hillclimb", g, fb, n, time.process_time() - t0, {})
    return results


def run(exp, set_progress):
    exp_id = exp["id"]
    spec = life.get_spec(suite.WORLD)
    day = (exp["created_at"] or S.now())[:10]
    mem_head = memory.head_id()
    mem_size = len(memory.entries(suite.WORLD, active_only=True))
    model = memory.model_info()
    anchors = suite.anchors()
    fresh = suite.fresh_problems(exp_id)
    S.append("benchmark.started", {"series": SERIES, "suite": suite.SUITE2, "anchors": [p["id"] for p in anchors],
                                   "fresh": [{"id": p["id"], "objective": p["objective"], "conditions": p["conditions"]}
                                             for p in fresh],
                                   "memory_frozen_at": S.fmt_mem(mem_head) if mem_head else None,
                                   "active_memories": mem_size, "learned_model": model}, experiment_id=exp_id)
    cells = {"anchor": {}, "fresh": {}}
    total_cpu, llm_usd = 0.0, 0.0
    jobs = [("anchor", p, i, s) for p in anchors for i, s in enumerate(p["search_seeds"])] + \
           [("fresh", p, i, s) for p in fresh for i, s in enumerate(p["search_seeds"])]
    calib = {}
    for n_done, (group, prob, rep, seed) in enumerate(jobs):
        label = f"{group} {prob['id']} r{rep + 1} ({n_done + 1}/{len(jobs)})"
        set_progress({"phase": label, "cell": n_done, "of": len(jobs)})
        if prob["id"] not in calib:
            if group == "anchor":
                r0, r1, ccpu = bench.calibrate(prob, bench.DEFAULTS["calibration_n"], suite.SUITE_VERSION)
            else:
                r0, r1, ccpu = bench.calibrate(prob, suite.FRESH_CALIBRATION_N, suite.SUITE2)
            total_cpu += ccpu
            calib[prob["id"]] = {"r0": r0, "r1": r1}
        r0, r1 = calib[prob["id"]]["r0"], calib[prob["id"]]["r1"]
        res = _cell(exp_id, prob, rep, seed, mem_head, r0, r1, spec, lambda p: set_progress({**p, "cell": n_done, "of": len(jobs)}), label)
        with S.engine().begin() as conn:
            for name, r in res.items():
                total_cpu += r["cpu"]
                conn.execute(S.bench_results.insert().values(
                    experiment_id=exp_id, day=day, split=group, suite=suite.SUITE2, problem=prob["id"],
                    contestant=name, replicate=rep, evaluations=int(r["evals"]), cpu_s=round(r["cpu"], 4),
                    cost_usd=costs.compute_usd(r["cpu"]), cost_kind="estimated", score=r["score"],
                    score_seeds=S.canon([round(float(x), 6) for x in r["seeds"]]), normalized=r["normalized"],
                    genome=S.canon([round(float(x), 6) for x in r["genome"]]),
                    detail=S.canon({**r["detail"], "train_best": r["train_best"], "objective": prob["objective"],
                                    "conditions": prob["conditions"], "seed": int(seed)}),
                    code_version=S.code_version()))
            S.append("benchmark.cell", {"group": group, "problem": prob["id"], "replicate": rep,
                                        "normalized": {k: round(v["normalized"], 4) for k, v in res.items()}},
                     experiment_id=exp_id, cost_usd=costs.compute_usd(sum(v["cpu"] for v in res.values())),
                     cost_kind="estimated", conn=conn)
        cells[group][(prob["id"], rep)] = res
    for prob in anchors:
        ref = bench._llm_reference(exp_id, prob, day, "anchor", calib[prob["id"]]["r0"], calib[prob["id"]]["r1"],
                                   suite_tag=suite.SUITE2)
        if ref:
            llm_usd += ref.get("new_cost", 0.0)

    def agg(cs):
        by = {}
        for res in cs.values():
            for name, r in res.items():
                by.setdefault(name, []).append(r["normalized"])
        return {k: {"mean": round(float(np.mean(v)), 4), "sd": round(float(np.std(v, ddof=1)) if len(v) > 1 else 0.0, 4),
                    "n": len(v)} for k, v in by.items()}

    per_problem = {}
    for (pid, rep), res in list(cells["fresh"].items()) + list(cells["anchor"].items()):
        for name, r in res.items():
            per_problem.setdefault(pid, {}).setdefault(name, []).append(r["normalized"])
    per_problem = {pid: {k: round(float(np.mean(v)), 4) for k, v in d.items()} for pid, d in per_problem.items()}
    comps = {f"{a}__vs__{b}": bench.paired(cells["fresh"], a, b) for a, b in COMPARISONS}
    wins = 0
    for res in cells["fresh"].values():
        best_base = max(("random", "hillclimb"), key=lambda k: res[k]["score"])
        if int((res["darwin_memory_fw"]["seeds"] > res[best_base]["seeds"]).sum()) >= 7:
            wins += 1
    practice_usd = bench._practice_cost_since(exp_id)
    compute_usd = costs.compute_usd(total_cpu)
    spend = compute_usd + llm_usd + practice_usd
    drift = _anchor_drift(exp_id, cells["anchor"])
    summary = {"benchmark": {
        "series": SERIES, "split": "cycle", "suite": suite.SUITE2, "world": suite.WORLD, "day": day,
        "cycle_started": exp["created_at"], "params": {**PARAMS, "fresh_problems": len(fresh),
                                                       "fresh_replicates": suite.FRESH_REPLICATES},
        "problems": [p["id"] for p in anchors + fresh],
        "fresh": [{"id": p["id"], "objective": p["objective"], "conditions": p["conditions"]} for p in fresh],
        "memory_size": mem_size, "memory_frozen_at": S.fmt_mem(mem_head) if mem_head else None,
        "learned_model": model,
        "contestants": agg(cells["fresh"]), "anchor": {"contestants": agg(cells["anchor"])},
        "per_problem": per_problem, "comparisons": comps, "calibration": calib,
        "validated_wins": {"wins": wins, "cells": len(cells["fresh"]),
                           "definition": "fresh cells where the full system beat the better of random search and "
                                         "hill climbing on at least 7 of 8 scoring seeds"},
        "spend": {"benchmark_compute_usd": round(compute_usd, 6), "llm_usd": round(llm_usd, 6),
                  "practice_compute_usd": round(practice_usd, 6), "total_usd": round(spend, 6),
                  "cpu_s": round(total_cpu, 2)},
        "usd_per_validated_win": round(spend / wins, 6) if wins else None,
        "validated_wins_per_10usd": round(wins / spend * 10, 2) if spend > 0 else None,
        "control_drift": drift}}
    summary["benchmark"]["claims"] = update_claims(exp_id, day, comps, mem_size, model)
    S.append("benchmark.finished", {k: summary["benchmark"][k] for k in
                                    ("series", "day", "contestants", "comparisons", "validated_wins", "spend",
                                     "memory_size", "control_drift", "usd_per_validated_win")},
             experiment_id=exp_id, cost_usd=compute_usd, cost_kind="estimated")
    return summary


def _anchor_drift(exp_id, anchor_cells):
    with S.engine().connect() as c:
        prev = c.execute(sa.select(sa.func.max(S.bench_results.c.experiment_id)).where(
            (S.bench_results.c.experiment_id < exp_id) & (S.bench_results.c.suite == suite.SUITE2) &
            (S.bench_results.c.split == "anchor") & (S.bench_results.c.code_version == S.code_version()))).scalar()
        if not prev:
            return {"checked": False, "note": "no earlier series-2 cycle with the same code version"}
        rows = c.execute(sa.select(S.bench_results.c.problem, S.bench_results.c.replicate,
                                   S.bench_results.c.contestant, S.bench_results.c.score).where(
            (S.bench_results.c.experiment_id == prev) & (S.bench_results.c.split == "anchor") &
            S.bench_results.c.contestant.in_(["random", "hillclimb", "darwin"]))).all()
    diffs = []
    for pid, rep, name, score in rows:
        r = anchor_cells.get((pid, rep), {}).get(name)
        if r is not None and abs(r["score"] - score) > 1e-9:
            diffs.append({"problem": pid, "contestant": name, "before": score, "now": r["score"]})
    if diffs:
        S.append("failure.nondeterminism", {"compared_with": S.fmt_exp(prev), "differences": diffs[:20]},
                 experiment_id=exp_id)
    return {"checked": True, "compared_with": S.fmt_exp(prev), "identical": not diffs, "differences": len(diffs)}


def _streak(key):
    rows = history(limit=30)
    streak = 0
    for b in reversed(rows):
        if ((b.get("claims") or {}).get(key) or {}).get("replicated_today"):
            streak += 1
        else:
            break
    return streak


def update_claims(exp_id, day, comps, mem_size, model):
    out = {}
    existing = {c["kind"]: c for c in S.all_claims() if (c["kind"] or "").startswith("standing:")}
    for key, (a, b, statement) in STANDING.items():
        kind = f"standing:{key}:{suite.SUITE2}"
        cmp = comps.get(f"{a}__vs__{b}")
        cl = existing.get(kind)
        if cl is None:
            cid = S.add_claim(exp_id, kind, statement, {"comparison": f"{a} vs {b}", "suite": suite.SUITE2},
                              "candidate", "standing claim opened with the first series-2 cycle")
            prev = "candidate"
        else:
            cid, prev = cl["id"], cl["status"]
        rep = bool(cmp and cmp["mean_diff"] > 0 and cmp["p_sign_test"] <= 0.05)
        if key == "memory" and mem_size == 0:
            new, reason, rep = "candidate", "Discovery Memory is empty", False
        elif key == "learned" and not model.get("ready"):
            new, reason, rep = "candidate", (f"learned retrieval not active yet (needs {model.get('needs')} recorded "
                                             "transfers); both variants used the rule"), False
        elif cmp is None:
            new, reason = prev, "no comparison data"
        elif rep:
            streak = _streak(key) + 1
            new = "robust" if streak >= 3 else "replicated"
            reason = (f"cycle {S.fmt_exp(exp_id)}: {cmp['wins']}/{cmp['n']} paired wins on fresh problems, "
                      f"mean +{cmp['mean_diff']}, p={cmp['p_sign_test']}" +
                      (f"; held on fresh problems {streak} cycles running" if streak >= 3 else ""))
        elif cmp["mean_diff"] > 0:
            new, reason = "observed", f"cycle {S.fmt_exp(exp_id)}: ahead by {cmp['mean_diff']} but p={cmp['p_sign_test']}"
        else:
            new = ("failed replication" if prev in ("replicated", "robust")
                   else "contradicted" if prev == "observed" else "candidate")
            reason = f"cycle {S.fmt_exp(exp_id)}: not ahead ({cmp['wins']} wins, {cmp['losses']} losses, mean {cmp['mean_diff']})"
        if new != prev:
            S.set_claim_status(cid, new, reason, evidence=cmp, experiment_id=exp_id)
        out[key] = {"claim": S.fmt_claim(cid), "status": new, "reason": reason, "replicated_today": rep}
    return out


def history(limit=200):
    return bench.history("cycle", limit=limit)


def versions():
    return bench.versions("fresh", suite.SUITE2)


def learning_curve(limit=200):
    """Fresh-problem score of each contestant per cycle, plus memory size: the curve that should rise."""
    out = []
    for b in history(limit):
        out.append({"label": b["label"], "day": b["day"], "memory_size": b["memory_size"],
                    "contestants": {k: v["mean"] for k, v in (b.get("contestants") or {}).items()},
                    "memory_effect": (b["comparisons"].get("darwin_memory_fw__vs__darwin") or {}).get("mean_diff")})
    return out
