"""MORPHOGENESIS — the process by which form and structure develop.

A lit sea floor seen from the side. Each organism grows from a single cell by following its own developmental
program, so its shape is not written anywhere: it unfolds, cell by cell, from rules.
- Growing tips (buds) add cells upward or sideways, may branch, may put out leaves, or stop, and the chances
  of each depend on how far the bud is from the root (a positional signal, like a morphogen gradient) and on
  how much light reaches it (phototropism). Stem cells hold the form up; leaf cells catch light.
- Light falls from the surface and is absorbed by every cell it passes, so tall forms shade short ones.
- An organism lives on what its leaves earn minus what every cell costs. When it has stored enough it releases
  a spore that drifts down and settles on the floor with a slightly changed program.
Selection acts only on how well a developmental program turns light into spores. The forms that result (stalks,
fans, trees, crowns, creepers) are discovered, not designed.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World, rle

GW, GH = 180, 96                # cells (the panel's proportions)
CAP_O = 260                     # organisms at once
# cell types
EMPTY, STEM, LEAF, BUD, POD = 0, 1, 2, 3, 4
# genome: three depth bands x (up, side, branch, leaf, stop) + band edges + colours + thresholds
NB = 3
G_UP, G_SIDE, G_BRANCH, G_LEAF, G_STOP = range(5)
NG = NB * 5 + 7
I_T1, I_T2, I_HUE1, I_HUE2, I_SPORE, I_PHOTO, I_WIDTH = range(NB * 5, NB * 5 + 7)
LO = np.array([0.0] * (NB * 5) + [2, 6, 0, 0, 20, 0, 0], np.float32)
HI = np.array([1.0] * (NB * 5) + [40, 80, 1, 1, 160, 1, 1], np.float32)
STEP = np.array([0.06] * (NB * 5) + [1.5, 2.5, 0.03, 0.03, 6, 0.06, 0.06], np.float32)
DIRS = [(0, -1), (-1, -1), (1, -1), (-1, 0), (1, 0)]       # up, up-left, up-right, left, right


class Morphogenesis(World):
    SLUG = "morphogenesis"
    TITLE = "Morphogenesis"
    DEFINITION = "The process by which form and structure develop"
    TAGLINE = "Every form grows from one cell by its own rules. Light decides which rules spread."
    TPS = 8.0
    STATS_EVERY = 160
    EPOCH = 3200
    LIGHT_CYCLE = 1600
    ABOUT = [
        "A lit sea floor seen from the side. Every organism here grows from a single cell, following its own developmental program, so its shape is never written down: it unfolds, cell by cell.",
        "Growing tips add cells upward or to the side, branch, put out leaves or stop. The odds of each depend on how far the tip is from the root (a positional signal, like a morphogen gradient) and on how much light reaches it.",
        "Light falls from the surface and every cell it passes takes some, so tall forms shade short ones. Leaves earn, every cell costs.",
        "An organism that has stored enough releases a spore, which drifts down and settles with a slightly changed program. The forms that spread (stalks, fans, trees, creepers) are discovered, not designed.",
    ]
    STAT_LABELS = [("organisms", "Organisms"), ("cells", "Living cells"), ("tallest", "Tallest form (cells)"),
                   ("canopy", "Canopy height (%)"), ("branching", "Branch points per form"),
                   ("leaf_share", "Leaf cells (%)"), ("lineages", "Lineages"), ("generations", "Generations"),
                   ("spores", "Spores released")]
    SERIES = [[("tallest", "Tallest form", "#e5602a"), ("mean_height", "Average height", "#f2b33d")],
              [("branching", "Branch points per form", "#a8c94a"), ("leaf_share", "Leaf share", "#3f97b5")],
              [("organisms", "Organisms", "#8fd3c8"), ("lineages", "Lineages", "#c9b6ff")]]
    DIALS = [D("light", "Light", "sun", "#f2b33d", "Dim", "Bright",
               "How much light falls from the surface. Bright water feeds tall, leafy forms; dim water rewards thrift."),
             D("mutation", "Mutation", "spark", "#e5602a", "Steady", "Restless",
               "How much each spore's growth program differs from its parent's. Restless spores try more new shapes; most fail.")]
    JOURNAL_HINT = ("These are sessile, plant-like forms on a sea floor seen from the side, growing by developmental "
                    "rules and competing for light. Describe shapes and how growth programs change.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.owner = np.zeros((GH, GW), np.int32)        # organism slot + 1
        self.ctype = np.zeros((GH, GW), np.int8)
        self.depth = np.zeros((GH, GW), np.int16)
        # the floor: a gentle rocky profile
        xs = np.arange(GW)
        prof = 5 + 2 * np.sin(xs / 17 + rng.random() * 6) + 1.5 * np.sin(xs / 7 + rng.random() * 6)
        for _ in range(4):
            c, w, h = rng.uniform(0, GW), rng.uniform(6, 16), rng.uniform(3, 11)
            prof += h * np.exp(-((xs - c) / w) ** 2)
        self.floor = (GH - np.round(prof)).astype(int)       # first rock row at each column
        self.o_alive = np.zeros(CAP_O, bool)
        self.G = np.zeros((CAP_O, NG), np.float32)
        self.oe = np.zeros(CAP_O, np.float32)
        self.oage = np.zeros(CAP_O, np.int32)
        self.olin = np.zeros(CAP_O, np.int64)
        self.ogen = np.zeros(CAP_O, np.int32)
        self.oid = np.zeros(CAP_O, np.int64)
        self.next_id = 1
        self.spores = 0
        self.lin_founder = {}
        self.next_lin = 1
        for _ in range(30):
            self._sow(self._random_genome(), None, 0)

    # ── genomes ──────────────────────────────────────────────────────────
    def _random_genome(self):
        rng = self.rng
        g = LO + (HI - LO) * rng.random(NG).astype(np.float32)
        for b in range(NB):
            g[b * 5 + G_UP] = rng.uniform(0.3, 0.8)
            g[b * 5 + G_SIDE] = rng.uniform(0.0, 0.3)
            g[b * 5 + G_BRANCH] = rng.uniform(0.0, 0.15)
            g[b * 5 + G_LEAF] = rng.uniform(0.1, 0.5)
            g[b * 5 + G_STOP] = rng.uniform(0.0, 0.1)
        g[I_T1], g[I_T2] = rng.uniform(4, 10), rng.uniform(12, 30)
        g[I_SPORE] = rng.uniform(40, 80)
        return g

    def _mutate(self, g):
        rng = self.rng
        g = g.copy()
        mm = mult(self.dial("mutation"), 2.5)
        m = rng.random(NG) < min(0.6, 0.2 * mm)
        g[m] += rng.normal(0, 1, int(m.sum())).astype(np.float32) * STEP[m] * mm
        if rng.random() < 0.02:
            k = int(rng.integers(NG))
            g[k] += rng.normal(0, 5) * STEP[k]
        g[I_HUE1] %= 1.0
        g[I_HUE2] %= 1.0
        g = np.clip(g, LO, HI)
        g[I_T2] = max(g[I_T2], g[I_T1] + 1)
        return g

    def _sow(self, g, parent_lin, gen):
        free = np.flatnonzero(~self.o_alive)
        if not len(free):
            return None
        rng = self.rng
        for _ in range(12):
            x = int(rng.integers(1, GW - 1))
            y = int(self.floor[x]) - 1
            if y > 2 and self.owner[y, x] == 0:
                break
        else:
            return None
        k = int(free[0])
        self.o_alive[k] = True
        self.G[k] = g
        self.oe[k] = 10.0
        self.oage[k] = 0
        self.ogen[k] = gen
        self.oid[k] = self.next_id
        self.next_id += 1
        lin = parent_lin
        if lin is None or self._far(g, self.lin_founder.get(lin)):
            lin = self.next_lin
            self.next_lin += 1
            self.lin_founder[lin] = g.copy()
        self.olin[k] = lin
        self.owner[y, x] = k + 1
        self.ctype[y, x] = BUD
        self.depth[y, x] = 0
        return k

    @staticmethod
    def _far(g, f):
        if f is None:
            return True
        d = np.abs(g[:NB * 5] - f[:NB * 5]).sum() + abs(g[I_HUE2] - f[I_HUE2]) * 3
        return d > 1.6

    # ── light ────────────────────────────────────────────────────────────
    def _lightfield(self, sun):
        absorb = np.where(self.ctype == LEAF, 0.45, np.where(self.ctype > 0, 0.18, 0.0)).astype(np.float32)
        trans = np.cumprod(1 - absorb, axis=0)
        above = np.vstack([np.ones((1, GW), np.float32), trans[:-1]])
        depthfade = np.linspace(1.0, 0.55, GH, dtype=np.float32)[:, None]     # water dims light with depth
        return sun * above * depthfade

    # ── one step ─────────────────────────────────────────────────────────
    def _step(self):
        rng = self.rng
        sun = (0.15 + 0.85 * self.light()) * mult(self.dial("light"), 1.7)
        if self.tick % 2:
            return
        lightf = self._lightfield(sun)
        own = self.owner
        occ = own > 0
        flat_own = own[occ] - 1
        # income and upkeep per organism
        green = (self.ctype == LEAF) | (self.ctype == BUD)
        rate = np.where(self.ctype == LEAF, 0.34, 0.15).astype(np.float32)
        earn = np.bincount((own[green] - 1), weights=lightf[green] * rate[green], minlength=CAP_O)
        cells = np.bincount(flat_own, minlength=CAP_O)
        self.oe += (earn - 0.011 * cells - 0.01).astype(np.float32)
        self.oage[self.o_alive] += 2
        # death: starvation or old age; the body decays
        dead = np.flatnonzero(self.o_alive & ((self.oe < 0) | (self.oage > 9000 + 40 * cells)))
        if len(dead):
            mask = np.isin(own, dead + 1)
            own[mask] = 0
            self.ctype[mask] = EMPTY
            self.o_alive[dead] = False
        # growth: buds act on their program
        by, bx = np.nonzero(self.ctype == BUD)
        order = rng.permutation(len(by))
        for n in order[:600]:
            y, x = int(by[n]), int(bx[n])
            k = int(own[y, x]) - 1
            if k < 0 or not self.o_alive[k]:
                continue
            g = self.G[k]
            if self.oe[k] < 0.8 or rng.random() > 0.35:
                continue
            d = int(self.depth[y, x])
            b = 0 if d < g[I_T1] else 1 if d < g[I_T2] else 2
            base = b * 5
            if rng.random() < g[base + G_STOP] * 0.3:
                self.ctype[y, x] = LEAF if rng.random() < 0.6 else STEM
                continue
            # choose a direction: up, diagonal or sideways; light pulls toward brighter cells
            pu, ps = g[base + G_UP], g[base + G_SIDE]
            weights = np.array([pu, pu * 0.5 * g[I_WIDTH] + 0.05, pu * 0.5 * g[I_WIDTH] + 0.05, ps, ps], np.float32)
            opts = []
            for j, (dx, dy) in enumerate(DIRS):
                nx, ny = x + dx, y + dy
                if 0 <= nx < GW and 1 <= ny < self.floor[nx] and own[ny, nx] == 0:
                    w = weights[j] * (1 + g[I_PHOTO] * 2 * lightf[ny, nx])
                    opts.append((w, nx, ny))
            if not opts:
                self.ctype[y, x] = LEAF
                continue
            ws = np.array([o[0] for o in opts]) + 1e-6
            pick = opts[int(rng.choice(len(opts), p=ws / ws.sum()))]
            _, nx, ny = pick
            own[ny, nx] = k + 1
            self.ctype[ny, nx] = BUD
            self.depth[ny, nx] = d + 1
            self.oe[k] -= 0.6
            # the old bud becomes stem, or a leaf; it may also branch
            self.ctype[y, x] = LEAF if rng.random() < g[base + G_LEAF] * 0.5 else STEM
            if rng.random() < g[base + G_BRANCH] * 0.5:
                self.ctype[y, x] = BUD
            # leaves sprout beside stems
            if rng.random() < g[base + G_LEAF] * 0.4:
                for dx in (-1, 1):
                    lx = x + dx
                    if 0 <= lx < GW and own[y, lx] == 0 and y < self.floor[lx] and self.oe[k] > 1:
                        own[y, lx] = k + 1
                        self.ctype[y, lx] = LEAF
                        self.depth[y, lx] = d
                        self.oe[k] -= 0.6
                        break
            if d + 1 >= 20:
                self.milestone("tall20", "A form has grown twenty cells high.")
            if d + 1 >= 50:
                self.milestone("tall50", "A form has grown fifty cells high.")
            if d + 1 >= 70:
                self.milestone("tall70", "A form has reached seventy cells: close to the surface.")
        # spores
        ready = np.flatnonzero(self.o_alive & (self.oe > self.G[:, I_SPORE]))
        for k in ready[:6]:
            self.oe[k] -= 0.6 * self.G[k, I_SPORE]
            child = self._mutate(self.G[k])
            if self._sow(child, int(self.olin[k]), int(self.ogen[k]) + 1) is not None:
                self.spores += 1
                self.milestone("first_spore", "The first spore has settled and begun to grow: form is now inherited.")
        if self.o_alive.sum() < 6:
            for _ in range(10):
                self._sow(self._random_genome(), None, 0)
            self.event("reseed", "Almost nothing was left; new spores drift in from outside.")

    # ── measurement ──────────────────────────────────────────────────────
    def _heights(self):
        own = self.owner
        ys, xs = np.nonzero(own)
        if not len(ys):
            return np.zeros(CAP_O), np.zeros(CAP_O)
        ks = own[ys, xs] - 1
        top = np.full(CAP_O, GH, np.int64)
        np.minimum.at(top, ks, ys)
        dep = np.zeros(CAP_O, np.int64)
        np.maximum.at(dep, ks, self.depth[ys, xs])
        return top, dep

    def stats(self):
        O = np.flatnonzero(self.o_alive)
        cells = int((self.owner > 0).sum())
        out = {"organisms": int(len(O)), "cells": cells, "spores": int(self.spores)}
        if len(O):
            top, dep = self._heights()
            hts = (self.floor.min() - top[O]).clip(0)
            branches = (self.ctype == BUD).sum() / len(O)
            lin = np.unique(self.olin[O])
            out.update({"tallest": int(dep[O].max()), "mean_height": round(float(dep[O].mean()), 1),
                        "canopy": int(round(100 * (GH - top[O].min()) / GH)), "branching": round(float(branches), 2),
                        "leaf_share": int(round(100 * (self.ctype == LEAF).sum() / max(1, cells))),
                        "lineages": int(len(lin)), "generations": int(self.ogen[O].max())})
        return out

    def stratum(self):
        O = np.flatnonzero(self.o_alive)
        cols = []
        if len(O):
            cells = np.bincount(self.owner[self.owner > 0] - 1, minlength=CAP_O)
            lins = {}
            for k in O:
                lins.setdefault(int(self.olin[k]), [0, k])
                lins[int(self.olin[k])][0] += int(cells[k])
            for lin, (n, k) in sorted(lins.items(), key=lambda kv: -kv[1][0])[:6]:
                cols.append([round(float(self.G[k, I_HUE2]), 3), 0.7, n])
        return {"cols": cols}

    def frame(self):
        own = self.owner
        slot = np.where(own > 0, ((own - 1) % 250) + 1, 0).astype(np.int16)
        O = np.flatnonzero(self.o_alive)
        pal = [[int(k % 250) + 1, round(float(self.G[k, I_HUE1]), 3), round(float(self.G[k, I_HUE2]), 3), int(self.olin[k])]
               for k in O]
        return {"gw": GW, "gh": GH, "types": rle(self.ctype.ravel()), "slots": rle(slot.ravel()), "palette": pal,
                "floor": self.floor.tolist()}
