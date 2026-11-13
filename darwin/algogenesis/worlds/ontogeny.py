"""ONTOGENY — the development of an organism from its earliest stages.

In the middle of the panel an organism develops from a single cell. The cell divides (cleavage), the cells pack
into a ball (blastula), then begin to differ: those on the surface become skin, those near the organiser (a signal
from one pole) become nerve, those far from it gut, those in between muscle. Cells of a kind cling together, so
the ball folds into layers, the body stretches along its axis, and buds of fin may grow from its sides. The
grown larva swims, then lays the eggs of the next generation.

Five siblings develop alongside it from slightly different eggs. What differs is the developmental program: the
reach of the organiser's signal, the thresholds that decide each cell's fate, how strongly division follows the
body's axis, how soon cells commit to a fate, how large the body grows. The adult that is best built to live
(balanced organs, a body that can swim) becomes the parent of the next six. So it is development that evolves:
the timing and shape of growth, not a finished body handed down.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
NEMB = 6
UNDIFF, SKIN, MUSCLE, GUT, NERVE, FIN = range(6)
STAGES = ["zygote", "cleavage", "blastula", "gastrula", "organogenesis", "larva", "adult"]
# genes: signal reach, nerve threshold, gut threshold, axis bias, division pace, adult size, commitment (cells),
#        fin propensity, fin position, adhesion, hue
GLO = np.array([20, 0.3, 0.05, 0.0, 0.5, 120, 16, 0.0, 0.2, 0.0, 0.0], np.float32)
GHI = np.array([140, 0.95, 0.5, 1.0, 2.0, 420, 160, 1.0, 0.8, 1.0, 1.0], np.float32)
GSTEP = np.array([6, 0.03, 0.03, 0.05, 0.08, 15, 8, 0.06, 0.04, 0.05, 0.03], np.float32)
R_CELL = 5.0
ADULT_LIFE = 900


class Embryo:
    def __init__(self, g, rng):
        self.g = g.astype(np.float32)
        self.pos = np.zeros((1, 2), np.float32)
        self.typ = np.zeros(1, np.int8)
        self.phase = np.zeros(1, np.float32)
        self.age = 0
        self.adult_at = None
        self.score = None
        self.parts = None
        self.axis = rng.uniform(-0.3, 0.3)

    @property
    def n(self):
        return len(self.typ)


class Ontogeny(World):
    SLUG = "ontogeny"
    TITLE = "Ontogeny"
    DEFINITION = "The development of an organism from its earliest stages"
    TAGLINE = "From one cell to a swimming larva, again and again; and the way it grows is what evolves."
    TPS = 10.0
    STATS_EVERY = 200
    EPOCH = 4000
    ABOUT = [
        "In the middle of the panel an organism develops from a single cell. The cell divides (cleavage), the cells pack into a ball (blastula), then begin to differ.",
        "Cells on the surface become skin (cream), those near the organiser, a signal from one pole, become nerve (violet), those far from it gut (gold), those between muscle (red). Cells of a kind cling together, so the ball folds into layers and stretches along its axis; buds of fin (aqua) may grow from its sides.",
        "The grown larva swims, then lays the eggs of the next generation. Five siblings develop alongside it from slightly different eggs.",
        "What differs between them is the developmental program: the reach of the organiser's signal, the thresholds that decide fates, how strongly division follows the body's axis, how soon cells commit, how big the body grows. The best-built adult parents the next six. So it is development itself that evolves.",
    ]
    STAT_LABELS = [("generation", "Generation"), ("stage", "Stage of the one in the middle"), ("cells", "Its cells"),
                   ("best_score", "Best adult so far"), ("last_score", "Last parent's score"), ("tissues", "Tissues in the last parent"),
                   ("elongation", "Body length to width"), ("commit", "Cells before fates are set")]
    SERIES = [[("last_score", "Parent's score", "#e5602a"), ("mean_score", "Siblings' average", "#f2b33d")],
              [("adult_size", "Adult size (cells)", "#3f97b5")],
              [("elongation", "Length to width", "#a8c94a"), ("fins", "Fin share ×10", "#8fd3c8")]]
    DIALS = [D("warmth", "Warmth", "flame", "#e5602a", "Cool", "Warm",
               "Warm water speeds every division; cool water slows development so each stage lingers on the panel."),
             D("mutation", "Variation", "spark", "#c9b6ff", "Faithful", "Varied",
               "How much each sibling's egg differs from its parent's. Varied eggs try bolder programs; most do worse.")]
    JOURNAL_HINT = ("This is one organism developing, generation after generation: speak of cells, divisions, the blastula, "
                    "gastrulation, tissues (skin, muscle, gut, nerve, fins), the body axis, and how the developmental "
                    "program is changing across generations.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        g = GLO + (GHI - GLO) * np.array([0.12, 0.55, 0.5, 0.6, 0.5, 0.3, 0.25, 0.35, 0.5, 0.5, rng.random()], np.float32)
        self.parent = g
        self.generation = 0
        self.best = 0.0
        self.last_score = 0.0
        self.last_parts = {}
        self.emb = [self._egg(i) for i in range(NEMB)]

    def _egg(self, i):
        g = self.parent.copy()
        if i:
            mm = mult(self.dial("mutation"), 2.5)
            m = self.rng.random(len(g)) < min(0.7, 0.35 * mm)
            g[m] += self.rng.normal(0, 1, int(m.sum())).astype(np.float32) * GSTEP[m] * mm
            g[10] %= 1.0
            g = np.clip(g, GLO, GHI)
        return Embryo(g, self.rng)

    # ── development of one embryo ────────────────────────────────────────
    def _develop(self, e):
        rng = self.rng
        g = e.g
        e.age += 1
        n = e.n
        target = int(g[5])
        if n < target and e.adult_at is None:
            e.phase += rng.random(n).astype(np.float32) * 0.01 * g[4] * mult(self.dial("warmth"), 1.8)
            ready = np.flatnonzero(e.phase >= 1.0)[: max(1, target - n)]
            if len(ready):
                ax = np.array([math.cos(e.axis), math.sin(e.axis)], np.float32)
                k = len(ready)
                rnd = rng.normal(0, 1, (k, 2)).astype(np.float32)
                rnd /= np.linalg.norm(rnd, axis=1, keepdims=True) + 1e-6
                dirs = (1 - g[3]) * rnd + g[3] * ax * np.sign(rng.normal(0, 1, (k, 1)))
                dirs /= np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-6
                new = e.pos[ready] + dirs * R_CELL * 0.8
                e.pos[ready] -= dirs * R_CELL * 0.3
                e.pos = np.vstack([e.pos, new])
                e.typ = np.concatenate([e.typ, e.typ[ready]])
                e.phase[ready] = 0
                e.phase = np.concatenate([e.phase, np.zeros(k, np.float32)])
        elif e.adult_at is None:
            e.adult_at = e.age
        # fates: once enough cells, each cell reads where it is
        if e.n >= g[6] and e.age % 4 == 0:
            self._fates(e)
        self._physics(e)

    def _fates(self, e):
        g = e.g
        p = e.pos
        c = p.mean(0)
        ax = np.array([math.cos(e.axis), math.sin(e.axis)], np.float32)
        along = (p - c) @ ax
        organiser = c + ax * along.max()
        sig = np.exp(-np.linalg.norm(p - organiser, axis=1) / g[0])
        from scipy.spatial import cKDTree
        cnt = np.array([len(x) for x in cKDTree(p).query_ball_point(p, R_CELL * 2.3)])
        surface = cnt < 6
        t = np.where(surface, SKIN, np.where(sig > g[1], NERVE, np.where(sig < g[2], GUT, MUSCLE))).astype(np.int8)
        # fin buds: surface cells at the chosen distance along the body, if the program makes fins
        if g[7] > 0.3:
            rel = (along - along.min()) / max(1e-3, np.ptp(along))
            side = np.abs((p - c) @ np.array([-ax[1], ax[0]])) / max(1e-3, np.abs((p - c) @ np.array([-ax[1], ax[0]])).max())
            fin = surface & (np.abs(rel - g[8]) < 0.08 * (0.5 + g[7])) & (side > 0.55)
            t[fin] = FIN
        e.typ = t

    def _physics(self, e):
        from scipy.spatial import cKDTree
        p = e.pos
        n = len(p)
        if n < 2:
            return
        pairs = cKDTree(p).query_pairs(R_CELL * 2.2, output_type="ndarray")
        f = np.zeros_like(p)
        if len(pairs):
            a, b = pairs[:, 0], pairs[:, 1]
            d = p[b] - p[a]
            dist = np.linalg.norm(d, axis=1) + 1e-4
            same = e.typ[a] == e.typ[b]
            rest = R_CELL * 1.6
            stick = np.where(same, 0.02 + 0.05 * e.g[9], 0.0)
            mag = np.where(dist < rest, -(rest - dist) * 0.25, stick * (dist - rest))
            fv = d / dist[:, None] * mag[:, None]
            np.add.at(f, a, fv)
            np.add.at(f, b, -fv)
        # a gentle pull to the middle keeps the body whole; fins push outward
        c = p.mean(0)
        f += (c - p) * 0.004
        fin = e.typ == FIN
        if fin.any():
            f[fin] += (p[fin] - c) * 0.01
        e.pos = p + np.clip(f, -2, 2)

    def _judge(self, e):
        t = e.typ
        n = max(1, e.n)
        fr = {k: float((t == k).sum()) / n for k in (SKIN, MUSCLE, GUT, NERVE, FIN)}
        p = e.pos - e.pos.mean(0)
        ev = np.linalg.eigvalsh(np.cov(p.T) + 1e-3 * np.eye(2))
        elong = float(math.sqrt(ev[1] / ev[0]))
        organs = (max(fr[MUSCLE], 1e-3) * max(fr[GUT], 1e-3) * max(fr[NERVE], 1e-3)) ** (1 / 3)
        swim = min(2.2, elong) / 2.2 * (0.6 + min(fr[FIN], 0.15) / 0.15 * 0.4)
        skin = min(1.0, fr[SKIN] / 0.25)
        size = min(1.0, n / 260)
        score = round(10 * organs * (0.4 + swim) * skin * (0.5 + 0.5 * size), 3)
        e.parts = {"skin": round(fr[SKIN], 3), "muscle": round(fr[MUSCLE], 3), "gut": round(fr[GUT], 3),
                   "nerve": round(fr[NERVE], 3), "fin": round(fr[FIN], 3), "elongation": round(elong, 2), "cells": n}
        return score

    def _step(self):
        for e in self.emb:
            self._develop(e)
        # when all are grown and have lived a while as adults, the best lays the next eggs
        if all(e.adult_at is not None for e in self.emb):
            main = self.emb[0]
            if main.age - main.adult_at > ADULT_LIFE:
                scores = [self._judge(e) for e in self.emb]
                for e, s in zip(self.emb, scores):
                    e.score = s
                k = int(np.argmax(scores))
                best = self.emb[k]
                self.parent = best.g.copy()
                self.last_score = float(scores[k])
                self.mean_score = float(np.mean(scores))
                self.last_parts = best.parts
                self.best = max(self.best, self.last_score)
                self.generation += 1
                self.milestone("first_gen", "The first larva has grown, swum and laid the eggs of the next generation.")
                kinds = sum(1 for v in best.parts.values() if isinstance(v, float) and v > 0.05) if best.parts else 0
                if best.parts and best.parts.get("fin", 0) > 0.04:
                    self.milestone("fins", "A larva has grown fins from its sides.")
                if best.parts and best.parts.get("elongation", 0) > 1.8:
                    self.milestone("long", "A larva has grown long along its axis: a body built to swim.")
                if kinds >= 5:
                    self.milestone("five", "A larva has grown all five tissues: skin, muscle, gut, nerve and fin.")
                self.emb = [self._egg(i) for i in range(NEMB)]

    def stage(self, e):
        n = e.n
        if n == 1:
            return 0
        if n < 16:
            return 1
        if n < e.g[6]:
            return 2
        if e.adult_at is None:
            return 3 if n < 0.6 * e.g[5] else 4
        return 5 if e.age - e.adult_at < ADULT_LIFE * 0.4 else 6

    def stats(self):
        main = self.emb[0]
        return {"generation": int(self.generation), "stage": STAGES[self.stage(main)], "cells": int(main.n),
                "best_score": round(self.best, 3), "last_score": round(self.last_score, 3),
                "mean_score": round(getattr(self, "mean_score", 0.0), 3),
                "tissues": ", ".join(f"{k} {int(v * 100)}%" for k, v in self.last_parts.items() if isinstance(v, float) and k != "elongation" and v > 0.01) or "—",
                "elongation": self.last_parts.get("elongation", 0), "fins": round(10 * self.last_parts.get("fin", 0), 2),
                "adult_size": int(self.parent[5]), "commit": int(self.parent[6])}

    def stratum(self):
        cols = []
        hue = float(self.parent[10])
        for k, w in self.last_parts.items():
            if k in ("skin", "muscle", "gut", "nerve", "fin") and w > 0:
                cols.append([{"skin": 0.12, "muscle": 0.02, "gut": 0.13, "nerve": 0.75, "fin": 0.5}[k], 0.7, int(w * 100) + 1])
        return {"cols": cols or [[hue, 0.5, 1]]}

    def frame(self):
        out = []
        for i, e in enumerate(self.emb):
            out.append({"cells": np.round(e.pos, 1).ravel().tolist(), "types": e.typ.astype(int).tolist(), "stage": self.stage(e),
                        "axis": round(float(e.axis), 3), "score": e.score, "hue": round(float(e.g[10]), 3)})
        return {"w": W, "h": H, "embryos": out, "stages": STAGES, "generation": int(self.generation)}
