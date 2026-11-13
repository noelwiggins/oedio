"""PALINGENESIS — rebirth, regeneration, recreation.

A forest that burns and comes back. Lightning strikes now and then; fire runs through the trees it can reach and
leaves ash. The ash is the richest ground there is, and life returns to it: from seeds waiting in the soil, from
trees at the edge reaching in, from cones that only open in fire. The forest after a fire is never the forest
that burned: it is reborn from whatever survived and whatever was waiting.

Trees carry heritable traits, and each is paid for: thick bark resists fire but slows growth; cones that open
only in fire fill the ash with their seed but cost every year; far-flung seed reaches new ground but thins at
home. Big fires favour different trees than small ones, so the forest's character changes with its fire history.
"""
from __future__ import annotations

import numpy as np

from ..dials import D, mult
from .base import World, rle

GW, GH = 180, 96
SOIL, ASH, TREE, FIRE = 0, 1, 2, 3
CAP_SP = 6000
NBR = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class Palingenesis(World):
    SLUG = "palingenesis"
    TITLE = "Palingenesis"
    DEFINITION = "Rebirth, regeneration, or recreation"
    TAGLINE = "A forest that burns and comes back, never as the forest that burned."
    TPS = 8.0
    STATS_EVERY = 160
    EPOCH = 3200
    ABOUT = [
        "A forest that burns and comes back. Lightning strikes now and then; fire runs through every tree it can reach and leaves ash.",
        "Ash is the richest ground there is, and life returns to it: from seeds waiting in the soil, from trees at the edge reaching in, and from cones that open only in fire.",
        "Trees carry heritable traits, each with a price. Thick bark resists fire but slows growth; cones that open in fire fill the ash with their seed but cost every year; far-flung seed reaches new ground but thins at home.",
        "Big fires favour different trees than small ones, so the forest's character follows its history of fire. Each rebirth is from whatever survived and whatever was waiting.",
    ]
    STAT_LABELS = [("cover", "Forest cover (%)"), ("ash", "Ash (%)"), ("burning", "Trees burning now"), ("fires", "Fires so far"),
                   ("largest", "Largest fire (trees)"), ("species", "Kinds of tree"), ("bark", "Bark thickness, average"),
                   ("cones", "Fire-opened cones, average"), ("seed_bank", "Seeds waiting in the soil")]
    SERIES = [[("cover", "Forest cover %", "#6b8f2a"), ("ash", "Ash %", "#9aa3aa")],
              [("bark", "Bark", "#b9560c"), ("cones", "Fire cones", "#e5602a"), ("reach", "Seed reach", "#3f97b5")],
              [("species", "Kinds of tree", "#a8c94a")]]
    DIALS = [D("lightning", "Lightning", "bolt", "#f2b33d", "Rare", "Frequent",
               "How often lightning strikes. Frequent fire favours thick bark and fire-opened cones; rare fire lets fast growers crowd in until the big one comes."),
             D("rain", "Rain", "drop", "#3f97b5", "Drought", "Wet",
               "Wet years speed regrowth and slow the spread of fire; drought does the opposite.")]
    JOURNAL_HINT = ("This is a forest shaped by fire: speak of fires, ash, regrowth, seeds waiting in the soil, bark, cones that "
                    "open in fire, and how the forest that returns differs from the one that burned.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.state = np.zeros((GH, GW), np.int8)
        self.sp = np.zeros((GH, GW), np.int32)
        self.burn = np.zeros((GH, GW), np.int8)
        self.seeds = np.zeros((GH, GW), np.float32)
        self.seed_sp = np.zeros((GH, GW), np.int32)
        self.grow = np.zeros(CAP_SP, np.float32)
        self.bark = np.zeros(CAP_SP, np.float32)
        self.cone = np.zeros(CAP_SP, np.float32)
        self.reach = np.zeros(CAP_SP, np.float32)
        self.hue = np.zeros(CAP_SP, np.float32)
        self.founder = {}
        self.next_sp = 1
        self.fires = 0
        self.largest = 0
        self.cur_fire = 0
        for _ in range(8):
            s = self._new_sp(None)
            for _ in range(30):
                y, x = rng.integers(0, GH), rng.integers(0, GW)
                self.state[y, x] = TREE
                self.sp[y, x] = s

    def _new_sp(self, parent):
        rng = self.rng
        if self.next_sp >= CAP_SP:
            self._compact()
        s = self.next_sp
        self.next_sp += 1
        if parent is None:
            self.grow[s], self.bark[s], self.cone[s], self.reach[s] = rng.uniform(0.3, 0.7), rng.uniform(0, 0.4), rng.uniform(0, 0.3), rng.uniform(0, 0.5)
            self.hue[s] = rng.uniform(0.18, 0.42)
            self.founder[s] = s
        else:
            for arr, sd in ((self.grow, 0.06), (self.bark, 0.06), (self.cone, 0.06), (self.reach, 0.06)):
                arr[s] = np.clip(arr[parent] + rng.normal(0, sd), 0, 1)
            self.hue[s] = (self.hue[parent] + rng.normal(0, 0.02)) % 1
            self.founder[s] = self.founder.get(parent, parent)
        return s

    def _compact(self):
        live = np.unique(np.concatenate([self.sp[self.state == TREE].ravel(), self.seed_sp[self.seeds > 0.05].ravel()]))
        live = live[live > 0]
        remap = np.zeros(CAP_SP, np.int32)
        remap[live] = np.arange(1, len(live) + 1)
        for arr in (self.grow, self.bark, self.cone, self.reach, self.hue):
            arr[1:len(live) + 1] = arr[live]
        self.founder = {int(remap[s]): int(remap[self.founder.get(int(s), int(s))]) or int(remap[s]) for s in live}
        self.sp = remap[self.sp]
        self.seed_sp = remap[self.seed_sp]
        self.next_sp = len(live) + 1

    def _step(self):
        if self.tick % 2:
            return
        rng = self.rng
        st, sp = self.state, self.sp
        rain = mult(self.dial("rain"), 1.8)
        tree = st == TREE
        # lightning
        if rng.random() < 0.012 * mult(self.dial("lightning"), 3.0):
            y, x = rng.integers(0, GH), rng.integers(0, GW)
            if st[y, x] == TREE:
                st[y, x] = FIRE
                self.burn[y, x] = 3
                self.fires += 1
                self.cur_fire = 0
                self.milestone("first_fire", "Lightning has set the forest alight for the first time.")
        # fire spreads to neighbouring trees that do not resist it
        burning = st == FIRE
        if not burning.any():
            self.cur_fire = 0
        if burning.any():
            near = np.zeros((GH, GW), bool)
            for dy, dx in NBR:
                near |= np.roll(np.roll(burning, dy, 0), dx, 1)
            p_catch = (1 - self.bark[sp]) * 0.55 / rain
            catch = tree & near & (rng.random((GH, GW)) < p_catch)
            st[catch] = FIRE
            self.burn[catch] = 3
            n = int(catch.sum())
            self.cur_fire += n
            if self.cur_fire > self.largest:
                self.largest = self.cur_fire
            self.burn[burning] -= 1
            done = burning & (self.burn <= 0)
            # fire-opened cones drop their seed into the ash
            ys, xs = np.nonzero(done)
            if len(ys):
                c = self.cone[sp[ys, xs]]
                self.seeds[ys, xs] += 0.2 + 2.5 * c
                self.seed_sp[ys, xs] = sp[ys, xs]
                st[done] = ASH
            if self.cur_fire >= 1500:
                self.milestone("great_fire", "A great fire has burned more than fifteen hundred trees.")
        tree = st == TREE
        # growth: each tree may seed a neighbour (or further, if its seed travels)
        ys, xs = np.nonzero(tree)
        if len(ys):
            s = sp[ys, xs]
            rate = self.grow[s] * (1 - 0.55 * self.bark[s]) * (1 - 0.35 * self.cone[s]) * 0.08 * rain
            go = rng.random(len(ys)) < rate
            ys, xs, s = ys[go], xs[go], s[go]
            far = rng.random(len(ys)) < self.reach[s] * 0.5
            dist = np.where(far, rng.integers(2, 7, len(ys)), 1)
            d = rng.integers(0, 8, len(ys))
            ty = (ys + np.array([n[0] for n in NBR])[d] * dist) % GH
            tx = (xs + np.array([n[1] for n in NBR])[d] * dist) % GW
            ok = (st[ty, tx] == SOIL) | ((st[ty, tx] == ASH) & (rng.random(len(ty)) < 0.9))
            for y0, x0, s0 in zip(ty[ok], tx[ok], s[ok]):
                if st[y0, x0] == TREE:
                    continue
                st[y0, x0] = TREE
                sp[y0, x0] = self._new_sp(int(s0)) if rng.random() < 0.004 else s0
        # the seed bank sprouts in ash and soil
        sprout = (st != TREE) & (st != FIRE) & (self.seeds > 0.1) & (rng.random((GH, GW)) < 0.01 * self.seeds * rain)
        st[sprout] = TREE
        sp[sprout] = self.seed_sp[sprout]
        self.seeds[sprout] *= 0.5
        self.seeds *= 0.9995
        # old ash weathers back into soil; old trees fall
        weather = (st == ASH) & (rng.random((GH, GW)) < 0.004)
        st[weather] = SOIL
        fall = (st == TREE) & (rng.random((GH, GW)) < 0.0004)
        st[fall] = SOIL
        if not (st == TREE).any():
            for _ in range(4):
                s0 = self._new_sp(None)
                for _ in range(20):
                    y, x = rng.integers(0, GH), rng.integers(0, GW)
                    st[y, x] = TREE
                    sp[y, x] = s0
            self.event("reseed", "Not a tree was left standing. Seed blew in from beyond the hills.")
        if self.tick % 400 == 0:
            cover = float((st == TREE).mean())
            if cover > 0.6:
                self.milestone("closed", "The forest has closed its canopy over most of the land.")

    def stats(self):
        st = self.state
        t = st == TREE
        out = {"cover": int(round(100 * float(t.mean()))), "ash": int(round(100 * float((st == ASH).mean()))),
               "burning": int((st == FIRE).sum()), "fires": int(self.fires), "largest": int(self.largest),
               "seed_bank": int(self.seeds.sum())}
        if t.any():
            s = self.sp[t]
            fam = np.array([self.founder.get(int(v), int(v)) for v in np.unique(s)])
            out.update({"species": int(len(np.unique(fam))), "bark": round(float(self.bark[s].mean()), 3),
                        "cones": round(float(self.cone[s].mean()), 3), "reach": round(float(self.reach[s].mean()), 3),
                        "growth": round(float(self.grow[s].mean()), 3)})
        return out

    def stratum(self):
        t = self.state == TREE
        if not t.any():
            return {"cols": [[0.08, 0.1, 1]]}
        s, n = np.unique(self.sp[t], return_counts=True)
        top = np.argsort(-n)[:6]
        cols = [[round(float(self.hue[s[k]]), 3), 0.6, int(n[k])] for k in top]
        cols.append([0.08, 0.05, max(1, int((self.state == ASH).sum()) // 4)])
        return {"cols": cols}

    def frame(self):
        st = self.state
        t = st == TREE
        import base64
        s_all, n = np.unique(self.sp[t], return_counts=True)
        live = s_all[np.argsort(-n)][:250]
        slot = np.zeros(CAP_SP, np.int32)
        slot[live] = np.arange(1, len(live) + 1)
        # one byte per cell: 0 soil, 1 ash, 2 fire, 3 ash with seed waiting, 4+ a tree of palette slot (byte - 4)
        code = np.where(st == ASH, np.where(self.seeds > 0.3, 3, 1), np.where(st == FIRE, 2, 0)).astype(np.int32)
        code = np.where(t, 4 + np.minimum(slot[self.sp], 251) - 1, code)
        code = np.where(t & (slot[self.sp] == 0), 4, code)
        pal = [[round(float(self.hue[s]), 3), round(float(self.bark[s]), 2), round(float(self.cone[s]), 2)] for s in live]
        return {"gw": GW, "gh": GH, "cells": base64.b64encode(code.astype(np.uint8).tobytes()).decode(), "palette": pal}
