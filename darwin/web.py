"""/darwin — the Darwin site, reached through the secret book on the Oedio shelf."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

import numpy as np
import sqlalchemy as sa
from flask import Blueprint, Response, abort, jsonify, make_response, render_template, request

from . import bench, core, costs, life, memory, openlab, schedule, snapshot, store, suite, world_live

S = store
bp = Blueprint("darwin", __name__, url_prefix="/darwin")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_worker = None
_worker_lock = threading.Lock()
_rate = {}


# ── identity ─────────────────────────────────────────────────────────────
def _owner_key():
    return os.environ.get("DARWIN_OWNER_KEY", "")


def _owner_token():
    k = _owner_key()
    return hmac.new(k.encode(), b"darwin-owner-v1", hashlib.sha256).hexdigest() if k else None


def is_owner() -> bool:
    t = _owner_token()
    return bool(t) and hmac.compare_digest(request.cookies.get("darwin_owner", ""), t)


def requester_id() -> str:
    ip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip()
    salt = os.environ.get("DARWIN_SALT", "") or _owner_key() or "darwin"
    return hashlib.sha256((salt + "|" + ip).encode()).hexdigest()[:16]


def _limit(key: str, n: int, per_s: int) -> bool:
    """Small in-process rate limiter for cheap endpoints. True = allowed."""
    now = time.time()
    q = [t for t in _rate.get(key, []) if now - t < per_s]
    if len(q) >= n:
        _rate[key] = q
        return False
    q.append(now)
    _rate[key] = q
    return True


def start_background():
    """Called from the gunicorn post_worker_init hook, and lazily on the first request."""
    world_live.ensure_background()
    try:
        ensure_pool()
    except Exception as e:
        print(f"[darwin] pool start failed: {e!r}")


@bp.before_app_request
def _bg():
    if request.path.startswith("/darwin"):
        world_live.ensure_background()


SYSTEM_SOURCES = ("practice", "benchmark", "dev", "final")


@bp.context_processor
def _ctx():
    return {"is_owner": is_owner(), "fmt_exp": S.fmt_exp, "year": datetime.now().year}


@bp.after_request
def _headers(resp):
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    if request.path.startswith("/darwin/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ── worker management ────────────────────────────────────────────────────
_workers = {}


def ensure_worker():
    """Start the Life Lab and Web Lab workers if they have queued work and none is running."""
    _ensure_group("life")
    _ensure_group("weblab")
    ensure_pool()


_pool_proc = {"p": None}


def ensure_pool():
    """The tidal pool runs in its own process; the advisory lock inside it prevents duplicates."""
    if os.environ.get("DARWIN_POOL", "on") == "off":
        return
    with _worker_lock:
        p = _pool_proc["p"]
        if p is not None and p.poll() is None:
            return
        _pool_proc["p"] = subprocess.Popen([sys.executable, "-m", "darwin.pool", "run"], cwd=ROOT, start_new_session=True)


def _ensure_group(group):
    from .runner import WEBLAB_KINDS, reap_stale
    with _worker_lock:
        w = _workers.get(group)
        if w is not None and w.poll() is None:
            return
        _workers[group] = None
        kind_ok = S.experiments.c.kind.in_(WEBLAB_KINDS) if group == "weblab" else S.experiments.c.kind.notin_(WEBLAB_KINDS)
        with S.engine().connect() as c:
            queued = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
                (S.experiments.c.status == "queued") & kind_ok)).scalar()
            running = c.execute(sa.select(S.experiments.c.heartbeat).where(
                (S.experiments.c.status == "running") & kind_ok)).scalars().all()
        fresh = False
        for hb in running:
            try:
                fresh = fresh or (datetime.now(timezone.utc) - datetime.fromisoformat(hb)).total_seconds() < 120
            except Exception:
                pass
        if queued and not fresh:
            _workers[group] = subprocess.Popen(
                [sys.executable, "-m", "darwin.runner", "work" if group == "life" else "work-weblab"], cwd=ROOT,
                start_new_session=True)
        elif running and not fresh:
            reap_stale(120, group=group)


# ── pages ────────────────────────────────────────────────────────────────
def _recent_experiments(limit=12):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments).order_by(S.experiments.c.id.desc()).limit(limit)).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["label"] = S.fmt_exp(d["id"])
        d["progress"] = S.loads(d["progress"], {}) or {}
        d["cost"] = S.loads(d["cost"], {}) or {}
        d["summary"] = S.loads(d["summary"], {}) or {}
        out.append(d)
    return out


@bp.route("/")
def home():
    ensure_worker()
    return render_template("darwin/world.html", labs=openlab.LABS, experiments=_recent_experiments(6),
                           claims=S.all_claims()[:6], portal=request.args.get("via") == "portal")


@bp.route("/lab/life")
def lab_life():
    preset = {}
    worlds = [{"version": sp.version, "description": sp.description, "default": sp.version == life.DEFAULT_WORLD}
              for sp in life.SPECS.values()]
    if request.args.get("preset"):
        try:
            preset = json.loads(request.args["preset"])
        except Exception:
            preset = {}
    return render_template("darwin/lab_life.html", genes=life.GENES, objectives=life.OBJECTIVES, worlds=worlds,
                           disturbances=core.DISTURBANCES, defaults=core.Config().to_dict(), preset=preset,
                           presets=costs.BUDGET_PRESETS, public=costs.PUBLIC_LIMITS, ownerlim=costs.OWNER_LIMITS,
                           rate=costs.COMPUTE_RATES)


@bp.route("/experiment/<int:exp_id>")
def experiment_page(exp_id):
    ensure_worker()
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.experiments).where(S.experiments.c.id == exp_id)).mappings().first()
    if not row:
        abort(404)
    if row["kind"] == "benchmark":
        from flask import redirect
        return redirect(f"/darwin/intelligence?run={exp_id}")
    return render_template("darwin/experiment.html", exp_id=exp_id, label=S.fmt_exp(exp_id),
                           genes=life.GENES, operators=core.OPERATORS, not_applicable=core.NOT_APPLICABLE)


@bp.route("/ledger")
def ledger_page():
    return render_template("darwin/ledger.html")


@bp.route("/history")
def history_page():
    snap = snapshot.build()
    return render_template("darwin/history.html", snap=snap, experiments=_recent_experiments(200),
                           claims=S.all_claims())


@bp.route("/snapshots")
def snapshots_page():
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.snapshots.c.id, S.snapshots.c.created_at).order_by(
            S.snapshots.c.id.desc()).limit(50)).all()
    return render_template("darwin/snapshots.html", snaps=[{"id": i, "label": S.fmt_snap(i), "created_at": t}
                                                           for i, t in rows])


@bp.route("/system")
def system_page():
    return render_template("darwin/system.html", caps=snapshot.CAPABILITIES, spec=life.WORLD_SPEC,
                           operators=core.OPERATORS, not_applicable=core.NOT_APPLICABLE,
                           disturbances=core.DISTURBANCES, public=costs.PUBLIC_LIMITS, rates=costs.COMPUTE_RATES,
                           llm_prices=costs.LLM_PRICES, llm_note=costs.LLM_PRICES_NOTE)


# ── owner ────────────────────────────────────────────────────────────────
@bp.route("/owner", methods=["GET", "POST"])
def owner():
    msg = None
    if request.method == "POST":
        if not _limit("login:" + requester_id(), 5, 600):
            msg = "Too many attempts. Try again in a few minutes."
        elif _owner_key() and hmac.compare_digest(request.form.get("key", ""), _owner_key()):
            resp = make_response(render_template("darwin/owner.html", ok=True, msg="Owner mode on."))
            resp.set_cookie("darwin_owner", _owner_token(), max_age=60 * 60 * 24 * 30, httponly=True,
                            secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https",
                            samesite="Lax", path="/darwin")
            S.append("owner.login", {"requester": requester_id()})
            return resp
        else:
            msg = "That passphrase is not right." if _owner_key() else "No owner passphrase is configured."
    if request.args.get("logout"):
        resp = make_response(render_template("darwin/owner.html", ok=False, msg="Owner mode off."))
        resp.delete_cookie("darwin_owner", path="/darwin")
        return resp
    return render_template("darwin/owner.html", ok=is_owner(), msg=msg)


# ── the tidal pool (life-3.0) ───────────────────────────────────────────
@bp.route("/barricelli")
def barricelli_page():
    return render_template("darwin/barricelli.html")


@bp.route("/pool")
def pool_page():
    ensure_pool()
    from . import pool
    return render_template("darwin/pool.html", milestones=[{"key": k, "title": t} for k, t, _ in pool.Pool.MILESTONES],
                           years_per_gen=pool.YEARS_PER_GEN, cell_names=pool.CELL_NAMES, version=pool.VERSION)


@bp.route("/api/pool")
def api_pool():
    from . import pool
    try:
        ensure_pool()
    except Exception:
        pass
    d = pool.read_live()
    if d is None:
        return jsonify({"standby": True, "note": "the pool is starting for the first time"})
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["written_at"])).total_seconds()
    except Exception:
        age = 0
    d["stale"] = age > 20
    d["age_s"] = round(age, 1)
    return jsonify(d)


@bp.route("/api/pool/history")
def api_pool_history():
    from . import pool
    return jsonify(pool.history(limit=min(int(request.args.get("limit", 600)), 2000)))


@bp.route("/api/pool/archive")
def api_pool_archive():
    """The archived life-1.0 world (era 4 and earlier): its final record from the Ledger."""
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.events.c.ts, S.events.c.payload).where(S.events.c.type == "world.archived")
                        .order_by(S.events.c.id.desc()).limit(1)).first()
    return jsonify({"archived": bool(row), "ts": row[0] if row else None, "record": S.loads(row[1], {}) if row else None})


# ── live world ───────────────────────────────────────────────────────────
@bp.route("/api/world/frames")
def api_world_frames():
    since = request.args.get("since", type=int, default=-1)
    return jsonify(world_live.frames(since))


@bp.route("/api/world/history")
def api_world_history():
    return jsonify(world_live.history(max(1, min(int(request.args.get("limit", 400)), 2000))))


# ── open lab ─────────────────────────────────────────────────────────────
@bp.route("/api/assess", methods=["POST"])
def api_assess():
    goal = ((request.get_json(silent=True) or {}).get("goal") or "").strip()[:2000]
    if not goal:
        return jsonify({"error": "Describe what you want Darwin to discover."}), 400
    out = {"routing": openlab.route(goal)}
    if is_owner() and (request.get_json(silent=True) or {}).get("llm"):
        out["assessment"] = openlab.assess_llm(goal)
    S.append("openlab.request", {"goal": goal[:500], "lab": out["routing"]["lab"],
                                 "llm": "assessment" in out}, provenance={"requester": requester_id(),
                                                                           "owner": is_owner()})
    return jsonify(out)


# ── experiments ──────────────────────────────────────────────────────────
def _today_public_cpu():
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.cost, S.experiments.c.max_cpu_s, S.experiments.c.status).where(
            (S.experiments.c.owner == False) & (S.experiments.c.created_at >= start))).all()  # noqa: E712
    used = 0.0
    for cost, cap, st in rows:
        if st in ("queued", "running"):
            used += cap or 0
        else:
            used += (S.loads(cost, {}) or {}).get("cpu_s", 0)
    return used


@bp.route("/api/experiments", methods=["POST"])
def api_create():
    body = request.get_json(silent=True) or {}
    owner = is_owner()
    limits = costs.OWNER_LIMITS if owner else costs.PUBLIC_LIMITS
    raw = body.get("config") or {}
    seed = raw.get("seed")
    if seed in (None, "", 0):
        seed = random.SystemRandom().randint(1, 2 ** 31 - 1)
    raw = {k: v for k, v in raw.items() if k != "seed_genomes"}   # memory seeds come only from Discovery Memory
    cfg = core.Config.from_dict({**raw, "seed": int(seed)})
    errs = cfg.validate(limits)
    budget = float(body.get("budget_usd") or 0.10)
    if budget <= 0:
        errs.append("budget must be positive")
    if not owner and budget > 0.10:
        errs.append("visitors can run the $0.10 preset; larger budgets need the owner passphrase")
    if owner and budget > 10:
        errs.append("$100 and $1,000 budgets are not enabled on this deployment (one shared vCPU)")
    rid = requester_id()
    if not owner:
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with S.engine().connect() as c:
            recent = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
                (S.experiments.c.requester == rid) & (S.experiments.c.created_at >= since))).scalar()
            queued = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
                S.experiments.c.status.in_(["queued", "running"]) &
                sa.or_(S.experiments.c.source.is_(None), S.experiments.c.source.notin_(SYSTEM_SOURCES)))).scalar()
        if recent >= limits["per_ip_per_hour"]:
            errs.append(f"limit reached: {limits['per_ip_per_hour']} experiments per hour per visitor")
        if queued >= limits["max_queue"]:
            errs.append("the queue is full; try again when the current experiments finish")
        if _today_public_cpu() + limits["max_cpu_s"] > limits["daily_cpu_s"]:
            errs.append("today's shared public compute allowance is used up; it resets at 00:00 UTC")
    if errs:
        S.append("budget.denied" if any("limit" in e or "budget" in e or "allowance" in e or "queue" in e
                                        for e in errs) else "experiment.rejected",
                 {"errors": errs}, provenance={"requester": rid, "owner": owner})
        return jsonify({"errors": errs}), 400
    max_cpu = min(limits["max_cpu_s"], budget / costs.COMPUTE_RATES["usd_per_vcpu_second"])
    title = (body.get("title") or "").strip()[:120] or f"Life Lab · {cfg.objective}"
    goal = (body.get("goal") or "").strip()[:1000] or None
    with S.engine().begin() as c:
        exp_id = c.execute(S.experiments.insert().values(
            created_at=S.now(), kind="evolve", lab="life", title=title, goal=goal, objective=cfg.objective,
            config=S.canon(cfg.to_dict()), seed=cfg.seed, status="queued", owner=owner, requester=rid,
            budget_usd=budget, max_cpu_s=max_cpu, stop_requested=False, source="owner" if owner else "visitor",
            progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
        S.append("experiment.created", {"title": title, "goal": goal, "config": cfg.to_dict(),
                                        "budget_usd": budget, "max_cpu_s": round(max_cpu, 2),
                                        "world": cfg.world},
                 experiment_id=exp_id, provenance={"requester": rid, "owner": owner}, conn=c)
    ensure_worker()
    return jsonify({"id": exp_id, "label": S.fmt_exp(exp_id), "url": f"/darwin/experiment/{exp_id}"})


def _exp_or_404(exp_id):
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.experiments).where(S.experiments.c.id == exp_id)).mappings().first()
    if not row:
        abort(404)
    return dict(row)


@bp.route("/api/experiments/<int:exp_id>")
def api_experiment(exp_id):
    ensure_worker()
    e = _exp_or_404(exp_id)
    with S.engine().connect() as c:
        gens = [json.loads(s) for (s,) in c.execute(sa.select(S.generations.c.stats).where(
            S.generations.c.experiment_id == exp_id).order_by(S.generations.c.gen))]
        pos = None
        if e["status"] == "queued":
            pos = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
                (S.experiments.c.status == "queued") & (S.experiments.c.id < exp_id))).scalar()
        replays = [dict(r) for r in c.execute(sa.select(S.experiments.c.id, S.experiments.c.status,
                                                        S.experiments.c.summary).where(
            S.experiments.c.replay_of == exp_id).order_by(S.experiments.c.id)).mappings()]
        llm = c.execute(sa.select(sa.func.coalesce(sa.func.sum(S.llm_calls.c.cost_usd), 0.0)).where(
            S.llm_calls.c.experiment_id == exp_id)).scalar()
    cfg = json.loads(e["config"])
    spec = life.get_spec(cfg.get("world"))
    disp = [[n, float(spec.LOW[spec.idx[n]]), float(spec.HIGH[spec.idx[n]])] for n in spec.body]
    return jsonify({
        "world": spec.version, "world_description": spec.description, "display_genes": disp,
        "source": e.get("source"),
        "id": exp_id, "label": S.fmt_exp(exp_id), "kind": e["kind"], "replay_of": e["replay_of"],
        "title": e["title"], "goal": e["goal"], "status": e["status"], "queue_position": pos,
        "created_at": e["created_at"], "started_at": e["started_at"], "finished_at": e["finished_at"],
        "stop_reason": e["stop_reason"], "config": cfg, "seed": e["seed"],
        "train_seeds": core.Config.from_dict(cfg).train_seed_list(),
        "holdout_seeds": core.Config.from_dict(cfg).holdout_seed_list(),
        "budget_usd": e["budget_usd"], "max_cpu_s": e["max_cpu_s"], "owner_run": bool(e["owner"]),
        "progress": S.loads(e["progress"], {}), "summary": S.loads(e["summary"], {}),
        "cost": {**(S.loads(e["cost"], {}) or {}), "llm_usd_billed": llm},
        "code_version": e["code_version"], "environment": S.loads(e["environment"], {}),
        "digest": e["result_digest"], "generations": gens,
        "claims": [{"id": cl["label"], "statement": cl["statement"], "status": cl["status"],
                    "history": [{"ts": h["ts"], "status": h["status"], "reason": h["reason"]} for h in cl["history"]]}
                   for cl in S.all_claims(exp_id)],
        "replays": [{"id": r["id"], "label": S.fmt_exp(r["id"]), "status": r["status"],
                     "result": (S.loads(r["summary"], {}) or {}).get("replay")} for r in replays],
        "can_stop": e["status"] in ("queued", "running") and (is_owner() or e["requester"] == requester_id()),
    })


@bp.route("/api/experiments/<int:exp_id>/stop", methods=["POST"])
def api_stop(exp_id):
    e = _exp_or_404(exp_id)
    if not (is_owner() or e["requester"] == requester_id()):
        return jsonify({"error": "only the person who started an experiment, or the owner, can stop it"}), 403
    with S.engine().begin() as c:
        if e["status"] == "queued":
            c.execute(S.experiments.update().where(S.experiments.c.id == exp_id).values(
                status="stopped", stop_reason="cancelled before start", finished_at=S.now()))
        else:
            c.execute(S.experiments.update().where(S.experiments.c.id == exp_id).values(stop_requested=True))
        S.append("experiment.stop_requested", {"status_at_request": e["status"]}, experiment_id=exp_id,
                 provenance={"requester": requester_id(), "owner": is_owner()}, conn=c)
    return jsonify({"ok": True})


@bp.route("/api/experiments/<int:exp_id>/replay", methods=["POST"])
def api_replay(exp_id):
    e = _exp_or_404(exp_id)
    if e["kind"] != "evolve" or e["status"] not in ("completed", "stopped"):
        return jsonify({"error": "only finished evolution experiments can be replayed"}), 400
    owner = is_owner()
    if not owner:
        lim = costs.PUBLIC_LIMITS
        if not _limit("replay:" + requester_id(), 2, 3600):
            return jsonify({"error": "limit reached: 2 replays per hour per visitor"}), 429
        if _today_public_cpu() + lim["max_cpu_s"] > lim["daily_cpu_s"]:
            return jsonify({"error": "today's shared public compute allowance is used up"}), 429
    with S.engine().begin() as c:
        rid = c.execute(S.experiments.insert().values(
            created_at=S.now(), kind="replay", replay_of=exp_id, lab=e["lab"], title=f"Replay of {S.fmt_exp(exp_id)}",
            objective=e["objective"], config=e["config"], seed=e["seed"], status="queued", owner=owner,
            requester=requester_id(), budget_usd=e["budget_usd"],
            max_cpu_s=(e["max_cpu_s"] or 60) * 1.5, stop_requested=False,
            progress=S.canon({"phase": "queued"}))).inserted_primary_key[0]
        S.append("replay.requested", {"replay_experiment": S.fmt_exp(rid)}, experiment_id=exp_id, conn=c,
                 provenance={"requester": requester_id(), "owner": owner})
    ensure_worker()
    return jsonify({"id": rid, "label": S.fmt_exp(rid), "url": f"/darwin/experiment/{rid}"})


@bp.route("/api/experiments/<int:exp_id>/candidates")
def api_candidates(exp_id):
    gen = request.args.get("gen", type=int)
    q = sa.select(S.candidates).where(S.candidates.c.experiment_id == exp_id)
    if gen is not None:
        q = q.where(S.candidates.c.gen == gen)
    with S.engine().connect() as c:
        rows = c.execute(q.order_by(S.candidates.c.fitness.desc()).limit(400)).mappings().all()
    return jsonify([_cand(r) for r in rows])


def _cand(r, spec=None):
    d = dict(r)
    for k in ("parents", "params", "genome", "fitness_seeds"):
        d[k] = S.loads(d[k], [])
    if isinstance(d["genome"], list):
        spec = spec or (life.NEURAL if len(d["genome"]) == life.NEURAL.G else life.LINEAR)
        d["genome_named"] = life.genome_summary(d["genome"], spec)
    return d


@bp.route("/api/experiments/<int:exp_id>/lineage/<cid>")
def api_lineage(exp_id, cid):
    """Ancestry of one candidate, walking parent links back to generation 0."""
    nodes, edges, frontier, seen = {}, [], [cid], set()
    with S.engine().connect() as c:
        while frontier and len(nodes) < 400:
            batch = [x for x in frontier if x not in seen]
            seen.update(batch)
            if not batch:
                break
            rows = c.execute(sa.select(S.candidates).where((S.candidates.c.experiment_id == exp_id) &
                                                            (S.candidates.c.cid.in_(batch)))).mappings().all()
            frontier = []
            for r in rows:
                d = _cand(r)
                nodes[d["cid"]] = {k: d[k] for k in ("cid", "gen", "island", "operator", "fitness", "params", "root")}
                for p in d["parents"]:
                    edges.append([p, d["cid"]])
                    frontier.append(p)
    if cid not in nodes:
        abort(404)
    return jsonify({"nodes": list(nodes.values()), "edges": edges})


@bp.route("/api/experiments/<int:exp_id>/episode/<cid>")
def api_episode(exp_id, cid):
    """Time Machine: re-simulate one recorded candidate on a recorded seed and return frames.
    This is a deterministic re-run from stored genome + seed + conditions, not a recording."""
    if not _limit("episode:" + requester_id(), 30, 600):
        return jsonify({"error": "slow down: 30 re-simulations per 10 minutes"}), 429
    e = _exp_or_404(exp_id)
    with S.engine().connect() as c:
        r = c.execute(sa.select(S.candidates).where((S.candidates.c.experiment_id == exp_id) &
                                                    (S.candidates.c.cid == cid))).mappings().first()
    if not r:
        abort(404)
    d = _cand(r)
    cfg = core.Config.from_dict(json.loads(e["config"]))
    spec = life.get_spec(cfg.world)
    which = request.args.get("seed", "train")
    seeds = cfg.holdout_seed_list() if which == "holdout" else cfg.train_seed_list()
    seed = seeds[0]
    cond = core.conditions_at(cfg, d["gen"])
    cond = life.Conditions(**{**cond.to_dict(), "reproduction": cfg.objective == "thrive"})
    rng = np.random.default_rng(seed)
    M = cfg.cohort * 4 if cfg.objective == "thrive" else cfg.cohort
    sim = life.LifeSim(rng, 1, M, cond, spec)
    start = rng.random((cfg.cohort, 2)) * life.ARENA
    sim.place(0, np.repeat(np.array(d["genome"])[None, :], cfg.cohort, 0), positions=start)
    frames = []
    for t in range(cfg.ticks):
        if cfg.objective == "survive":
            sim.cond = life.famine(cond, t, cfg.ticks)
        sim.step()
        if t % 2 == 0:
            a = sim.alive[0]
            fa = sim.favail[0]
            frames.append({"t": sim.tick,
                           "c": np.stack([np.flatnonzero(a), np.round(sim.px[0][a] * 10), np.round(sim.py[0][a] * 10),
                                          np.round(np.clip(sim.energy[0][a], 0, 999))], 1).astype(int).tolist(),
                           "f": np.stack([np.round(sim.fx[0][fa] * 10), np.round(sim.fy[0][fa] * 10),
                                          sim.ftype[0][fa]], 1).astype(int).tolist(),
                           "h": np.stack([np.round(sim.hx[0] * 10), np.round(sim.hy[0] * 10)], 1).astype(int).tolist()})
        if not sim.alive.any():
            break
    score = {"forage": float(sim.energy_gathered[0] / cfg.cohort),
             "survive": float(life.endurance(sim, cfg.cohort, cfg.ticks)[0]),
             "thrive": float(sim.alive[0].sum() / cfg.cohort)}[cfg.objective]
    return jsonify({"cid": cid, "seed": seed, "seed_set": which, "conditions": cond.to_dict(), "frames": frames,
                    "size": d["genome_named"]["size"], "pref": d["genome_named"]["pref"],
                    "score": round(score, 6), "recorded_score": (d["fitness_seeds"] or [None])[0] if which == "train" else None,
                    "hazard_radius": life.HAZARD_RADIUS, "genome": d["genome_named"]})


# ── ledger, claims, history ──────────────────────────────────────────────
@bp.route("/api/ledger")
def api_ledger():
    before = request.args.get("before", type=int)
    typ = request.args.get("type", "").strip()
    exp = request.args.get("experiment", type=int)
    q = sa.select(S.events)
    if before:
        q = q.where(S.events.c.id < before)
    if typ:
        q = q.where(S.events.c.type.like(typ.replace("*", "%") if "*" in typ else typ + "%"))
    if exp:
        q = q.where(S.events.c.experiment_id == exp)
    with S.engine().connect() as c:
        rows = c.execute(q.order_by(S.events.c.id.desc()).limit(100)).mappings().all()
        total = c.execute(sa.select(sa.func.count()).select_from(S.events)).scalar()
        spent = c.execute(sa.select(S.events.c.cost_kind, sa.func.sum(S.events.c.cost_usd)).group_by(
            S.events.c.cost_kind)).all()
    out = []
    for r in rows:
        d = dict(r)
        d["payload"] = S.loads(d["payload"], {})
        d["provenance"] = S.loads(d["provenance"], {})
        d["experiment"] = S.fmt_exp(d["experiment_id"]) if d["experiment_id"] else None
        out.append(d)
    return jsonify({"events": out, "total": total, "spent": {k or "none": v for k, v in spent}})


@bp.route("/api/ledger/verify")
def api_ledger_verify():
    if not _limit("verify", 6, 60):
        return jsonify({"error": "verification is rate limited"}), 429
    return jsonify(S.verify_chain())


@bp.route("/api/claims")
def api_claims():
    return jsonify([{"id": c["label"], "experiment": S.fmt_exp(c["experiment_id"]) if c["experiment_id"] else None,
                     "experiment_id": c["experiment_id"], "kind": c["kind"], "statement": c["statement"],
                     "status": c["status"], "evidence": c["evidence"],
                     "history": [{"ts": h["ts"], "status": h["status"], "reason": h["reason"]} for h in c["history"]]}
                    for c in S.all_claims()])


# ── snapshots ────────────────────────────────────────────────────────────
@bp.route("/api/snapshots", methods=["POST"])
def api_snapshot_create():
    if not is_owner() and not _limit("snap:" + requester_id(), 3, 3600):
        return jsonify({"error": "limit reached: 3 snapshots per hour per visitor"}), 429
    snap = snapshot.build()
    with S.engine().begin() as c:
        sid = c.execute(S.snapshots.insert().values(created_at=snap["created_at"],
                                                    data=snapshot.redact(json.dumps(snap, default=str)))).inserted_primary_key[0]
        S.append("snapshot.created", {"snapshot": S.fmt_snap(sid), "totals": snap["totals"],
                                      "warnings": snap["warnings"]}, conn=c,
                 provenance={"requester": requester_id(), "owner": is_owner()})
    return jsonify({"id": sid, "label": S.fmt_snap(sid), "zip": f"/darwin/snapshots/{sid}.zip"})


def _snap(sid):
    with S.engine().connect() as c:
        d = c.execute(sa.select(S.snapshots.c.data).where(S.snapshots.c.id == sid)).scalar()
    if d is None:
        abort(404)
    return json.loads(d)


@bp.route("/snapshots/<int:sid>.zip")
def snapshot_zip(sid):
    snap = _snap(sid)
    with S.engine().connect() as c:
        rows = [dict(r) for r in c.execute(sa.select(S.events).where(
            S.events.c.ts <= snap["created_at"]).order_by(S.events.c.id)).mappings()]
    data = snapshot.package(snap, rows)
    return Response(data, mimetype="application/zip", headers={
        "Content-Disposition": f'attachment; filename="DARWIN_SNAPSHOT_{S.fmt_snap(sid)}.zip"'})


@bp.route("/snapshots/<int:sid>.md")
def snapshot_md(sid):
    return Response(snapshot.render_md(_snap(sid)), mimetype="text/markdown; charset=utf-8")


@bp.route("/api/snapshots/<int:sid>/compare")
def api_snapshot_compare(sid):
    other = request.args.get("with", type=int)
    with S.engine().connect() as c:
        if other is None:
            other = c.execute(sa.select(S.snapshots.c.id).where(S.snapshots.c.id < sid).order_by(
                S.snapshots.c.id.desc()).limit(1)).scalar()
    if other is None:
        return jsonify({"error": "no earlier snapshot to compare with"}), 404
    a, b = sorted([other, sid])
    out = snapshot.compare(_snap(a), _snap(b))
    out["from_id"], out["to_id"] = S.fmt_snap(a), S.fmt_snap(b)
    return jsonify(out)


# ── Phase 2: Intelligence (benchmarks) and Memory ────────────────────────
@bp.route("/intelligence")
def intelligence_page():
    ensure_worker()
    from . import bench2, curriculum
    return render_template("darwin/intelligence.html", problems=suite.problems(), suite_version=suite.SUITE2,
                           world=suite.WORLD, contestants=bench2.CONTESTANTS, final_uses=bench.final_uses(),
                           params=bench2.PARAMS, run_id=request.args.get("run", type=int),
                           cycle_hours=schedule.CYCLE_HOURS, practice=curriculum.PRACTICE_PER_CYCLE,
                           fresh_n=suite.FRESH_PER_CYCLE, fresh_reps=suite.FRESH_REPLICATES,
                           dist=suite.DISTRIBUTION, fresh_cal=suite.FRESH_CALIBRATION_N,
                           series=request.args.get("series", type=int))


def _has_series2_run():
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.config).where(S.experiments.c.kind == "benchmark")).scalars().all()
    return any((S.loads(r, {}) or {}).get("series") == 2 for r in rows)


def _bench_run(exp_id=None, series=None):
    with S.engine().connect() as c:
        q = sa.select(S.experiments).where(S.experiments.c.kind == "benchmark")
        if exp_id:
            e = c.execute(q.where(S.experiments.c.id == exp_id)).mappings().first()
        else:
            e = None
            for row in c.execute(q.order_by(S.experiments.c.id.desc()).limit(40)).mappings():
                cs = (S.loads(row["config"], {}) or {}).get("series", 1)
                if series is None or cs == series or (series == 1 and cs != 2):
                    e = row
                    break
        if not e:
            return None
        rows = c.execute(sa.select(S.bench_results).where(S.bench_results.c.experiment_id == e["id"]).order_by(
            S.bench_results.c.id)).mappings().all()
    return {"id": e["id"], "label": S.fmt_exp(e["id"]), "title": e["title"], "status": e["status"],
            "created_at": e["created_at"], "finished_at": e["finished_at"], "progress": S.loads(e["progress"], {}),
            "stop_reason": e["stop_reason"], "config": S.loads(e["config"], {}),
            "summary": (S.loads(e["summary"], {}) or {}).get("benchmark"), "code_version": e["code_version"],
            "series": (S.loads(e["config"], {}) or {}).get("series", 1),
            "cells": [{"problem": r["problem"], "group": r["split"], "contestant": r["contestant"],
                       "replicate": r["replicate"], "normalized": r["normalized"], "score": r["score"],
                       "evaluations": r["evaluations"], "cpu_s": r["cpu_s"], "detail": S.loads(r["detail"], {})}
                      for r in rows]}


@bp.route("/api/benchmark")
def api_benchmark():
    from . import bench2
    h2 = bench2.history()
    series = request.args.get("series", type=int) or (2 if h2 or _has_series2_run() else 1)
    run = _bench_run(request.args.get("run", type=int), series=None if request.args.get("run") else series)
    return jsonify({"series": series, "run": run,
                    "history": h2 if series == 2 else bench.history("holdout"),
                    "versions": bench2.versions() if series == 2 else bench.versions("holdout"),
                    "learned_model": memory.model_info(),
                    "contestants": bench2.CONTESTANTS if series == 2 else bench.CONTESTANTS,
                    "runs": _bench_runs(), "memory_size": len(memory.entries(suite.WORLD, active_only=True)),
                    "final_uses": bench.final_uses(),
                    "standing": [{"id": c["label"], "kind": c["kind"], "statement": c["statement"], "status": c["status"],
                                  "history": [{"ts": h["ts"], "status": h["status"], "reason": h["reason"]}
                                              for h in c["history"]]}
                                 for c in S.all_claims() if (c["kind"] or "").startswith("standing:")]})


def _bench_runs(limit=60):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments.c.id, S.experiments.c.title, S.experiments.c.status,
                                   S.experiments.c.created_at, S.experiments.c.config).where(
            S.experiments.c.kind == "benchmark").order_by(S.experiments.c.id.desc()).limit(limit)).all()
    return [{"id": i, "label": S.fmt_exp(i), "title": t, "status": st, "created_at": ts,
             "series": (S.loads(cf, {}) or {}).get("series", 1),
             "split": "cycle" if (S.loads(cf, {}) or {}).get("series") == 2 else (S.loads(cf, {}) or {}).get("split")}
            for i, t, st, ts, cf in rows]


@bp.route("/api/benchmark/run", methods=["POST"])
def api_benchmark_run():
    """Owner-only: dev benchmarks any time; the final never-seen set, recorded and counted."""
    if not is_owner():
        return jsonify({"error": "owner only"}), 403
    split = (request.get_json(silent=True) or {}).get("split", "dev")
    if split not in ("dev", "final"):
        return jsonify({"error": "only dev and final can be run on demand; holdout runs daily on its own"}), 400
    with S.engine().begin() as c:
        busy = c.execute(sa.select(sa.func.count()).select_from(S.experiments).where(
            (S.experiments.c.kind == "benchmark") & S.experiments.c.status.in_(["queued", "running"]))).scalar()
        if busy:
            return jsonify({"error": "a benchmark is already queued or running"}), 409
        eid = schedule.queue_benchmark(split, S.now()[:10], c, requester="owner", source=split)
    ensure_worker()
    return jsonify({"id": eid, "label": S.fmt_exp(eid), "url": f"/darwin/intelligence?run={eid}"})


@bp.route("/memory")
def memory_page():
    st = memory.stats()
    ents = memory.entries()
    for e in ents:
        e["label"] = S.fmt_mem(e["id"])
        e["uses"], e["helped"] = st.get(e["id"], (0, 0))
        near = suite.protected_near(e["objective"], e["conditions"] or {})
        e["nearest_protected"] = {"problem": near[0], "distance": round(near[1], 3)} if near else None
        e["summary"] = life.genome_summary(e["genome"], life.get_spec(e["world"]))
    model = memory.model_info()
    with S.engine().connect() as c:
        excluded = c.execute(sa.select(sa.func.count()).select_from(S.events).where(
            S.events.c.type == "memory.excluded")).scalar()
    return render_template("darwin/memory.html", entries=list(reversed(ents)), failures=memory.failures_list(),
                           failure_counts=memory.failure_counts(), excluded=excluded, leak=suite.LEAK_DISTANCE,
                           fmt_mem=S.fmt_mem, model=model, retire_uses=memory.RETIRE_MIN_USES,
                           retire_rate=memory.RETIRE_MAX_RATE)


from .weblab import pages as _weblab_pages  # noqa: E402,F401  (Web Lab routes)
