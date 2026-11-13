"""PSYCHOGENESIS — the origin and development of psychological processes.

A meadow scattered with eight kinds of thing (shapes in colours). Some are food, some are poison, most are nothing,
and which is which changes from time to time without warning. The creatures here are born with instincts (a
liking or dislike for each kind, inherited) and with a temperament: how fast they learn from what happens to
them, how curious they are about kinds they have not tried, how long fear stays with them after they are hurt.
Within its life each creature learns, by taste and by pain, which kinds are good now. What it learns dies with it;
only the instincts and the temperament are passed on.

So two minds are at work: evolution writes instincts over generations, and learning revises them within a life.
When the world changes fast, learning and curiosity pay; when it holds still, instinct catches up and learning
matters less (the Baldwin effect). Each creature's face shows its mood: hungry, afraid, curious or content.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
NK = 8                          # kinds of thing
CAP_A, CAP_O = 130, 240
SENSE = 130.0


class Psychogenesis(World):
    SLUG = "psychogenesis"
    TITLE = "Psychogenesis"
    DEFINITION = "The origin and development of psychological processes"
    TAGLINE = "Instinct written by evolution, revised by learning within a life: and the world keeps changing its rules."
    TPS = 12.0
    STATS_EVERY = 240
    EPOCH = 4800
    ABOUT = [
        "A meadow scattered with eight kinds of thing. Some are food, some poison, most are nothing, and which is which changes from time to time without warning.",
        "The creatures are born with instincts (a liking or dislike for each kind, inherited) and a temperament: how fast they learn, how curious they are about kinds they have not tried, and how long fear stays with them after they are hurt.",
        "Within its life each creature learns, by taste and by pain, which kinds are good now. What it learns dies with it; only instincts and temperament are passed on. Each face shows its mood: hungry, afraid, curious or content.",
        "So two minds are at work: evolution writes instincts over generations, and learning revises them within a life. When the world changes fast, learning and curiosity pay; when it holds still, instinct catches up (the Baldwin effect).",
    ]
    STAT_LABELS = [("creatures", "Creatures"), ("learning", "Learning rate, average"), ("curiosity", "Curiosity, average"),
                   ("fearfulness", "Fearfulness, average"), ("instinct", "Instincts right (%)"), ("knowledge", "Learned right (%)"),
                   ("poisoned", "Meals that were poison (%)"), ("changes", "Times the rules changed"), ("generations", "Generations")]
    SERIES = [[("learning", "Learning rate", "#3f97b5"), ("curiosity", "Curiosity", "#a8c94a"), ("fearfulness", "Fear", "#c9b6ff")],
              [("instinct", "Instinct right %", "#e5602a"), ("knowledge", "Learned right %", "#f2b33d")],
              [("poisoned", "Poisoned meals %", "#e58bb0")]]
    DIALS = [D("change", "Change", "clock", "#c9b6ff", "Settled", "Fickle",
               "How often the world changes which things are food and which are poison. A fickle world rewards learning and curiosity; a settled one lets instinct do."),
             D("danger", "Danger", "bolt", "#e5602a", "Mild", "Deadly",
               "How much harm poison does. Deadly poison makes caution and fear pay; mild poison makes tasting everything cheap.")]
    JOURNAL_HINT = ("These creatures learn within their lives what is food and what is poison; speak of instinct, learning, "
                    "curiosity, fear, mood, and the rules of the meadow changing. Do not overclaim feelings.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.meaning = np.zeros(NK, np.float32)
        self.changes = 0
        self._shuffle(first=True)
        self.o_alive = np.zeros(CAP_O, bool)
        self.ox, self.oy = np.zeros(CAP_O, np.float32), np.zeros(CAP_O, np.float32)
        self.ok = np.zeros(CAP_O, np.int8)
        self.alive = np.zeros(CAP_A, bool)
        self.x, self.y, self.h = (np.zeros(CAP_A, np.float32) for _ in range(3))
        self.e = np.zeros(CAP_A, np.float32)
        self.age = np.zeros(CAP_A, np.int32)
        self.inst = np.zeros((CAP_A, NK), np.float32)     # inherited liking
        self.V = np.zeros((CAP_A, NK), np.float32)        # learned value
        self.tries = np.zeros((CAP_A, NK), np.float32)
        self.lr, self.cur, self.fearg = (np.zeros(CAP_A, np.float32) for _ in range(3))
        self.fear, self.joy = np.zeros(CAP_A, np.float32), np.zeros(CAP_A, np.float32)
        self.target = np.full(CAP_A, -1, np.int32)
        self.gen = np.zeros(CAP_A, np.int32)
        self.lin = np.zeros(CAP_A, np.int64)
        self.next_lin = 1
        self.meals = []
        self.next_change = 6000
        for _ in range(CAP_O):
            self._object()
        for _ in range(60):
            self._spawn(None)

    def _shuffle(self, first=False):
        rng = self.rng
        kinds = rng.permutation(NK)
        m = np.zeros(NK, np.float32)
        m[kinds[:3]] = 1.0
        m[kinds[3:5]] = -1.0
        self.meaning = m
        if not first:
            self.changes += 1
            self.event("change", "The meadow has changed its rules: some things that fed now harm, and the reverse.")

    def _object(self):
        free = np.flatnonzero(~self.o_alive)
        if not len(free):
            return
        i = int(free[0])
        self.o_alive[i] = True
        self.ox[i], self.oy[i] = self.rng.uniform(15, W - 15), self.rng.uniform(15, H - 15)
        self.ok[i] = self.rng.integers(0, NK)

    def _spawn(self, p):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        rng = self.rng
        if p is None:
            self.inst[i] = rng.normal(0, 0.3, NK)
            self.lr[i], self.cur[i], self.fearg[i] = rng.uniform(0.05, 0.3), rng.uniform(0, 0.5), rng.uniform(0, 0.5)
            self.x[i], self.y[i] = rng.uniform(20, W - 20), rng.uniform(20, H - 20)
            self.e[i] = 40
            self.lin[i] = self.next_lin
            self.next_lin += 1
            self.gen[i] = 0
        else:
            self.inst[i] = self.inst[p] + rng.normal(0, 0.08, NK)
            self.lr[i] = np.clip(self.lr[p] + rng.normal(0, 0.03), 0, 1)
            self.cur[i] = np.clip(self.cur[p] + rng.normal(0, 0.04), 0, 1.5)
            self.fearg[i] = np.clip(self.fearg[p] + rng.normal(0, 0.04), 0, 1)
            self.x[i], self.y[i] = self.x[p] + rng.normal(0, 8), self.y[p] + rng.normal(0, 8)
            self.e[i] = 0.4 * self.e[p]
            self.e[p] *= 0.55
            self.lin[i], self.gen[i] = self.lin[p], self.gen[p] + 1
        self.alive[i] = True
        self.V[i] = self.inst[i]
        self.tries[i] = 0
        self.h[i] = rng.uniform(0, 2 * math.pi)
        self.age[i] = 0
        self.fear[i] = self.joy[i] = 0
        self.target[i] = -1
        return i

    def _step(self):
        rng = self.rng
        if self.tick >= self.next_change:
            self._shuffle()
            self.next_change = self.tick + int(rng.uniform(4000, 9000) / mult(self.dial("change"), 3.0))
        Oa = np.flatnonzero(self.o_alive)
        self.o_alive[Oa[rng.random(len(Oa)) < 0.0025]] = False          # things wither and others grow in their place
        for _ in range(2):
            if self.o_alive.sum() < CAP_O and rng.random() < 0.7:
                self._object()
        A = np.flatnonzero(self.alive)
        if len(A) < 6:
            for _ in range(15):
                self._spawn(None)
            self.event("arrivals", "Few creatures were left; newcomers wander into the meadow.")
            A = np.flatnonzero(self.alive)
        O = np.flatnonzero(self.o_alive)
        # choose what to approach, every few steps
        if self.tick % 5 == 0 and len(O):
            from scipy.spatial import cKDTree
            tree = cKDTree(np.stack([self.ox[O], self.oy[O]], 1))
            d, idx = tree.query(np.stack([self.x[A], self.y[A]], 1), k=min(8, len(O)), distance_upper_bound=SENSE)
            for a, i in enumerate(A):
                best, bt = 0.05, -1
                afraid = self.fear[i] > 0.4
                for dd, j in zip(d[a], idx[a]):
                    if not np.isfinite(dd):
                        continue
                    o = int(O[j]); k = int(self.ok[o])
                    novelty = 1.0 / (1.0 + self.tries[i, k])
                    hunger = 1.2 - min(1.0, self.e[i] / 60)
                    v = (self.V[i, k] * hunger + self.cur[i] * novelty * (0.2 if afraid else 1.0)) / (1 + dd / 80)
                    if v > best:
                        best, bt = v, o
                self.target[i] = bt
        # move
        tg = self.target[A]
        has = (tg >= 0) & self.o_alive[np.maximum(tg, 0)]
        tx = np.where(has, self.ox[np.maximum(tg, 0)], 0)
        ty = np.where(has, self.oy[np.maximum(tg, 0)], 0)
        want = np.arctan2(ty - self.y[A], tx - self.x[A])
        turn = ((want - self.h[A] + math.pi) % (2 * math.pi)) - math.pi
        self.h[A] = np.where(has, self.h[A] + np.clip(turn, -0.3, 0.3), self.h[A] + rng.normal(0, 0.25, len(A)))
        sp = 1.2 + 0.6 * self.fear[A]
        self.x[A] = np.clip(self.x[A] + sp * np.cos(self.h[A]), 8, W - 8)
        self.y[A] = np.clip(self.y[A] + sp * np.sin(self.h[A]), 8, H - 8)
        self.e[A] -= 0.035 + 0.01 * self.cur[A] + 0.01 * self.lr[A]
        self.age[A] += 1
        self.fear[A] *= 1 - 0.01 / (0.2 + self.fearg[A])
        self.joy[A] *= 0.99
        # eating (tasting) what was reached
        reached = A[has & (np.hypot(tx - self.x[A], ty - self.y[A]) < 9)]
        harm = 14.0 * mult(self.dial("danger"), 2.0)
        for i in reached:
            o = int(self.target[i])
            if not self.o_alive[o]:
                continue
            k = int(self.ok[o])
            r = float(self.meaning[k])
            self.o_alive[o] = False
            self.target[i] = -1
            self.tries[i, k] += 1
            self.V[i, k] += self.lr[i] * (r - self.V[i, k])
            if r > 0:
                self.e[i] = min(self.e[i] + 12, 90); self.joy[i] = 1.0
            elif r < 0:
                self.e[i] -= harm; self.fear[i] = 1.0
            else:
                self.e[i] -= 0.5
            self.meals.append(1 if r < 0 else 0)
        self.meals = self.meals[-500:]
        dead = A[(self.e[A] <= 0) | (self.age[A] > 8000)]
        self.alive[dead] = False
        for i in np.flatnonzero(self.alive & (self.e > 60))[:3]:
            self._spawn(int(i))
        if self.tick % 600 == 0:
            s = self.stats()
            if s.get("knowledge", 0) >= 80:
                self.milestone("learned", "Most creatures now know, from experience, which things are food under the present rules.")
            if s.get("instinct", 0) >= 70:
                self.milestone("instinct", "Instinct has caught up with the meadow: most creatures are born knowing what to eat (until the rules change).")
            if s.get("curiosity", 0) >= 0.8:
                self.milestone("curious", "Curiosity has become strong: creatures go out of their way to try what they do not know.")

    def stats(self):
        A = np.flatnonzero(self.alive)
        out = {"creatures": int(len(A)), "changes": int(self.changes),
               "poisoned": int(round(100 * sum(self.meals) / max(1, len(self.meals))))}
        if len(A):
            sig = np.sign(self.meaning)
            mask = sig != 0
            inst = (np.sign(self.inst[A][:, mask]) == sig[mask]).mean()
            know = (np.sign(np.round(self.V[A][:, mask], 1)) == sig[mask]).mean()
            out.update({"learning": round(float(self.lr[A].mean()), 3), "curiosity": round(float(self.cur[A].mean()), 3),
                        "fearfulness": round(float(self.fearg[A].mean()), 3), "instinct": int(round(100 * float(inst))),
                        "knowledge": int(round(100 * float(know))), "generations": int(self.gen[A].max())})
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
        O = np.flatnonzero(self.o_alive)

        def mood(i):
            hunger = 1 - min(1.0, self.e[i] / 60)
            m = {"afraid": float(self.fear[i]), "hungry": hunger * 0.9, "content": float(self.joy[i]) * 0.9,
                 "curious": float(self.cur[i]) * 0.5 * (self.target[i] >= 0 and self.tries[i, int(self.ok[self.target[i]])] < 1)}
            return ["afraid", "hungry", "content", "curious"].index(max(m, key=m.get))
        return {"w": W, "h": H,
                "creatures": [[int(i), round(float(self.x[i]), 1), round(float(self.y[i]), 1), round(float(self.h[i]), 2), mood(i),
                               round((int(self.lin[i]) * 0.618034) % 1, 3), round(float(self.lr[i]), 2)] for i in A],
                "things": np.stack([np.round(self.ox[O]), np.round(self.oy[O]), self.ok[O]], 1).astype(int).ravel().tolist()}
