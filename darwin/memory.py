"""Discovery Memory and Failure Memory (Brief s.13-14).

Discovery Memory holds genomes whose claims passed held-out validation
("replicated" or "robust"), with the conditions they won under. New
experiments can seed part of their starting population from the most
similar entries. Whether that helps is exactly what the daily benchmark
measures; transfer is a hypothesis, never assumed.

Failure Memory records what did not work: runs that never improved, winners
that failed replication or adversarial tests, and memory seeds that were tried
on a new problem and did not found the winning lineage ("failed transfer").
It does not forbid anything. With failure weighting on, an entry's retrieval
weight is multiplied by (helped + 1) / (uses + 2), so memories that keep failing
to transfer are tried less often, but never ruled out.

Leakage guards (s.62): an entry is refused if its conditions are within
LEAK_DISTANCE of any holdout or final problem, and benchmark runs read memory
but never write entries or use statistics.
"""
from __future__ import annotations

import json
import math

import sqlalchemy as sa

from . import store, suite

S = store
VALIDATED = ("replicated", "robust")
MAX_DISTINCT = 6           # distinct memories retrieved per experiment


def _row(r):
    d = dict(r)
    for k in ("conditions", "genome", "validation", "detail"):
        if k in d:
            d[k] = S.loads(d[k], None)
    return d


def stats(conn=None):
    """{memory_id: (uses, helped)} from the use log."""
    def _do(c):
        q = sa.select(S.memory_uses.c.memory_id, sa.func.count(),
                      sa.func.sum(sa.case((S.memory_uses.c.helped == True, 1), else_=0))  # noqa: E712
                      ).group_by(S.memory_uses.c.memory_id)
        return {m: (int(n), int(h or 0)) for m, n, h in c.execute(q)}
    if conn is not None:
        return _do(conn)
    with S.engine().connect() as c:
        return _do(c)


def entries(world=None, upto_id=None):
    q = sa.select(S.memory).order_by(S.memory.c.id)
    if world:
        q = q.where(S.memory.c.world == world)
    if upto_id is not None:
        q = q.where(S.memory.c.id <= upto_id)
    with S.engine().connect() as c:
        return [_row(r) for r in c.execute(q).mappings()]


def size(world=None) -> int:
    q = sa.select(sa.func.count()).select_from(S.memory)
    if world:
        q = q.where(S.memory.c.world == world)
    with S.engine().connect() as c:
        return int(c.execute(q).scalar() or 0)


def head_id():
    with S.engine().connect() as c:
        return c.execute(sa.select(sa.func.max(S.memory.c.id))).scalar()


def retrieve(world, objective, conditions, k=MAX_DISTINCT, failure_weighting=True, upto_id=None):
    """Most useful memories for a problem: similarity exp(-d/0.25), times the
    Laplace-smoothed transfer success rate when failure weighting is on."""
    es = entries(world, upto_id)
    if not es:
        return []
    st = stats()
    scored = []
    for e in es:
        d = suite.distance(objective, conditions, e["objective"], e["conditions"] or {})
        uses, helped = st.get(e["id"], (0, 0))
        w = math.exp(-d / 0.25)
        if failure_weighting:
            w *= (helped + 1) / (uses + 2)
        scored.append((w, -e["id"], e, d, uses, helped))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [{"memory_id": e["id"], "genome": e["genome"], "distance": round(d, 4), "weight": round(w, 6),
             "uses": uses, "helped": helped, "objective": e["objective"], "from_experiment": e["experiment_id"]}
            for w, _, e, d, uses, helped in scored[:k]]


def admit(exp_id, claim_id, candidate, world, objective, conditions, genome, train_fitness, validation,
          source, status):
    """Add a validated winner to Discovery Memory, unless a guard refuses it.
    Returns (memory_id or None, reason)."""
    if status not in VALIDATED:
        return None, f"claim status '{status}' is not validated"
    near = suite.protected_near(objective, conditions)
    if near and near[1] < suite.LEAK_DISTANCE:
        S.append("memory.excluded", {"reason": "too close to a protected benchmark problem",
                                     "nearest": near[0], "distance": round(near[1], 4),
                                     "threshold": suite.LEAK_DISTANCE}, experiment_id=exp_id)
        return None, f"too close to protected problem {near[0]} (distance {near[1]:.3f})"
    with S.engine().begin() as c:
        mid = c.execute(S.memory.insert().values(
            created_at=S.now(), experiment_id=exp_id, claim_id=claim_id, candidate=candidate, world=world,
            objective=objective, conditions=S.canon(conditions), genome=S.canon([round(float(x), 6) for x in genome]),
            train_fitness=float(train_fitness), validation=S.canon(validation), source=source)).inserted_primary_key[0]
        S.append("memory.admitted", {"memory": S.fmt_mem(mid), "claim": S.fmt_claim(claim_id) if claim_id else None,
                                     "status": status, "objective": objective, "world": world,
                                     "nearest_protected": near[0] if near else None,
                                     "distance_to_protected": round(near[1], 4) if near else None},
                 experiment_id=exp_id, conn=c)
    return mid, "admitted"


def record_uses(exp_id, objective, conditions, seeds, winner_memory_id, winner_fitness):
    """After an experiment that used memory seeds: one use row per distinct memory,
    helped = that memory's seed founded the winning lineage. Not called for benchmarks."""
    seen = {}
    for e in seeds:
        seen.setdefault(e["memory_id"], e)
    if not seen:
        return
    with S.engine().begin() as c:
        for mid, e in seen.items():
            helped = winner_memory_id == mid
            c.execute(S.memory_uses.insert().values(
                ts=S.now(), memory_id=mid, experiment_id=exp_id, objective=objective, conditions=S.canon(conditions),
                distance=e.get("distance"), helped=helped,
                detail=S.canon({"winner_fitness": winner_fitness, "weight": e.get("weight")})))
            if not helped:
                c.execute(S.failures.insert().values(
                    ts=S.now(), experiment_id=exp_id, kind="failed_transfer", world=None, objective=objective,
                    conditions=S.canon(conditions), genome=None,
                    detail=S.canon({"memory": S.fmt_mem(mid), "distance": e.get("distance"),
                                    "note": "seeded from memory but did not found the winning lineage"})))
        S.append("memory.uses", {"memories": [S.fmt_mem(m) for m in seen],
                                 "winner_from": S.fmt_mem(winner_memory_id) if winner_memory_id else None},
                 experiment_id=exp_id, conn=c)


def record_failure(exp_id, kind, world, objective, conditions, genome=None, detail=None):
    with S.engine().begin() as c:
        c.execute(S.failures.insert().values(
            ts=S.now(), experiment_id=exp_id, kind=kind, world=world, objective=objective,
            conditions=S.canon(conditions), genome=S.canon([round(float(x), 6) for x in genome]) if genome is not None else None,
            detail=S.canon(detail or {})))


def failures_list(limit=200):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.failures).order_by(S.failures.c.id.desc()).limit(limit)).mappings().all()
    return [_row(r) for r in rows]


def failure_counts():
    with S.engine().connect() as c:
        return {k: n for k, n in c.execute(sa.select(S.failures.c.kind, sa.func.count()).group_by(S.failures.c.kind))}
