"""NOOGENESIS — the emergence or evolution of mind.

A dark field. Food blooms travel slowly round fixed orbits and blink: lit for a while, then dark. While a bloom is
dark nothing can see it, only remember where it was and guess where it has gone. Each forager carries a small
recurrent brain (up to ten neurons that feed back into themselves, so they can hold a trace of the past). Neurons
cost food to keep, so a brain grows only when what it remembers pays for itself.

Foragers can also make light. Others see it. A light that means "food is here" helps relatives and also attracts
rivals; whether signalling evolves, and what it comes to mean, is up to the foragers.

What is measured is mind in the plainest sense: how many neurons are kept, how much they use their own past, and
how often a meal is found in the dark, which only memory or prediction can do.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 680.0
CAP = 150
NI, NH, NO = 8, 10, 3         # inputs, hidden (max), outputs: turn, speed, glow
NBLOOM = 9


class Noogenesis(World):
    SLUG = "noogenesis"
    TITLE = "Noogenesis"
    DEFINITION = "Emergence or evolution of mind and consciousness"
    TAGLINE = "Food that hides in the dark rewards anything that can remember where it went."
    TPS = 14.0
    STATS_EVERY = 280
    EPOCH = 5600
    ABOUT = [
        "A dark field. Food blooms travel slowly round fixed orbits and blink: lit for a while, then dark. While a bloom is dark nothing can see it; it can only be remembered.",
        "Each forager carries a small brain of up to ten neurons that feed back into themselves, so they can hold a trace of the past. Its lit dots are the neurons it keeps. Neurons cost food, so a brain grows only when what it remembers pays.",
        "Foragers can also make light, and others see it. A signal that says 'food here' helps relatives and also draws rivals. Whether signalling evolves, and what it comes to mean, is up to them.",
        "Mind is measured in the plainest way: how many neurons are kept, how much they use their own past, and how often a meal is found in the dark, which only memory or prediction can do.",
    ]
    STAT_LABELS = [("foragers", "Foragers"), ("neurons", "Neurons per brain"), ("memory", "Use of memory (0-1)"),
                   ("dark_meals", "Meals found in the dark (%)"), ("signalling", "Foragers signalling (%)"),
                   ("meals", "Meals so far"), ("generations", "Generations"), ("lineages", "Lineages")]
    SERIES = [[("neurons", "Neurons per brain", "#c9b6ff"), ("memory_x10", "Use of memory ×10", "#8fd3c8")],
              [("dark_meals", "Meals in the dark %", "#f2b33d"), ("signalling", "Signalling %", "#e5602a")],
              [("foragers", "Foragers", "#a8c94a"), ("lineages", "Lineages", "#3f97b5")]]
    DIALS = [D("dark", "Darkness", "eye", "#c9b6ff", "Brief", "Long",
               "How long the blooms stay dark. Long darkness makes memory pay; brief darkness lets simple chasers do well."),
             D("food", "Food", "drop", "#f2b33d", "Meagre", "Rich",
               "How much each bloom holds. Rich blooms feed even careless foragers; meagre ones reward the clever.")]
    JOURNAL_HINT = ("These are foragers with small evolving brains in a dark field. Speak of neurons, memory, prediction, "
                    "signals and meals found in the dark; do not claim they are conscious.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.alive = np.zeros(CAP, bool)
        self.x, self.y, self.h = (np.zeros(CAP, np.float32) for _ in range(3))
        self.e = np.zeros(CAP, np.float32)
        self.age = np.zeros(CAP, np.int32)
        self.hid = np.zeros((CAP, NH), np.float32)
        self.Win = np.zeros((CAP, NH, NI), np.float32)
        self.Wh = np.zeros((CAP, NH, NH), np.float32)
        self.Wout = np.zeros((CAP, NO, NH), np.float32)
        self.bout = np.zeros((CAP, NO), np.float32)
        self.mask = np.zeros((CAP, NH), bool)
        self.glow = np.zeros(CAP, np.float32)
        self.lin = np.zeros(CAP, np.int64)
        self.gen = np.zeros(CAP, np.int32)
        self.next_lin = 1
        self.meals = self.dark_meals = 0
        self.recent = []                 # (lit) per meal, recent window
        # blooms: centre, radius, phase speed, blink period and duty
        self.bc = np.stack([rng.uniform(220, W - 220, NBLOOM), rng.uniform(150, H - 150, NBLOOM)], 1).astype(np.float32)
        self.br = rng.uniform(70, 160, NBLOOM).astype(np.float32)
        self.bw = (rng.uniform(0.0015, 0.004, NBLOOM) * rng.choice([-1, 1], NBLOOM)).astype(np.float32)
        self.bph = rng.uniform(0, 2 * math.pi, NBLOOM).astype(np.float32)
        self.bper = rng.integers(500, 900, NBLOOM)
        self.boff = rng.integers(0, 900, NBLOOM)
        self.bfood = np.full(NBLOOM, 30.0, np.float32)
        for _ in range(70):
            self._spawn(None)

    def _spawn(self, parent):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        rng = self.rng
        if parent is None:
            self.Win[i] = rng.normal(0, 0.8, (NH, NI))
            self.Wh[i] = rng.normal(0, 0.3, (NH, NH))
            self.Wout[i] = rng.normal(0, 0.8, (NO, NH))
            self.bout[i] = rng.normal(0, 0.3, NO)
            self.mask[i] = rng.random(NH) < 0.25
            self.x[i], self.y[i] = rng.uniform(20, W - 20), rng.uniform(20, H - 20)
            self.lin[i] = self.next_lin
            self.next_lin += 1
            self.gen[i] = 0
            self.e[i] = 30
        else:
            p = parent
            mm = 1.0
            for arr in (self.Win, self.Wh, self.Wout):
                arr[i] = arr[p] + rng.normal(0, 0.12 * mm, arr[p].shape) * (rng.random(arr[p].shape) < 0.15)
            self.bout[i] = self.bout[p] + rng.normal(0, 0.1, NO)
            self.mask[i] = self.mask[p]
            if rng.random() < 0.06:                       # a neuron gained or lost
                k = int(rng.integers(NH))
                self.mask[i, k] = not self.mask[i, k]
            self.x[i], self.y[i] = self.x[p] + rng.normal(0, 6), self.y[p] + rng.normal(0, 6)
            self.lin[i], self.gen[i] = self.lin[p], self.gen[p] + 1
            self.e[i] = 0.45 * self.e[p]
            self.e[p] *= 0.5
        self.alive[i] = True
        self.h[i] = rng.uniform(0, 2 * math.pi)
        self.age[i] = 0
        self.hid[i] = 0
        self.glow[i] = 0
        return i

    def _blooms(self):
        t = self.tick
        ang = self.bph + self.bw * t
        pos = self.bc + np.stack([np.cos(ang), np.sin(ang)], 1) * self.br[:, None]
        dark_frac = float(np.clip(0.45 * mult(self.dial("dark"), 1.7), 0.1, 0.85))
        lit = ((t + self.boff) % self.bper) < self.bper * (1 - dark_frac)
        return pos, lit

    def _step(self):
        rng = self.rng
        A = np.flatnonzero(self.alive)
        if len(A) < 8:
            for _ in range(20):
                self._spawn(None)
            self.event("reseed", "Few foragers were left; newcomers wander in.")
            A = np.flatnonzero(self.alive)
        bpos, lit = self._blooms()
        self.bfood = np.minimum(self.bfood + 0.13 * mult(self.dial("food"), 2.0), 40 * mult(self.dial("food"), 1.6))
        x, y, h = self.x[A], self.y[A], self.h[A]
        n = len(A)
        # senses: the nearest lit bloom, the nearest glowing forager
        dx = bpos[None, :, 0] - x[:, None]
        dy = bpos[None, :, 1] - y[:, None]
        dist = np.hypot(dx, dy)
        seen = np.where(lit[None, :] & (self.bfood[None, :] > 1), dist, np.inf)
        j = seen.argmin(1)
        has = np.isfinite(seen[np.arange(n), j]) & (seen[np.arange(n), j] < 320)
        rel = np.arctan2(dy[np.arange(n), j], dx[np.arange(n), j]) - h
        g = self.glow[A]
        gx = x[None, :] - x[:, None]
        gy = y[None, :] - y[:, None]
        gd = np.hypot(gx, gy) + np.eye(n) * 1e6
        gw = np.where(g[None, :] > 0.5, gd, np.inf)
        k = gw.argmin(1)
        hs = np.isfinite(gw[np.arange(n), k]) & (gw[np.arange(n), k] < 260)
        srel = np.arctan2(gy[np.arange(n), k], gx[np.arange(n), k]) - h
        inp = np.stack([np.where(has, np.sin(rel), 0), np.where(has, np.cos(rel), 0),
                        np.where(has, 1 - seen[np.arange(n), j] / 320, 0),
                        np.where(hs, np.sin(srel), 0), np.where(hs, np.cos(srel), 0), hs.astype(np.float32),
                        np.clip(self.e[A] / 60, 0, 1), np.ones(n)], 1).astype(np.float32)
        m = self.mask[A].astype(np.float32)
        hid = np.tanh(np.einsum("nhi,ni->nh", self.Win[A], inp) + np.einsum("nhk,nk->nh", self.Wh[A], self.hid[A] * m)) * m
        self.hid[A] = hid
        out = np.tanh(np.einsum("noh,nh->no", self.Wout[A], hid) + self.bout[A])
        # with no neurons, a forager still drifts toward what it sees (a reflex)
        reflex = np.where(has, np.clip(np.sin(rel), -1, 1) * 0.25, 0)
        h = h + 0.3 * out[:, 0] + reflex + rng.normal(0, 0.05, n)
        sp = 1.1 + 1.0 * out[:, 1]
        self.x[A] = np.clip(x + sp * np.cos(h), 5, W - 5)
        self.y[A] = np.clip(y + sp * np.sin(h), 5, H - 5)
        edge = (self.x[A] <= 5) | (self.x[A] >= W - 5) | (self.y[A] <= 5) | (self.y[A] >= H - 5)
        h = np.where(edge, h + math.pi, h)
        self.h[A] = h % (2 * math.pi)
        self.glow[A] = (out[:, 2] > 0.3).astype(np.float32)
        neurons = m.sum(1)
        self.e[A] -= 0.04 + 0.006 * neurons + 0.03 * self.glow[A] + 0.01 * np.abs(sp)
        self.age[A] += 1
        # meals: anyone on a bloom eats, lit or not
        d2 = np.hypot(bpos[None, :, 0] - self.x[A][:, None], bpos[None, :, 1] - self.y[A][:, None])
        at = d2.argmin(1)
        on = d2[np.arange(n), at] < 22
        for a in np.flatnonzero(on):
            b = int(at[a])
            if self.bfood[b] < 1:
                continue
            take = min(2.0, float(self.bfood[b]))
            self.bfood[b] -= take
            i = int(A[a])
            self.e[i] = min(self.e[i] + 4.0 * take, 90)
            self.meals += 1
            if not lit[b]:
                self.dark_meals += 1
            self.recent.append(0 if lit[b] else 1)
        self.recent = self.recent[-600:]
        if self.recent and len(self.recent) >= 300 and sum(self.recent) / len(self.recent) > 0.2:
            self.milestone("dark20", "One meal in five is now found in the dark: foragers are going where blooms will be, not where they are seen.")
        if self.recent and len(self.recent) >= 300 and sum(self.recent) / len(self.recent) > 0.35:
            self.milestone("dark35", "More than a third of meals are found in the dark. Memory is paying for itself.")
        # deaths and births
        dead = A[(self.e[A] <= 0) | (self.age[A] > 6000)]
        self.alive[dead] = False
        for i in np.flatnonzero(self.alive & (self.e > 52))[:4]:
            if self._spawn(int(i)) is None:
                break
        if self.tick % 500 == 0:
            A = np.flatnonzero(self.alive)
            if len(A):
                nm = float(self.mask[A].sum(1).mean())
                if nm >= 4:
                    self.milestone("brain4", "Foragers now keep four neurons on average.")
                if nm >= 7:
                    self.milestone("brain7", "Foragers now keep seven neurons on average: brains are paying their way.")
                if float(self.glow[A].mean()) > 0.3:
                    self.milestone("signal", "Nearly a third of the foragers are making light at any moment: signalling has caught on.")

    def stats(self):
        A = np.flatnonzero(self.alive)
        out = {"foragers": int(len(A)), "meals": int(self.meals)}
        if len(A):
            m = self.mask[A]
            wh = np.abs(self.Wh[A]) * m[:, :, None] * m[:, None, :]
            mem = float(np.clip(wh.sum((1, 2)) / np.maximum(1, m.sum(1) ** 2) / 1.0, 0, 1).mean())
            out.update({"neurons": round(float(m.sum(1).mean()), 2), "memory": round(mem, 3), "memory_x10": round(10 * mem, 2),
                        "dark_meals": int(round(100 * sum(self.recent) / max(1, len(self.recent)))),
                        "signalling": int(round(100 * float(self.glow[A].mean()))), "generations": int(self.gen[A].max()),
                        "lineages": int(len(np.unique(self.lin[A])))})
        return out

    def stratum(self):
        A = np.flatnonzero(self.alive)
        if not len(A):
            return {"cols": []}
        l, n = np.unique(self.lin[A], return_counts=True)
        top = np.argsort(-n)[:6]
        return {"cols": [[round((int(l[k]) * 0.618034) % 1, 3), 0.7, int(n[k])] for k in top]}

    def frame(self):
        A = np.flatnonzero(self.alive)
        bpos, lit = self._blooms()
        return {"w": W, "h": H,
                "foragers": [[int(i), round(float(self.x[i]), 1), round(float(self.y[i]), 1), round(float(self.h[i]), 2),
                              int(self.mask[i].sum()), int(self.glow[i] > 0.5), round((int(self.lin[i]) * 0.618034) % 1, 3)]
                             for i in A],
                "blooms": [[round(float(bpos[b, 0]), 1), round(float(bpos[b, 1]), 1), int(lit[b]), round(float(self.bfood[b]), 1),
                            round(float(self.bc[b, 0]), 1), round(float(self.bc[b, 1]), 1), round(float(self.br[b]), 1)]
                           for b in range(NBLOOM)]}
