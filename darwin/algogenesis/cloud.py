"""Algogenesis in the cloud: runs the world inside Oedio's server as its own process.

Started by the web app (web.ensure_algo); an advisory lock keeps it to one copy. The world is checkpointed to
the database every minute, the latest frame is written twice a second for the panel, and at the end of every
epoch the naturalist writes a journal entry.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time

import sqlalchemy as sa

from .. import store as S
from . import chronicle, controls, engine as E

TPS = float(os.environ.get("ALGO_TPS", "20"))
LEADER_KEY = 774415
MODEL = os.environ.get("ALGO_CLOUD_MODEL", "claude-haiku-4-5")


def _leader():
    eng = S.engine()
    if eng.dialect.name == "postgresql":
        conn = eng.connect()
        ok = bool(conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({LEADER_KEY})").scalar())
        conn.commit()
        if not ok:
            conn.close()
            return None
        return conn
    import fcntl
    fh = open(S.db_url()[len("sqlite:///"):] + ".algo-leader", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def load_or_create() -> E.World:
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_checkpoints).order_by(S.algo_checkpoints.c.id.desc()).limit(1)).mappings().first()
    if row is not None:
        try:
            return E.from_bytes(row["blob"])
        except Exception as e:
            S.append("failure.algo_checkpoint", {"error": repr(e)})
    seed = int(time.time()) % (2 ** 31)
    w = E.World(seed=seed, name="Panel I")
    S.append("algo.genesis", {"seed": seed, "version": E.VERSION, "name": w.name})
    add_entry(w, "genesis", "The first day. Ten small kinds of animal, pale and slow, drift in the shallows of a "
                            "new coast, and scattered flowers open on the shore above them. Nothing here has been "
                            "designed; whatever comes next will have to evolve.", {"seed": seed})
    return w


def checkpoint(w: E.World):
    blob = E.to_bytes(w)
    with S.engine().begin() as c:
        c.execute(S.algo_checkpoints.insert().values(ts=S.now(), tick=w.tick, blob=blob))
        old = c.execute(sa.select(S.algo_checkpoints.c.id).order_by(S.algo_checkpoints.c.id.desc()).offset(3)).scalars().all()
        if old:
            c.execute(S.algo_checkpoints.delete().where(S.algo_checkpoints.c.id.in_(old)))
        hist = json.dumps({"history": w.history[-1500:], "strata": w.strata, "events": w.events[-200:]},
                          separators=(",", ":"))
        r = c.execute(S.algo_live.update().where(S.algo_live.c.id == 2).values(ts=S.now(), data=hist))
        if r.rowcount == 0:
            c.execute(S.algo_live.insert().values(id=2, ts=S.now(), data=hist))


def live_payload(w: E.World, chron=None) -> dict:
    d = w.frame()
    d.update({"stats": w.last_stats or w.stats(), "events": w.events[-12:], "strata": w.strata[-240:],
              "name": w.name, "version": w.version, "tps": TPS})
    if chron is not None:
        d["chronicle"] = chron
    return d


def write_live(w: E.World, chron):
    js = json.dumps(live_payload(w, chron), separators=(",", ":"))
    with S.engine().begin() as c:
        r = c.execute(S.algo_live.update().where(S.algo_live.c.id == 1).values(ts=S.now(), data=js))
        if r.rowcount == 0:
            c.execute(S.algo_live.insert().values(id=1, ts=S.now(), data=js))


def read_live():
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_live.c.ts, S.algo_live.c.data).where(S.algo_live.c.id == 1)).first()
    if row is None:
        return None
    d = json.loads(row[1])
    d["written_at"] = row[0]
    return d


def add_entry(w, kind, text, facts):
    with S.engine().begin() as c:
        c.execute(S.algo_chronicle.insert().values(ts=S.now(), tick=int(w.tick), day=float(w.day()), kind=kind,
                                                   text=text, facts=json.dumps(facts, ensure_ascii=False)))


def recent_chronicle(n=6):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.algo_chronicle.c.day, S.algo_chronicle.c.kind, S.algo_chronicle.c.text)
                         .order_by(S.algo_chronicle.c.id.desc()).limit(n)).all()
    return [{"day": r[0], "kind": r[1], "text": r[2]} for r in rows]


def _cloud_call(system, user):
    from ..openlab import _call
    r = _call(system, user, 260, "algogenesis.chronicle", model=MODEL, temperature=0.7)
    if r["status"] != "ok":
        raise RuntimeError(r["status"])
    return r["text"]


def _chronicle_epoch(w_snapshot_facts, tick, day):
    text, src = chronicle.write_entry(w_snapshot_facts, _cloud_call)
    with S.engine().begin() as c:
        c.execute(S.algo_chronicle.insert().values(ts=S.now(), tick=tick, day=day, kind="epoch", text=text,
                                                   facts=json.dumps({**w_snapshot_facts, "source": src}, ensure_ascii=False)))


def run():
    lock = _leader()
    if lock is None:
        print("[algo] another process holds the world; exiting", flush=True)
        return
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    w = load_or_create()
    print(f"[algo] {w.name} running from tick {w.tick} at up to {TPS:g} ticks/s", flush=True)
    last_live = last_ck = last_chron_read = 0.0
    chron = recent_chronicle()
    prev_stats, since = (w.history[-1] if w.history else None), w.tick
    budget = 1.0 / TPS
    ctl, ctl_read = controls.Applier("coast"), 0.0
    while not stop["now"]:
        t0 = time.time()
        w.step()
        if w.tick % E.EPOCH == 0:
            facts = chronicle.facts_for_epoch(w, prev_stats, since)
            prev_stats, since = w.stats(), w.tick
            threading.Thread(target=_chronicle_epoch, args=(facts, int(w.tick), float(w.day())), daemon=True).start()
        now = time.time()
        if now - last_chron_read > 20:
            last_chron_read = now
            try:
                chron = recent_chronicle()
            except Exception:
                pass
        if now - ctl_read > 2.5:
            ctl_read = now
            ctl.apply(w)
        if now - last_live >= 0.5:
            last_live = now
            try:
                write_live(w, chron)
            except Exception as e:
                print(f"[algo] live write failed: {e!r}", flush=True)
        if now - last_ck >= 60:
            last_ck = now
            try:
                checkpoint(w)
            except Exception as e:
                print(f"[algo] checkpoint failed: {e!r}", flush=True)
        rest = budget - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)
    checkpoint(w)
    print(f"[algo] stopped at tick {w.tick}; checkpoint written", flush=True)


def read_history():
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_live.c.data).where(S.algo_live.c.id == 2)).first()
    return json.loads(row[0]) if row else {"history": []}


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "run") == "run":
        run()
