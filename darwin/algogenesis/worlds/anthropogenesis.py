"""ANTHROPOGENESIS — the origin and development of humanity.

A continent under shifting ice ages, and small bands of people living on it. Each band forages where the land is
kind and moves when it is not. What makes them human here is culture: a band invents (a better tool, the keeping
of fire, words, images) with odds that rise with its size and its talk; it can also forget, and a small band
loses skills it can no longer keep alive. Bands that meet and trust each other share what they know; bands that
don't, fight. A band that grows big splits, and the daughter band carries its culture away with it.

So knowledge ratchets upward where people are many and connected, and slips back where they are few and alone.
Cold drives bands south unless they keep fire; warmth opens the north. Nothing is scripted: when fire, language
and art appear, and where, is decided by population, contact and climate.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
GX, GY = 60, 32
CAP = 200


class Anthropogenesis(World):
    SLUG = "anthropogenesis"
    TITLE = "Anthropogenesis"
    DEFINITION = "The origin and development of humanity"
    TAGLINE = "Bands of people under shifting ice ages: knowledge ratchets up where they are many and connected."
    TPS = 10.0
    STATS_EVERY = 200
    EPOCH = 4000
    LIGHT_CYCLE = 2000
    ABOUT = [
        "A continent under shifting ice ages, and small bands of people living on it. Each band forages where the land is kind and moves when it is not; the ice in the north comes and goes.",
        "What makes them human here is culture. A band invents (a better tool, the keeping of fire, words, images) with odds that rise with its size and its talk. It can also forget: a small band loses skills it can no longer keep alive.",
        "Bands that meet and trust each other share what they know; bands that don't, fight. A band that grows big splits, and the daughter carries its culture away. Fires show at night; painted bands wear a red mark.",
        "Knowledge ratchets up where people are many and connected and slips back where they are few and alone. When fire, language and art appear, and where, is decided by numbers, contact and climate.",
    ]
    STAT_LABELS = [("people", "People"), ("bands", "Bands"), ("tools_max", "Best tools (level)"), ("tools_mean", "Tools, average"),
                   ("fire", "Bands keeping fire (%)"), ("language", "Language, average (0-1)"), ("art", "Bands making art (%)"),
                   ("range", "Land settled (%)"), ("ice", "Land under ice (%)")]
    SERIES = [[("people", "People", "#e5602a")], [("tools_mean", "Tools, average", "#f2b33d"), ("language_x10", "Language ×10", "#c9b6ff")],
              [("fire", "Fire %", "#e58bb0"), ("art", "Art %", "#a8c94a"), ("ice", "Ice %", "#8fd3c8")]]
    DIALS = [D("climate", "Climate", "snow", "#8fd3c8", "Cold", "Warm",
               "Pushes the world toward an ice age or a warm spell. Cold squeezes bands south and makes fire precious; warmth opens the north."),
             D("bounty", "Bounty", "leaf", "#a8c94a", "Lean", "Plentiful",
               "How much the land yields. Plenty swells bands, and big bands invent; lean years break bands up and skills are lost.")]
    JOURNAL_HINT = ("These are bands of early humans: speak of bands, people, tools, fire, language, art, ice, migration, "
                    "meetings and quarrels. Do not name real places or real archaeological cultures.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        yy, xx = np.mgrid[0:GY, 0:GX].astype(np.float32)
        base = 0.55 + 0.35 * (yy / GY)                       # kinder toward the south
        for _ in range(10):
            cx, cy, r, a = rng.uniform(0, GX), rng.uniform(0, GY), rng.uniform(4, 12), rng.normal(0, 0.35)
            base += a * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))
        self.lat = (yy / GY).astype(np.float32)               # 0 north, 1 south
        self.base = np.clip(base, 0.05, 1.3).astype(np.float32)
        self.alive = np.zeros(CAP, bool)
        self.x, self.y = np.zeros(CAP, np.float32), np.zeros(CAP, np.float32)
        self.size = np.zeros(CAP, np.float32)
        self.tools, self.lang, self.art = (np.zeros(CAP, np.float32) for _ in range(3))
        self.fire = np.zeros(CAP, bool)
        self.coop = np.zeros(CAP, np.float32)
        self.lin = np.zeros(CAP, np.int64)
        self.next_lin = 1
        for _ in range(8):
            self._band(rng.uniform(400, 800), rng.uniform(450, 600), 20, 0, False, 0, 0, rng.uniform(0.3, 0.7), None)

    def _band(self, x, y, size, tools, fire, lang, art, coop, lin):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        self.alive[i] = True
        self.x[i], self.y[i], self.size[i] = np.clip(x, 5, W - 5), np.clip(y, 5, H - 5), size
        self.tools[i], self.fire[i], self.lang[i], self.art[i], self.coop[i] = tools, fire, lang, art, coop
        if lin is None:
            lin = self.next_lin
            self.next_lin += 1
        self.lin[i] = lin
        return i

    def temp(self):
        t = self.tick
        cycle = 0.55 * math.sin(2 * math.pi * t / 36000) + 0.25 * math.sin(2 * math.pi * t / 9000 + 1.0)
        return float(cycle + 0.6 * self.dial("climate"))        # -1 deep ice age .. +1 warm

    def field(self):
        temp = self.temp()
        ice_line = 0.38 - 0.32 * temp                          # how far south the ice reaches (0..1 of the map)
        ice = self.lat < ice_line
        cold = np.clip((ice_line + 0.2 - self.lat) / 0.2, 0, 1)
        prod = self.base * (1 - 0.75 * cold) * mult(self.dial("bounty"), 1.8)
        prod[ice] = 0.02
        return prod.astype(np.float32), ice, cold

    def _step(self):
        if self.tick % 2:
            return
        rng = self.rng
        A = np.flatnonzero(self.alive)
        if len(A) < 3:
            for _ in range(5):
                self._band(rng.uniform(400, 800), rng.uniform(470, 600), 18, 0, False, 0, 0, rng.uniform(0.3, 0.7), None)
            self.event("arrivals", "Humanity was down to a handful of bands. New bands wander in from the south.")
            A = np.flatnonzero(self.alive)
        prod, ice, cold = self.field()
        gx = np.clip((self.x[A] / W * GX).astype(int), 0, GX - 1)
        gy = np.clip((self.y[A] / H * GY).astype(int), 0, GY - 1)
        here = prod[gy, gx]
        crowd = np.zeros((GY, GX), np.float32)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                np.add.at(crowd, (np.clip(gy + dy, 0, GY - 1), np.clip(gx + dx, 0, GX - 1)), 1.0)
        # move toward kinder, emptier land nearby, with some wandering
        for a, i in enumerate(A):
            best, bx, by = here[a] - 0.12 * (crowd[gy[a], gx[a]] - 1), 0, 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = min(GX - 1, max(0, gx[a] + 2 * dx)), min(GY - 1, max(0, gy[a] + 2 * dy))
                v = prod[ny, nx] - 0.12 * crowd[ny, nx]
                if v > best + 0.02:
                    best, bx, by = v, dx, dy
            self.x[i] += 1.4 * bx + rng.normal(0, 1.0)
            self.y[i] += 1.4 * by + rng.normal(0, 1.0)
        self.x[A] = np.clip(self.x[A], 5, W - 5)
        self.y[A] = np.clip(self.y[A], 5, H - 5)
        # food, growth, cold
        size = self.size[A]
        chill = cold[gy, gx] * np.where(self.fire[A], 0.15, 1.0)
        # what the land can carry, raised by tools and talk (with diminishing returns), lowered by cold without fire
        K = 46 * here * (1 + 0.08 * self.tools[A]) ** 0.5 * (1 + 0.2 * self.lang[A]) * (1 - 0.7 * chill) / (1 + 0.1 * (crowd[gy, gx] - 1))
        growth = 0.006 * (1 - size / np.maximum(K, 1)) - 0.003 * chill
        self.size[A] = size * (1 + np.clip(growth, -0.05, 0.02)) + rng.normal(0, 0.15, len(A))
        # invention and loss
        for a, i in enumerate(A):
            n = float(self.size[i])
            p = 0.000035 * min(n, 60) * (1 + 2 * self.lang[i]) / (1 + 0.25 * self.tools[i])
            if rng.random() < p:
                k = rng.random()
                if k < 0.5:
                    self.tools[i] += 1
                    if self.tools[i] >= 5:
                        self.milestone("tools5", "A band has reached a fifth level of tool-making, each built on the last.")
                    for lvl in (12, 25, 50, 100, 200):
                        if self.tools[i] >= lvl:
                            self.milestone(f"tools{lvl}", f"A band's tool-making has reached level {lvl}, each level standing on the ones before.")
                elif k < 0.65 and not self.fire[i] and self.tools[i] >= 2:
                    self.fire[i] = True
                    self.milestone("fire", "A band has learned to keep fire. The cold can be faced now.")
                elif k < 0.9:
                    self.lang[i] = min(1.0, self.lang[i] + 0.035 * (1.05 - self.lang[i]))
                    if self.lang[i] >= 0.5:
                        self.milestone("language", "A band's talk has become rich enough to pass on more than it shows: language.")
                elif self.lang[i] >= 0.6 and n > 30:
                    self.art[i] += 1
                    self.milestone("art", "A band has begun to make images. Nobody needed them; they made them anyway.")
            if n < 16 and rng.random() < 0.002 * (16 - n) / 16:      # the small band forgets
                if self.tools[i] > 0:
                    self.tools[i] -= 1
                elif self.art[i] > 0:
                    self.art[i] -= 1
                if rng.random() < 0.15:
                    self.fire[i] = False
                self.lang[i] = max(0.0, self.lang[i] - 0.02)
        # meetings
        if len(A) > 1 and self.tick % 6 == 0:
            from scipy.spatial import cKDTree
            pairs = cKDTree(np.stack([self.x[A], self.y[A]], 1)).query_pairs(26.0, output_type="ndarray")
            for a, b in pairs[:30]:
                i, j = int(A[a]), int(A[b])
                if not (self.alive[i] and self.alive[j]):
                    continue
                if self.coop[i] > 0.45 and self.coop[j] > 0.45:
                    for arr in (self.tools, self.lang, self.art):
                        m = max(arr[i], arr[j])
                        arr[i] = arr[j] = m - (0.3 if arr is self.tools and rng.random() < 0.2 else 0)
                    self.fire[i] = self.fire[j] = self.fire[i] or self.fire[j]
                else:
                    loser = i if self.size[i] < self.size[j] else j
                    self.size[loser] *= 0.85
        # splitting and dying
        for i in np.flatnonzero(self.alive & (self.size > 44))[:3]:
            if self.alive.all():
                break
            self.size[i] *= 0.5
            ang = rng.uniform(0, 2 * math.pi)
            self._band(self.x[i] + 40 * math.cos(ang), self.y[i] + 30 * math.sin(ang), float(self.size[i]), float(self.tools[i]),
                       bool(self.fire[i]), float(self.lang[i]), float(self.art[i]),
                       float(np.clip(self.coop[i] + rng.normal(0, 0.08), 0, 1)), int(self.lin[i]))
        dead = np.flatnonzero(self.alive & (self.size < 3))
        self.alive[dead] = False
        if self.alive.any() and float(self.size[self.alive].sum()) > 2000:
            self.milestone("people2000", "There are now two thousand people.")

    def stats(self):
        A = np.flatnonzero(self.alive)
        prod, ice, cold = self.field()
        out = {"bands": int(len(A)), "people": int(self.size[A].sum()) if len(A) else 0, "ice": int(round(100 * float(ice.mean())))}
        if len(A):
            gx = np.clip((self.x[A] / W * GX).astype(int), 0, GX - 1)
            gy = np.clip((self.y[A] / H * GY).astype(int), 0, GY - 1)
            occ = np.zeros((GY, GX), bool)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    occ[np.clip(gy + dy, 0, GY - 1), np.clip(gx + dx, 0, GX - 1)] = True
            out.update({"tools_max": int(self.tools[A].max()), "tools_mean": round(float(self.tools[A].mean()), 2),
                        "fire": int(round(100 * float(self.fire[A].mean()))), "language": round(float(self.lang[A].mean()), 3),
                        "language_x10": round(10 * float(self.lang[A].mean()), 2), "art": int(round(100 * float((self.art[A] > 0).mean()))),
                        "range": int(round(100 * float((occ & ~ice).sum() / max(1, (~ice).sum()))))})
        return out

    def stratum(self):
        A = np.flatnonzero(self.alive)
        if not len(A):
            return {"cols": []}
        l, idx = np.unique(self.lin[A], return_inverse=True)
        n = np.bincount(idx, weights=self.size[A])
        top = np.argsort(-n)[:6]
        return {"cols": [[round((int(l[k]) * 0.618034) % 1, 3), 0.7, int(n[k])] for k in top]}

    def frame(self):
        prod, ice, cold = self.field()
        A = np.flatnonzero(self.alive)
        zone = np.where(ice, 0, np.where(cold > 0.5, 1, np.where(prod < 0.45, 2, np.where(prod < 0.8, 3, 4))))
        return {"w": W, "h": H, "gx": GX, "gy": GY, "zones": zone.astype(int).ravel().tolist(), "temp": round(self.temp(), 3),
                "bands": [[int(i), round(float(self.x[i]), 1), round(float(self.y[i]), 1), int(self.size[i]), int(self.tools[i]),
                           int(self.fire[i]), round(float(self.lang[i]), 2), int(self.art[i]), round((int(self.lin[i]) * 0.618034) % 1, 3)]
                          for i in A]}
