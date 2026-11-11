"""Runs every live Algogenesis concept world in one process, each at its own pace.

Each world is checkpointed to the database every two minutes, its latest frame is written about once a second
for its panel, and at the end of each of its epochs the naturalist writes a journal entry for it.
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
from . import chronicle
from .worlds import LIVE, world_class
from .worlds.base import from_bytes, to_bytes

LEADER_KEY = 774416
MODEL = os.environ.get("ALGO_CLOUD_MODEL", "claude-haiku-4-5")
SPEED = float(os.environ.get("GENESIS_SPEED", "1.0"))


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
    fh = open(S.db_url()[len("sqlite:///"):] + ".genesis-leader", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def _upsert_live(c, key, js):
    r = c.execute(S.algo_world_live.update().where(S.algo_world_live.c.key == key).values(ts=S.now(), data=js))
    if r.rowcount == 0:
        c.execute(S.algo_world_live.insert().values(key=key, ts=S.now(), data=js))


def load(slug):
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_worlds.c.blob).where(S.algo_worlds.c.slug == slug)).first()
    if row is not None:
        try:
            return from_bytes(row[0])
        except Exception as e:
            S.append("failure.algo_world_checkpoint", {"slug": slug, "error": repr(e)})
    seed = (int(time.time()) + hash(slug)) % (2 ** 31)
    w = world_class(slug)(seed=seed)
    S.append("algo.world_genesis", {"slug": slug, "seed": seed})
    return w


def checkpoint(w):
    blob = to_bytes(w)
    hist = json.dumps({"history": w.history[-1500:], "strata": w.strata, "events": w.events[-200:],
                       "milestones": w.milestones}, separators=(",", ":"))
    with S.engine().begin() as c:
        r = c.execute(S.algo_worlds.update().where(S.algo_worlds.c.slug == w.SLUG).values(ts=S.now(), tick=w.tick, blob=blob))
        if r.rowcount == 0:
            c.execute(S.algo_worlds.insert().values(slug=w.SLUG, ts=S.now(), tick=w.tick, blob=blob))
        _upsert_live(c, w.SLUG + ":history", hist)


def write_live(w, chron):
    d = w.live()
    d["chronicle"] = chron
    with S.engine().begin() as c:
        _upsert_live(c, w.SLUG, json.dumps(d, separators=(",", ":")))


def read_live(key):
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_world_live.c.ts, S.algo_world_live.c.data).where(S.algo_world_live.c.key == key)).first()
    if row is None:
        return None
    d = json.loads(row[1])
    d["written_at"] = row[0]
    return d


def recent_journal(slug, n=6):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.algo_world_journal.c.epoch, S.algo_world_journal.c.tick, S.algo_world_journal.c.text)
                         .where(S.algo_world_journal.c.slug == slug)
                         .order_by(S.algo_world_journal.c.id.desc()).limit(n)).all()
    return [{"epoch": r[0], "tick": r[1], "text": r[2]} for r in rows]


def _cloud_call(system, user):
    from ..openlab import _call
    r = _call(system, user, 260, "algogenesis.journal", model=MODEL, temperature=0.7)
    if r["status"] != "ok":
        raise RuntimeError(r["status"])
    return r["text"]


def _journal(w_cls, facts, slug, tick, epoch):
    text, src = chronicle.world_entry(facts, w_cls.TITLE, w_cls.DEFINITION, w_cls.JOURNAL_HINT, _cloud_call)
    with S.engine().begin() as c:
        c.execute(S.algo_world_journal.insert().values(slug=slug, ts=S.now(), tick=tick, epoch=epoch, text=text,
                                                       facts=json.dumps({**facts, "source": src}, ensure_ascii=False)))


def run():
    lock = _leader()
    if lock is None:
        print("[genesis] another process runs the concept worlds; exiting", flush=True)
        return
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    worlds = {slug: load(slug) for slug in LIVE}
    state = {}
    for slug, w in worlds.items():
        state[slug] = {"due": time.time(), "dt": 1.0 / (w.TPS * SPEED), "live": 0.0, "ck": time.time() + 20 * len(state),
                       "prev": w.history[-1] if w.history else None, "since": w.tick, "chron": recent_journal(slug),
                       "chron_read": time.time()}
        print(f"[genesis] {slug} from tick {w.tick} at {w.TPS * SPEED:g}/s", flush=True)
    while not stop["now"]:
        slug = min(state, key=lambda s: state[s]["due"])
        st, w = state[slug], worlds[slug]
        wait = st["due"] - time.time()
        if wait > 0:
            time.sleep(min(wait, 0.05))
            continue
        st["due"] = max(st["due"] + st["dt"], time.time() - 1.0)       # never try to catch up more than a second
        try:
            w.step()
        except Exception as e:
            print(f"[genesis] {slug} step failed: {e!r}", flush=True)
            S.append("failure.algo_world_step", {"slug": slug, "error": repr(e), "tick": int(w.tick)})
            st["due"] = time.time() + 5
            continue
        if w.tick % w.EPOCH == 0:
            facts = w.facts(st["prev"], st["since"])
            st["prev"], st["since"] = w.stats(), w.tick
            threading.Thread(target=_journal, args=(type(w), facts, slug, int(w.tick), int(w.epoch_no())), daemon=True).start()
        now = time.time()
        if now - st["chron_read"] > 30:
            st["chron_read"] = now
            try:
                st["chron"] = recent_journal(slug)
            except Exception:
                pass
        if now - st["live"] >= 0.9:
            st["live"] = now
            try:
                write_live(w, st["chron"])
            except Exception as e:
                print(f"[genesis] {slug} live write failed: {e!r}", flush=True)
        if now >= st["ck"]:
            st["ck"] = now + 120
            try:
                checkpoint(w)
            except Exception as e:
                print(f"[genesis] {slug} checkpoint failed: {e!r}", flush=True)
    for w in worlds.values():
        try:
            checkpoint(w)
        except Exception:
            pass
    print("[genesis] stopped; checkpoints written", flush=True)


if __name__ == "__main__":
    if (sys.argv[1] if len(sys.argv) > 1 else "run") == "run":
        run()
