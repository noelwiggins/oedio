"""Autonomous work, driven once a minute by the world thread.

Series 2 (Phase 2b): every CYCLE_HOURS hours (slots start at 00, 04, 08, ... UTC):
  1. PRACTICE_PER_CYCLE practice runs chosen by the curriculum (memory on).
     Validated winners grow Discovery Memory.
  2. One series-2 benchmark, queued after the practice runs, so it measures
     this cycle's memory on fresh, never-seen problems.
  3. Hourly memory consolidation (retire memories that keep failing to transfer).
A failed cycle benchmark (for example, interrupted by a redeploy) is retried
up to MAX_TRIES times in the same slot. A hard daily spending guard skips
cycles if the last 24 hours of recorded spend exceed DARWIN_DAILY_HARD_USD.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from . import bench, core, curriculum, store, suite

S = store
CYCLE_HOURS = 4
MAX_TRIES = 2
PRACTICE = {"population": 40, "generations": 30, "islands": 2, "train_seeds": 2, "holdout_seeds": 8,
            "ticks": suite.TICKS, "cohort": suite.COHORT, "stagnation": 15}
# kept for series-1 tooling and tests
DAILY_HOUR_UTC = 6
PRACTICE_PER_DAY = curriculum.PRACTICE_PER_CYCLE


def hard_budget_usd() -> float:
    try:
        return float(os.environ.get("DARWIN_DAILY_HARD_USD", "2.0"))
    except ValueError:
        return 2.0


def spend_last_24h() -> float:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with S.engine().connect() as c:
        weblab = sa.select(S.experiments.c.id).where(S.experiments.c.kind == "weblab")
        # Web Lab has its own cap (DARWIN_WEBLAB_DAILY_USD); it must not starve the Life Lab cycles
        return float(c.execute(sa.select(sa.func.coalesce(sa.func.sum(S.events.c.cost_usd), 0.0)).where(
            (S.events.c.ts >= since) & ~S.events.c.type.like("weblab.%") &
            (S.events.c.experiment_id.is_(None) | S.events.c.experiment_id.not_in(weblab)))).scalar() or 0.0)


def queue_practice(problem, seed, day, conn, kind="fixed", label=""):
    cfg = core.Config.from_dict({**PRACTICE, "world": suite.WORLD, "objective": problem["objective"],
                                 "conditions": problem["conditions"], "memory": True,
                                 "memory_failure_weighting": True, "seed": seed})
    name = problem.get("id") or kind
    eid = conn.execute(S.experiments.insert().values(
        created_at=S.now(), kind="evolve", lab="life", title=f"Practice · {name} · {day}",
        goal=f"Practice ({kind}{': ' + label if label else ''}) to build Discovery Memory",
        objective=cfg.objective, config=S.canon(cfg.to_dict()), seed=cfg.seed, status="queued", owner=True,
        requester="darwin", budget_usd=None, max_cpu_s=400.0, stop_requested=False, source="practice",
        progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
    S.append("experiment.created", {"title": f"Practice {name}", "curriculum": kind, "config": cfg.to_dict(),
                                    "source": "practice"}, experiment_id=eid, conn=conn,
             provenance={"requester": "darwin scheduler"})
    return eid


def queue_benchmark(split, day, conn, requester="darwin scheduler", source="benchmark", series=1):
    if series == 2:
        cfg = {"series": 2, "suite": suite.SUITE2, "world": suite.WORLD}
        title = f"Cycle benchmark · {S.now()[:13].replace('T', ' ')}h UTC"
    else:
        cfg = {"split": split, **bench.DEFAULTS, "suite": suite.SUITE_VERSION, "world": suite.WORLD}
        title = f"{'Daily benchmark' if split == 'holdout' else split.capitalize() + ' benchmark'} · {day}"
    eid = conn.execute(S.experiments.insert().values(
        created_at=S.now(), kind="benchmark", lab="life", title=title,
        goal="Equal-budget comparison of Darwin (with and without memory) against baselines",
        objective=None, config=S.canon(cfg), seed=0, status="queued", owner=True,
        requester=requester, budget_usd=None, max_cpu_s=5400.0, stop_requested=False, source=source,
        progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
    S.append("experiment.created", {"title": title, "config": cfg, "source": source},
             experiment_id=eid, conn=conn, provenance={"requester": requester})
    return eid


def slot_start(now):
    h = (now.hour // CYCLE_HOURS) * CYCLE_HOURS
    return now.replace(hour=h, minute=0, second=0, microsecond=0)


def tick(now=None):
    if os.environ.get("DARWIN_SCHEDULER", "on") == "off":
        return
    from .web import ensure_worker
    now = now or datetime.now(timezone.utc)
    _cycle(now)
    _consolidate_hourly(now)
    try:
        from .weblab import evolve
        evolve.maybe_schedule(now)
    except Exception as e:
        print(f"[darwin] weblab scheduling error: {e!r}")
    ensure_worker()


_last_consolidate = {"t": None}


def _consolidate_hourly(now):
    """Memory consolidation (retire memories that keep failing to transfer), once an hour."""
    from . import memory
    if _last_consolidate["t"] and (now - _last_consolidate["t"]).total_seconds() < 3600:
        return
    _last_consolidate["t"] = now
    try:
        memory.consolidate()
    except Exception as e:
        print(f"[darwin] consolidation error: {e!r}")


def _cycle(now):
    start = slot_start(now)
    key = int(start.timestamp() // (CYCLE_HOURS * 3600))
    since = start.isoformat()
    day = start.date().isoformat()
    with S.engine().begin() as c:
        rows = c.execute(sa.select(S.experiments.c.status, S.experiments.c.config).where(
            (S.experiments.c.created_at >= since) & (S.experiments.c.source == "benchmark"))).all()
        benches = [st for st, cfg in rows if (S.loads(cfg, {}) or {}).get("series") == 2]
        if any(st in ("queued", "running", "completed") for st in benches) or len(benches) >= MAX_TRIES:
            return
        spent = spend_last_24h()
        if spent > hard_budget_usd():
            already = c.execute(sa.select(sa.func.count()).select_from(S.events).where(
                (S.events.c.type == "schedule.skipped_budget") & (S.events.c.ts >= since))).scalar()
            if not already:
                S.append("schedule.skipped_budget", {"spent_24h": round(spent, 4), "hard_limit": hard_budget_usd()},
                         conn=c)
            return
        practiced = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
            (S.experiments.c.created_at >= since) & (S.experiments.c.source == "practice"))).scalar()
        made = []
        if not practiced:
            for k, (kind, label, obj, cond) in enumerate(curriculum.plan(key)):
                prob = {"objective": obj, "conditions": cond,
                        "id": label if kind == "fixed" else None}
                made.append(queue_practice(prob, key * 10 + k, day, c, kind=kind, label=label))
        bid = queue_benchmark("cycle", day, c, series=2)
        S.append("schedule.cycle", {"slot": since, "cycle_key": key, "practice": [S.fmt_exp(i) for i in made],
                                    "benchmark": S.fmt_exp(bid), "retry": bool(benches)}, conn=c)
