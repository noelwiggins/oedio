"""Practice curriculum (Phase 2b): what Darwin practises on each cycle.

Practice problems come from the same distribution as the fresh test problems,
so experience can transfer to them, but no practice problem is ever a test
problem: tests are drawn after memory is frozen and are never reused.

Each cycle, PRACTICE_PER_CYCLE runs are chosen as:
  * 1 fixed training problem (T1-T6 rotation), for continuity with series 1
  * coverage problems: of COVERAGE_CANDIDATES random draws, the one farthest
    from everything in memory and from recent practice (fill the gaps)
  * 1 revisit: a recent practice problem whose winner failed validation, if any
    (Brief s.14: failures are not forbidden, they are retried as memory grows)
A problem within LEAK_DISTANCE of a protected (anchor/final) problem is never
chosen, so validated winners can always enter memory.
"""
from __future__ import annotations

import json

import numpy as np
import sqlalchemy as sa

from . import memory, store, suite

S = store
PRACTICE_PER_CYCLE = 5
COVERAGE_CANDIDATES = 40
MAX_REVISITS = 2


def _recent_practice(limit=60):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.id, S.experiments.c.config, S.experiments.c.summary,
                                   S.experiments.c.status, S.experiments.c.goal).where(
            S.experiments.c.source == "practice").order_by(S.experiments.c.id.desc()).limit(limit)).all()
    out = []
    for i, cfg, summ, st, goal in rows:
        c = S.loads(cfg, {}) or {}
        sm = S.loads(summ, {}) or {}
        out.append({"id": i, "objective": c.get("objective"), "conditions": c.get("conditions") or {},
                    "status": st, "admitted": ((sm.get("memory") or {}).get("admitted")),
                    "goal": goal or ""})
    return out


def _protected_ok(obj, cond):
    near = suite.protected_near(obj, cond)
    return not near or near[1] >= suite.LEAK_DISTANCE


def plan(cycle_key: int, n=PRACTICE_PER_CYCLE):
    """Deterministic practice plan for one cycle: list of (kind, label, objective, conditions)."""
    rng = np.random.default_rng([3, int(cycle_key)])
    out = []
    train = suite.problems("train")
    t = train[int(cycle_key) % len(train)]
    out.append(("fixed", t["id"], t["objective"], t["conditions"]))

    recent = _recent_practice()
    # revisit: newest finished practice whose winner did not enter memory, revisited < MAX_REVISITS times
    revisit = None
    for r in recent:
        if r["status"] == "completed" and not r["admitted"] and r["objective"]:
            key = json.dumps([r["objective"], r["conditions"]], sort_keys=True)
            times = sum(1 for x in recent if json.dumps([x["objective"], x["conditions"]], sort_keys=True) == key)
            if times <= MAX_REVISITS and _protected_ok(r["objective"], r["conditions"]):
                revisit = ("revisit", f"retry of E-{r['id']:06d}", r["objective"], r["conditions"])
                break

    mem = [(e["objective"], e["conditions"] or {}) for e in memory.entries(suite.WORLD)]
    seen = mem + [(r["objective"], r["conditions"]) for r in recent[:20] if r["objective"]]
    n_cov = n - 1 - (1 if revisit else 0)
    for _ in range(n_cov):
        best, best_d = None, -1.0
        for _ in range(COVERAGE_CANDIDATES):
            obj, cond = suite.sample_problem(rng)
            if not _protected_ok(obj, cond):
                continue
            d = min((suite.distance(obj, cond, o, c) for o, c in seen), default=9.0)
            if d > best_d:
                best, best_d = (obj, cond), d
        if best:
            out.append(("coverage", "no prior experience" if best_d >= 9 else f"gap {best_d:.2f} from nearest experience", best[0], best[1]))
            seen.append(best)
    if revisit:
        out.append(revisit)
    return out
