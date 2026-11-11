"""PROTOGENESIS — first origin: from a soup of building blocks to the first things that copy themselves.

A warm pond. Vents on the floor and sunlight at the surface make four kinds of monomer: A pairs with B, C with D.
- Monomers that meet can bond into short chains, and chains grow by picking up monomers at their ends.
- Chains break apart over time, unless their sequence folds back on itself (a hairpin), which protects them.
- A chain can serve as a template: if it gathers the complementary monomers for every position, a copy forms
  alongside it (a complement; the copy of the copy is the original). Copying makes mistakes.
- Some sequences also act as catalysts: the closer a chain carries this world's hidden "active site" motif,
  the faster it copies itself and every chain beside it. That help can be exploited: short chains that do not
  catalyse but sit next to a catalyst get copied for free (parasites). Survival of catalysts depends on where
  they sit. This is the hypercycle problem Manfred Eigen described.
Nothing is told what to become; selection is only differential copying and breaking.
"""
from __future__ import annotations

import math

import numpy as np

from .base import World

NT = 4                      # monomer types: 0 A, 1 B, 2 C, 3 D
COMP = np.array([1, 0, 3, 2])
MAXL = 24
CAP_M, CAP_C = 3800, 420
W, H = 1200.0, 800.0
MOTIF_LEN = 5


class Protogenesis(World):
    SLUG = "protogenesis"
    TITLE = "Protogenesis"
    DEFINITION = "First origin or initial formation"
    TAGLINE = "From a soup of building blocks to the first things that copy themselves."
    TPS = 12.0
    STATS_EVERY = 240
    EPOCH = 4800
    LIGHT_CYCLE = 2400
    ABOUT = [
        "A warm pond. Vents on the floor and sunlight at the surface make four kinds of building block (the coloured balls). Red pairs with yellow, blue with green.",
        "Blocks that meet can bond into chains, and chains grow at their ends. Chains break apart in time, unless their sequence folds back on itself into a hairpin, which protects them.",
        "A chain can act as a template: when the complementary blocks for every position gather beside it, a copy forms. Copying makes mistakes, so copies vary.",
        "Some sequences are catalysts (they wear a gold ring): the closer a chain comes to this pond's hidden active site, the faster it copies itself and every chain next to it. Short chains that copy for free beside a catalyst are parasites.",
        "No chain is told what to become. Over time the pond fills with the sequences that copy fastest and break least: the first heredity.",
    ]
    STAT_LABELS = [("monomers", "Free building blocks"), ("chains", "Chains"), ("longest", "Longest chain"),
                   ("replicators", "Chains that are copies"), ("families", "Families of copies"),
                   ("max_generation", "Most generations in a family"), ("best_activity", "Best catalyst (0-1)"),
                   ("copies", "Copies made so far"), ("parasites", "Parasites (copied, not catalysing)")]
    SERIES = [[("chains", "Chains", "#e5602a"), ("replicators", "Copies", "#3f97b5")],
              [("best_activity", "Best catalyst", "#f2b33d"), ("mean_activity", "Average catalysis", "#a8c94a"),
               ("mean_fold", "Average folding", "#c9b6ff")],
              [("families", "Families of copies", "#8fd3c8"), ("max_generation", "Generations", "#e58bb0")]]
    JOURNAL_HINT = ("This is a prebiotic pond, before life. Speak of building blocks, chains, templates, copies, "
                    "folding, catalysts and parasites, never of organisms or creatures.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.motif = rng.integers(0, NT, MOTIF_LEN)
        self.vents = [rng.uniform(150, 500), rng.uniform(700, 1050)]
        self.m_alive = np.zeros(CAP_M, bool)
        self.mx, self.my = np.zeros(CAP_M, np.float32), np.zeros(CAP_M, np.float32)
        self.mt = np.zeros(CAP_M, np.int8)
        self.c_alive = np.zeros(CAP_C, bool)
        self.cx, self.cy, self.ca = (np.zeros(CAP_C, np.float32) for _ in range(3))
        self.seq = np.zeros((CAP_C, MAXL), np.int8)
        self.clen = np.zeros(CAP_C, np.int16)
        self.cgen = np.zeros(CAP_C, np.int32)
        self.cfam = np.zeros(CAP_C, np.int64)
        self.cid = np.zeros(CAP_C, np.int64)
        self.ccopied = np.zeros(CAP_C, bool)      # this chain is a copy
        self.cprog = np.zeros(CAP_C, np.int16)     # how many positions of a copy have gathered on the template
        self.next_id, self.next_fam = 1, 1
        self.fam_root = {}                        # family -> founder sequence
        self.copies = self.parasite_copies = 0
        for _ in range(2600):
            self._new_monomer()

    # ── building blocks ──────────────────────────────────────────────────
    def _new_monomer(self, x=None, y=None, t=None):
        free = np.flatnonzero(~self.m_alive)
        if not len(free):
            return
        i = int(free[0])
        rng = self.rng
        self.m_alive[i] = True
        self.mx[i] = x if x is not None else rng.uniform(5, W - 5)
        self.my[i] = y if y is not None else rng.uniform(5, H - 5)
        self.mt[i] = t if t is not None else rng.integers(0, NT)

    def _new_chain(self, seq, x, y, gen=0, fam=0, copied=False, evict=False):
        free = np.flatnonzero(~self.c_alive)
        if not len(free):
            if not evict:
                return None
            # the pond is crowded: a copy displaces a short chain that nobody has copied
            weak = np.flatnonzero(self.c_alive & (self.clen <= 4) & (self.cgen == 0) & ~self.ccopied)
            if not len(weak):
                weak = np.flatnonzero(self.c_alive & (self.cgen == 0))
            if not len(weak):
                return None
            i = int(self.rng.choice(weak))
            L0 = int(self.clen[i])
            for v in self.seq[i, :L0]:
                self._new_monomer(self.cx[i] + self.rng.normal(0, 4), self.cy[i] + self.rng.normal(0, 4), int(v))
            free = [i]
        i = int(free[0])
        L = min(len(seq), MAXL)
        self.c_alive[i] = True
        self.seq[i] = 0
        self.seq[i, :L] = seq[:L]
        self.clen[i] = L
        self.cx[i], self.cy[i] = np.clip(x, 5, W - 5), np.clip(y, 5, H - 5)
        self.ca[i] = self.rng.uniform(0, 2 * math.pi)
        self.cgen[i], self.cfam[i], self.ccopied[i] = gen, fam, copied
        self.cprog[i] = 0
        self.cid[i] = self.next_id
        self.next_id += 1
        return i

    # ── chemistry of a single chain ──────────────────────────────────────
    def _fold(self, i):
        """Fraction of the chain that pairs with itself as a hairpin (protects it from breaking)."""
        L = int(self.clen[i])
        if L < 4:
            return 0.0
        s = self.seq[i, :L]
        h = L // 2
        return float((COMP[s[:h]] == s[::-1][:h]).mean())

    def _activity(self, i):
        """How close the chain comes to the pond's hidden active site (0-1)."""
        L = int(self.clen[i])
        if L < MOTIF_LEN:
            return 0.0
        s = self.seq[i, :L]
        best = 0
        for strand in (s, COMP[s]):          # either strand of a template pair can carry the site
            for k in range(L - MOTIF_LEN + 1):
                best = max(best, int((strand[k:k + MOTIF_LEN] == self.motif).sum()))
        return (best / MOTIF_LEN) ** 3

    def _step(self):
        rng = self.rng
        t = self.tick
        light = self.light()
        # supply: vents always, sunlight by day; keep the pond from overfilling
        n_m = int(self.m_alive.sum())
        if n_m < 3300:
            for vx in self.vents:
                if rng.random() < 1.0:
                    self._new_monomer(vx + rng.normal(0, 25), H - rng.uniform(5, 40))
            if rng.random() < 1.6 * light:
                self._new_monomer(rng.uniform(5, W - 5), rng.uniform(5, 60))
        # motion: monomers jiggle, with a slow overturning current (up over the vents, down elsewhere)
        M = np.flatnonzero(self.m_alive)
        if len(M):
            x, y = self.mx[M], self.my[M]
            up = np.exp(-((x[:, None] - np.array(self.vents)[None, :]) / 90) ** 2).sum(1)
            self.mx[M] = np.clip(x + rng.normal(0, 2.2, len(M)) + 0.4 * np.sin(y / H * math.pi * 2), 2, W - 2)
            self.my[M] = np.clip(y + rng.normal(0, 2.2, len(M)) - 0.9 * up + 0.25, 2, H - 2)
            dead = M[rng.random(len(M)) < 0.0005]
            self.m_alive[dead] = False
        C = np.flatnonzero(self.c_alive)
        if len(C):
            L = self.clen[C].astype(np.float32)
            j = 1.6 / np.sqrt(L)
            self.cx[C] = np.clip(self.cx[C] + rng.normal(0, 1, len(C)) * j + 0.3 * np.sin(self.cy[C] / H * math.pi * 2), 5, W - 5)
            self.cy[C] = np.clip(self.cy[C] + rng.normal(0, 1, len(C)) * j + 0.15, 5, H - 5)
            self.ca[C] += rng.normal(0, 0.05, len(C)).astype(np.float32)
        if t % 3:
            return
        self._chemistry()

    def _chemistry(self):
        from scipy.spatial import cKDTree
        rng = self.rng
        M = np.flatnonzero(self.m_alive)
        C = np.flatnonzero(self.c_alive)
        if len(M) < 2:
            return
        mt = cKDTree(np.stack([self.mx[M], self.my[M]], 1))
        used = np.zeros(CAP_M, bool)
        # two blocks that meet may bond into a chain of two
        pairs = mt.query_pairs(5.0, output_type="ndarray")
        if len(pairs):
            pairs = pairs[rng.random(len(pairs)) < 0.012][:3]
            for a, b in pairs:
                ia, ib = int(M[a]), int(M[b])
                if used[ia] or used[ib]:
                    continue
                k = self._new_chain(np.array([self.mt[ia], self.mt[ib]], np.int8), self.mx[ia], self.my[ia])
                if k is None:
                    break
                used[ia] = used[ib] = True
                self.milestone("first_chain", "The first two building blocks have bonded into a chain.")
        if len(C):
            pos = np.stack([self.cx[C], self.cy[C]], 1)
            # chains grow at their ends
            near = mt.query_ball_point(pos, 20.0)
            act = np.array([self._activity(i) for i in C])
            fold = np.array([self._fold(i) for i in C])
            ctree = cKDTree(pos)
            help_ = np.zeros(len(C))
            neigh = ctree.query_ball_point(pos, 26.0)
            for a, nb in enumerate(neigh):
                help_[a] = max(act[nb]) if nb else 0.0
            for a, i in enumerate(C):
                i = int(i)
                if not self.c_alive[i]:
                    continue
                L = int(self.clen[i])
                cand = [M[k] for k in near[a] if not used[M[k]]]
                # growth at an end
                if cand and L < MAXL and rng.random() < 0.02 * (1 - 0.7 * fold[a]):
                    m = int(cand[0])
                    self.seq[i, L] = self.mt[m]
                    self.clen[i] = L + 1
                    used[m] = True
                    if L + 1 >= 8:
                        self.milestone("long_chain", "A chain eight blocks long has formed.")
                    if L + 1 >= 16:
                        self.milestone("very_long", "A chain sixteen blocks long has formed.")
                # breaking: hairpins protect, long chains are fragile
                if rng.random() < (0.0015 + 0.0006 * L) * (1 - 0.85 * fold[a]):
                    cut = int(rng.integers(1, L)) if L > 1 else 1
                    tail = self.seq[i, cut:L].copy()
                    self.clen[i] = cut
                    self.cprog[i] = 0
                    if len(tail) >= 2:
                        self._new_chain(tail, self.cx[i] + rng.normal(0, 6), self.cy[i] + rng.normal(0, 6))
                    elif len(tail) == 1:
                        self._new_monomer(self.cx[i], self.cy[i], int(tail[0]))
                    if cut < 2:
                        self._new_monomer(self.cx[i], self.cy[i], int(self.seq[i, 0]))
                        self.c_alive[i] = False
                        continue
                # templating: complements gather one position at a time; catalysts speed this up
                L = int(self.clen[i])
                if L >= 4 and cand:
                    rate = (0.08 + 0.9 * max(act[a] * 0.6, help_[a])) * (1 - 0.5 * fold[a])
                    if rng.random() < rate:
                        p = int(self.cprog[i])
                        want = COMP[self.seq[i, p]]
                        hit = next((m for m in cand if not used[m] and self.mt[m] == want), None)
                        if hit is not None:
                            used[hit] = True
                            self.m_alive[hit] = False
                            self.cprog[i] = p + 1
                            if p + 1 >= L:
                                self.cprog[i] = 0
                                self._copy(i, act[a] < 0.1 and help_[a] > 0.3)
        # chains that lost their last partner dissolve slowly
        if self.tick % 30 == 0:
            for i in np.flatnonzero(self.c_alive & (self.clen < 2)):
                self.c_alive[i] = False

    def _copy(self, i, parasite):
        rng = self.rng
        L = int(self.clen[i])
        child = COMP[self.seq[i, :L]].copy()
        err = rng.random(L) < 0.015                     # copying mistakes
        child[err] = rng.integers(0, NT, int(err.sum()))
        fam = int(self.cfam[i])
        if fam == 0:
            fam = self.next_fam
            self.next_fam += 1
            self.cfam[i] = fam
            self.fam_root[fam] = self.seq[i, :L].copy()
        k = self._new_chain(child.astype(np.int8), self.cx[i] + rng.normal(0, 8), self.cy[i] + rng.normal(0, 8),
                            int(self.cgen[i]) + 1, fam, True, evict=True)
        if k is None:
            return
        self.copies += 1
        if parasite:
            self.parasite_copies += 1
        self.ccopied[i] = True
        g = int(self.cgen[k])
        self.milestone("first_copy", "A chain has been copied for the first time: the first template, the first heredity.")
        if g >= 5:
            self.milestone("gen5", "A family of copies has reached five generations.")
        if g >= 25:
            self.milestone("gen25", "A family of copies has reached twenty-five generations.")
        if g >= 100:
            self.milestone("gen100", "A family of copies has reached a hundred generations.")
        a = self._activity(k)
        if a >= 0.51:
            self.milestone("catalyst", "A copied chain carries most of the active site: the first catalyst.")
        if a >= 0.99:
            self.milestone("ribozyme", "A chain carries the whole active site: a true catalyst, copying itself and its neighbours.")

    # ── measurement ──────────────────────────────────────────────────────
    def stats(self):
        C = np.flatnonzero(self.c_alive)
        out = {"monomers": int(self.m_alive.sum()), "chains": int(len(C)), "copies": int(self.copies)}
        if len(C):
            act = np.array([self._activity(i) for i in C])
            fold = np.array([self._fold(i) for i in C])
            fams = self.cfam[C][self.cfam[C] > 0]
            rep = self.ccopied[C] | (self.cgen[C] > 0)
            out.update({"longest": int(self.clen[C].max()), "mean_length": round(float(self.clen[C].mean()), 2),
                        "replicators": int(rep.sum()), "families": int(len(np.unique(fams))),
                        "max_generation": int(self.cgen[C].max()), "best_activity": round(float(act.max()), 3),
                        "mean_activity": round(float(act.mean()), 3), "mean_fold": round(float(fold.mean()), 3),
                        "parasites": int(((act < 0.1) & (self.cgen[C] > 0)).sum())})
        return out

    def _fam_hue(self, fam):
        return ((fam * 0.618034) % 1.0)

    def stratum(self):
        C = np.flatnonzero(self.c_alive & (self.cfam > 0))
        cols = []
        if len(C):
            f, n = np.unique(self.cfam[C], return_counts=True)
            for k in np.argsort(-n)[:6]:
                cols.append([round(self._fam_hue(int(f[k])), 3), 0.75, int(n[k])])
        cols.append([0.12, 0.25, max(1, int(self.m_alive.sum()) // 40)])
        return {"cols": cols}

    def frame(self):
        M = np.flatnonzero(self.m_alive)[:1600]
        C = np.flatnonzero(self.c_alive)
        mon = np.stack([np.round(self.mx[M]).astype(int), np.round(self.my[M]).astype(int), self.mt[M].astype(int)], 1)
        chains = []
        for i in C:
            L = int(self.clen[i])
            chains.append([int(self.cid[i]), round(float(self.cx[i]), 1), round(float(self.cy[i]), 1), round(float(self.ca[i]), 2),
                           "".join("ABCD"[v] for v in self.seq[i, :L]), int(self.cfam[i]),
                           round(self._activity(i), 2), round(self._fold(i), 2), int(self.cgen[i])])
        return {"w": W, "h": H, "monomers": mon.ravel().tolist(), "chains": chains, "vents": [round(v) for v in self.vents]}
