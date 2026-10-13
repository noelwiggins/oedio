"""Experiment worker. Runs as a subprocess of the web app:

    python -m darwin.runner work

It claims queued experiments one at a time, runs them, writes generations,
lineage, cost and Ledger events, validates the result, files claims, and exits
when the queue is empty. A hard CPU rlimit backs up the budget checks so an
experiment can never silently exceed its authorised compute (s.42).
"""
from __future__ import annotations

import json
import os
import platform
import resource
import signal
import sys
import time
import traceback

import numpy as np
import sqlalchemy as sa

from . import core, life, store
from .costs import Meter, compute_usd

S = store


def _env_record():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "world": life.WORLD_VERSION, "platform": platform.platform(terse=True),
            "code_version": S.code_version()}


def claim_next():
    """Atomically move the oldest queued experiment to running."""
    eng = S.engine()
    with eng.begin() as c:
        row = c.execute(sa.select(S.experiments.c.id).where(S.experiments.c.status == "queued")
                        .order_by(S.experiments.c.id).limit(1)).scalar()
        if row is None:
            return None
        n = c.execute(S.experiments.update().where(
            (S.experiments.c.id == row) & (S.experiments.c.status == "queued")).values(
            status="running", started_at=S.now(), heartbeat=S.now(),
            code_version=S.code_version(), environment=S.canon(_env_record()))).rowcount
        return row if n == 1 else None


def _get(exp_id):
    with S.engine().connect() as c:
        return dict(c.execute(sa.select(S.experiments).where(S.experiments.c.id == exp_id)).mappings().one())


def _update(exp_id, **vals):
    with S.engine().begin() as c:
        c.execute(S.experiments.update().where(S.experiments.c.id == exp_id).values(**vals))


def run_experiment(exp_id: int):
    exp = _get(exp_id)
    if exp["kind"] == "replay":
        return run_replay(exp)
    cfg = core.Config.from_dict(json.loads(exp["config"]))
    meter = Meter()
    max_cpu = exp["max_cpu_s"]
    if max_cpu:
        # Hard backstop: the kernel stops the process at 1.25x the cap.
        soft = int(time.process_time() + max_cpu * 1.25) + 1
        resource.setrlimit(resource.RLIMIT_CPU, (soft, soft + 5))

    S.append("experiment.started", {"config": cfg.to_dict(), "seed": cfg.seed,
                                    "environment": _env_record(),
                                    "train_seeds": cfg.train_seed_list(),
                                    "holdout_seeds": cfg.holdout_seed_list()}, experiment_id=exp_id)

    def on_generation(gen, stats, pop, snap):
        with S.engine().begin() as c:
            c.execute(S.generations.insert().values(experiment_id=exp_id, gen=gen, stats=S.canon(stats),
                                                    cpu_s=stats["cpu_s"], sim_steps=stats["sim_steps"]))
            c.execute(S.candidates.insert(), [
                {"experiment_id": exp_id, **{k: (S.canon(v) if k in ("parents", "params", "genome", "fitness_seeds") else v)
                                             for k, v in cand.record().items()}} for cand in pop])
            c.execute(S.experiments.update().where(S.experiments.c.id == exp_id).values(
                heartbeat=S.now(), cost=S.canon(snap),
                progress=S.canon({"gen": gen, "of": cfg.generations, "best": stats["best"],
                                  "phase": "evolving"})))
            S.append("generation.completed", {
                "gen": gen, "best": stats["best"], "best_cid": stats["best_cid"], "mean": stats["mean"],
                "diversity": stats["diversity"], "lineages": stats["lineages"],
                "warnings": stats["warnings"]}, experiment_id=exp_id,
                cost_usd=compute_usd(stats["cpu_s"]), cost_kind="estimated", conn=c)
            if stats["collapsed_cohorts"]:
                S.append("failure.collapsed_cohorts", {
                    "gen": gen, "count": stats["collapsed_cohorts"],
                    "note": "candidates whose whole cohort scored zero (starved or never fed)"},
                    experiment_id=exp_id, conn=c)

    def should_stop():
        with S.engine().connect() as c:
            return bool(c.execute(sa.select(S.experiments.c.stop_requested).where(
                S.experiments.c.id == exp_id)).scalar())

    ev = core.Evolution(cfg, meter=meter, on_generation=on_generation, should_stop=should_stop,
                        budget_usd=exp["budget_usd"], max_cpu_s=max_cpu)
    ev.run()
    S.append("experiment.evolution_stopped", {"reason": ev.stop_reason, "generations_run": len(ev.history)},
             experiment_id=exp_id)

    summary = {"stop_reason": ev.stop_reason, "generations_run": len(ev.history),
               "gen0_best": {"cid": ev.gen0_best.cid, "fitness": ev.gen0_best.fitness,
                             "genome": life.genome_dict(ev.gen0_best.genome)},
               "final_best": {"cid": ev.best.cid, "fitness": ev.best.fitness,
                              "genome": life.genome_dict(ev.best.genome)},
               "operator_stats": ev.op_stats, "digest": ev.digest(), "validation": {}}
    _update(exp_id, progress=S.canon({"gen": len(ev.history) - 1, "of": cfg.generations,
                                      "best": ev.best.fitness, "phase": "validating"}),
            heartbeat=S.now(), summary=S.canon(summary))

    final_cond = core.conditions_at(cfg, len(ev.history) - 1)
    hold = cfg.holdout_seed_list()
    validation = summary["validation"]

    # Claim: evolution improved on the starting point. Status moves only on evidence.
    improved_train = ev.best.fitness > ev.gen0_best.fitness
    statement = (f"In Life Lab ({cfg.objective}), evolved genome {S.fmt_exp(exp_id)}/{ev.best.cid} scores higher "
                 f"than the best initial genome {ev.gen0_best.cid}.")
    # A claim is filed only when there is an observation to claim. A run that did not
    # improve is recorded as a failure, not left as an orphaned candidate.
    claim_id = None
    if improved_train:
        claim_id = S.add_claim(exp_id, "optimization", statement,
                               {"objective": cfg.objective, "a": ev.best.cid, "b": ev.gen0_best.cid,
                                "train": {"a": ev.best.fitness, "b": ev.gen0_best.fitness}},
                               "candidate", "proposed automatically at end of evolution")
        S.set_claim_status(claim_id, "observed",
                           f"training seeds: {ev.best.fitness:.3f} vs {ev.gen0_best.fitness:.3f}",
                           experiment_id=exp_id)
    else:
        S.append("failure.no_improvement", {
            "note": "final best did not beat the initial best on training seeds; no claim filed",
            "gen0_best": ev.gen0_best.fitness, "final_best": ev.best.fitness}, experiment_id=exp_id)

    stopped_by_cap = False
    try:
        if improved_train and not ev.stop_reason.startswith("cancelled"):
            h = core.head_to_head(ev.best.genome, ev.gen0_best.genome, cfg.objective, final_cond, hold,
                                  cfg.ticks, cfg.cohort, meter)
            validation["holdout"] = h
            S.append("validation.holdout", h, experiment_id=exp_id)
            need = max(1, int(np.ceil(0.875 * len(hold))))
            if h["wins"] >= need and h["p_sign_test"] <= 0.05:
                S.set_claim_status(claim_id, "replicated",
                                   f"held-out seeds: won {h['wins']}/{len(hold)}, p={h['p_sign_test']}",
                                   evidence=h, experiment_id=exp_id)
                pc = core.perturbed(final_cond)
                h2 = core.head_to_head(ev.best.genome, ev.gen0_best.genome, cfg.objective, pc, hold,
                                       cfg.ticks, cfg.cohort, meter)
                validation["adversarial"] = h2
                S.append("validation.adversarial", h2, experiment_id=exp_id)
                if h2["wins"] >= need and h2["p_sign_test"] <= 0.05:
                    S.set_claim_status(claim_id, "robust",
                                       f"perturbed conditions (scarcity x1.6, +2 hazards, diet flip): won "
                                       f"{h2['wins']}/{len(hold)}, p={h2['p_sign_test']}",
                                       evidence=h2, experiment_id=exp_id)
                else:
                    S.append("failure.adversarial", {"claim": S.fmt_claim(claim_id), "result": h2},
                             experiment_id=exp_id)
            else:
                S.set_claim_status(claim_id, "failed replication",
                                   f"held-out seeds: won {h['wins']}/{len(hold)}, p={h['p_sign_test']}",
                                   evidence=h, experiment_id=exp_id)

        if cfg.baseline_random and not ev.stop_reason.startswith("cancelled"):
            # Equal budget: as many random genomes as Darwin actually simulated.
            n_eval = max(cfg.population, len(getattr(ev, "_cache", {})))
            bg, bf = core.random_search(cfg, n_eval, meter)
            hb = core.head_to_head(ev.best.genome, bg, cfg.objective, final_cond, hold, cfg.ticks,
                                   cfg.cohort, meter)
            hb["random_candidates"] = n_eval
            hb["random_best_train"] = bf
            validation["baseline_random"] = hb
            S.append("validation.baseline_random", hb, experiment_id=exp_id)
            st = (f"In Life Lab ({cfg.objective}), {S.fmt_exp(exp_id)}/{ev.best.cid} beats the best of {n_eval} "
                  f"random genomes (equal evaluation count) on held-out seeds.")
            need = max(1, int(np.ceil(0.875 * len(hold))))
            ok = hb["wins"] >= need and hb["p_sign_test"] <= 0.05
            cid2 = S.add_claim(exp_id, "optimization", st, {"baseline": "random_search", "result": hb},
                               "candidate", "baseline comparison")
            S.set_claim_status(cid2, "replicated" if ok else "failed replication",
                               f"won {hb['wins']}/{len(hold)}, p={hb['p_sign_test']}", evidence=hb,
                               experiment_id=exp_id)
    except (Exception, SystemExit) as e:  # CPU soft limit (SIGXCPU) or error during validation
        stopped_by_cap = True
        validation["error"] = repr(e)
        S.append("failure.validation", {"error": repr(e)}, experiment_id=exp_id)

    snap = meter.snapshot()
    summary["validation"] = validation
    status = "stopped" if ev.stop_reason.startswith("cancelled") else "completed"
    _update(exp_id, status=status, finished_at=S.now(), stop_reason=ev.stop_reason + (
        "; validation interrupted" if stopped_by_cap else ""), summary=S.canon(summary), cost=S.canon(snap),
            result_digest=ev.digest(), progress=S.canon({"gen": len(ev.history) - 1, "of": cfg.generations,
                                                          "best": ev.best.fitness, "phase": "done"}))
    S.append("experiment.finished", {"status": status, "digest": ev.digest(), "cost": snap},
             experiment_id=exp_id, cost_usd=snap["compute_usd_estimated"], cost_kind="estimated")


def run_replay(exp):
    """REPLAY EXPERIMENT (s.54): re-run the original config and seed, compare digests."""
    orig = _get(exp["replay_of"])
    cfg = core.Config.from_dict(json.loads(orig["config"]))
    meter = Meter()
    ev = core.Evolution(cfg, meter=meter).run()
    same_code = (orig["code_version"] or "") == S.code_version()
    env_then = S.loads(orig["environment"], {})
    env_now = _env_record()
    match = ev.digest() == orig["result_digest"]
    explain = []
    if not match:
        if not same_code:
            explain.append(f"code changed ({orig['code_version']} -> {S.code_version()})")
        for k in ("numpy", "python", "world", "platform"):
            if env_then.get(k) != env_now.get(k):
                explain.append(f"{k} changed ({env_then.get(k)} -> {env_now.get(k)})")
        if (orig["stop_reason"] or "").startswith(("cancelled", "compute cap", "budget")):
            explain.append("original run stopped early on a resource/cancel condition, which the replay does not repeat")
        if not explain:
            explain.append("no recorded difference in code or environment; treat as unexplained nondeterminism")
    snap = meter.snapshot()
    result = {"original": S.fmt_exp(orig["id"]), "match": match, "original_digest": orig["result_digest"],
              "replay_digest": ev.digest(), "explanation": explain, "environment_then": env_then,
              "environment_now": env_now}
    _update(exp["id"], status="completed", finished_at=S.now(), result_digest=ev.digest(),
            summary=S.canon({"replay": result, "final_best": {"cid": ev.best.cid, "fitness": ev.best.fitness}}),
            cost=S.canon(snap), stop_reason=ev.stop_reason,
            progress=S.canon({"gen": len(ev.history) - 1, "of": cfg.generations, "phase": "done"}))
    S.append("replay.result", result, experiment_id=orig["id"], cost_usd=snap["compute_usd_estimated"],
             cost_kind="estimated", provenance={"replay_experiment": S.fmt_exp(exp["id"])})


def reap_stale(max_age_s=300):
    """Mark experiments whose worker vanished (e.g. a redeploy) as failed. Never deletes."""
    from datetime import datetime, timezone
    with S.engine().begin() as c:
        rows = c.execute(sa.select(S.experiments.c.id, S.experiments.c.heartbeat).where(
            S.experiments.c.status == "running")).all()
        for i, hb in rows:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb)).total_seconds()
            except Exception:
                age = 1e9
            if age > max_age_s:
                c.execute(S.experiments.update().where(S.experiments.c.id == i).values(
                    status="failed", finished_at=S.now(), stop_reason="worker lost (no heartbeat)"))
                S.append("failure.worker_lost", {"heartbeat_age_s": round(age)}, experiment_id=i, conn=c)


def work():
    """Run one queued experiment, then re-exec a fresh process for the next one,
    so every experiment starts with clean CPU accounting and its own rlimit."""
    reap_stale()
    exp_id = claim_next()
    if exp_id is None:
        return
    try:
        run_experiment(exp_id)
    except BaseException as e:
        tb = traceback.format_exc(limit=6)
        reason = "CPU limit reached" if isinstance(e, SystemExit) else repr(e)
        _update(exp_id, status="failed", finished_at=S.now(), stop_reason=reason)
        S.append("failure.experiment", {"error": reason, "trace": tb[-1500:]}, experiment_id=exp_id)
    with S.engine().connect() as c:
        more = c.execute(sa.select(S.experiments.c.id).where(S.experiments.c.status == "queued").limit(1)).scalar()
    if more is not None:
        os.execv(sys.executable, [sys.executable, "-m", "darwin.runner", "work"])


def _on_xcpu(signum, frame):
    raise SystemExit("CPU limit")


if __name__ == "__main__":
    signal.signal(signal.SIGXCPU, _on_xcpu)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "work"
    if cmd == "work":
        work()
    elif cmd == "run":
        run_experiment(int(sys.argv[2]))
