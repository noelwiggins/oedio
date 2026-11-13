"""EPIGENESIS — development through successive stages of differentiation.

Sixteen wells, an embryo in each. Every embryo starts as one cell and divides in stages (1, 2, 4 ... 64 cells),
packed in a disc. Each cell carries the same small gene network (four genes that switch each other on and off) and
hears a signal from its neighbours. Between divisions the network settles, and which genes end up on decides the
cell's type: so identical genomes become different cells because of where they sit and what their neighbours say.
That is Waddington's landscape: one genome, many fates, chosen step by step.

When an embryo finishes developing it is judged on what it built: how many distinct cell types it made and how
orderly their arrangement is (types in coherent tissues rather than salt and pepper). The better embryos seed the
wells that come free, with small changes to their gene networks. Nothing describes the target body: the patterns
(rings, halves, stripes, centres) are found by the networks.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

NWELL = 16
NGENE = 4
STAGES = 7                      # 1,2,4,...,64 cells
SETTLE = 70                     # steps between divisions
MAXC = 2 ** (STAGES - 1)
GL = NGENE * NGENE + 4 * NGENE              # weights, neighbour signal, bias, pole gradient, centre gradient


def _disc(n):
    """n cell positions packed in a disc (sunflower spiral), centre first."""
    k = np.arange(n) + 0.5
    r = np.sqrt(k / n)
    th = k * math.pi * (3 - math.sqrt(5))
    return np.stack([r * np.cos(th), r * np.sin(th)], 1)


POS = {s: _disc(2 ** s) for s in range(STAGES)}
NEIGH = {}
for s in range(STAGES):
    p = POS[s]
    d = np.hypot(p[:, None, 0] - p[None, :, 0], p[:, None, 1] - p[None, :, 1])
    near = (d < 2.4 / math.sqrt(len(p)) + 1e-9) & (d > 0)
    NEIGH[s] = near.astype(np.float32) / np.maximum(1, near.sum(1, keepdims=True))


class Epigenesis(World):
    SLUG = "epigenesis"
    TITLE = "Epigenesis"
    DEFINITION = "Development through successive stages of differentiation"
    TAGLINE = "One genome, many fates: cells become different by where they sit and what their neighbours say."
    TPS = 10.0
    STATS_EVERY = 200
    EPOCH = 4000
    ABOUT = [
        "Sixteen wells, an embryo in each. Every embryo begins as one cell and divides in stages, one, two, four, up to sixty-four cells.",
        "The egg starts with two faint gradients from the mother, one from pole to pole and one from centre to edge. Each cell carries the same small gene network, four genes switching each other on and off, and listens to a signal from its neighbours. Between divisions the network settles, and the genes left on decide the cell's type, shown as its colour.",
        "So identical genomes become different cells because of where they are: Waddington's landscape, a ball rolling into one valley or another, step by step.",
        "A finished embryo is judged on what it built: how many kinds of cell, and how orderly their tissues are. Better embryos seed the wells that come free, with small changes to their networks. Rings, halves, stripes and centres are found by the networks, not drawn by anyone.",
    ]
    STAT_LABELS = [("best_types", "Most cell types in one embryo"), ("mean_types", "Cell types, average"),
                   ("best_order", "Most orderly tissue (0-1)"), ("best_score", "Best embryo score"),
                   ("embryos", "Embryos completed"), ("generations", "Generations"), ("lineages", "Lineages in the wells")]
    SERIES = [[("best_types", "Most cell types", "#e5602a"), ("mean_types", "Average types", "#f2b33d")],
              [("best_order", "Most orderly", "#a8c94a"), ("mean_order", "Average order", "#3f97b5")],
              [("best_score", "Best score", "#c9b6ff"), ("mean_score", "Average score", "#8fd3c8")]]
    DIALS = [D("signal", "Signal", "wave", "#3f97b5", "Quiet", "Loud",
               "How strongly cells hear their neighbours. Loud signals tie cells into large tissues; quiet ones leave each cell to its own network."),
             D("mutation", "Mutation", "spark", "#e5602a", "Steady", "Restless",
               "How much a new embryo's gene network differs from its parent's.")]
    JOURNAL_HINT = ("These are embryos developing in wells: speak of cells, divisions, gene networks, signals, cell types, "
                    "tissues and patterns, not of animals.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.G = (rng.normal(0, 1.2, (NWELL, GL))).astype(np.float32)
        self.stage = np.zeros(NWELL, np.int32)
        self.clock = rng.integers(0, SETTLE, NWELL).astype(np.int32)
        self.state = [rng.random((1, NGENE)).astype(np.float32) for _ in range(NWELL)]
        self.lin = np.arange(1, NWELL + 1, dtype=np.int64)
        self.gen = np.zeros(NWELL, np.int32)
        self.next_lin = NWELL + 1
        self.score = np.zeros(NWELL, np.float32)
        self.last = [None] * NWELL           # last finished embryo per well: (types, order, score)
        self.hall = []                       # recent finished embryos: score, types, order, lineage, cell types
        self.done = 0
        self.rest = np.zeros(NWELL, np.int32)   # a finished embryo is shown for a while before the well clears

    def _net(self, w, x, s):
        g = self.G[w]
        W = g[:16].reshape(4, 4)
        sw = g[16:20]
        b = g[20:24]
        pole, radial = g[24:28], g[28:32]
        p = POS[s]
        ap = p[:, 0:1]                                    # the mother's gradient from one pole to the other
        rad = np.hypot(p[:, 0:1], p[:, 1:2]) * 2 - 1      # and from the centre to the edge
        sig = (NEIGH[s] @ x[:, 0:1]) * mult(self.dial("signal"), 2.0)
        return 1.0 / (1.0 + np.exp(-(x @ W.T + sig * sw + b + ap * pole + rad * radial) * 3.0))

    def _types(self, x):
        bits = (x > 0.5).astype(np.int32)
        return bits[:, 0] + 2 * bits[:, 1] + 4 * bits[:, 2] + 8 * bits[:, 3]

    def _judge(self, w):
        x = self.state[w]
        t = self._types(x)
        kinds, counts = np.unique(t, return_counts=True)
        real = int((counts >= 3).sum())                  # a type counts if it makes at least a small tissue
        same = (NEIGH[STAGES - 1] > 0) & (t[:, None] == t[None, :])
        order = float(same.sum() / max(1, (NEIGH[STAGES - 1] > 0).sum()))
        score = real * (0.4 + order)
        return real, order, score, t

    def _step(self):
        rng = self.rng
        for w in range(NWELL):
            if self.rest[w] > 0:
                self.rest[w] -= 1
                if self.rest[w] == 0:
                    self._reseed(w)
                continue
            s = int(self.stage[w])
            x = self.state[w]
            x = 0.7 * x + 0.3 * self._net(w, x, s) + rng.normal(0, 0.01, x.shape).astype(np.float32)
            self.state[w] = x
            self.clock[w] += 1
            if self.clock[w] >= SETTLE:
                self.clock[w] = 0
                if s + 1 < STAGES:
                    # division: each cell's daughters land in the next stage's disc, inheriting its state
                    p0, p1 = POS[s], POS[s + 1]
                    nearest = np.argmin(np.hypot(p1[:, None, 0] - p0[None, :, 0], p1[:, None, 1] - p0[None, :, 1]), 1)
                    self.state[w] = x[nearest] + rng.normal(0, 0.02, (len(p1), NGENE)).astype(np.float32)
                    self.stage[w] = s + 1
                else:
                    real, order, score, t = self._judge(w)
                    self.score[w] = score
                    self.last[w] = (real, order, score)
                    self.done += 1
                    self.hall.append({"score": float(score), "types": real, "order": float(order), "lin": int(self.lin[w]),
                                      "gen": int(self.gen[w]), "cells": t.tolist()})
                    self.hall = sorted(self.hall, key=lambda h: -h["score"])[:12]
                    self.rest[w] = SETTLE
                    if real >= 3:
                        self.milestone("types3", "An embryo has made three distinct kinds of tissue.")
                    if real >= 5:
                        self.milestone("types5", "An embryo has made five kinds of tissue from one genome.")
                    if real >= 8:
                        self.milestone("types8", "An embryo has made eight kinds of tissue: a body of many parts.")
                    if order > 0.8 and real >= 3:
                        self.milestone("ordered", "An embryo has laid its cell types out in clean, coherent tissues.")

    def _reseed(self, w):
        rng = self.rng
        done = [v for v in range(NWELL) if self.last[v] is not None]
        if done:
            sc = np.array([self.last[v][2] for v in done]) ** 2 + 0.05
            pick = done[int(rng.choice(len(done), p=sc / sc.sum()))]
            # tournament with the hall of fame keeps good networks from being lost
            mm = mult(self.dial("mutation"), 2.5)
            parent = self.G[pick].copy()
            m = rng.random(GL) < min(0.6, 0.15 * mm)
            parent[m] += rng.normal(0, 0.35 * mm, int(m.sum())).astype(np.float32)
            self.G[w] = parent
            if pick != w:
                self.lin[w] = self.lin[pick]
            self.gen[w] = self.gen[pick] + 1
        self.stage[w] = 0
        self.clock[w] = 0
        self.state[w] = rng.random((1, NGENE)).astype(np.float32)

    def stats(self):
        fin = [l for l in self.last if l is not None]
        out = {"embryos": int(self.done), "generations": int(self.gen.max()), "lineages": int(len(np.unique(self.lin)))}
        if fin:
            t = np.array([f[0] for f in fin]); o = np.array([f[1] for f in fin]); sc = np.array([f[2] for f in fin])
            out.update({"best_types": int(t.max()), "mean_types": round(float(t.mean()), 2), "best_order": round(float(o.max()), 3),
                        "mean_order": round(float(o.mean()), 3), "best_score": round(float(sc.max()), 2),
                        "mean_score": round(float(sc.mean()), 2)})
        return out

    def stratum(self):
        lins, n = np.unique(self.lin, return_counts=True)
        return {"cols": [[round((int(l) * 0.618034) % 1, 3), 0.75, int(c)] for l, c in zip(lins, n)]}

    def frame(self):
        wells = []
        for w in range(NWELL):
            s = int(self.stage[w])
            t = self._types(self.state[w])
            x = self.state[w]
            wells.append({"stage": s, "types": t.tolist(), "level": np.round(x.mean(1), 2).tolist(), "lin": int(self.lin[w]),
                          "gen": int(self.gen[w]), "done": bool(self.rest[w] > 0),
                          "score": round(float(self.last[w][2]), 2) if self.last[w] else None})
        return {"w": 1200, "h": 640, "wells": wells, "positions": {str(s): np.round(POS[s], 3).tolist() for s in range(STAGES)}}
