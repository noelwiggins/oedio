"""Persistence for Darwin: experiments, lineage, claims, LLM calls, live-world
checkpoints, snapshots, and the append-only Ledger (Brief s.41, 50-59).

Uses Postgres when DATABASE_URL is set (Railway), otherwise a local SQLite
file. Both the Ledger and claim-status history are append-only, enforced by
database triggers, and every Ledger event carries a SHA-256 hash chained to the
previous event so tampering with history is detectable (s.59). Corrections are
new events; nothing is ever updated or deleted in those two tables.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

import sqlalchemy as sa

_engine = None
md = sa.MetaData()

T = sa.Text
J = sa.Text  # JSON stored as text: identical behaviour on SQLite and Postgres

events = sa.Table(
    "darwin_events", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("version", T),
    sa.Column("type", T, nullable=False, index=True),
    sa.Column("parent_id", sa.Integer),
    sa.Column("payload", J),
    sa.Column("cost_usd", sa.Float, default=0.0),
    sa.Column("cost_kind", T),          # billed | estimated | none
    sa.Column("provenance", J),
    sa.Column("prev_hash", T),
    sa.Column("hash", T, nullable=False),
)

experiments = sa.Table(
    "darwin_experiments", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", T, nullable=False),
    sa.Column("kind", T, nullable=False, default="evolve"),   # evolve | replay
    sa.Column("replay_of", sa.Integer),
    sa.Column("lab", T, nullable=False, default="life"),
    sa.Column("title", T),
    sa.Column("goal", T),
    sa.Column("objective", T),
    sa.Column("config", J, nullable=False),
    sa.Column("seed", sa.BigInteger, nullable=False),
    sa.Column("status", T, nullable=False, index=True),       # queued running completed stopped failed
    sa.Column("owner", sa.Boolean, default=False),
    sa.Column("requester", T),                                # salted hash of IP; never the IP
    sa.Column("budget_usd", sa.Float),
    sa.Column("max_cpu_s", sa.Float),
    sa.Column("stop_requested", sa.Boolean, default=False),
    sa.Column("started_at", T),
    sa.Column("finished_at", T),
    sa.Column("heartbeat", T),
    sa.Column("stop_reason", T),
    sa.Column("progress", J),
    sa.Column("summary", J),
    sa.Column("cost", J),
    sa.Column("code_version", T),
    sa.Column("environment", J),
    sa.Column("result_digest", T),
    sa.Column("source", T),          # visitor | owner | practice | benchmark (added in Phase 2)
)

generations = sa.Table(
    "darwin_generations", md,
    sa.Column("experiment_id", sa.Integer, primary_key=True),
    sa.Column("gen", sa.Integer, primary_key=True),
    sa.Column("stats", J),
    sa.Column("cpu_s", sa.Float),
    sa.Column("sim_steps", sa.BigInteger),
)

candidates = sa.Table(
    "darwin_candidates", md,
    sa.Column("experiment_id", sa.Integer, primary_key=True),
    sa.Column("cid", T, primary_key=True),
    sa.Column("gen", sa.Integer, index=True),
    sa.Column("island", sa.Integer),
    sa.Column("parents", J),
    sa.Column("root", T),
    sa.Column("operator", T),
    sa.Column("params", J),
    sa.Column("genome", J),
    sa.Column("fitness", sa.Float),
    sa.Column("fitness_seeds", J),
    sa.Column("selected", sa.Boolean),
)

claims = sa.Table(
    "darwin_claims", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", T, nullable=False),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("kind", T),            # optimization | discovery
    sa.Column("statement", T, nullable=False),
    sa.Column("evidence", J),
)

claim_status = sa.Table(
    "darwin_claim_status", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("claim_id", sa.Integer, index=True, nullable=False),
    sa.Column("ts", T, nullable=False),
    sa.Column("status", T, nullable=False),
    sa.Column("reason", T),
    sa.Column("event_id", sa.Integer),
)

llm_calls = sa.Table(
    "darwin_llm_calls", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("experiment_id", sa.Integer),
    sa.Column("purpose", T),
    sa.Column("provider", T),
    sa.Column("model", T),
    sa.Column("input_tokens", sa.Integer),
    sa.Column("output_tokens", sa.Integer),
    sa.Column("cache_read_tokens", sa.Integer),
    sa.Column("cache_write_tokens", sa.Integer),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("pricing", J),
    sa.Column("cost_usd", sa.Float),
    sa.Column("cost_kind", T),
    sa.Column("status", T),
)

world_checkpoints = sa.Table(
    "darwin_world_checkpoints", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("era", sa.Integer),
    sa.Column("tick", sa.BigInteger),
    sa.Column("blob", sa.LargeBinary),
)

world_stats = sa.Table(
    "darwin_world_stats", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("era", sa.Integer),
    sa.Column("tick", sa.BigInteger),
    sa.Column("stats", J),
)

snapshots = sa.Table(
    "darwin_snapshots", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", T, nullable=False),
    sa.Column("data", J),
)

# ── Phase 2: Discovery Memory, Failure Memory, benchmark ─────────────────
memory = sa.Table(
    "darwin_memory", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", T, nullable=False),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("claim_id", sa.Integer),
    sa.Column("candidate", T),
    sa.Column("world", T, nullable=False),
    sa.Column("objective", T, nullable=False),
    sa.Column("conditions", J),
    sa.Column("genome", J),
    sa.Column("train_fitness", sa.Float),
    sa.Column("validation", J),
    sa.Column("source", T),
)

memory_uses = sa.Table(
    "darwin_memory_uses", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("memory_id", sa.Integer, index=True),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("objective", T),
    sa.Column("conditions", J),
    sa.Column("distance", sa.Float),
    sa.Column("helped", sa.Boolean),
    sa.Column("detail", J),
)

failures = sa.Table(
    "darwin_failures", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("kind", T, index=True),      # no_improvement | failed_replication | adversarial_failure | failed_transfer | ...
    sa.Column("world", T),
    sa.Column("objective", T),
    sa.Column("conditions", J),
    sa.Column("genome", J),
    sa.Column("detail", J),
)

calibration = sa.Table(
    "darwin_calibration", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("created_at", T, nullable=False),
    sa.Column("suite", T, nullable=False),
    sa.Column("problem", T, nullable=False),
    sa.Column("world", T, nullable=False),
    sa.Column("r0", sa.Float),
    sa.Column("r1", sa.Float),
    sa.Column("detail", J),
)

bench_results = sa.Table(
    "darwin_bench_results", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("experiment_id", sa.Integer, index=True),
    sa.Column("day", T, index=True),
    sa.Column("split", T),
    sa.Column("suite", T),
    sa.Column("problem", T),
    sa.Column("contestant", T),
    sa.Column("replicate", sa.Integer),
    sa.Column("evaluations", sa.Integer),
    sa.Column("cpu_s", sa.Float),
    sa.Column("cost_usd", sa.Float),
    sa.Column("cost_kind", T),
    sa.Column("score", sa.Float),
    sa.Column("score_seeds", J),
    sa.Column("normalized", sa.Float),
    sa.Column("genome", J),
    sa.Column("detail", J),
    sa.Column("code_version", T),
)

memory_status = sa.Table(
    "darwin_memory_status", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("memory_id", sa.Integer, index=True, nullable=False),
    sa.Column("status", T, nullable=False),      # active | retired
    sa.Column("reason", T),
)

audits = sa.Table(
    "darwin_audits", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("kind", T, nullable=False),        # ops | code
    sa.Column("experiment_id", sa.Integer),
    sa.Column("code_version", T),
    sa.Column("summary", J),
    sa.Column("findings", J),
    sa.Column("cost_usd", sa.Float),
)

proposals = sa.Table(
    "darwin_proposals", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("audit_id", sa.Integer, index=True),
    sa.Column("title", T),
    sa.Column("severity", T),
    sa.Column("category", T),
    sa.Column("safety_relevant", sa.Boolean),
    sa.Column("detail", J),                      # explanation, edits, guard results
    sa.Column("pr_number", sa.Integer),
    sa.Column("pr_url", T),
    sa.Column("branch", T),
)

proposal_status = sa.Table(
    "darwin_proposal_status", md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("ts", T, nullable=False),
    sa.Column("proposal_id", sa.Integer, index=True, nullable=False),
    sa.Column("status", T, nullable=False),      # proposed | rejected_by_guard | pr_opened | ci_passed | ci_failed | merged | closed
    sa.Column("reason", T),
)

APPEND_ONLY = ("darwin_events", "darwin_claim_status", "darwin_memory", "darwin_memory_uses", "darwin_failures",
               "darwin_bench_results", "darwin_memory_status", "darwin_audits", "darwin_proposal_status")

# Columns added after the first deploy; created with ALTER TABLE when missing.
ADDED_COLUMNS = [("darwin_experiments", "source", "TEXT")]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def db_url() -> str:
    url = os.environ.get("DARWIN_DB_URL") or os.environ.get("DATABASE_URL") or ""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not url:
        base = "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".darwin")
        os.makedirs(base, exist_ok=True)
        url = "sqlite:///" + os.path.join(base, "darwin.sqlite")
    return url


def engine():
    global _engine
    if _engine is None:
        url = db_url()
        kw = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"timeout": 30}
        eng = sa.create_engine(url, **kw)
        init(eng)            # only cache the engine once the schema is in place
        _engine = eng
    return _engine


def is_sqlite(eng=None) -> bool:
    return (eng or engine()).dialect.name == "sqlite"


def init(eng):
    with eng.begin() as c:
        if eng.dialect.name == "postgresql":
            # web process and worker may start together; serialise schema setup
            c.exec_driver_sql("SELECT pg_advisory_xact_lock(774412)")
        md.create_all(c)
        insp = sa.inspect(c)
        for table, col, typ in ADDED_COLUMNS:
            if col not in {x["name"] for x in insp.get_columns(table)}:
                c.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        if eng.dialect.name == "sqlite":
            for t in APPEND_ONLY:
                for op in ("UPDATE", "DELETE"):
                    c.exec_driver_sql(
                        f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
                        f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;")
        elif eng.dialect.name == "postgresql":
            c.exec_driver_sql(
                "CREATE OR REPLACE FUNCTION darwin_append_only() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION USING MESSAGE = TG_TABLE_NAME || ' is append-only'; END; "
                "$$ LANGUAGE plpgsql;")  # no percent sign: the driver would read it as a placeholder
            for t in APPEND_ONLY:
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS {t}_append_only ON {t};")
                c.exec_driver_sql(
                    f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
                    f"FOR EACH ROW EXECUTE FUNCTION darwin_append_only();")


@contextlib.contextmanager
def ledger_lock(conn):
    """Serialise ledger appends across processes so the hash chain stays linear."""
    if is_sqlite():
        path = db_url()[len("sqlite:///"):] + ".lock"
        with open(path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    else:
        conn.exec_driver_sql("SELECT pg_advisory_xact_lock(774411)")
        yield


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def event_hash(prev_hash, row) -> str:
    body = {k: row.get(k) for k in ("ts", "experiment_id", "version", "type", "parent_id",
                                     "payload", "cost_usd", "cost_kind", "provenance")}
    return hashlib.sha256(((prev_hash or "") + canon(body)).encode()).hexdigest()


_code_version = None


def code_version() -> str:
    global _code_version
    if _code_version is None:
        v = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")
        if not v:
            try:
                v = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(os.path.abspath(__file__)),
                    stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            except Exception:
                v = "unknown"
        _code_version = v[:12]
    return _code_version


def append(type_: str, payload: dict | None = None, experiment_id=None, parent_id=None,
           cost_usd: float = 0.0, cost_kind: str = "none", provenance: dict | None = None,
           conn=None) -> int:
    """Append one Ledger event. Returns its id."""
    def _do(c):
        with ledger_lock(c):
            prev = c.execute(sa.select(events.c.hash).order_by(events.c.id.desc()).limit(1)).scalar()
            row = {
                "ts": now(), "experiment_id": experiment_id, "version": code_version(),
                "type": type_, "parent_id": parent_id, "payload": canon(payload or {}),
                "cost_usd": float(cost_usd or 0.0), "cost_kind": cost_kind,
                "provenance": canon(provenance or {}),
            }
            row["prev_hash"] = prev
            row["hash"] = event_hash(prev, row)
            return c.execute(events.insert().values(**row)).inserted_primary_key[0]
    if conn is not None:
        return _do(conn)
    with engine().begin() as c:
        return _do(c)


def verify_chain(limit: int | None = None) -> dict:
    """Recompute every hash in order. Returns ok flag and first bad event, if any."""
    prev = None
    n = 0
    with engine().connect() as c:
        for r in c.execute(sa.select(events).order_by(events.c.id)).mappings():
            d = dict(r)
            if d["prev_hash"] != prev or event_hash(prev, d) != d["hash"]:
                return {"ok": False, "checked": n, "bad_event": d["id"]}
            prev = d["hash"]
            n += 1
    return {"ok": True, "checked": n, "head": prev}


def add_claim(experiment_id, kind, statement, evidence, status, reason, conn=None) -> int:
    def _do(c):
        cid = c.execute(claims.insert().values(
            created_at=now(), experiment_id=experiment_id, kind=kind,
            statement=statement, evidence=canon(evidence))).inserted_primary_key[0]
        ev = append("claim.created", {"claim": fmt_claim(cid), "kind": kind, "statement": statement,
                                      "status": status}, experiment_id=experiment_id, conn=c)
        c.execute(claim_status.insert().values(claim_id=cid, ts=now(), status=status,
                                               reason=reason, event_id=ev))
        return cid
    if conn is not None:
        return _do(conn)
    with engine().begin() as c:
        return _do(c)


def set_claim_status(claim_id, status, reason, evidence=None, experiment_id=None):
    with engine().begin() as c:
        ev = append("claim.status", {"claim": fmt_claim(claim_id), "status": status, "reason": reason,
                                     "evidence": evidence or {}}, experiment_id=experiment_id, conn=c)
        c.execute(claim_status.insert().values(claim_id=claim_id, ts=now(), status=status,
                                               reason=reason, event_id=ev))


def claim_history(claim_id):
    with engine().connect() as c:
        return [dict(r) for r in c.execute(sa.select(claim_status).where(
            claim_status.c.claim_id == claim_id).order_by(claim_status.c.id)).mappings()]


def all_claims(experiment_id=None):
    q = sa.select(claims).order_by(claims.c.id.desc())
    if experiment_id is not None:
        q = q.where(claims.c.experiment_id == experiment_id)
    out = []
    with engine().connect() as c:
        rows = [dict(r) for r in c.execute(q).mappings()]
        hist = {}
        if rows:
            for h in c.execute(sa.select(claim_status).where(
                    claim_status.c.claim_id.in_([r["id"] for r in rows])).order_by(claim_status.c.id)).mappings():
                hist.setdefault(h["claim_id"], []).append(dict(h))
    for r in rows:
        r["evidence"] = json.loads(r["evidence"] or "{}")
        r["history"] = hist.get(r["id"], [])
        r["status"] = r["history"][-1]["status"] if r["history"] else "unknown"
        r["label"] = fmt_claim(r["id"])
        out.append(r)
    return out


def fmt_exp(i) -> str:
    return f"E-{int(i):06d}"


def fmt_claim(i) -> str:
    return f"C-{int(i):06d}"


def fmt_mem(i) -> str:
    return f"M-{int(i):05d}"


def fmt_snap(i) -> str:
    return f"S-{int(i):04d}"


def loads(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default
