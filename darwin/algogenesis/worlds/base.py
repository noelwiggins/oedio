"""What every Algogenesis concept world shares: a clock, events, milestones, measurements, a fossil record.

A world subclass sets the class attributes and implements _step(), frame(), stats() and stratum().
Worlds depend only on numpy and scipy, so each can run in the cloud or on a computer behind its own panel.
"""
from __future__ import annotations

import pickle
import zlib

import numpy as np

from ..dials import DialsMixin


class World(DialsMixin):
    SLUG = ""
    TITLE = ""
    DEFINITION = ""
    TAGLINE = ""
    TPS = 10.0                 # steps per second when live
    STATS_EVERY = 300
    EPOCH = 6000               # a fossil layer and a journal entry
    LIGHT_CYCLE = 0            # ticks per day; 0 = no day and night
    ABOUT: list[str] = []      # paragraphs for the "how it works" card
    STAT_LABELS: list[tuple[str, str]] = []      # (key, label) for the "now" card and the page metrics
    SERIES: list[list[tuple[str, str, str]]] = []  # charts: [(key, label, colour), ...] per chart
    JOURNAL_HINT = ""          # what the naturalist should watch for in this world
    # the dark side (Algolysis): every world's own dissolution, and what it returns to genesis
    LYSIS_NAME = ""            # its reverse, from "Genesis and its reversals": Cosmophthora, Epilysis, ...
    LYSIS_ABOUT: list[str] = []  # paragraphs for the dark side's card
    GSL_SCALE = (1.0, 1.0)     # how sensitive the genesis and lysis needles are, per world

    def __init__(self, seed: int = 1, name: str = ""):
        self.seed, self.name = seed, name or self.TITLE
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.events, self.strata, self.history = [], [], []
        self.milestones = {}
        self.last_stats = None
        self.version = self.SLUG + "-1"

    # ── the clock ────────────────────────────────────────────────────────
    def light(self):
        if not self.LIGHT_CYCLE:
            return 1.0
        import math
        return float(np.clip(0.5 + 0.75 * math.sin(2 * math.pi * self.tick / self.LIGHT_CYCLE), 0, 1))

    def step(self):
        self.tick += 1
        self.ease_dials()
        self._step()
        out = None
        if self.tick % self.STATS_EVERY == 0:
            self.last_stats = self.stats()
            self._update_gsl()
            if getattr(self, "gsl", None) is not None:
                self.last_stats["gsl"] = list(self.gsl)
            self.last_stats["tick"] = int(self.tick)
            self.history.append(self.last_stats)
            self.history = self.history[-2000:]
            out = self.last_stats
        if self.tick % self.EPOCH == 0:
            layer = self.stratum()
            layer["tick"] = int(self.tick)
            self.strata.append(layer)
            self.strata = self.strata[-1500:]
        return out

    def _step(self):
        raise NotImplementedError

    # ── genesis · stasis · lysis ─────────────────────────────────────────
    def lysis_counts(self):
        """(made so far, broken down so far, material returned so far, how many are alive now) — or None."""
        return None

    def _update_gsl(self):
        import math
        c = self.lysis_counts()
        if c is None:
            return
        born, died, ret, n = c
        prev = getattr(self, "_gsl_prev", None)
        self._gsl_prev = (born, died, ret, self.tick)
        if prev is None or self.tick <= prev[3]:
            return
        span = (self.tick - prev[3]) / max(1, self.EPOCH / 10)          # per tenth of an epoch
        n = max(1.0, float(n))
        b, d, r = (born - prev[0]) / n / span, (died - prev[1]) / n / span, (ret - prev[2]) / n / span
        # each needle reads against this world's own usual pace: half-way is "as usual"
        typ = getattr(self, "_gsl_typ", None) or [max(b, 1e-6), max(d + r, 1e-6)]
        typ = [0.97 * typ[0] + 0.03 * max(b, 1e-9), 0.97 * typ[1] + 0.03 * max(d + r, 1e-9)]
        self._gsl_typ = typ
        gb, ld = b / max(typ[0], 1e-9), (d + r) / max(typ[1], 1e-9)
        g, l = 1 - math.exp(-0.69 * gb), 1 - math.exp(-0.69 * ld)
        st = math.exp(-0.35 * (gb + ld))
        old = getattr(self, "gsl", None) or [g, st, l]
        self.gsl = [round(0.7 * o + 0.3 * v, 4) for o, v in zip(old, (g, st, l))]

    # ── record keeping ───────────────────────────────────────────────────
    def event(self, kind, text):
        self.events.append({"tick": int(self.tick), "kind": kind, "text": text})
        self.events = self.events[-300:]

    def milestone(self, key, text):
        if key in self.milestones:
            return False
        self.milestones[key] = int(self.tick)
        self.event("milestone", text)
        return True

    def epoch_no(self):
        return self.tick // self.EPOCH

    # ── what the panel needs ─────────────────────────────────────────────
    def frame(self) -> dict:
        raise NotImplementedError

    def stats(self) -> dict:
        raise NotImplementedError

    def stratum(self) -> dict:
        """One fossil layer: {"cols": [[hue, sat, weight], ...]} drawn top to bottom in the tray window."""
        raise NotImplementedError

    def live(self) -> dict:
        d = self.frame()
        d.update({"slug": self.SLUG, "tick": int(self.tick), "epoch": int(self.epoch_no()), "light": round(self.light(), 3),
                  "stats": self.last_stats or self.stats(), "events": self.events[-12:], "strata": self.strata[-240:],
                  "milestones": self.milestones, "name": self.name, "tps": self.TPS, "dials": self.dials_payload(),
                  "gsl": list(getattr(self, "gsl", None) or [])})
        return d

    @classmethod
    def meta(cls) -> dict:
        return {"slug": cls.SLUG, "title": cls.TITLE, "definition": cls.DEFINITION, "tagline": cls.TAGLINE,
                "about": cls.ABOUT, "stat_labels": cls.STAT_LABELS, "series": cls.SERIES, "tps": cls.TPS,
                "epoch": cls.EPOCH, "light_cycle": cls.LIGHT_CYCLE, "dials": cls.DIALS,
                "lysis_name": cls.LYSIS_NAME, "lysis_about": cls.LYSIS_ABOUT}

    def facts(self, prev: dict | None, since_tick: int) -> dict:
        s = self.stats()
        change = {k: [prev.get(k), v] for k, v in s.items() if prev and isinstance(v, (int, float)) and k in prev}
        return {"world": self.TITLE, "definition": self.DEFINITION, "epoch": int(self.epoch_no()), "tick": int(self.tick),
                "now": s, "change_since_last_epoch": change,
                "events": [e["text"] for e in self.events if e["tick"] > since_tick][-10:],
                "milestones_so_far": len(self.milestones),
                "dials_now": {k: v[0] for k, v in self.dials_payload().items() if abs(v[0]) > 0.05}}


def to_bytes(w: World) -> bytes:
    return zlib.compress(pickle.dumps(w, protocol=4), 6)


def from_bytes(b: bytes) -> World:
    return pickle.loads(zlib.decompress(b))


def rle(a: np.ndarray) -> list[int]:
    """Run-length code a flat integer array as [value, run, value, run, ...] (the panel decodes it)."""
    a = np.asarray(a).ravel()
    if not len(a):
        return []
    edges = np.flatnonzero(np.diff(a)) + 1
    starts = np.concatenate([[0], edges])
    runs = np.diff(np.concatenate([starts, [len(a)]]))
    out = np.empty(2 * len(starts), np.int64)
    out[0::2], out[1::2] = a[starts], runs
    return out.tolist()
