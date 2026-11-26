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
# Nov 26: dry years. By then the forest had covered 99% of the land with thick-barked trees that fire could not run
# through, so there was nothing left to be reborn. Now the climate swings slowly between wet and dry spells (a
# drought every DRY_PERIOD ticks, of varying strength): in a drought the canopy dries, fire climbs into the crowns
# where thick bark is no shield, and the seedlings struggle, so the old fire-proof forest can burn again and the race between bark and growth reopens.
DRY_PERIOD = 48000


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
        "The climate swings between wet years and dry spells. In a drought the canopy dries and fire climbs into the crowns, where even thick bark is no shield, so no forest is fire-proof for ever.",
    ]
    STAT_LABELS = [("cover", "Forest cover (%)"), ("drought", "Drought (0-1)"), ("ash", "Ash (%)"), ("burning", "Trees burning now"), ("fires", "Fires so far"),
                   ("largest", "Largest fire (trees)"), ("species", "Kinds of tree"), ("bark", "Bark thickness, average"),
                   ("cones", "Fire-opened cones, average"), ("seed_bank", "Seeds waiting in the soil")]
    SERIES = [[("cover", "Forest cover %", "#6b8f2a"), ("ash", "Ash %", "#9aa3aa")],
              [("bark", "Bark", "#b9560c"), ("cones", "Fire cones", "#e5602a"), ("reach", "Seed reach", "#3f97b5")],
              [("species", "Kinds of tree", "#a8c94a")]]
    DIALS = [D("lightning", "Lightning", "bolt", "#f2b33d", "Rare", "Frequent",
               "How often lightning strikes. Frequent fire favours thick bark and fire-opened cones; rare fire lets fast growers crowd in until the big one comes."),
             D("rain", "Rain", "drop", "#3f97b5", "Drought", "Wet",
               "Wet years speed regrowth and slow the spread of fire; drought does the opposite.")]
    LYSIS_NAME = "Palinphthora"
    GSL_SCALE = (0.5, 0.5)
    LYSIS_ABOUT = [
        "Palinphthora: the decay that follows every rebirth. Fire is only one way a forest dies. Old trees fall and lie as dead wood; fungi and beetles rot it slowly into humus, the dark soil in which young trees grow fastest.",
        "Dead wood is also fuel. A forest left long unburned fills with it, and when fire comes it runs through the dead as through tinder: a quiet century makes a great fire.",
        "Bark beetles break out where one kind of tree stands alone in a crowd of its own kind, and spread from tree to tree of that kind. A mixed forest resists them; a monoculture falls. On the underside you see the dead wood in bone, the humus glowing amber, and the beetles' trail in red.",
    ]
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
        self._lysis_init()
        for _ in range(8):
            s = self._new_sp(None)
            for _ in range(30):
                y, x = rng.integers(0, GH), rng.integers(0, GW)
                self.state[y, x] = TREE
                self.sp[y, x] = s

    def _lysis_init(self):
        if not hasattr(self, "dead"):
            self.dead = np.zeros((GH, GW), np.float32)      # fallen wood lying on the ground
            self.humus = np.zeros((GH, GW), np.float32)     # what rot has made of it: the richest soil
            self.beetle = np.zeros((GH, GW), np.int8)       # trees infested now (counts down to death)
            self.l_born = self.l_died = 0
            self.l_ret = 0.0
            self.outbreaks = 0

    def lysis_counts(self):
        self._lysis_init()
        return (int(self.l_born), int(self.l_died), int(self.l_ret), int((self.state == TREE).sum()) + 50)

    def _drought(self):
        """0 in wet years, rising to 1 at the height of a severe drought. Each dry spell has its own strength."""
        t = self.tick
        k = t // DRY_PERIOD
        ph = (t % DRY_PERIOD) / DRY_PERIOD
        strength = 0.45 + 0.55 * ((k * 0.618034 + self.seed * 0.1) % 1.0)
        d = strength * max(0.0, np.sin(np.pi * (ph - 0.6) / 0.4)) if ph > 0.6 else 0.0
        if ph > 0.6 and not getattr(self, "dry_told", -1) == k:
            self.dry_told = k
            self.event("climate", "A dry spell begins: the canopy dries and fire will run further." if strength > 0.7
                       else "A dry year: the forest is thirsty.")
        return float(d)

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
        self._lysis_init()
        rng = self.rng
        st, sp = self.state, self.sp
        rain = mult(self.dial("rain"), 1.8)
        dry = self._drought()
        rain = rain * (1 - 0.4 * dry)
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
            # in a drought fire climbs into the dry crowns, where thick bark is no shield
            p_catch = np.minimum(1.0, (1 - self.bark[sp] * (1 - 0.6 * dry)) * 0.55 * (1 + 0.8 * dry) / rain
                                 + 0.35 * np.minimum(self.dead, 2.0))   # dead wood is tinder; a drought dries the canopy
            catch = tree & near & (rng.random((GH, GW)) < p_catch)
            self.dead[near & (rng.random((GH, GW)) < 0.5)] *= 0.3                                            # and burns away
            st[catch] = FIRE
            self.burn[catch] = 3
            n = int(catch.sum())
            self.l_died += n
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
            rate = rate * (1 + 0.45 * self.humus[ys, xs] / (self.humus[ys, xs] + 1.5))      # rich humus feeds the living
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
                self.l_born += 1
        # the seed bank sprouts in ash and soil
        sprout = (st != TREE) & (st != FIRE) & (self.seeds > 0.1) & (rng.random((GH, GW)) < 0.01 * self.seeds * rain)
        st[sprout] = TREE
        sp[sprout] = self.seed_sp[sprout]
        self.l_born += int(sprout.sum())
        self.seeds[sprout] *= 0.5
        self.seeds *= 0.9995
        # old ash weathers back into soil; old trees fall
        weather = (st == ASH) & (rng.random((GH, GW)) < 0.004)
        st[weather] = SOIL
        self.humus[weather] += 0.6                                  # ash weathers into the soil it enriches
        fall = (st == TREE) & (rng.random((GH, GW)) < 0.0004)
        st[fall] = SOIL
        self.dead[fall] += 1.0 + 0.6 * self.bark[sp[fall]]          # the fallen tree lies where it fell
        self.l_died += int(fall.sum())
        # rot: fungi and beetles turn dead wood into humus, faster when it is wet
        rot = self.dead * 0.004 * rain
        self.dead -= rot
        self.humus += 0.8 * rot
        self.l_ret += float(rot.sum()) * 2 + float(weather.sum()) * 0.5
        self.humus *= 0.998
        # bark beetles: an outbreak starts where one kind of tree is crowded among its own kind
        if rng.random() < 0.01:
            y, x = rng.integers(0, GH), rng.integers(0, GW)
            if st[y, x] == TREE:
                s0 = sp[y, x]
                win = sp[max(0, y - 4):y + 5, max(0, x - 4):x + 5] == s0
                if win.mean() > 0.45:
                    self.beetle[y, x] = 12
                    self.outbreaks += 1
                    self.milestone("beetles", "Bark beetles have broken out in a stand of one kind of tree.")
        inf = self.beetle > 0
        if inf.any():
            ys, xs = np.nonzero(inf)
            for dy, dx in NBR:
                ty, tx = (ys + dy) % GH, (xs + dx) % GW
                same = (st[ty, tx] == TREE) & (sp[ty, tx] == sp[ys, xs]) & (self.beetle[ty, tx] == 0) & (rng.random(len(ys)) < 0.14)
                self.beetle[ty[same], tx[same]] = 12
            self.beetle[inf] -= 1
            killed = inf & (self.beetle <= 0) & (st == TREE)
            st[killed] = SOIL
            self.dead[killed] += 1.2
            self.l_died += int(killed.sum())
            self.beetle[st != TREE] = 0
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
        out = {"drought": round(self._drought(), 2), "cover": int(round(100 * float(t.mean()))), "ash": int(round(100 * float((st == ASH).mean()))),
               "burning": int((st == FIRE).sum()), "fires": int(self.fires), "largest": int(self.largest),
               "seed_bank": int(self.seeds.sum()),
               "deadwood": int(getattr(self, "dead", np.zeros(1)).sum()), "humus": int(getattr(self, "humus", np.zeros(1)).sum()),
               "infested": int((getattr(self, "beetle", np.zeros(1)) > 0).sum()), "outbreaks": int(getattr(self, "outbreaks", 0))}
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
        self._lysis_init()
        # the dark side: dead wood, humus and beetles, at half resolution, one byte each
        half = lambda a: a.reshape(GH // 2, 2, GW // 2, 2).mean((1, 3))
        under = np.stack([np.clip(half(self.dead) * 90, 0, 255), np.clip(half(self.humus) * 60, 0, 255),
                          np.clip(half((self.beetle > 0).astype(np.float32)) * 255, 0, 255)], -1).astype(np.uint8)
        return {"gw": GW, "gh": GH, "cells": base64.b64encode(code.astype(np.uint8).tobytes()).decode(), "palette": pal,
                "under": base64.b64encode(under.tobytes()).decode()}
