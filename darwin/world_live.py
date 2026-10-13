"""DARWIN WORLD: the shared, open-ended terrarium on the Darwin homepage.

One world, run server-side by the same simulator the experiments use, with
reproduction and inheritance switched on. It advances while someone is
watching (up to TPS ticks per wall-clock second), so every visitor sees the
same population. Frames are sampled every FRAME_EVERY ticks and the browser
interpolates between them; nothing on screen is invented by the client.

The environment changes slowly by itself: the food mix cycles with a long
"season", so the population's diet is under shifting selection. Population
statistics are logged every STATS_EVERY ticks; the full state is checkpointed
so a redeploy resumes the same world instead of silently starting a new one.
Extinctions are recorded in the Ledger and the world is re-seeded as a new era.
"""
from __future__ import annotations

import io
import json
import math
import threading
import time

import numpy as np
import sqlalchemy as sa

from . import life, store

S = store
SLOTS = 220
START_POP = 50
FOOD = 200
HAZARDS = 4
TPS = 10
FRAME_EVERY = 2
MAX_CATCHUP = 40          # ticks simulated per request at most
STATS_EVERY = 50
CHECKPOINT_EVERY = 1000
SEASON_TICKS = 4000

_lock = threading.Lock()
_state = None


def _conditions(tick: int) -> life.Conditions:
    green = 0.5 + 0.3 * math.sin(2 * math.pi * tick / SEASON_TICKS)
    return life.Conditions(food=FOOD, green_share=round(green, 4), scarcity=1.0, hazards=HAZARDS,
                           hazard_drift=0.25, reproduction=True, mutation_sigma=0.05)


class World:
    def __init__(self, era: int, seed: int):
        self.era, self.seed = era, seed
        rng = np.random.default_rng(seed)
        self.sim = life.LifeSim(rng, 1, SLOTS, _conditions(0))
        self.sim.track_events = True
        self.depth = {}           # uid -> generation depth (0 = founder)
        uids = self.sim.place(0, life.random_genomes(rng, START_POP))
        for u in uids:
            self.depth[u] = 0
        self.sim.events.clear()
        self.frames = []          # ring of recent frames
        self.last_wall = time.time()
        self.births = 0
        self.deaths = 0
        self.resumed_from = None

    # ── persistence ───────────────────────────────────────────────────
    def to_blob(self) -> bytes:
        s = self.sim
        buf = io.BytesIO()
        np.savez_compressed(buf, px=s.px, py=s.py, hvx=s.hvx, hvy=s.hvy, energy=s.energy, alive=s.alive,
                            age=s.age, genome=s.genome, uid=s.uid, fx=s.fx, fy=s.fy, ftype=s.ftype,
                            favail=s.favail, fregrow=s.fregrow, hx=s.hx, hy=s.hy, hzx=s.hzx, hzy=s.hzy)
        meta = {"era": self.era, "seed": self.seed, "tick": s.tick, "next_uid": s.next_uid,
                "rng": s.rng.bit_generator.state, "births": self.births, "deaths": self.deaths,
                "depth": {str(k): v for k, v in self.depth.items() if k in set(s.uid[s.alive].tolist())}}
        return json.dumps(meta).encode() + b"\n--NPZ--\n" + buf.getvalue()

    @classmethod
    def from_blob(cls, blob: bytes) -> "World":
        head, npz = blob.split(b"\n--NPZ--\n", 1)
        meta = json.loads(head)
        w = cls.__new__(cls)
        w.era, w.seed = meta["era"], meta["seed"]
        rng = np.random.default_rng()
        rng.bit_generator.state = meta["rng"]
        w.sim = life.LifeSim(rng, 1, SLOTS, _conditions(meta["tick"]))
        arr = np.load(io.BytesIO(npz))
        for k in arr.files:
            setattr(w.sim, k, arr[k])
        w.sim.tick, w.sim.next_uid = meta["tick"], meta["next_uid"]
        w.sim.track_events = True
        w.depth = {int(k): v for k, v in meta["depth"].items()}
        w.frames, w.last_wall = [], time.time()
        w.births, w.deaths = meta["births"], meta["deaths"]
        w.resumed_from = meta["tick"]
        return w

    # ── stepping ──────────────────────────────────────────────────────
    def step(self, n: int):
        s = self.sim
        for _ in range(n):
            if s.tick % 100 == 0:
                s.set_conditions(_conditions(s.tick))
            s.step()
            for kind, _w, uid, parent in s.events:
                if kind == "birth":
                    self.births += 1
                    self.depth[uid] = self.depth.get(parent, 0) + 1 if parent is not None else 0
                else:
                    self.deaths += 1
                    self.depth.pop(uid, None)
            s.events.clear()
            if s.tick % FRAME_EVERY == 0:
                self.frames.append(self.frame())
                if len(self.frames) > 60:
                    self.frames = self.frames[-60:]
            if s.tick % STATS_EVERY == 0:
                _log_stats(self)
            if s.tick % CHECKPOINT_EVERY == 0:
                _checkpoint(self)
            if not s.alive.any():
                return "extinct"
        return None

    def frame(self) -> dict:
        s = self.sim
        a = s.alive[0]
        g = s.genome[0][a]
        return {
            "t": int(s.tick),
            "c": np.stack([s.uid[0][a], np.round(s.px[0][a] * 10), np.round(s.py[0][a] * 10),
                           np.round(g[:, 2] * 10), np.round(g[:, 3] * 100),
                           np.round(np.clip(s.energy[0][a], 0, 999))], 1).astype(int).tolist(),
        }

    def scene(self) -> dict:
        s = self.sim
        fa = s.favail[0]
        return {
            "food": np.stack([np.round(s.fx[0][fa] * 10), np.round(s.fy[0][fa] * 10), s.ftype[0][fa]], 1)
            .astype(int).tolist(),
            "hazards": np.stack([np.round(s.hx[0] * 10), np.round(s.hy[0] * 10)], 1).astype(int).tolist(),
            "hazard_radius": life.HAZARD_RADIUS,
        }

    def stats(self) -> dict:
        s = self.sim
        a = s.alive[0]
        n = int(a.sum())
        out = {"era": self.era, "tick": int(s.tick), "population": n, "births": self.births,
               "deaths": self.deaths, "green_share": s.cond.green_share}
        if n:
            g = s.genome[0][a]
            out["mean_genome"] = life.genome_dict(g.mean(0))
            out["std_genome"] = life.genome_dict(g.std(0))
            depths = [self.depth.get(int(u), 0) for u in s.uid[0][a]]
            out["max_generation"] = int(max(depths))
            out["mean_generation"] = round(float(np.mean(depths)), 2)
            pref = g[:, 3]
            out["diet_green_specialists"] = round(float((pref > 0.7).mean()), 3)
            out["diet_amber_specialists"] = round(float((pref < 0.3).mean()), 3)
            out["diet_generalists"] = round(float(((pref >= 0.3) & (pref <= 0.7)).mean()), 3)
            # Clustering: observed mean nearest-neighbour distance relative to what
            # the same number of uniformly random points would give (Clark-Evans R).
            # R < 1 means grouping, R > 1 means spacing out. Measured, not assumed.
            if n >= 5:
                x, y = s.px[0][a], s.py[0][a]
                d = np.sqrt((x[:, None] - x[None, :]) ** 2 + (y[:, None] - y[None, :]) ** 2)
                np.fill_diagonal(d, np.inf)
                expected = 0.5 / math.sqrt(n / (life.ARENA ** 2))
                out["clark_evans_R"] = round(float(d.min(1).mean() / expected), 3)
        return out


def _log_stats(w: World):
    try:
        with S.engine().begin() as c:
            c.execute(S.world_stats.insert().values(ts=S.now(), era=w.era, tick=w.sim.tick,
                                                    stats=S.canon(w.stats())))
    except Exception as e:
        print(f"[darwin] world stats write failed: {e}")


def _checkpoint(w: World):
    try:
        with S.engine().begin() as c:
            c.execute(S.world_checkpoints.insert().values(ts=S.now(), era=w.era, tick=w.sim.tick,
                                                          blob=w.to_blob()))
            # keep the latest few checkpoints; older ones are superseded state, not evidence
            old = c.execute(sa.select(S.world_checkpoints.c.id).order_by(
                S.world_checkpoints.c.id.desc()).offset(5)).scalars().all()
            if old:
                c.execute(S.world_checkpoints.delete().where(S.world_checkpoints.c.id.in_(old)))
    except Exception as e:
        print(f"[darwin] world checkpoint failed: {e}")


def _genesis(era: int) -> World:
    seed = int(time.time() * 1000) % (2 ** 31)
    w = World(era, seed)
    S.append("world.genesis", {"era": era, "seed": seed, "world_version": life.WORLD_VERSION,
                               "founders": START_POP, "slots": SLOTS, "food": FOOD, "hazards": HAZARDS})
    return w


def get() -> World:
    global _state
    if _state is None:
        with S.engine().connect() as c:
            row = c.execute(sa.select(S.world_checkpoints).order_by(
                S.world_checkpoints.c.id.desc()).limit(1)).mappings().first()
        if row is not None:
            try:
                _state = World.from_blob(row["blob"])
                S.append("world.resumed", {"era": _state.era, "tick": _state.sim.tick})
            except Exception as e:
                print(f"[darwin] checkpoint unreadable, starting a new era: {e}")
                S.append("failure.world_checkpoint", {"error": repr(e)})
        if _state is None:
            _state = _genesis(1)
    return _state


def advance_and_frames(since: int) -> dict:
    """Advance the world in step with wall-clock time, return frames newer than `since`."""
    global _state
    with _lock:
        w = get()
        nowt = time.time()
        due = min(int((nowt - w.last_wall) * TPS), MAX_CATCHUP)
        if due > 0:
            w.last_wall = nowt if due < MAX_CATCHUP else nowt  # don't bank unwatched time
            if w.step(due) == "extinct":
                S.append("world.extinction", {"era": w.era, "tick": w.sim.tick, "births": w.births,
                                              "deaths": w.deaths})
                _state = _genesis(w.era + 1)
                w = _state
        frames = [f for f in w.frames if f["t"] > since]
        return {"frames": frames, "scene": w.scene(), "stats": w.stats(), "tps": TPS,
                "frame_every": FRAME_EVERY, "arena": life.ARENA, "resumed_from": w.resumed_from}


def history(limit=400):
    with S.engine().connect() as c:
        rows = c.execute(sa.select(S.world_stats).order_by(S.world_stats.c.id.desc()).limit(limit)).mappings().all()
    return [{"tick": r["tick"], "era": r["era"], "ts": r["ts"], **json.loads(r["stats"])} for r in reversed(rows)]
