"""BIOGENESIS — life arising from preexisting life.

A dish of cells. Three nutrients seep in from three sides and spread through the water. Every cell feeds on the
mix its genes prefer (a specialist takes more of one, a generalist a little of all), grows, and divides in two;
each daughter inherits its parent's genes, with small changes. Cells crowd, push and starve.

No cell ever appears from nothing: every cell on the panel descends from another by division. If the dish ever
empties, it is reinoculated from a frozen stock of its own past lineages, never from scratch. Above the dish the
tree of life is drawn as it grows: each line a lineage, branching where one became two, ending where it died out.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
DISH_TOP = 170.0              # the tree is drawn above this line
GX, GY = 60, 24
CAP = 700


class Biogenesis(World):
    SLUG = "biogenesis"
    TITLE = "Biogenesis"
    DEFINITION = "Life arising from preexisting life"
    TAGLINE = "Every cell comes from a cell. Above the dish, the tree of life draws itself."
    TPS = 12.0
    STATS_EVERY = 240
    EPOCH = 4800
    ABOUT = [
        "A dish of cells. Three nutrients seep in from three sides and spread through the water: the dish's tints show where each is rich.",
        "Each cell feeds on the mix its genes prefer: a specialist takes more of one nutrient, a generalist a little of each. It grows and divides in two, and each daughter inherits its genes with small changes.",
        "No cell ever appears from nothing: every cell descends from another by division. If the dish should empty, it is reinoculated from a frozen stock of its own past, never from scratch.",
        "Above the dish the tree of life draws itself: each line a lineage, branching where one became two, ending where it died out.",
    ]
    STAT_LABELS = [("cells", "Cells"), ("lineages", "Living lineages"), ("branches", "Branchings so far"),
                   ("extinct", "Lineages extinct"), ("specialists", "Specialists (%)"), ("divisions", "Divisions so far"),
                   ("depth", "Deepest ancestry (divisions)")]
    SERIES = [[("cells", "Cells", "#a8c94a")], [("lineages", "Living lineages", "#e5602a"), ("extinct_recent", "Lost this epoch", "#3f97b5")],
              [("specialists", "Specialists %", "#f2b33d")]]
    DIALS = [D("food", "Nutrients", "drop", "#a8c94a", "Starved", "Rich",
               "How fast nutrients seep into the dish. Rich water crowds the dish with cells; starvation thins it to the efficient few."),
             D("warmth", "Warmth", "flame", "#e5602a", "Cold", "Warm",
               "Warmth speeds every cell's life, and its copying slips more often: faster change, more new lineages, more losses.")]
    JOURNAL_HINT = ("These are single cells dividing in a dish. Speak of cells, divisions, lineages, nutrients, branching "
                    "and extinction, and of descent: every cell from a cell.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.N = np.zeros((3, GY, GX), np.float32)
        self.alive = np.zeros(CAP, bool)
        self.x, self.y, self.m = (np.zeros(CAP, np.float32) for _ in range(3))
        self.aff = np.zeros((CAP, 3), np.float32)
        self.div = np.zeros(CAP, np.float32)
        self.hue = np.zeros(CAP, np.float32)
        self.sp = np.zeros(CAP, np.int64)
        self.depth = np.zeros(CAP, np.int64)
        self.tree = {}                  # sid -> {"parent", "born", "died", "hue", "g", "lane"}
        self.next_sid = 1
        self.divisions = 0
        self.extinct = 0
        self.extinct_recent = 0
        self.stock = []
        for _ in range(6):
            a = rng.random(3).astype(np.float32)
            a /= a.sum()
            sid = self._new_sp(None, a, rng.random())
            for _ in range(5):
                self._spawn(rng.uniform(300, 900), rng.uniform(DISH_TOP + 120, H - 120), a, 6.0, rng.uniform(10, 14), sid, 0)

    def _new_sp(self, parent, aff, hue):
        sid = self.next_sid
        self.next_sid += 1
        lane = (self.tree[parent]["lane"] + self.rng.normal(0, 0.06)) if parent in self.tree else self.rng.random()
        self.tree[sid] = {"parent": parent, "born": int(self.tick), "died": None, "hue": float(hue) % 1, "g": aff.copy(),
                          "lane": float(np.clip(lane, 0.02, 0.98))}
        if parent is not None:
            self.milestone("branch", "A lineage has split in two: the first branch on the tree of life.")
        return sid

    def _spawn(self, x, y, aff, m, div, sid, depth):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        self.alive[i] = True
        self.x[i], self.y[i], self.m[i] = np.clip(x, 8, W - 8), np.clip(y, DISH_TOP + 8, H - 8), m
        self.aff[i], self.div[i] = aff, div
        self.hue[i] = self.tree[sid]["hue"]
        self.sp[i], self.depth[i] = sid, depth
        return i

    def _step(self):
        rng = self.rng
        food = mult(self.dial("food"), 2.0)
        warm = mult(self.dial("warmth"), 1.6)
        # nutrients seep in from the left, the right and the floor, and spread
        if self.tick % 2 == 0:
            N = self.N
            N[0, :, :3] += 0.06 * food
            N[1, :, -3:] += 0.06 * food
            N[2, -3:, :] += 0.035 * food
            for k in range(3):
                n = N[k]
                N[k] = n + 0.2 * (np.roll(n, 1, 0) + np.roll(n, -1, 0) + np.roll(n, 1, 1) + np.roll(n, -1, 1) - 4 * n)
                N[k, 0, :] = N[k, 1, :]
            np.minimum(N, 4.0, out=N)
            N *= 0.999
        A = np.flatnonzero(self.alive)
        if len(A) == 0:
            self._reinoculate()
            return
        gx = np.clip((self.x[A] / W * GX).astype(int), 0, GX - 1)
        gy = np.clip(((self.y[A] - DISH_TOP) / (H - DISH_TOP) * GY).astype(int), 0, GY - 1)
        local = self.N[:, gy, gx].T                                  # n x 3
        eff = self.aff[A] ** 1.6                                     # specialists draw harder on one source
        take = np.minimum(local * eff * 0.05 * warm, local * 0.5)
        for k in range(3):
            np.subtract.at(self.N[k], (gy, gx), take[:, k])
        self.m[A] += take.sum(1) * 2.2 - 0.004 * self.m[A] * warm
        # jostle: cells push apart, and drift a little
        self.x[A] += rng.normal(0, 0.35, len(A))
        self.y[A] += rng.normal(0, 0.35, len(A))
        if self.tick % 2 == 0 and len(A) > 1:
            from scipy.spatial import cKDTree
            pos = np.stack([self.x[A], self.y[A]], 1)
            r = 2.2 * np.sqrt(np.maximum(self.m[A], 0.5))
            pairs = cKDTree(pos).query_pairs(18.0, output_type="ndarray")
            if len(pairs):
                a, b = pairs[:, 0], pairs[:, 1]
                dx, dy = pos[b, 0] - pos[a, 0], pos[b, 1] - pos[a, 1]
                d = np.hypot(dx, dy) + 1e-3
                over = np.maximum(0, r[a] + r[b] - d)
                f = 0.25 * over / d
                np.add.at(self.x, A[a], -f * dx); np.add.at(self.y, A[a], -f * dy)
                np.add.at(self.x, A[b], f * dx); np.add.at(self.y, A[b], f * dy)
        self.x[A] = np.clip(self.x[A], 8, W - 8)
        self.y[A] = np.clip(self.y[A], DISH_TOP + 8, H - 8)
        # deaths
        dead = A[(self.m[A] < 1.0) | (rng.random(len(A)) < 0.00025 * warm)]
        self.alive[dead] = False
        # divisions
        for i in A[self.m[A] >= self.div[A]][:12]:
            if not self.alive[i]:
                continue
            i = int(i)
            mm = mult(self.dial("warmth"), 2.0)
            half = float(self.m[i]) / 2
            self.m[i] = half
            aff = self.aff[i] + self.rng.normal(0, 0.03 * mm, 3).astype(np.float32)
            aff = np.clip(aff, 0.01, None); aff /= aff.sum()
            div = float(np.clip(self.div[i] + self.rng.normal(0, 0.3 * mm), 6, 30))
            sid = int(self.sp[i])
            if np.abs(aff - self.tree[sid]["g"]).sum() > 0.32:          # far enough from its founder: a new branch
                sid = self._new_sp(sid, aff, self.tree[sid]["hue"] + self.rng.normal(0, 0.08))
            ang = self.rng.uniform(0, 2 * math.pi)
            k = self._spawn(self.x[i] + 4 * math.cos(ang), self.y[i] + 4 * math.sin(ang), aff, half, div, sid,
                            int(self.depth[i]) + 1)
            if k is None:
                self.m[i] = half * 2
                break
            self.depth[i] += 1
            self.divisions += 1
            if self.divisions == 1:
                self.milestone("first_div", "A cell has divided: the first of a line of descent that will never be broken.")
        if self.tick % 60 == 0:
            self._census()

    def _census(self):
        live = set(np.unique(self.sp[self.alive]).tolist())
        for sid, t in self.tree.items():
            if t["died"] is None and sid not in live and self.tick - t["born"] > 60:
                t["died"] = int(self.tick)
                self.extinct += 1
                self.extinct_recent += 1
        # keep the frozen stock: one founder genome per lineage alive now
        if self.tick % 1200 == 0 and live:
            self.stock = [(sid, self.tree[sid]["g"].copy()) for sid in list(live)[:12]]
        # prune the tree of long-dead twigs with no living descendants, so it stays readable
        if len(self.tree) > 500:
            keep = set(live)
            for sid in list(live):
                p = self.tree[sid]["parent"]
                while p is not None and p not in keep:
                    keep.add(p)
                    p = self.tree[p]["parent"]
            cutoff = self.tick - 40 * self.EPOCH
            self.tree = {s: t for s, t in self.tree.items() if s in keep or (t["died"] or 0) > cutoff}

    def _reinoculate(self):
        rng = self.rng
        stock = self.stock or [(None, np.array([1 / 3] * 3, np.float32))]
        for sid, g in stock:
            nsid = self._new_sp(sid if sid in self.tree else None, g, rng.random())
            for _ in range(4):
                self._spawn(rng.uniform(300, 900), rng.uniform(DISH_TOP + 100, H - 100), g, 6.0, 12.0, nsid, 0)
        self.event("reinoculation", "The dish emptied. It was seeded again from its own frozen stock: life from life, never from nothing.")

    def stats(self):
        A = np.flatnonzero(self.alive)
        out = {"cells": int(len(A)), "branches": int(sum(1 for t in self.tree.values() if t["parent"] is not None)),
               "extinct": int(self.extinct), "extinct_recent": int(self.extinct_recent), "divisions": int(self.divisions)}
        if len(A):
            out.update({"lineages": int(len(np.unique(self.sp[A]))), "specialists": int(round(100 * float((self.aff[A].max(1) > 0.7).mean()))),
                        "depth": int(self.depth[A].max())})
        return out

    def stratum(self):
        self.extinct_recent = 0
        A = np.flatnonzero(self.alive)
        if not len(A):
            return {"cols": []}
        s, n = np.unique(self.sp[A], return_counts=True)
        top = np.argsort(-n)[:6]
        return {"cols": [[round(self.tree[int(s[k])]["hue"], 3), 0.75, int(n[k])] for k in top]}

    def frame(self):
        A = np.flatnonzero(self.alive)
        tmin = max(0, self.tick - 60 * self.EPOCH)
        live = set(np.unique(self.sp[A]).tolist())
        tree = [[sid, t["parent"] or 0, max(t["born"], tmin), t["died"] if t["died"] else -1, round(t["hue"], 3), round(t["lane"], 3),
                 int(sid in live)] for sid, t in self.tree.items() if (t["died"] or self.tick) >= tmin]
        return {"w": W, "h": H, "top": DISH_TOP, "tick": int(self.tick), "tmin": int(tmin),
                "cells": [[round(float(self.x[i]), 1), round(float(self.y[i]), 1), round(float(self.m[i]), 1), round(float(self.hue[i]), 3),
                           round(float(self.aff[i].max()), 2)] for i in A],
                "field": np.round(np.clip(self.N, 0, 4) * 2.4).astype(int).ravel().tolist(), "gx": GX, "gy": GY, "tree": tree[-400:]}
