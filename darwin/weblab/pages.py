"""Web Lab pages and API, registered on the Darwin blueprint."""
from __future__ import annotations

import json
import random

import sqlalchemy as sa
from flask import abort, jsonify, render_template, request

from .. import store
from ..web import _limit, bp, ensure_worker, is_owner, requester_id
from . import client as cs
from . import evolve, shop, strategy
from .defects import DECOYS, DEFECTS, HEURISTICS, HOLDOUT_ONLY

S = store


@bp.route("/lab/web")
def weblab_page():
    ensure_worker()
    return render_template("darwin/lab_web.html", defects=DEFECTS, heuristics=HEURISTICS, decoys=DECOYS,
                           holdout_only=HOLDOUT_ONLY, personas=strategy.PERSONAS, probes=strategy.PROBES,
                           stances=strategy.STANCES, baselines=evolve.BASELINES, configured=cs.Client().configured(),
                           cap=evolve.daily_cap(), pop=evolve.POP, shops=evolve.SHOPS_PER_GEN,
                           holdout_every=evolve.HOLDOUT_EVERY, estimate=round(evolve.generation_estimate_usd(), 2),
                           price_note=cs.PRICE_NOTE, codestroller=cs.BASE)


@bp.route("/lab/web/audit/<int:aid>")
def weblab_audit_page(aid):
    return render_template("darwin/lab_web_audit.html", aid=aid, heuristics=HEURISTICS)


def _gens():
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.experiments).where(S.experiments.c.kind == "weblab").order_by(
            S.experiments.c.id.desc()).limit(60)).mappings().all()
    out = []
    for r in rows:
        cfg = S.loads(r["config"], {}) or {}
        summ = (S.loads(r["summary"], {}) or {}).get("weblab") or {}
        out.append({"id": r["id"], "label": S.fmt_exp(r["id"]), "title": r["title"], "status": r["status"],
                    "created_at": r["created_at"], "finished_at": r["finished_at"], "generation": cfg.get("generation"),
                    "holdout": cfg.get("holdout"), "progress": S.loads(r["progress"], {}), "stop_reason": r["stop_reason"],
                    "summary": summ})
    return out


@bp.route("/api/weblab")
def api_weblab():
    ensure_worker()
    audits = evolve._audits()
    recent = []
    for a in reversed(audits[-80:]):
        sc = a["score"] or {}
        recent.append({"id": a["id"], "generation": a["generation"], "contestant": a["contestant"], "split": a["split"],
                       "status": a["status"] if evolve.current(a) or a["status"] != "judged" else "superseded",
                       "bench": (a["strategy"] or {}).get("bench") or "shop-1+judge-1", "created_at": a["created_at"], "fitness": sc.get("fitness"),
                       "found": sc.get("found"), "missed": sc.get("missed"), "decoy_hits": sc.get("decoy_hits"),
                       "coverage": sc.get("coverage"), "safety": sc.get("safety"), "precision": sc.get("precision"),
                       "cost": (a["cost"] or {}).get("total_usd"), "error": sc.get("error")})
    per_gen = {}
    for a in audits:
        sc = a["score"] or {}
        if a["status"] != "judged" or sc.get("fitness") is None or not evolve.current(a):
            continue
        g = per_gen.setdefault(a["generation"], {"generation": a["generation"], "split": a["split"], "evolved": [],
                                                 "codestroller_default": [], "nielsen_prompt": []})
        key = a["contestant"] if a["contestant"] in ("codestroller_default", "nielsen_prompt") else "evolved"
        g[key].append(sc["fitness"])
    curve = []
    for g in sorted(per_gen.values(), key=lambda x: x["generation"]):
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
        curve.append({"generation": g["generation"], "split": g["split"], "best_evolved": max(g["evolved"]) if g["evolved"] else None,
                      "mean_evolved": mean(g["evolved"]), "codestroller_default": mean(g["codestroller_default"]),
                      "nielsen_prompt": mean(g["nielsen_prompt"])})
    claims = [{"id": c["label"], "kind": c["kind"], "statement": c["statement"], "status": c["status"],
               "history": [{"ts": h["ts"], "status": h["status"], "reason": h["reason"]} for h in c["history"]]}
              for c in S.all_claims() if (c["kind"] or "").startswith("weblab:")]
    return jsonify({"bench": evolve.BENCH, "configured": cs.Client().configured(), "cap_usd": evolve.daily_cap(),
                    "spent_24h": round(evolve.spent_24h(), 4), "generations": _gens(), "leaderboard": evolve.leaderboard(),
                    "curve": curve, "recent": recent, "claims": claims,
                    "totals": {"audits": len(audits), "judged": sum(1 for a in audits if a["status"] == "judged"),
                               "spend_usd": round(sum((a["cost"] or {}).get("total_usd", 0.0) for a in audits), 4)}})


@bp.route("/api/weblab/audit/<int:aid>")
def api_weblab_audit(aid):
    rows = evolve._audits(S.weblab_audits.c.id == aid)
    if not rows:
        abort(404)
    a = rows[0]
    with S.engine().connect() as c:
        tok, spec = c.execute(sa.select(S.weblab_shops.c.token, S.weblab_shops.c.spec).where(
            S.weblab_shops.c.id == a["shop_id"])).first() or (None, None)
    spec = S.loads(spec, {}) or {}
    return jsonify({**{k: a[k] for k in ("id", "generation", "contestant", "split", "status", "created_at", "finished_at",
                                         "job_id", "strategy", "raw", "judged", "score", "cost")},
                    "shop": {"url": f"/darwin/weblab/s/{tok}/" if tok else None, "name": spec.get("name"),
                             "domain": spec.get("domain"), "answer_key": shop.answer_key(spec) if spec else [],
                             "decoys": [{"id": d, "text": DECOYS[d]} for d in spec.get("decoys", [])]}})


@bp.route("/api/weblab/run", methods=["POST"])
def api_weblab_run():
    if not is_owner():
        return jsonify({"error": "owner only"}), 403
    if not cs.Client().configured():
        return jsonify({"error": "Codestroller credentials are not configured on this deployment"}), 400
    eid = evolve.maybe_schedule_now()
    if not eid:
        return jsonify({"error": "a generation is already queued or running, or today's Web Lab budget is used up"}), 409
    ensure_worker()
    return jsonify({"id": eid, "label": S.fmt_exp(eid)})


@bp.route("/api/weblab/sample-shop", methods=["POST"])
def api_weblab_sample():
    """Anyone can open a freshly generated test shop to see what the auditor faces (answer key hidden)."""
    if not is_owner() and not _limit("sample-shop:" + requester_id(), 5, 3600):
        return jsonify({"error": "limit: 5 sample shops per hour"}), 429
    spec = shop.make_spec(random.SystemRandom().randint(1, 2 ** 31 - 1), "train")
    sid, tok = shop.create_instance(spec)
    S.append("weblab.sample_shop", {"shop": sid}, provenance={"requester": requester_id(), "owner": is_owner()})
    out = {"url": f"/darwin/weblab/s/{tok}/", "name": spec["name"]}
    if is_owner():
        out["answer_key"] = shop.answer_key(spec)
        out["decoys"] = spec["decoys"]
    return jsonify(out)
