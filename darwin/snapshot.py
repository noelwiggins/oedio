"""CREATE DARWIN SNAPSHOT (Brief s.66-70): a self-contained review package.

ZIP contents: DARWIN_SNAPSHOT.md, DARWIN_SNAPSHOT.json, DARWIN_LEDGER_EXPORT.csv,
DARWIN_BENCHMARKS.csv, and SVG graphs. Every figure is computed from stored
records; anything not yet measured is listed as missing rather than drawn.
Secrets are never included: the export carries no keys, IPs or tokens, and any
string that looks like a credential is redacted.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile

import sqlalchemy as sa

from . import core, costs, life, store

S = store
SCHEMA_VERSION = "darwin-snapshot-1"
_SECRET = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{20,}|[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-"
                     r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}|Bearer\s+\S+)")


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


CAPABILITIES = [
    # (area, status, note) — status: operational | experimental | planned | unsupported
    ("Darwin Core loop (generate, evaluate, select, vary, stop)", "operational", "core.py"),
    ("Life Lab world + Darwin World terrarium", "operational", "life.py, world_live.py"),
    ("Variation: point/multi mutation, uniform/blend crossover, distant recombination, immigrants, island migration",
     "operational", "fit the fixed-length vector genome"),
    ("Variation: duplication, deletion, structural change", "unsupported",
     "not applicable to Life World 1.0's fixed-length genome"),
    ("Disturbances: scarcity shock, hazard shock, diet shift, mutation burst", "operational", "per-experiment"),
    ("Candidate lineage + ancestry view", "operational", ""),
    ("Diversity, dominant-lineage and premature-convergence warnings", "operational", ""),
    ("Cost tracking (CPU, wall, sim steps, estimated $, electricity)", "operational", "estimates, not invoices"),
    ("LLM token + cost accounting", "operational", "Open Lab assessment only (owner)"),
    ("Budget presets and hard compute caps", "operational", "public: 45 CPU-s/experiment"),
    ("Append-only hash-chained Ledger + verification", "operational", "DB triggers + SHA-256 chain"),
    ("Claims with status history (candidate→observed→replicated→robust / failed replication)",
     "operational", "automatic, evidence-linked"),
    ("Held-out seed validation, adversarial perturbation test", "operational", ""),
    ("Random-search baseline", "experimental", "optional per experiment"),
    ("REPLAY EXPERIMENT with digest comparison", "operational", ""),
    ("Time Machine: inspect generations, re-simulate any recorded candidate", "operational", ""),
    ("Snapshot export + comparison with previous snapshot", "operational", ""),
    ("Open Lab: natural-language goal → feasibility assessment", "experimental",
     "LLM assessment for owner; keyword routing for visitors"),
    ("Pause / resume from checkpoint", "planned", "stop is supported; resume is not"),
    ("Discovery Memory, Failure Memory reuse across experiments", "planned", "Phase 2 (failures are recorded now)"),
    ("Baselines beyond random search, holdout worlds, ablations", "planned", "Phase 2"),
    ("Web Lab, Space Lab, Operations Lab", "planned", "Phase 3"),
    ("Meta-evolution, hybrid gradient learning, transfer", "planned", "Phase 4"),
    ("External review import, reviewer accountability", "planned", "Phase 4"),
    ("Real-world validation, Reality Gap tracking", "planned", "requires real-world tests"),
]


def _rows(c, table, order):
    return [dict(r) for r in c.execute(sa.select(table).order_by(order)).mappings()]


def build() -> dict:
    with S.engine().connect() as c:
        exps = _rows(c, S.experiments, S.experiments.c.id)
        n_events = c.execute(sa.select(sa.func.count()).select_from(S.events)).scalar()
        llm = _rows(c, S.llm_calls, S.llm_calls.c.id)
        n_gens = c.execute(sa.select(sa.func.count()).select_from(S.generations)).scalar()
        n_cands = c.execute(sa.select(sa.func.count()).select_from(S.candidates)).scalar()
        failures = c.execute(sa.select(S.events.c.type, sa.func.count()).where(
            S.events.c.type.like("failure.%")).group_by(S.events.c.type)).all()
        world_last = c.execute(sa.select(S.world_stats).order_by(S.world_stats.c.id.desc()).limit(1)).mappings().first()
    claims = S.all_claims()
    chain = S.verify_chain()

    compute_usd = 0.0
    cpu_s = 0.0
    exp_list = []
    for e in exps:
        cost = S.loads(e["cost"], {}) or {}
        summ = S.loads(e["summary"], {}) or {}
        compute_usd += cost.get("compute_usd_estimated", 0.0)
        cpu_s += cost.get("cpu_s", 0.0)
        exp_list.append({
            "id": S.fmt_exp(e["id"]), "kind": e["kind"], "lab": e["lab"], "objective": e["objective"],
            "status": e["status"], "created_at": e["created_at"], "stop_reason": e["stop_reason"],
            "seed": e["seed"], "code_version": e["code_version"], "owner": bool(e["owner"]),
            "cpu_s": cost.get("cpu_s"), "compute_usd_estimated": cost.get("compute_usd_estimated"),
            "generations_run": summ.get("generations_run"),
            "gen0_best": (summ.get("gen0_best") or {}).get("fitness"),
            "final_best": (summ.get("final_best") or {}).get("fitness"),
            "holdout": (summ.get("validation") or {}).get("holdout"),
            "replay": summ.get("replay"),
            "digest": e["result_digest"],
        })
    llm_usd = sum((r["cost_usd"] or 0.0) for r in llm)
    by_status = {}
    for cl in claims:
        by_status[cl["status"]] = by_status.get(cl["status"], 0) + 1
    validated = sum(by_status.get(k, 0) for k in ("replicated", "robust", "transferred", "real-world validated"))
    total = compute_usd + llm_usd

    warnings = []
    if not chain["ok"]:
        warnings.append(f"LEDGER CHAIN BROKEN at event {chain['bad_event']}")
    stuck = [e for e in exp_list if e["status"] == "failed"]
    if stuck:
        warnings.append(f"{len(stuck)} experiment(s) failed; see failures")
    if by_status.get("failed replication"):
        warnings.append(f"{by_status['failed replication']} claim(s) failed replication")
    if not validated:
        warnings.append("no claim has passed held-out validation yet")

    return {
        "schema": SCHEMA_VERSION,
        "created_at": S.now(),
        "system": {"code_version": S.code_version(), "world": life.WORLD_VERSION,
                   "phase": "Phase 1 nucleus", "capabilities": [
                       {"area": a, "status": s, "note": n} for a, s, n in CAPABILITIES],
                   "operators": core.OPERATORS, "not_applicable_operators": core.NOT_APPLICABLE,
                   "public_limits": costs.PUBLIC_LIMITS},
        "totals": {"experiments": len(exps), "generations": n_gens, "candidates": n_cands,
                   "ledger_events": n_events, "cpu_s": round(cpu_s, 3),
                   "compute_usd_estimated": round(compute_usd, 6), "llm_usd_billed": round(llm_usd, 6),
                   "llm_calls": len(llm), "total_usd": round(total, 6),
                   "claims": len(claims), "claims_by_status": by_status, "validated_claims": validated,
                   "usd_per_validated_claim": round(total / validated, 6) if validated else None,
                   "validated_claims_per_usd": round(validated / total, 3) if total > 0 else None},
        "ledger": chain,
        "experiments": exp_list,
        "claims": [{"id": cl["label"], "experiment": S.fmt_exp(cl["experiment_id"]) if cl["experiment_id"] else None,
                    "kind": cl["kind"], "statement": cl["statement"], "status": cl["status"],
                    "history": [{"ts": h["ts"], "status": h["status"], "reason": h["reason"]} for h in cl["history"]]}
                   for cl in claims],
        "failures": {t: n for t, n in failures},
        "world": json.loads(world_last["stats"]) if world_last else None,
        "warnings": warnings,
        "missing": {
            "discovery_capability_per_10usd": "not measured: requires Phase 2 benchmark suite on unseen problems",
            "transfer": "not measured: only one World exists",
            "reality_gap": "not measured: no real-world tests",
            "version_benchmarks": "not measured: no fixed benchmark set yet",
            "novelty": "not measured",
        },
    }


def _svg_line(title, xs, ys, xlabel, ylabel, w=640, h=300):
    if not xs:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><text x="20" y="40" '
                f'font-family="sans-serif" font-size="14">{title}: no data yet</text></svg>')
    pad = 50
    x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    y0, y1 = min(0, min(ys)), max(ys) if max(ys) > min(0, min(ys)) else 1
    def px(x): return pad + (x - x0) / (x1 - x0) * (w - 2 * pad)
    def py(y): return h - pad - (y - y0) / (y1 - y0) * (h - 2 * pad)
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" font-family="sans-serif">'
            f'<rect width="100%" height="100%" fill="white"/>'
            f'<text x="{pad}" y="24" font-size="14" font-weight="bold">{title}</text>'
            f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="#888"/>'
            f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h-pad}" stroke="#888"/>'
            f'<text x="{w/2}" y="{h-12}" font-size="11" text-anchor="middle">{xlabel}</text>'
            f'<text x="14" y="{h/2}" font-size="11" transform="rotate(-90 14 {h/2})" text-anchor="middle">{ylabel}</text>'
            f'<text x="{pad-6}" y="{py(y1)+4:.0f}" font-size="10" text-anchor="end">{y1:.3g}</text>'
            f'<text x="{pad-6}" y="{py(y0)+4:.0f}" font-size="10" text-anchor="end">{y0:.3g}</text>'
            f'<polyline fill="none" stroke="#1f5c4a" stroke-width="2" points="{pts}"/></svg>')


def package(snap: dict, ledger_rows: list) -> bytes:
    md = render_md(snap)
    led = io.StringIO()
    wr = csv.writer(led)
    wr.writerow(["id", "ts", "experiment", "version", "type", "parent_id", "cost_usd", "cost_kind",
                 "payload_json", "prev_hash", "hash"])
    for r in ledger_rows:
        wr.writerow([r["id"], r["ts"], S.fmt_exp(r["experiment_id"]) if r["experiment_id"] else "", r["version"],
                     r["type"], r["parent_id"] or "", r["cost_usd"], r["cost_kind"], redact(r["payload"] or ""),
                     r["prev_hash"] or "", r["hash"]])
    bench = io.StringIO()
    wb = csv.writer(bench)
    wb.writerow(["experiment", "objective", "status", "generations", "gen0_best", "final_best",
                 "holdout_wins", "holdout_losses", "holdout_p", "holdout_relative_gain", "cpu_s",
                 "compute_usd_estimated"])
    for e in snap["experiments"]:
        h = e.get("holdout") or {}
        wb.writerow([e["id"], e["objective"], e["status"], e["generations_run"], e["gen0_best"], e["final_best"],
                     h.get("wins", ""), h.get("losses", ""), h.get("p_sign_test", ""), h.get("relative_gain", ""),
                     e["cpu_s"], e["compute_usd_estimated"]])
    # Graphs from the ledger: cumulative cost and validated claims vs cumulative cost.
    cum, xs, ys = 0.0, [], []
    vx, vy, nval = [], [], 0
    for r in ledger_rows:
        cum += r["cost_usd"] or 0.0
        xs.append(r["id"]); ys.append(cum)
        if r["type"] == "claim.status":
            p = S.loads(r["payload"], {})
            if p.get("status") in ("replicated", "robust"):
                nval += 1
                vx.append(cum); vy.append(nval)
    files = {
        "DARWIN_SNAPSHOT.md": md,
        "DARWIN_SNAPSHOT.json": redact(json.dumps(snap, indent=2, default=str)),
        "DARWIN_LEDGER_EXPORT.csv": led.getvalue(),
        "DARWIN_BENCHMARKS.csv": bench.getvalue(),
        "graphs/cumulative_cost.svg": _svg_line("Cumulative recorded cost (USD)", xs, ys, "ledger event", "USD"),
        "graphs/validated_claims_vs_cost.svg": _svg_line(
            "Validated claim transitions vs cumulative cost", vx, vy, "cumulative USD", "validated claims"),
        "README.txt": ("Darwin Snapshot package. Units: costs in USD (compute = estimated from published hosting "
                       "rates; LLM = provider-reported tokens x price table). Times in seconds. Ledger hashes are "
                       "SHA-256 over prev_hash + canonical JSON of the event (see darwin/store.py)."),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def render_md(s: dict) -> str:
    t = s["totals"]
    L = [f"# DARWIN SNAPSHOT", f"", f"Created {s['created_at']} · code {s['system']['code_version']} · "
         f"{s['system']['world']} · {s['system']['phase']}", ""]
    if s["warnings"]:
        L += ["## Warning signs", ""] + [f"- {w}" for w in s["warnings"]] + [""]
    L += ["## Totals", "",
          f"- Experiments: {t['experiments']} · generations: {t['generations']} · candidates: {t['candidates']}",
          f"- Ledger events: {t['ledger_events']} · chain verified: {s['ledger']['ok']}",
          f"- CPU: {t['cpu_s']} s · compute (estimated): ${t['compute_usd_estimated']:.6f} · "
          f"LLM (billed): ${t['llm_usd_billed']:.6f} over {t['llm_calls']} calls",
          f"- Claims: {t['claims']} · by status: {t['claims_by_status']}",
          f"- Validated claims: {t['validated_claims']} · USD per validated claim: {t['usd_per_validated_claim']}",
          "", "## Claims", ""]
    for c in s["claims"]:
        L.append(f"- **{c['id']}** [{c['status']}] {c['statement']}")
        for h in c["history"]:
            L.append(f"  - {h['ts']} → {h['status']}: {h['reason']}")
    L += ["", "## Experiments", "", "| id | objective | status | gens | gen-0 best | final best | holdout W/L (p) | CPU s |",
          "|---|---|---|---|---|---|---|---|"]
    for e in s["experiments"]:
        h = e.get("holdout") or {}
        hv = f"{h.get('wins')}/{h.get('losses')} ({h.get('p_sign_test')})" if h else "—"
        fmt = lambda v: f"{v:.3f}" if isinstance(v, (int, float)) else "—"
        L.append(f"| {e['id']} | {e['objective'] or e['kind']} | {e['status']} | {e['generations_run'] or '—'} | "
                 f"{fmt(e['gen0_best'])} | {fmt(e['final_best'])} | {hv} | {fmt(e['cpu_s'])} |")
    L += ["", "## Failures recorded", ""] + ([f"- {k}: {v}" for k, v in s["failures"].items()] or ["- none"])
    L += ["", "## Not yet measured", ""] + [f"- {k}: {v}" for k, v in s["missing"].items()]
    L += ["", "## Capability status", ""] + [f"- [{c['status']}] {c['area']}" for c in s["system"]["capabilities"]]
    return "\n".join(L) + "\n"


def compare(a: dict, b: dict) -> dict:
    """COMPARE WITH PREVIOUS SNAPSHOT (s.70). a = older, b = newer."""
    ta, tb = a["totals"], b["totals"]
    keys = ["experiments", "generations", "candidates", "ledger_events", "cpu_s", "compute_usd_estimated",
            "llm_usd_billed", "total_usd", "claims", "validated_claims", "usd_per_validated_claim"]
    delta = {}
    for k in keys:
        va, vb = ta.get(k), tb.get(k)
        delta[k] = {"before": va, "after": vb,
                    "change": (round(vb - va, 6) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None)}
    ca = {c["id"]: c["status"] for c in a["claims"]}
    cb = {c["id"]: c["status"] for c in b["claims"]}
    changed = [{"claim": k, "before": ca.get(k), "after": v} for k, v in cb.items() if ca.get(k) != v]
    fa, fb = a.get("failures", {}), b.get("failures", {})
    new_fail = {k: fb[k] - fa.get(k, 0) for k in fb if fb[k] - fa.get(k, 0)}
    return {"from": a["created_at"], "to": b["created_at"], "totals": delta, "claim_changes": changed,
            "new_failures": new_fail,
            "retractions": [c for c in changed if c["after"] in ("retracted", "contradicted", "failed replication")],
            "code_changed": a["system"]["code_version"] != b["system"]["code_version"]}
