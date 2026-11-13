"""ANAGENESIS — evolutionary transformation within a lineage.

One population, one lineage, never splitting: every animal can mate with every other, so whatever changes, changes
for all of them together. Their surroundings drift slowly (the climate warms or cools, the vegetation shifts, the
predators change), and with it the shape that suits them best: a longer neck one age, shorter legs or heavier
armour the next. Each generation the better-suited leave a few more young, and the lineage follows its moving
target, always a little behind.

Across the top of the panel walks the lineage's own past: one ancestor for each epoch, oldest at the left, drawn
from the average of the population then. Over days the parade shows a single line becoming something else
without ever branching: anagenesis, as opposed to the splitting of one line into two.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
TRAITS = ["size", "neck", "legs", "tail", "armour", "horn", "ears", "hue"]
NT = len(TRAITS)
CAP = 180
LO = np.array([0.5, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0], np.float32)
HI = np.array([2.2, 1.6, 1.6, 1.4, 1.0, 1.0, 1.0, 1.0], np.float32)
PARADE_TOP = 150.0


class Anagenesis(World):
    SLUG = "anagenesis"
    TITLE = "Anagenesis"
    DEFINITION = "Evolutionary transformation within a lineage"
    TAGLINE = "One lineage that never splits, following a drifting world; its ancestors walk across the top."
    TPS = 10.0
    STATS_EVERY = 200
    EPOCH = 4000
    ABOUT = [
        "One population, one lineage, never splitting: every animal can mate with every other, so whatever changes, changes for all of them together.",
        "Their surroundings drift slowly, and with them the shape that suits best: a longer neck in one age, shorter legs or heavier armour in the next. Each generation the better-suited leave a few more young, and the lineage follows its moving target, always a little behind.",
        "Across the top walks the lineage's own past: one ancestor per epoch, oldest at the left, drawn from the average animal of that time.",
        "Over days the parade shows a single line becoming something else without ever branching: anagenesis, as against the splitting of one line into two.",
    ]
    STAT_LABELS = [("animals", "Animals"), ("generations", "Generations"), ("distance", "Distance from the first ancestor"),
                   ("lag", "Lag behind the best shape"), ("variation", "Variation in the population"), ("fitness", "How well suited (0-1)")]
    SERIES = [[("distance", "Distance from the first ancestor", "#e5602a"), ("lag", "Lag behind the best shape", "#3f97b5")],
              [("size", "Body size", "#f2b33d"), ("neck", "Neck", "#a8c94a"), ("armour", "Armour", "#c9b6ff")],
              [("fitness", "How well suited", "#8fd3c8"), ("variation", "Variation", "#e58bb0")]]
    DIALS = [D("change", "Change", "wave", "#3f97b5", "Slow", "Fast",
               "How quickly the surroundings drift. Fast change leaves the lineage chasing a target it cannot reach; slow change lets it settle into each shape."),
             D("pressure", "Pressure", "gauge", "#e5602a", "Gentle", "Fierce",
               "How strongly the surroundings judge. Fierce selection pulls the lineage quickly toward the best shape but wears its variation thin.")]
    JOURNAL_HINT = ("This is a single lineage changing shape over time without splitting. Speak of the lineage, its ancestors, "
                    "its body (size, neck, legs, tail, armour, horn, ears, colour), and the drifting surroundings it follows.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        start = LO + (HI - LO) * np.array([0.3, 0.2, 0.4, 0.4, 0.1, 0.1, 0.3, rng.random()], np.float32)
        self.G = np.clip(start + rng.normal(0, 0.05, (CAP, NT)), LO, HI).astype(np.float32)
        self.alive = np.ones(CAP, bool)
        self.x, self.y = rng.uniform(30, W - 30, CAP).astype(np.float32), rng.uniform(PARADE_TOP + 40, H - 30, CAP).astype(np.float32)
        self.h = rng.uniform(0, 2 * math.pi, CAP).astype(np.float32)
        self.opt = start.copy()
        self.vel = np.zeros(NT, np.float32)
        self.first = start.copy()
        self.generations = 0
        self.parade = [start.round(3).tolist()]
        self.births = 0

    def _fitness(self, G):
        sens = np.array([1.0, 1.2, 1.0, 0.8, 1.4, 1.0, 0.8, 0.6], np.float32)
        d2 = (((G - self.opt) / (HI - LO)) ** 2 * sens).sum(1)
        return np.exp(-d2 * 12 * mult(self.dial("pressure"), 2.5))

    def _step(self):
        rng = self.rng
        # the surroundings drift: a slow random walk with momentum
        spd = mult(self.dial("change"), 2.5)
        self.vel = 0.998 * self.vel + rng.normal(0, 0.0000022 * spd, NT).astype(np.float32) * (HI - LO)
        self.opt = self.opt + self.vel
        bounce = (self.opt < LO) | (self.opt > HI)
        self.vel[bounce] *= -1
        self.opt = np.clip(self.opt, LO, HI)
        # wander on the plain
        self.h += rng.normal(0, 0.15, CAP).astype(np.float32)
        sp = 0.6 * self.G[:, 2]
        self.x = np.clip(self.x + sp * np.cos(self.h), 20, W - 20)
        self.y = np.clip(self.y + sp * np.sin(self.h), PARADE_TOP + 30, H - 20)
        hit = (self.x <= 20) | (self.x >= W - 20) | (self.y <= PARADE_TOP + 30) | (self.y >= H - 20)
        self.h[hit] += math.pi
        # a turnover of individuals: the suited leave more young
        if self.tick % 6 == 0:
            f = self._fitness(self.G)
            for _ in range(3):
                die = int(rng.choice(CAP, p=(1.05 - f) / (1.05 - f).sum()))
                p = f / f.sum()
                a, b = rng.choice(CAP, 2, p=p)
                child = 0.5 * (self.G[a] + self.G[b]) + rng.normal(0, 0.012, NT).astype(np.float32) * (HI - LO)
                child[7] = (self.G[a, 7] if rng.random() < 0.5 else self.G[b, 7]) + rng.normal(0, 0.01)
                self.G[die] = np.clip(child, LO, HI)
                self.x[die], self.y[die] = self.x[a] + rng.normal(0, 5), self.y[a] + rng.normal(0, 5)
                self.births += 1
            self.generations = self.births // CAP
        if self.tick % self.EPOCH == 0:
            self.parade.append(self.G.mean(0).round(3).tolist())
            self.parade = self.parade[-400:]
        if self.tick % 400 == 0:
            dist = float(np.linalg.norm((self.G.mean(0) - self.first) / (HI - LO)))
            if dist > 0.5:
                self.milestone("changed", "The lineage has drifted far from its first ancestor: the animals walking now would not be recognised as the same kind.")
            if dist > 1.0:
                self.milestone("transformed", "The lineage has been transformed: little of the first ancestor's shape remains, and yet it never split.")

    def stats(self):
        m = self.G.mean(0)
        out = {"animals": CAP, "generations": int(self.generations),
               "distance": round(float(np.linalg.norm((m - self.first) / (HI - LO))), 3),
               "lag": round(float(np.linalg.norm((m - self.opt) / (HI - LO))), 3),
               "variation": round(float((self.G.std(0) / (HI - LO)).mean() * 10), 3),
               "fitness": round(float(self._fitness(self.G).mean()), 3)}
        for k, name in enumerate(TRAITS[:7]):
            out[name] = round(float(m[k]), 3)
        return out

    def stratum(self):
        m = self.G.mean(0)
        return {"cols": [[round(float(m[7]), 3), 0.7, 3], [0.1, 0.4 + 0.5 * float(m[4]), 2], [0.3, 0.6, 1]]}

    def frame(self):
        idx = np.arange(0, CAP, 2)            # half the herd is plenty to draw
        return {"w": W, "h": H, "top": PARADE_TOP, "traits": TRAITS,
                "animals": [[int(i), round(float(self.x[i]), 1), round(float(self.y[i]), 1), round(float(self.h[i]), 2)] +
                           np.round(self.G[i], 2).tolist() for i in idx],
                "parade": self.parade[-30:], "parade_total": len(self.parade), "optimum": np.round(self.opt, 2).tolist()}
