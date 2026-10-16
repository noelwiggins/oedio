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

import numpy as np
import sqlalchemy as sa

from . import store, suite

S = store
VALIDATED = ("replicated", "robust")
MAX_DISTINCT = 6           # distinct memories retrieved per experiment
DUP_COND = 0.08            # admission dedupe: same objective, conditions this close ...
DUP_GENOME = 0.04          # ... and genome this close (normalised RMS) = duplicate
RETIRE_MIN_USES = 6        # consolidation: retire after this many transfers ...
RETIRE_MAX_RATE = 0.10     # ... if fewer than this share founded the winning lineage
LEARN_MIN_ROWS = 30        # learned retrieval needs this many recorded transfers


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


def status_map():
    """{memory_id: (status, reason)} from the append-only status log (latest wins; default active)."""
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.memory_status.c.memory_id, S.memory_status.c.status,
                                   S.memory_status.c.reason).order_by(S.memory_status.c.id)).all()
    return {m: (st, r) for m, st, r in rows}


def entries(world=None, upto_id=None, active_only=False):
    q = sa.select(S.memory).order_by(S.memory.c.id)
    if world:
        q = q.where(S.memory.c.world == world)
    if upto_id is not None:
        q = q.where(S.memory.c.id <= upto_id)
    with S.engine().connect() as c:
        rows = [_row(r) for r in c.execute(q).mappings()]
    st = status_map()
    for r in rows:
        r["status"], r["status_reason"] = st.get(r["id"], ("active", None))
    if active_only:
        rows = [r for r in rows if r["status"] == "active"]
    return rows


def size(world=None) -> int:
    q = sa.select(sa.func.count()).select_from(S.memory)
    if world:
        q = q.where(S.memory.c.world == world)
    with S.engine().connect() as c:
        return int(c.execute(q).scalar() or 0)


def head_id():
    with S.engine().connect() as c:
        return c.execute(sa.select(sa.func.max(S.memory.c.id))).scalar()


def retrieve(world, objective, conditions, k=MAX_DISTINCT, failure_weighting=True, upto_id=None, mode=None):
    """Most useful memories for a problem.
    mode "rule"    : similarity exp(-d/0.25), times the Laplace-smoothed transfer success
                     rate when failure weighting is on (the Phase 2 rule)
    mode "learned" : predicted probability that the memory founds the winning lineage, from a
                     logistic model fitted to the transfer log; falls back to the rule (and says
                     so) until LEARN_MIN_ROWS transfers have been recorded.
    Retired memories are never retrieved."""
    es = entries(world, upto_id, active_only=True)
    if not es:
        return []
    st = stats()
    model = learned_model() if mode == "learned" else None
    scored = []
    for e in es:
        d = suite.distance(objective, conditions, e["objective"], e["conditions"] or {})
        uses, helped = st.get(e["id"], (0, 0))
        if model is not None:
            w = model.predict(d, objective == e["objective"], uses, helped)
        else:
            w = math.exp(-d / 0.25)
            if failure_weighting:
                w *= (helped + 1) / (uses + 2)
        scored.append((w, -e["id"], e, d, uses, helped))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    how = "learned" if model is not None else ("rule (learned model not ready)" if mode == "learned" else "rule")
    return [{"memory_id": e["id"], "genome": e["genome"], "distance": round(d, 4), "weight": round(w, 6),
             "uses": uses, "helped": helped, "objective": e["objective"], "from_experiment": e["experiment_id"],
             "retrieval": how}
            for w, _, e, d, uses, helped in scored[:k]]


# ── learned retrieval ─────────────────────────────────────────────────────
class _Logit:
    """P(helped) = sigmoid(w . [1, distance, same_objective, log(1+uses), smoothed rate])."""

    def __init__(self, w, n, acc):
        self.w, self.n, self.acc = w, n, acc

    @staticmethod
    def feats(d, same, uses, helped):
        return np.array([1.0, d, 1.0 if same else 0.0, math.log1p(uses), (helped + 1) / (uses + 2)])

    def predict(self, d, same, uses, helped):
        z = float(self.feats(d, same, uses, helped) @ self.w)
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


_model_cache = {"n": -1, "model": None}


def learned_model():
    """Fit (or reuse) the retrieval model on the transfer log. Features use only the counts a
    memory had *before* each recorded use, so the model never learns from the future."""
    with S.engine().connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(S.memory_uses)).scalar() or 0
        if n < LEARN_MIN_ROWS:
            return None
        if _model_cache["n"] == n:
            return _model_cache["model"]
        rows = c.execute(sa.select(S.memory_uses.c.memory_id, S.memory_uses.c.objective, S.memory_uses.c.distance,
                                   S.memory_uses.c.helped).order_by(S.memory_uses.c.id)).all()
        objs = {i: o for i, o in c.execute(sa.select(S.memory.c.id, S.memory.c.objective))}
    seen = {}
    X, y = [], []
    for mid, obj, d, helped in rows:
        u, h = seen.get(mid, (0, 0))
        X.append(_Logit.feats(float(d or 0.0), obj == objs.get(mid), u, h))
        y.append(1.0 if helped else 0.0)
        seen[mid] = (u + 1, h + (1 if helped else 0))
    X, y = np.array(X), np.array(y)
    w = np.zeros(X.shape[1])
    lam = 1.0
    for _ in range(50):                      # Newton steps, L2-regularised (not on the intercept)
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) + lam * np.r_[0.0, w[1:]]
        Hm = (X * (p * (1 - p))[:, None]).T @ X + lam * np.diag([0.0] + [1.0] * (X.shape[1] - 1)) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(Hm, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    acc = float((((1.0 / (1.0 + np.exp(-(X @ w)))) > 0.5) == (y > 0.5)).mean())
    m = _Logit(w, n, acc)
    _model_cache.update(n=n, model=m)
    return m


def model_info():
    m = learned_model()
    if m is None:
        return {"ready": False, "needs": LEARN_MIN_ROWS}
    return {"ready": True, "rows": m.n, "train_accuracy": round(m.acc, 3),
            "weights": dict(zip(["intercept", "distance", "same_objective", "log_uses", "success_rate"],
                                [round(float(x), 4) for x in m.w]))}


# ── consolidation ─────────────────────────────────────────────────────────
def _gdist(a, b, world):
    from . import life
    sp = life.get_spec(world)
    za = (np.asarray(a) - sp.LOW) / sp.SPAN
    zb = (np.asarray(b) - sp.LOW) / sp.SPAN
    return float(np.sqrt(((za - zb) ** 2).mean()))


def is_duplicate(world, objective, conditions, genome):
    for e in entries(world, active_only=True):
        if e["objective"] != objective or len(e["genome"] or []) != len(genome):
            continue
        if suite.distance(objective, conditions, e["objective"], e["conditions"] or {}) < DUP_COND and \
                _gdist(genome, e["genome"], world) < DUP_GENOME:
            return e["id"]
    return None


def consolidate():
    """Retire memories that keep failing to transfer. Returns the list of retirements.
    Retirement is a status event, not a deletion; the entry stays visible with its history."""
    st = stats()
    retired = []
    with S.engine().begin() as c:
        for e in entries(active_only=True):
            uses, helped = st.get(e["id"], (0, 0))
            if uses >= RETIRE_MIN_USES and helped / uses < RETIRE_MAX_RATE:
                reason = f"founded the winning lineage in {helped} of {uses} transfers"
                c.execute(S.memory_status.insert().values(ts=S.now(), memory_id=e["id"], status="retired",
                                                          reason=reason))
                S.append("memory.retired", {"memory": S.fmt_mem(e["id"]), "reason": reason}, conn=c)
                retired.append({"memory": S.fmt_mem(e["id"]), "reason": reason})
    return retired


def admit(exp_id, claim_id, candidate, world, objective, conditions, genome, train_fitness, validation,
          source, status):
    """Add a validated winner to Discovery Memory, unless a guard refuses it.
    Returns (memory_id or None, reason)."""
    if status not in VALIDATED:
        return None, f"claim status '{status}' is not validated"
    dup = is_duplicate(world, objective, conditions, genome)
    if dup:
        S.append("memory.excluded", {"reason": "duplicate of an existing memory", "duplicate_of": S.fmt_mem(dup)},
                 experiment_id=exp_id)
        return None, f"duplicate of {S.fmt_mem(dup)}"
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
