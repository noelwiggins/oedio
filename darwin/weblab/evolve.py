"""Web Lab evolution: Darwin breeds better audit strategies for Codestroller.

One *generation* = every contestant audits the same SHOPS_PER_GEN freshly
generated test shops (each contestant gets its own copy). Contestants are the
two fixed baselines (Codestroller's plain default and Noel's Nielsen-heuristic
prompt) plus the evolved population. Every HOLDOUT_EVERY-th generation is a
held-out test instead: the best evolved strategy and the baselines audit
held-out shops, which use defect types no training shop ever contains.

Selection uses the mean fitness over *all* of a strategy's training audits, so
a lucky single audit does not decide anything. The two best survive; the
rest of the population is replaced by a mutant of the best and a crossover of
the two best. Spending is capped per rolling 24 hours (DARWIN_WEBLAB_DAILY_USD,
default $5): a generation that would exceed it pauses and resumes later.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import sqlalchemy as sa

from .. import core, store
from . import client as cs
from . import judge as J
from . import shop, strategy

S = store
POP = 4
ELITES = 2
SHOPS_PER_GEN = 2
HOLDOUT_EVERY = 3
PUBLIC_URL = os.environ.get("DARWIN_PUBLIC_URL", "https://web-production-0df99e.up.railway.app").rstrip("/")
BENCH = f"{shop.SHOP_VERSION}+{J.JUDGE_VERSION}"   # audits from other bench versions are kept but never compared
BASELINES = [strategy.CODESTROLLER_DEFAULT, strategy.NOEL_HEURISTIC]
STANDING = {
    "vs_default": ("codestroller_default",
                   "On held-out test shops, Darwin's best evolved audit strategy scores higher than Codestroller's plain default."),
    "vs_nielsen": ("nielsen_prompt",
                   "On held-out test shops, Darwin's best evolved audit strategy scores higher than the Nielsen-heuristic prompt."),
}


def daily_cap():
    try:
        return float(os.environ.get("DARWIN_WEBLAB_DAILY_USD", "5.0"))
    except ValueError:
        return 5.0


def spent_24h():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.weblab_audits.c.cost).where(S.weblab_audits.c.created_at >= since)).scalars().all()
    return sum((S.loads(r, {}) or {}).get("total_usd", 0.0) for r in rows)


def _audits(where=None):
    q = sa.select(S.weblab_audits).order_by(S.weblab_audits.c.id)
    if where is not None:
        q = q.where(where)
    with S.engine().connect() as c:
        rows = [dict(r) for r in c.execute(q).mappings()]
    for r in rows:
        for k in ("strategy", "raw", "judged", "score", "cost"):
            r[k] = S.loads(r[k], None)
    return rows


def current(a):
    return (a.get("strategy") or {}).get("bench") == BENCH


def leaderboard():
    """Every strategy audited on training shops of the current bench version, ranked by mean fitness."""
    by = {}
    for a in filter(current, _audits(S.weblab_audits.c.status == "judged")):
        st, sc = a["strategy"] or {}, a["score"] or {}
        if a["split"] != "train" or sc.get("fitness") is None:
            continue
        e = by.setdefault(a["contestant"], {"label": a["contestant"], "kind": st.get("kind"), "strategy": st,
                                            "fitness": [], "recall_w": [], "precision": [], "coverage": [],
                                            "cost": [], "safety_failures": 0, "generations": set()})
        e["fitness"].append(sc["fitness"])
        e["recall_w"].append(sc["recall_weighted"])
        e["precision"].append(sc["precision"])
        e["coverage"].append(sc["coverage"])
        e["cost"].append((a["cost"] or {}).get("total_usd", 0.0))
        e["safety_failures"] += 0 if sc.get("safety") == "ok" else 1
        e["generations"].add(a["generation"])
    out = []
    for e in by.values():
        n = len(e["fitness"])
        out.append({**{k: e[k] for k in ("label", "kind", "strategy", "safety_failures")}, "audits": n,
                    "generations": sorted(e["generations"]),
                    "fitness": round(float(np.mean(e["fitness"])), 4),
                    "fitness_sd": round(float(np.std(e["fitness"], ddof=1)), 4) if n > 1 else None,
                    "recall_w": round(float(np.mean(e["recall_w"])), 4),
                    "precision": round(float(np.mean(e["precision"])), 4),
                    "coverage": round(float(np.mean(e["coverage"])), 4),
                    "usd_per_audit": round(float(np.mean(e["cost"])), 4),
                    "fitness_per_usd": round(float(np.mean(e["fitness"]) / max(np.mean(e["cost"]), 1e-6)), 2)})
    return sorted(out, key=lambda x: -x["fitness"])


def next_population(rng):
    board = [b for b in leaderboard() if b["kind"] == "evolved"]
    if not board:
        return [strategy.random_genome(rng) for _ in range(POP)], "initial random population"
    elites = [b["strategy"]["genome"] for b in board[:ELITES]]
    seen = {b["label"] for b in board}
    kids, notes = [], []
    tries = 0
    while len(elites) + len(kids) < POP and tries < 50:
        tries += 1
        if len(kids) == 0 or len(elites) < 2:
            g, how = strategy.mutate(elites[0], rng)
            how = f"mutation ({how}) of best"
        else:
            g = strategy.crossover(elites[0], elites[1], rng)
            g, m2 = strategy.mutate(g, rng)
            how = f"crossover of top two + mutation ({m2})"
        if strategy.gid(g) not in seen:
            seen.add(strategy.gid(g))
            kids.append(g)
            notes.append(how)
    while len(elites) + len(kids) < POP:
        kids.append(strategy.random_genome(rng))
        notes.append("random immigrant")
    return elites + kids, "; ".join([f"elites {', '.join(strategy.gid(e) for e in elites)}"] + notes)


def generation_number():
    with S.engine().connect() as c:
        return int(c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
            (S.experiments.c.kind == "weblab") & (S.experiments.c.status == "completed"))).scalar() or 0) + 1


def run(exp, set_progress, cl=None):
    cl = cl or cs.Client()
    if not cl.configured():
        raise cs.CodestrollerError("Codestroller credentials are not configured (DARWIN_CODESTROLLER_EMAIL/PASSWORD)")
    exp_id = exp["id"]
    cfg = S.loads(exp["config"], {}) or {}
    gen = cfg.get("generation") or generation_number()
    holdout = cfg.get("holdout", gen % HOLDOUT_EVERY == 0)
    rng = random.Random(exp_id * 7919)
    if cfg.get("contestants"):        # resuming: the field is fixed for the whole generation
        evolved, note = cfg["contestants"], cfg.get("selection", "")
    elif holdout:
        board = [b for b in leaderboard() if b["kind"] == "evolved"]
        evolved = [board[0]["strategy"]["genome"]] if board else []
        note = f"held-out test of the best evolved strategy {board[0]['label']}" if board else "no evolved strategy yet"
    else:
        evolved, note = next_population(rng)
    if not cfg.get("contestants"):
        with S.engine().begin() as conn:
            conn.execute(S.experiments.update().where(S.experiments.c.id == exp_id).values(
                config=S.canon({**cfg, "generation": gen, "holdout": holdout, "contestants": evolved, "selection": note})))
    contestants = [dict(b) for b in BASELINES] + [strategy.render(g) for g in evolved]
    split = "holdout" if holdout else "train"
    seeds = [(1_000_000 if holdout else 0) + exp_id * 10 + k for k in range(cfg.get("shops", SHOPS_PER_GEN))]
    S.append("weblab.generation_started", {"generation": gen, "split": split, "contestants": [c["label"] for c in contestants],
                                           "shop_seeds": seeds, "selection": note, "daily_cap_usd": daily_cap()},
             experiment_id=exp_id)
    plan = [(sd, c) for sd in seeds for c in contestants]
    mine = list(filter(current, _audits(S.weblab_audits.c.experiment_id == exp_id)))
    key = lambda a: (a["contestant"], (a["strategy"] or {}).get("shop_seed"))
    fails = {}
    for a in mine:
        if a["status"] == "failed":
            fails[key(a)] = fails.get(key(a), 0) + 1
    # done = judged, or failed twice (a worker lost mid-audit gets another go)
    done_keys = {key(a) for a in mine if a["status"] == "judged"} | {k for k, n in fails.items() if n >= 2}
    for n, (seed, c) in enumerate(plan):
        if (c["label"], seed) in done_keys:
            continue
        est = c["steps"] * cs.USD_PER_STEP + cs.USD_PER_SUMMARY + 0.03
        if spent_24h() + est > daily_cap():
            S.append("weblab.budget_pause", {"spent_24h": round(spent_24h(), 4), "cap": daily_cap(),
                                             "remaining_audits": len(plan) - n}, experiment_id=exp_id)
            return {"paused": True, "reason": f"daily Web Lab cap ${daily_cap():.2f} reached; resumes later",
                    "generation": gen}
        set_progress({"phase": f"gen {gen} · shop {seeds.index(seed) + 1}/{len(seeds)} · {c['label']} (waiting for Codestroller)",
                      "cell": n, "of": len(plan)})
        t0 = time.time()
        while not cl.queue_idle() and time.time() - t0 < 900:
            set_progress({"phase": f"gen {gen} · waiting for Codestroller's queue to clear", "cell": n, "of": len(plan)})
            time.sleep(30)
        for attempt in (1, 2):
            aid = _audit_one(exp_id, gen, split, seed, c, cl,
                             lambda ph: set_progress({"phase": ph, "cell": n, "of": len(plan)}))
            if not aid or _status(aid) != "invalid":
                break
            set_progress({"phase": f"gen {gen} · {c['label']}: shop was unreachable, retrying", "cell": n, "of": len(plan)})
            time.sleep(60)
    summ = summarize(exp_id, gen, split, [c["label"] for c in contestants], note)
    if split == "holdout":
        summ["claims"] = update_claims(exp_id)
    S.append("weblab.generation_finished", {k: summ[k] for k in ("generation", "split", "contestants", "comparisons", "spend")},
             experiment_id=exp_id, cost_usd=0.0, cost_kind="none")
    return summ


def _audit_one(exp_id, gen, split, seed, c, cl, progress):
    spec = shop.make_spec(seed, split)
    with S.engine().begin() as conn:
        aid = conn.execute(S.weblab_audits.insert().values(
            created_at=S.now(), experiment_id=exp_id, generation=gen, contestant=c["label"],
            strategy=S.canon({**c, "shop_seed": seed, "bench": BENCH}), split=split, status="queued")).inserted_primary_key[0]
        sid, tok = shop.create_instance(spec, audit_id=aid, conn=conn)
        conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(shop_id=sid))
    url = f"{PUBLIC_URL}/darwin/weblab/s/{tok}/"
    if not preflight(url):
        with S.engine().begin() as conn:
            conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(
                status="invalid", finished_at=S.now(), score=S.canon({"error": "shop not reachable from outside before submit"})))
        S.append("weblab.audit_invalid", {"audit": aid, "reason": "preflight failed"}, experiment_id=exp_id)
        return aid
    try:
        job_id = cl.submit(url, c["persona_text"], c["goal_text"], c["steps"], c["mobile"])
        with S.engine().begin() as conn:
            conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(job_id=job_id, status="running"))
        job = cl.wait(job_id, heartbeat=lambda j: progress(
            f"gen {gen} · {c['label']} · Codestroller step {len(j.get('steps') or [])}/{c['steps']}"))
    except Exception as e:
        with S.engine().begin() as conn:
            conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(
                status="failed", finished_at=S.now(), score=S.canon({"error": repr(e)[:300]})))
        S.append("failure.weblab_audit", {"audit": aid, "contestant": c["label"], "error": repr(e)[:300]},
                 experiment_id=exp_id)
        return None
    cost_cs = cs.estimate_cost(job, c["mobile"])
    inter = shop.interactions(sid)
    answer = shop.answer_key(spec)
    status = "judged"
    if unusable(job, inter):
        with S.engine().begin() as conn:
            conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(
                status="invalid", finished_at=S.now(), raw=S.canon({"steps": job.get("steps")}),
                score=S.canon({"error": "the agent could not use the shop (infrastructure, not strategy)"}),
                cost=S.canon({"codestroller_usd_estimated": cost_cs, "judge_usd_billed": 0.0, "total_usd": cost_cs,
                              "steps": len(job.get("steps") or []), "note": cs.PRICE_NOTE})))
            S.append("weblab.audit_invalid", {"audit": aid, "reason": "agent could not use the shop",
                                              "steps": len(job.get("steps") or []), "events": inter.get("events")},
                     experiment_id=exp_id, cost_usd=cost_cs, cost_kind="estimated", conn=conn)
        return aid
    if job.get("status") != "complete":
        judged, sc = {"labels": [], "issues": [], "call": None}, None
        status = "failed"
    else:
        judged = J.judge(job, answer, spec["decoys"], url)
        sc = J.score(answer, judged, inter) if not judged.get("error") else None
        if sc is None:
            status = "failed"
    judge_usd = ((judged.get("call") or {}).get("cost_usd") or 0.0)
    cost = {"codestroller_usd_estimated": cost_cs, "judge_usd_billed": judge_usd, "total_usd": round(cost_cs + judge_usd, 6),
            "steps": len(job.get("steps") or []), "note": cs.PRICE_NOTE}
    keep = {"status": job.get("status"), "error": job.get("error"), "report": job.get("report"),
            "steps": [{"step": s.get("step"), "url": s.get("url"), "narration": s.get("narration"),
                       "action": s.get("action"), "issues_found": s.get("issues_found")} for s in job.get("steps") or []]}
    with S.engine().begin() as conn:
        conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == aid).values(
            status=status, raw=S.canon(keep), judged=S.canon({**judged, "interactions": inter}),
            score=S.canon(sc or {"error": judged.get("error") or job.get("error")}), cost=S.canon(cost),
            finished_at=S.now()))
        S.append("weblab.audit", {"audit": aid, "generation": gen, "split": split, "contestant": c["label"],
                                  "shop_seed": seed, "defects": spec["defects"], "score": sc,
                                  "codestroller_job": job.get("id")},
                 experiment_id=exp_id, cost_usd=cost_cs, cost_kind="estimated", conn=conn)
    return aid


def _status(aid):
    with S.engine().connect() as c:
        return c.execute(sa.select(S.weblab_audits.c.status).where(S.weblab_audits.c.id == aid)).scalar()


def preflight(url, tries=3):
    """The shop must answer from the public internet before Codestroller is sent to it."""
    import urllib.request
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "darwin-preflight"}),
                                        timeout=20) as r:
                if r.status == 200 and b"<header>" in r.read(4000):
                    return True
        except Exception:
            pass
        time.sleep(10 * (i + 1))
    return False


DOWN_PHRASES = ("failed to respond", "application error", "bad gateway", "502", "503", "service unavailable",
                "site is down", "site is completely down", "could not load", "page did not load")


def unusable(job, inter):
    """An audit where the agent never really got to use the shop says nothing about its strategy."""
    steps = job.get("steps") or []
    text = " ".join(str(s.get("narration", "")) + " " + " ".join(str(i.get("description", "")) for i in s.get("issues_found") or [])
                    for s in steps[:3]).lower()
    if len(steps) <= 2 and any(p in text for p in DOWN_PHRASES):
        return True
    return job.get("status") == "complete" and inter.get("events", 0) <= 1 and len(steps) <= 2


_revalidated = {"done": False}


def revalidate():
    """Once per process: re-check already-judged audits with the current unusable() rule; corrections are logged."""
    if _revalidated["done"]:
        return
    _revalidated["done"] = True
    for a in _audits(S.weblab_audits.c.status == "judged"):
        raw = a["raw"] or {}
        inter = (a["judged"] or {}).get("interactions") or {}
        if unusable({"steps": raw.get("steps"), "status": raw.get("status")}, inter):
            with S.engine().begin() as conn:
                conn.execute(S.weblab_audits.update().where(S.weblab_audits.c.id == a["id"]).values(status="invalid"))
                S.append("weblab.audit_invalidated", {"audit": a["id"], "previous_score": (a["score"] or {}).get("fitness"),
                                                      "reason": "agent could not use the shop; excluded and re-run"},
                         experiment_id=a["experiment_id"], conn=conn)


_started = time.time()
STARTUP_GRACE_S = 180


def summarize(exp_id, gen, split, labels, note):
    rows = list(filter(current, _audits((S.weblab_audits.c.experiment_id == exp_id) & (S.weblab_audits.c.status == "judged"))))
    by = {}
    for a in rows:
        by.setdefault(a["contestant"], {})[(a["strategy"] or {}).get("shop_seed")] = a["score"]["fitness"]
    contestants = {k: {"mean": round(float(np.mean(list(v.values()))), 4), "n": len(v)} for k, v in by.items()}
    evolved = [l for l in labels if l.startswith("S-")]
    best = max(evolved, key=lambda l: contestants.get(l, {}).get("mean", -1)) if evolved else None
    comps = {}
    if best:
        for base in ("codestroller_default", "nielsen_prompt"):
            pairs = [(by[best][s], by[base][s]) for s in by.get(best, {}) if s in by.get(base, {})]
            if pairs:
                d = np.array([a - b for a, b in pairs])
                w, l = int((d > 1e-9).sum()), int((d < -1e-9).sum())
                comps[f"{best}__vs__{base}"] = {"a": best, "b": base, "n": len(d), "wins": w, "losses": l,
                                                "mean_diff": round(float(d.mean()), 4)}
    spend = sum((a["cost"] or {}).get("total_usd", 0.0) for a in
                _audits(S.weblab_audits.c.experiment_id == exp_id))
    return {"generation": gen, "split": split, "selection": note, "contestants": contestants, "best_evolved": best,
            "comparisons": comps, "spend": {"total_usd": round(spend, 4)},
            "failed_audits": len(_audits((S.weblab_audits.c.experiment_id == exp_id) &
                                         (S.weblab_audits.c.status == "failed")))}


def update_claims(exp_id):
    """Standing claims judged on ALL held-out audits so far, paired by shop."""
    rows = [a for a in _audits(S.weblab_audits.c.status == "judged") if a["split"] == "holdout" and current(a)]
    by_exp = {}
    for a in rows:
        by_exp.setdefault(a["experiment_id"], {}).setdefault(a["contestant"], {})[(a["strategy"] or {}).get("shop_seed")] = \
            a["score"]["fitness"]
    out = {}
    existing = {c["kind"]: c for c in S.all_claims() if (c["kind"] or "").startswith("weblab:")}
    for key, (base, statement) in STANDING.items():
        diffs, per_gen = [], []
        for eid, by in sorted(by_exp.items()):
            ev = [l for l in by if l.startswith("S-")]
            if not ev or base not in by:
                continue
            g = ev[0]
            dd = [by[g][s] - by[base][s] for s in by[g] if s in by[base]]
            diffs += dd
            if dd:
                per_gen.append(float(np.mean(dd)))
        kind = f"weblab:{key}"
        cl = existing.get(kind)
        if cl is None:
            cid = S.add_claim(exp_id, kind, statement, {"baseline": base}, "candidate",
                              "opened with the first held-out Web Lab test")
            prev = "candidate"
        else:
            cid, prev = cl["id"], cl["status"]
        if not diffs:
            out[key] = {"claim": S.fmt_claim(cid), "status": prev, "reason": "no paired held-out audits yet"}
            continue
        d = np.array(diffs)
        w, l = int((d > 1e-9).sum()), int((d < -1e-9).sum())
        p = core.sign_test_p(w, w + l) if w + l else 1.0
        mean = float(d.mean())
        if mean > 0 and p <= 0.05:
            new = "robust" if len(per_gen) >= 3 and all(x > 0 for x in per_gen[-3:]) else "replicated"
        elif mean > 0:
            new = "observed"
        else:
            new = "failed replication" if prev in ("replicated", "robust") else (
                "contradicted" if prev == "observed" else "candidate")
        reason = (f"{len(d)} paired held-out audits over {len(per_gen)} tests: {w} wins, {l} losses, "
                  f"mean {mean:+.3f}, p={p:.4f}")
        if new != prev:
            S.set_claim_status(cid, new, reason, evidence={"wins": w, "losses": l, "n": len(d), "mean_diff": mean,
                                                           "p_sign_test": p}, experiment_id=exp_id)
        out[key] = {"claim": S.fmt_claim(cid), "status": new, "reason": reason}
    return out


MIN_HOURS_BETWEEN = 6


def generation_estimate_usd():
    contestants = BASELINES + [strategy.render(strategy.random_genome(random.Random(0)))] * POP
    return SHOPS_PER_GEN * sum(c["steps"] * cs.USD_PER_STEP + cs.USD_PER_SUMMARY + 0.03 for c in contestants)


def maybe_schedule(now=None):
    """Called once a minute by the scheduler. Resume a paused generation when the budget
    allows; otherwise start a new one at most every MIN_HOURS_BETWEEN hours."""
    if not cs.Client().configured() or os.environ.get("DARWIN_WEBLAB", "on") == "off":
        return None
    if time.time() - _started < STARTUP_GRACE_S:      # let a fresh deploy take traffic first
        return None
    revalidate()
    now = now or datetime.now(timezone.utc)
    with S.engine().begin() as c:
        rows = c.execute(sa.select(S.experiments.c.id, S.experiments.c.status, S.experiments.c.finished_at,
                                   S.experiments.c.created_at).where(S.experiments.c.kind == "weblab").order_by(
            S.experiments.c.id.desc()).limit(5)).all()
        if any(st in ("queued", "running") for _, st, _, _ in rows):
            return None
        one_audit = 30 * cs.USD_PER_STEP + cs.USD_PER_SUMMARY + 0.03
        paused = [i for i, st, _, _ in rows if st == "paused"]
        if paused:
            if spent_24h() + one_audit <= daily_cap():
                c.execute(S.experiments.update().where(S.experiments.c.id == paused[0]).values(status="queued"))
                S.append("weblab.resumed", {"spent_24h": round(spent_24h(), 4)}, experiment_id=paused[0], conn=c)
                return paused[0]
            return None
        last = next(((f or cr) for _, st, f, cr in rows if st in ("completed", "failed")), None)
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < MIN_HOURS_BETWEEN * 3600:
                    return None
            except Exception:
                pass
        if spent_24h() + one_audit > daily_cap():
            return None
        gen = generation_number()
        holdout = gen % HOLDOUT_EVERY == 0
        eid = c.execute(S.experiments.insert().values(
            created_at=S.now(), kind="weblab", lab="web",
            title=f"Web Lab generation {gen}" + (" · held-out test" if holdout else ""),
            goal="Evolve audit strategies for Codestroller against test shops with planted usability defects",
            objective="audit_fitness", config=S.canon({"generation": gen, "holdout": holdout, "shops": SHOPS_PER_GEN}),
            seed=0, status="queued", owner=True, requester="darwin", budget_usd=daily_cap(), max_cpu_s=None,
            stop_requested=False, source="weblab", progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
        S.append("experiment.created", {"title": f"Web Lab generation {gen}", "holdout": holdout,
                                        "estimate_usd": round(generation_estimate_usd(), 3)},
                 experiment_id=eid, conn=c, provenance={"requester": "darwin scheduler"})
        return eid


def maybe_schedule_now():
    """Owner 'run now': ignore the cadence, still respect the queue and the budget."""
    global MIN_HOURS_BETWEEN
    keep = MIN_HOURS_BETWEEN
    try:
        MIN_HOURS_BETWEEN = 0
        return maybe_schedule()
    finally:
        MIN_HOURS_BETWEEN = keep
