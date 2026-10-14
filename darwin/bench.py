"""Daily benchmark (Brief s.17, 20, 23, 56-57, 61-64).

Every day, on the held-out problems, at an equal evaluation budget:

    random       best of N random genomes
    hillclimb    (1 + lambda) hill climber
    darwin       Darwin Core, no memory                       (control)
    darwin_memory     + Discovery Memory seeds                (ablation: no failure weighting)
    darwin_memory_fw  + Discovery Memory with failure weighting  (full system)
    llm_direct   an LLM-designed hand rule (life-1.0 genome), no search; reference only

Each search runs on its own training seeds, then the winner is scored on
SCORING_SEEDS seeds no search ever saw. Scores are normalised per problem
against a fixed calibration (0 = median random genome, 1 = best of 500 random
genomes on the same scoring seeds). Search seeds are fixed per (problem,
replicate), so the control contestants repeat bit-for-bit each day: a change
in their score with unchanged code is flagged as nondeterminism. Memory is the
only thing that changes from day to day. Benchmarks read memory, frozen at the
start of the run, and never write to it.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import numpy as np
import sqlalchemy as sa

from . import baselines, core, costs, life, memory, store, suite

S = store
CONTESTANTS = {
    "random": "Random search: best of N random genomes",
    "hillclimb": "Hill climber: (1+20) evolution strategy, 1/5th success rule",
    "darwin": "Darwin Core without memory (control)",
    "darwin_memory": "Darwin + Discovery Memory, no failure weighting (ablation)",
    "darwin_memory_fw": "Darwin + Discovery Memory + Failure Memory weighting (full system)",
    "llm_direct": "LLM-designed hand rule in the 10-gene life-1.0 representation; no search (reference only)",
}
SEARCH = ("random", "hillclimb", "darwin", "darwin_memory", "darwin_memory_fw")
DEFAULTS = {"replicates": 3, "max_evals": 500, "population": 30, "train_seeds": 2, "calibration_n": 500}
STANDING = {
    "memory": ("darwin_memory_fw", "darwin",
               "At an equal evaluation budget, Darwin with Discovery Memory scores higher than Darwin without "
               "memory on held-out problems ({suite})."),
    "random": ("darwin", "random",
               "At an equal evaluation budget, Darwin scores higher than random search on held-out problems ({suite})."),
    "hillclimb": ("darwin", "hillclimb",
                  "At an equal evaluation budget, Darwin scores higher than a hill climber on held-out problems ({suite})."),
}
COMPARISONS = [("darwin_memory_fw", "darwin"), ("darwin_memory", "darwin"), ("darwin_memory_fw", "darwin_memory"),
               ("darwin", "random"), ("darwin", "hillclimb"), ("darwin_memory_fw", "hillclimb"),
               ("hillclimb", "random")]


def _score(genome, prob, spec):
    f, _ = life.evaluate(np.asarray(genome, dtype=np.float64)[None], prob["objective"],
                         life.Conditions(**prob["conditions"]), suite.scoring_seeds(prob["index"]),
                         suite.TICKS, suite.COHORT, spec)
    return f[0]


def calibrate(prob, n=DEFAULTS["calibration_n"]):
    """Fixed per-problem normalisation, computed once per suite and world version."""
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.calibration).where(
            (S.calibration.c.suite == suite.SUITE_VERSION) & (S.calibration.c.problem == prob["id"]) &
            (S.calibration.c.world == suite.WORLD)).order_by(S.calibration.c.id).limit(1)).mappings().first()
    if row:
        return row["r0"], row["r1"], 0.0
    spec = life.get_spec(suite.WORLD)
    t0 = time.process_time()
    rng = np.random.default_rng(424242 + prob["index"])
    gs = life.random_genomes(rng, n, spec)
    f, _ = life.evaluate(gs, prob["objective"], life.Conditions(**prob["conditions"]),
                         suite.scoring_seeds(prob["index"]), suite.TICKS, suite.COHORT, spec)
    m = f.mean(1)
    r0, r1 = float(np.median(m)), float(m.max())
    cpu = time.process_time() - t0
    with S.engine().begin() as c:
        c.execute(S.calibration.insert().values(
            created_at=S.now(), suite=suite.SUITE_VERSION, problem=prob["id"], world=suite.WORLD, r0=r0, r1=r1,
            detail=S.canon({"n_random": n, "p90": float(np.percentile(m, 90)), "mean": float(m.mean()),
                            "cpu_s": round(cpu, 3), "note": "r1 is the best of n random genomes scored on the "
                            "scoring seeds themselves, so it is an optimistic reference"})))
        S.append("benchmark.calibrated", {"problem": prob["id"], "r0": r0, "r1": r1, "n_random": n},
                 cost_usd=costs.compute_usd(cpu), cost_kind="estimated", conn=c)
    return r0, r1, cpu


def _norm(x, r0, r1):
    return (x - r0) / (r1 - r0) if r1 - r0 > 1e-12 else 0.0


def paired(cells, a, b):
    """Paired comparison over (problem, replicate) cells: normalised score of a minus b."""
    diffs = []
    for key, by in cells.items():
        if a in by and b in by:
            diffs.append(by[a]["normalized"] - by[b]["normalized"])
    if not diffs:
        return None
    d = np.array(diffs)
    wins, losses = int((d > 1e-12).sum()), int((d < -1e-12).sum())
    return {"a": a, "b": b, "n": len(d), "wins": wins, "losses": losses, "ties": len(d) - wins - losses,
            "mean_diff": round(float(d.mean()), 4), "sd_diff": round(float(d.std(ddof=1)) if len(d) > 1 else 0.0, 4),
            "p_sign_test": round(core.sign_test_p(wins, wins + losses), 5) if wins + losses else 1.0}


def run(exp, set_progress):
    """Run one benchmark experiment row. Returns the summary dict."""
    cfg = json.loads(exp["config"])
    split = cfg.get("split", "holdout")
    params = {**DEFAULTS, **{k: cfg[k] for k in DEFAULTS if k in cfg}}
    probs = [p for p in suite.problems(split) if not cfg.get("problems") or p["id"] in cfg["problems"]]
    spec = life.get_spec(suite.WORLD)
    exp_id = exp["id"]
    day = (exp["created_at"] or S.now())[:10]
    mem_head = memory.head_id()
    mem_size = memory.size(suite.WORLD)
    S.append("benchmark.started", {"split": split, "suite": suite.SUITE_VERSION, "problems": [p["id"] for p in probs],
                                   "params": params, "memory_frozen_at": S.fmt_mem(mem_head) if mem_head else None,
                                   "memory_size": mem_size}, experiment_id=exp_id)
    if split == "final":
        S.append("benchmark.final_used", {"problems": [p["id"] for p in probs]}, experiment_id=exp_id)

    cells = {}
    total_cpu = 0.0
    rows = []
    llm_usd = 0.0
    calib = {}
    n_cells = len(probs) * params["replicates"]
    done = 0
    for prob in probs:
        r0, r1, ccpu = calibrate(prob, params["calibration_n"])
        total_cpu += ccpu
        calib[prob["id"]] = {"r0": r0, "r1": r1}
        cond = life.Conditions(**prob["conditions"])
        for rep in range(params["replicates"]):
            set_progress({"phase": f"benchmark {prob['id']} replicate {rep + 1}", "cell": done, "of": n_cells})
            base = core.Config.from_dict({
                "world": suite.WORLD, "objective": prob["objective"], "conditions": prob["conditions"],
                "population": params["population"], "generations": 400, "islands": 2,
                "train_seeds": params["train_seeds"], "holdout_seeds": 8, "ticks": suite.TICKS,
                "cohort": suite.COHORT, "max_evals": params["max_evals"], "stagnation": 400,
                "seed": suite.search_seed(prob["index"], rep)})
            seeds = base.train_seed_list()
            results = {}

            def record(name, genome, train_best, evals, cpu, detail):
                sc = _score(genome, prob, spec)
                nm = _norm(float(sc.mean()), r0, r1)
                results[name] = {"genome": genome, "score": float(sc.mean()), "seeds": sc, "normalized": nm,
                                 "evals": evals, "cpu": cpu, "detail": detail, "train_best": train_best}

            for name in ("darwin", "darwin_memory", "darwin_memory_fw"):
                set_progress({"phase": f"benchmark {prob['id']} r{rep + 1}: {name}", "cell": done, "of": n_cells})
                t0 = time.process_time()
                c = core.Config.from_dict(base.to_dict())
                seeds_used = []
                if name != "darwin":
                    seeds_used = memory.retrieve(suite.WORLD, prob["objective"], prob["conditions"],
                                                 failure_weighting=(name == "darwin_memory_fw"), upto_id=mem_head)
                    c.memory, c.memory_failure_weighting = True, name == "darwin_memory_fw"
                    c.seed_genomes = [{"memory_id": e["memory_id"], "genome": e["genome"]} for e in seeds_used]
                ev = core.Evolution(c).run()
                cpu = time.process_time() - t0
                record(name, ev.best.genome, ev.best.fitness, len(ev._cache), cpu, {
                    "generations": len(ev.history), "stop_reason": ev.stop_reason, "digest": ev.digest(),
                    "memory_seeds": [{"memory": S.fmt_mem(e["memory_id"]), "distance": e["distance"],
                                      "weight": e["weight"]} for e in seeds_used],
                    "winner_from_memory": S.fmt_mem(ev.winner_memory_id()) if ev.winner_memory_id() else None})
            n_budget = results["darwin"]["evals"]
            set_progress({"phase": f"benchmark {prob['id']} r{rep + 1}: baselines", "cell": done, "of": n_cells})
            t0 = time.process_time()
            g, fb, used = baselines.random_search(spec, prob["objective"], cond, seeds, n_budget, base.seed + 1,
                                                  suite.TICKS, suite.COHORT)
            record("random", g, fb, used, time.process_time() - t0, {})
            t0 = time.process_time()
            g, fb, used = baselines.hill_climb(spec, prob["objective"], cond, seeds, n_budget, base.seed + 2,
                                               suite.TICKS, suite.COHORT)
            record("hillclimb", g, fb, used, time.process_time() - t0, {})

            with S.engine().begin() as conn:
                for name, r in results.items():
                    total_cpu += r["cpu"]
                    conn.execute(S.bench_results.insert().values(
                        experiment_id=exp_id, day=day, split=split, suite=suite.SUITE_VERSION, problem=prob["id"],
                        contestant=name, replicate=rep, evaluations=int(r["evals"]), cpu_s=round(r["cpu"], 4),
                        cost_usd=costs.compute_usd(r["cpu"]), cost_kind="estimated", score=r["score"],
                        score_seeds=S.canon([round(float(x), 6) for x in r["seeds"]]), normalized=r["normalized"],
                        genome=S.canon([round(float(x), 6) for x in r["genome"]]),
                        detail=S.canon({**r["detail"], "train_best": r["train_best"]}), code_version=S.code_version()))
                S.append("benchmark.cell", {"problem": prob["id"], "replicate": rep, "budget": n_budget,
                                            "normalized": {k: round(v["normalized"], 4) for k, v in results.items()}},
                         experiment_id=exp_id, cost_usd=costs.compute_usd(sum(v["cpu"] for v in results.values())),
                         cost_kind="estimated", conn=conn)
            cells[(prob["id"], rep)] = results
            done += 1

        # LLM reference contestant: designed once per problem/model/prompt, then re-scored.
        ref = _llm_reference(exp_id, prob, day, split, r0, r1)
        if ref:
            llm_usd += ref.get("new_cost", 0.0)

    # Aggregate
    by_c = {}
    for (pid, rep), res in cells.items():
        for name, r in res.items():
            by_c.setdefault(name, []).append(r["normalized"])
    contestants = {k: {"mean": round(float(np.mean(v)), 4), "sd": round(float(np.std(v, ddof=1)) if len(v) > 1 else 0.0, 4),
                       "n": len(v)} for k, v in by_c.items()}
    per_problem = {}
    for (pid, rep), res in cells.items():
        for name, r in res.items():
            per_problem.setdefault(pid, {}).setdefault(name, []).append(r["normalized"])
    per_problem = {pid: {k: round(float(np.mean(v)), 4) for k, v in d.items()} for pid, d in per_problem.items()}
    comps = {f"{a}__vs__{b}": paired(cells, a, b) for a, b in COMPARISONS}

    # Validated wins: full system beats the better baseline on >= 7 of 8 scoring seeds.
    wins = 0
    for res in cells.values():
        best_base = max(("random", "hillclimb"), key=lambda k: res[k]["score"])
        a, b = res["darwin_memory_fw"]["seeds"], res[best_base]["seeds"]
        if int((a > b).sum()) >= 7:
            wins += 1
    practice_usd = _practice_cost_since(exp_id)
    compute_usd = costs.compute_usd(total_cpu)
    spend = compute_usd + llm_usd + practice_usd

    # Nondeterminism check: controls must repeat yesterday's scores under unchanged code.
    drift = _control_drift(exp_id, split, cells)
    summary = {
        "benchmark": {"split": split, "suite": suite.SUITE_VERSION, "world": suite.WORLD, "day": day, "params": params,
                      "problems": [p["id"] for p in probs], "memory_size": mem_size,
                      "memory_frozen_at": S.fmt_mem(mem_head) if mem_head else None,
                      "contestants": contestants, "per_problem": per_problem, "comparisons": comps,
                      "calibration": calib,
                      "validated_wins": {"wins": wins, "cells": len(cells),
                                         "definition": "cells where the full system beat the better of random search "
                                                       "and hill climbing on at least 7 of 8 scoring seeds"},
                      "spend": {"benchmark_compute_usd": round(compute_usd, 6), "llm_usd": round(llm_usd, 6),
                                "practice_compute_usd": round(practice_usd, 6), "total_usd": round(spend, 6),
                                "cpu_s": round(total_cpu, 2)},
                      "validated_wins_per_10usd": round(wins / spend * 10, 2) if spend > 0 else None,
                      "control_drift": drift}}
    if split == "holdout":
        summary["benchmark"]["claims"] = update_standing_claims(exp_id, day, comps, mem_size)
    S.append("benchmark.finished", {k: summary["benchmark"][k] for k in
                                    ("split", "day", "contestants", "comparisons", "validated_wins", "spend",
                                     "memory_size", "control_drift")},
             experiment_id=exp_id, cost_usd=compute_usd, cost_kind="estimated")
    return summary


def _practice_cost_since(exp_id):
    """Compute spent on practice runs since the previous daily benchmark (memory-building cost)."""
    with S.engine().connect() as c:
        prev = c.execute(sa.select(sa.func.max(S.experiments.c.id)).where(
            (S.experiments.c.kind == "benchmark") & (S.experiments.c.id < exp_id))).scalar() or 0
        rows = c.execute(sa.select(S.experiments.c.cost).where(
            (S.experiments.c.source == "practice") & (S.experiments.c.id > prev) &
            (S.experiments.c.id < exp_id))).scalars().all()
    return sum((S.loads(r, {}) or {}).get("compute_usd_estimated", 0.0) for r in rows)


def _control_drift(exp_id, split, cells):
    with S.engine().connect() as c:
        prev = c.execute(sa.select(sa.func.max(S.bench_results.c.experiment_id)).where(
            (S.bench_results.c.experiment_id < exp_id) & (S.bench_results.c.split == split) &
            (S.bench_results.c.code_version == S.code_version()))).scalar()
        if not prev:
            return {"checked": False, "note": "no earlier benchmark with the same code version"}
        rows = c.execute(sa.select(S.bench_results.c.problem, S.bench_results.c.replicate,
                                   S.bench_results.c.contestant, S.bench_results.c.score).where(
            (S.bench_results.c.experiment_id == prev) &
            S.bench_results.c.contestant.in_(["random", "hillclimb", "darwin"]))).all()
    diffs = []
    for pid, rep, name, score in rows:
        r = cells.get((pid, rep), {}).get(name)
        if r is not None and abs(r["score"] - score) > 1e-9:
            diffs.append({"problem": pid, "replicate": rep, "contestant": name, "before": score, "now": r["score"]})
    if diffs:
        S.append("failure.nondeterminism", {"compared_with": S.fmt_exp(prev), "differences": diffs[:20]},
                 experiment_id=exp_id)
    return {"checked": True, "compared_with": S.fmt_exp(prev), "identical": not diffs, "differences": len(diffs)}


def _streak(key, today_replicated):
    """Consecutive holdout benchmark days (ending today) on which the comparison was replicated."""
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.summary).where(
            (S.experiments.c.kind == "benchmark") & (S.experiments.c.status == "completed")).order_by(
            S.experiments.c.id.desc()).limit(30)).scalars().all()
    streak = 1 if today_replicated else 0
    if not today_replicated:
        return 0
    for r in rows:
        b = (S.loads(r, {}) or {}).get("benchmark") or {}
        if b.get("split") != "holdout" or b.get("suite") != suite.SUITE_VERSION:
            continue
        st = ((b.get("claims") or {}).get(key) or {}).get("replicated_today")
        if st:
            streak += 1
        else:
            break
    return streak


def update_standing_claims(exp_id, day, comps, mem_size):
    out = {}
    existing = {c["kind"]: c for c in S.all_claims() if (c["kind"] or "").startswith("standing:")}
    for key, (a, b, text) in STANDING.items():
        kind = f"standing:{key}:{suite.SUITE_VERSION}"
        cmp = comps.get(f"{a}__vs__{b}")
        statement = text.format(suite=suite.SUITE_VERSION)
        cl = existing.get(kind)
        if cl is None:
            cid = S.add_claim(exp_id, kind, statement, {"comparison": f"{a} vs {b}", "suite": suite.SUITE_VERSION},
                              "candidate", "standing claim opened with the first holdout benchmark")
            prev = "candidate"
        else:
            cid, prev = cl["id"], cl["status"]
        replicated = bool(cmp and cmp["mean_diff"] > 0 and cmp["p_sign_test"] <= 0.05)
        if key == "memory" and mem_size == 0:
            new, reason = "candidate", "Discovery Memory is empty, so the memory and no-memory runs are identical"
            replicated = False
        elif cmp is None:
            new, reason = prev, "no comparison data"
        elif replicated:
            streak = _streak(key, True)
            new = "robust" if streak >= 3 else "replicated"
            reason = (f"{day}: {cmp['wins']}/{cmp['n']} paired wins, mean +{cmp['mean_diff']} normalised, "
                      f"p={cmp['p_sign_test']}" + (f"; replicated {streak} benchmark days running" if streak >= 3 else ""))
        elif cmp["mean_diff"] > 0:
            new, reason = "observed", f"{day}: ahead by {cmp['mean_diff']} on average but p={cmp['p_sign_test']}"
        else:
            new = ("failed replication" if prev in ("replicated", "robust")
                   else "contradicted" if prev == "observed" else "candidate")
            reason = f"{day}: not ahead ({cmp['wins']} wins, {cmp['losses']} losses, mean {cmp['mean_diff']})"
        if new != prev:
            S.set_claim_status(cid, new, reason, evidence=cmp, experiment_id=exp_id)
        out[key] = {"claim": S.fmt_claim(cid), "status": new, "reason": reason, "replicated_today": replicated}
    return out


def _llm_reference(exp_id, prob, day, split, r0, r1):
    """llm_direct contestant. Designed once per (problem, model, prompt version); re-scored daily."""
    from . import openlab
    spec = life.LINEAR
    with S.engine().connect() as c:
        prev = c.execute(sa.select(S.bench_results.c.genome, S.bench_results.c.detail).where(
            (S.bench_results.c.contestant == "llm_direct") & (S.bench_results.c.problem == prob["id"]) &
            (S.bench_results.c.suite == suite.SUITE_VERSION)).order_by(S.bench_results.c.id.desc()).limit(1)).first()
    new_cost, call = 0.0, None
    genome = None
    if prev:
        d = S.loads(prev[1], {}) or {}
        if d.get("model") == openlab.MODEL and d.get("prompt_version") == openlab.DESIGN_PROMPT_VERSION:
            genome = S.loads(prev[0], None)
            call = {"reused_from_call": d.get("call_id")}
    if genome is None:
        res = openlab.design_genome(prob["objective"], prob["conditions"], experiment_id=exp_id)
        if not res or res.get("error"):
            S.append("benchmark.llm_skipped", {"problem": prob["id"], "reason": (res or {}).get("error", "no result")},
                     experiment_id=exp_id)
            return None
        genome, call, new_cost = res["genome"], res["call"], res["call"]["cost_usd"]
    t0 = time.process_time()
    sc = _score(genome, prob, spec)
    cpu = time.process_time() - t0
    nm = _norm(float(sc.mean()), r0, r1)
    with S.engine().begin() as c:
        c.execute(S.bench_results.insert().values(
            experiment_id=exp_id, day=day, split=split, suite=suite.SUITE_VERSION, problem=prob["id"],
            contestant="llm_direct", replicate=0, evaluations=1, cpu_s=round(cpu, 4),
            cost_usd=costs.compute_usd(cpu) + new_cost, cost_kind="billed+estimated" if new_cost else "estimated",
            score=float(sc.mean()), score_seeds=S.canon([round(float(x), 6) for x in sc]), normalized=nm,
            genome=S.canon([round(float(x), 6) for x in genome]),
            detail=S.canon({"model": openlab.MODEL, "prompt_version": openlab.DESIGN_PROMPT_VERSION,
                            "world": spec.version, "call_id": (call or {}).get("id") or (call or {}).get("reused_from_call"),
                            "note": "scored in the same conditions and seeds, but with the life-1.0 controller"}),
            code_version=S.code_version()))
    return {"normalized": nm, "new_cost": new_cost}


def history(split="holdout", limit=120):
    """Daily benchmark summaries, oldest first, for Intelligence History (s.56)."""
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.id, S.experiments.c.created_at, S.experiments.c.summary,
                                   S.experiments.c.code_version).where(
            (S.experiments.c.kind == "benchmark") & (S.experiments.c.status == "completed")).order_by(
            S.experiments.c.id.desc()).limit(limit)).all()
    out = []
    for i, ts, summ, cv in reversed(rows):
        b = (S.loads(summ, {}) or {}).get("benchmark")
        if b and b.get("split") == split:
            out.append({"id": i, "label": S.fmt_exp(i), "created_at": ts, "code_version": cv, **b})
    return out


def versions(split="holdout"):
    """Version comparison (s.57): per code version, mean normalised score per contestant."""
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.bench_results.c.code_version, S.bench_results.c.contestant,
                                   sa.func.avg(S.bench_results.c.normalized), sa.func.count(),
                                   sa.func.min(S.bench_results.c.day), sa.func.max(S.bench_results.c.day)).where(
            (S.bench_results.c.split == split) & (S.bench_results.c.suite == suite.SUITE_VERSION)).group_by(
            S.bench_results.c.code_version, S.bench_results.c.contestant)).all()
    out = {}
    for cv, name, avg, n, d0, d1 in rows:
        v = out.setdefault(cv, {"code_version": cv, "first_day": d0, "last_day": d1, "contestants": {}})
        v["first_day"], v["last_day"] = min(v["first_day"], d0), max(v["last_day"], d1)
        v["contestants"][name] = {"mean": round(float(avg), 4), "n": int(n)}
    return sorted(out.values(), key=lambda v: v["first_day"])


def final_uses():
    with S.engine().connect() as c:
        return int(c.execute(sa.select(sa.func.count()).select_from(S.events).where(
            S.events.c.type == "benchmark.final_used")).scalar() or 0)
