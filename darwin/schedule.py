"""Daily autonomous work, driven once a minute by the world thread.

From DAILY_HOUR_UTC each day:
  1. PRACTICE_PER_DAY practice experiments on training problems (rotating),
     with memory on. Validated winners grow Discovery Memory.
  2. One holdout benchmark, queued after the practice runs, so it measures
     today's memory.
A failed benchmark (for example, interrupted by a redeploy) is retried up to
MAX_TRIES times the same day. Everything is queued as ordinary experiments,
so it shows up in History and the Ledger like any other run.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa

from . import bench, core, store, suite

S = store
DAILY_HOUR_UTC = 6
PRACTICE_PER_DAY = 3
MAX_TRIES = 2
PRACTICE = {"population": 40, "generations": 30, "islands": 2, "train_seeds": 2, "holdout_seeds": 8,
            "ticks": suite.TICKS, "cohort": suite.COHORT, "stagnation": 15}


def queue_practice(problem, seed, day, conn):
    cfg = core.Config.from_dict({**PRACTICE, "world": suite.WORLD, "objective": problem["objective"],
                                 "conditions": problem["conditions"], "memory": True,
                                 "memory_failure_weighting": True, "seed": seed})
    eid = conn.execute(S.experiments.insert().values(
        created_at=S.now(), kind="evolve", lab="life", title=f"Practice · {problem['id']} · {day}",
        goal=f"Daily practice on training problem {problem['id']} ({problem['note']}) to build Discovery Memory",
        objective=cfg.objective, config=S.canon(cfg.to_dict()), seed=cfg.seed, status="queued", owner=True,
        requester="darwin", budget_usd=None, max_cpu_s=400.0, stop_requested=False, source="practice",
        progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
    S.append("experiment.created", {"title": f"Practice {problem['id']}", "config": cfg.to_dict(),
                                    "source": "practice"}, experiment_id=eid, conn=conn,
             provenance={"requester": "darwin scheduler"})
    return eid


def queue_benchmark(split, day, conn, requester="darwin scheduler", source="benchmark"):
    cfg = {"split": split, **bench.DEFAULTS, "suite": suite.SUITE_VERSION, "world": suite.WORLD}
    eid = conn.execute(S.experiments.insert().values(
        created_at=S.now(), kind="benchmark", lab="life",
        title=f"{'Daily benchmark' if split == 'holdout' else split.capitalize() + ' benchmark'} · {day}",
        goal="Equal-budget comparison of Darwin (with and without memory) against baselines on "
             f"{split} problems", objective=None, config=S.canon(cfg), seed=0, status="queued", owner=True,
        requester=requester, budget_usd=None, max_cpu_s=3600.0, stop_requested=False, source=source,
        progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
    S.append("experiment.created", {"title": f"{split} benchmark", "config": cfg, "source": source},
             experiment_id=eid, conn=conn, provenance={"requester": requester})
    return eid


def tick(now=None):
    import os
    if os.environ.get("DARWIN_SCHEDULER", "on") == "off":
        return
    from .web import ensure_worker
    now = now or datetime.now(timezone.utc)
    if now.hour >= DAILY_HOUR_UTC:
        _daily(now)
    ensure_worker()


def _daily(now):
    day = now.date().isoformat()
    with S.engine().begin() as c:
        rows = c.execute(sa.select(S.experiments.c.source, S.experiments.c.status, S.experiments.c.config).where(
            (S.experiments.c.created_at >= day) & S.experiments.c.source.in_(["practice", "benchmark"]))).all()
        benches = [st for src, st, cfg in rows if src == "benchmark" and (S.loads(cfg, {}) or {}).get("split") == "holdout"]
        if any(st in ("queued", "running", "completed") for st in benches) or len(benches) >= MAX_TRIES:
            return
        practiced = sum(1 for src, st, _ in rows if src == "practice")
        train = suite.problems("train")
        k0 = now.date().toordinal() * PRACTICE_PER_DAY
        made = []
        if not practiced:
            for k in range(PRACTICE_PER_DAY):
                p = train[(k0 + k) % len(train)]
                made.append(queue_practice(p, now.date().toordinal() * 10 + k, day, c))
        bid = queue_benchmark("holdout", day, c)
        S.append("schedule.daily", {"day": day, "practice": [S.fmt_exp(i) for i in made],
                                    "benchmark": S.fmt_exp(bid), "retry": bool(benches)}, conn=c)
