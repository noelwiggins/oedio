"""AUTOPOIESIS — a system's ability to produce and maintain itself.

After the computational model of Varela, Maturana and Uribe (1974), in continuous space.
- Substrate (small cream specks) drifts everywhere and passes through anything.
- A catalyst (a jewel) turns two substrate specks into one link.
- Links bond to each other, at most two bonds each, into chains; a chain that closes on itself is a ring.
- Links decay back into substrate. A ring that holds a catalyst inside is a cell: the catalyst keeps making
  links, and the free links find the gaps that decay opens in the ring and close them. The membrane is
  made by what it encloses, and the catalyst is sheltered by what it makes. That loop is autopoiesis.
- A catalyst left outside any ring wears out quickly; inside it lasts.
- Evolution on top of the 1974 model: catalysts carry heritable rates (how fast they make links, how far the
  links are thrown, how sticky they are). A catalyst in a large, well-fed cell can split; the ring then
  pinches into two, one daughter catalyst in each, with small changes to their rates.
"""
from __future__ import annotations

import math

import numpy as np

from .base import World

W, H = 1200.0, 800.0
CAP_S, CAP_L, CAP_K = 2600, 1700, 40
REST = 9.0                       # bond length
K_GENES = 4                      # produce, throw, stick, hue
LO = np.array([0.15, 6.0, 0.3, 0.0], np.float32)
HI = np.array([0.9, 22.0, 1.0, 1.0], np.float32)
STEP = np.array([0.02, 1.0, 0.05, 0.02], np.float32)


class Autopoiesis(World):
    SLUG = "autopoiesis"
    TITLE = "Autopoiesis"
    DEFINITION = "A system's ability to produce and maintain itself"
    TAGLINE = "A membrane made by what it encloses, enclosing what makes it."
    TPS = 14.0
    STATS_EVERY = 280
    EPOCH = 5600
    ABOUT = [
        "After the model Francisco Varela, Humberto Maturana and Ricardo Uribe built in 1974. Cream specks are substrate; they drift everywhere and pass through everything.",
        "A catalyst (a jewel) joins two specks into a link (an orange bead). Links bond to each other, two bonds at most, into chains, and a chain that closes becomes a ring.",
        "Links decay back into specks. A ring that holds a catalyst is a cell: the catalyst keeps making links, and loose links close the gaps that decay keeps opening. The membrane is made by what it encloses, and protects what makes it.",
        "Catalysts left outside wear out quickly. Each catalyst carries heritable rates; in a large, well-fed cell it can split, and the ring pinches into two, a daughter in each. Over time the catalysts that keep their cells whole spread.",
    ]
    STAT_LABELS = [("cells", "Cells (rings around a catalyst)"), ("rings", "Closed rings"), ("catalysts", "Catalysts"),
                   ("sheltered", "Catalysts inside cells (%)"), ("links", "Links"), ("bonds", "Bonds"),
                   ("oldest_cell", "Oldest cell (steps)"), ("repairs", "Membrane repairs"), ("divisions", "Cell divisions")]
    SERIES = [[("cells", "Cells", "#e5602a"), ("rings", "Rings", "#f2b33d"), ("catalysts", "Catalysts", "#3f97b5")],
              [("oldest_cell", "Oldest cell", "#a8c94a"), ("mean_cell_age", "Average cell age", "#8fd3c8")],
              [("produce_mean", "Link-making rate", "#c9b6ff"), ("stick_mean", "Stickiness", "#e58bb0")]]
    JOURNAL_HINT = ("This is a chemistry of membranes and catalysts, not organisms. Speak of rings, cells, catalysts, "
                    "links, gaps, repairs, divisions and how long cells hold themselves together.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.sx, self.sy = rng.uniform(0, W, CAP_S).astype(np.float32), rng.uniform(0, H, CAP_S).astype(np.float32)
        self.s_alive = np.zeros(CAP_S, bool)
        self.s_alive[:2200] = True
        self.lx, self.ly = np.zeros(CAP_L, np.float32), np.zeros(CAP_L, np.float32)
        self.l_alive = np.zeros(CAP_L, bool)
        self.nb = np.full((CAP_L, 2), -1, np.int32)
        self.kx, self.ky = np.zeros(CAP_K, np.float32), np.zeros(CAP_K, np.float32)
        self.k_alive = np.zeros(CAP_K, bool)
        self.KG = np.zeros((CAP_K, K_GENES), np.float32)
        self.kage, self.kid = np.zeros(CAP_K, np.int32), np.zeros(CAP_K, np.int64)
        self.kfam = np.zeros(CAP_K, np.int64)
        self.kin = np.zeros(CAP_K, np.int32)          # ring id the catalyst sits in (-1 none)
        self.kshel = np.zeros(CAP_K, bool)            # inside its membrane, or repairing a gap in it
        self.next_id = 1
        self.cells = {}               # ring key -> {"born", "k"} ; keyed by catalyst id
        self.rings = []               # list of lists of link indices
        self.ring_of = np.full(CAP_L, -1, np.int32)
        self.repairs = self.divisions = 0
        self.best_age = 0
        for _ in range(16):
            g = LO + (HI - LO) * rng.random(K_GENES).astype(np.float32)
            self._new_k(rng.uniform(100, W - 100), rng.uniform(100, H - 100), g, None)

    def _new_k(self, x, y, g, fam):
        free = np.flatnonzero(~self.k_alive)
        if not len(free):
            return None
        i = int(free[0])
        self.k_alive[i] = True
        self.kx[i], self.ky[i] = x, y
        self.KG[i] = np.clip(g, LO, HI)
        self.KG[i, 3] %= 1.0
        self.kage[i] = 0
        self.kid[i] = self.next_id
        self.kfam[i] = fam if fam else self.next_id
        self.next_id += 1
        self.kin[i] = -1
        self.kshel[i] = False
        return i

    def _new_l(self, x, y):
        free = np.flatnonzero(~self.l_alive)
        if not len(free):
            return None
        i = int(free[0])
        self.l_alive[i] = True
        self.lx[i], self.ly[i] = np.clip(x, 2, W - 2), np.clip(y, 2, H - 2)
        self.nb[i] = -1
        return i

    def _unbond(self, i):
        for j in self.nb[i]:
            if j >= 0:
                self.nb[j][self.nb[j] == i] = -1
        self.nb[i] = -1

    def _bond(self, a, b):
        sa = np.flatnonzero(self.nb[a] < 0)
        sb = np.flatnonzero(self.nb[b] < 0)
        if not len(sa) or not len(sb):
            return False
        self.nb[a, sa[0]] = b
        self.nb[b, sb[0]] = a
        return True

    # ── one step ─────────────────────────────────────────────────────────
    def _step(self):
        from scipy.spatial import cKDTree
        rng = self.rng
        S = np.flatnonzero(self.s_alive)
        Lk = np.flatnonzero(self.l_alive)
        K = np.flatnonzero(self.k_alive)
        # substrate: free diffusion, steady supply
        self.sx[S] = (self.sx[S] + rng.normal(0, 2.4, len(S))) % W
        self.sy[S] = (self.sy[S] + rng.normal(0, 2.4, len(S))) % H
        if len(S) < 2300:
            free = np.flatnonzero(~self.s_alive)[:6]
            self.s_alive[free] = True
            self.sx[free], self.sy[free] = rng.uniform(0, W, len(free)), rng.uniform(0, H, len(free))
        # links: weak jiggle, springs along bonds, repulsion from crowding links and from catalysts
        if len(Lk):
            fx = rng.normal(0, 0.28, len(Lk)).astype(np.float32)
            fy = rng.normal(0, 0.28, len(Lk)).astype(np.float32)
            idx = np.full(CAP_L, -1, np.int64)
            idx[Lk] = np.arange(len(Lk))
            for s in (0, 1):
                j = self.nb[Lk, s]
                ok = j >= 0
                dx = self.lx[j[ok]] - self.lx[Lk[ok]]
                dy = self.ly[j[ok]] - self.ly[Lk[ok]]
                d = np.hypot(dx, dy) + 1e-6
                f = 0.25 * (d - REST) / d
                fx[ok] += f * dx
                fy[ok] += f * dy
            pos = np.stack([self.lx[Lk], self.ly[Lk]], 1)
            tree = cKDTree(pos)
            pairs = tree.query_pairs(REST * 0.85, output_type="ndarray")
            if len(pairs):
                a, b = pairs[:, 0], pairs[:, 1]
                dx = pos[b, 0] - pos[a, 0]
                dy = pos[b, 1] - pos[a, 1]
                d = np.hypot(dx, dy) + 1e-6
                f = 0.35 * (REST * 0.85 - d) / d
                np.add.at(fx, a, -f * dx); np.add.at(fy, a, -f * dy)
                np.add.at(fx, b, f * dx); np.add.at(fy, b, f * dy)
            if len(K):
                # links shun the catalyst and gather at the edge of its reach, like oil around water:
                # each link is drawn to a shell around its nearest catalyst
                kp = np.stack([self.kx[K], self.ky[K]], 1)
                ktree = cKDTree(kp)
                dk, jk = ktree.query(pos, distance_upper_bound=70.0)
                near = np.isfinite(dk)
                if near.any():
                    q = jk[near]
                    shell = self.KG[K[q], 1] + 16.0
                    dx = pos[near, 0] - kp[q, 0]
                    dy = pos[near, 1] - kp[q, 1]
                    d = np.hypot(dx, dy) + 1e-6
                    f = np.clip(0.12 * (shell - d), -0.8, 1.5) / d
                    fx[near] += (f * dx).astype(np.float32)
                    fy[near] += (f * dy).astype(np.float32)
            # open ends seek each other (links bond only end to end, so this is how gaps close and rings form)
            ends = np.flatnonzero((self.nb[Lk] < 0).any(1))
            if len(ends) > 1:
                et = cKDTree(pos[ends])
                d2, j2 = et.query(pos[ends], k=min(4, len(ends)), distance_upper_bound=34.0)
                for q, e in enumerate(ends):
                    for dd, jj in zip(d2[q][1:], j2[q][1:]):
                        if not np.isfinite(dd) or dd < 1e-3:
                            continue
                        o = ends[jj]
                        if Lk[o] in self.nb[Lk[e]]:
                            continue
                        fx[e] += 0.35 * (pos[o, 0] - pos[e, 0]) / dd
                        fy[e] += 0.35 * (pos[o, 1] - pos[e, 1]) / dd
                        break
            self.lx[Lk] = np.clip(self.lx[Lk] + np.clip(fx, -3, 3), 2, W - 2)
            self.ly[Lk] = np.clip(self.ly[Lk] + np.clip(fy, -3, 3), 2, H - 2)
        # catalysts: slow drift, kept off links (they cannot cross a membrane)
        if len(K):
            nx = self.kx[K] + rng.normal(0, 0.22, len(K))
            ny = self.ky[K] + rng.normal(0, 0.22, len(K))
            if len(Lk):
                tree2 = cKDTree(np.stack([self.lx[Lk], self.ly[Lk]], 1))
                d, _ = tree2.query(np.stack([nx, ny], 1))
                block = d < 10.0
                nx = np.where(block, self.kx[K], nx)
                ny = np.where(block, self.ky[K], ny)
            self.kx[K], self.ky[K] = np.clip(nx, 20, W - 20), np.clip(ny, 20, H - 20)
            self.kage[K] += 1
        if self.tick % 2 == 0:
            self._chemistry()
        if self.tick % 20 == 0:
            self._find_cells()

    def _chemistry(self):
        from scipy.spatial import cKDTree
        rng = self.rng
        S = np.flatnonzero(self.s_alive)
        K = np.flatnonzero(self.k_alive)
        # production: catalyst + two substrate -> link
        if len(K) and len(S) > 2:
            st = cKDTree(np.stack([self.sx[S], self.sy[S]], 1))
            near = st.query_ball_point(np.stack([self.kx[K], self.ky[K]], 1), 22.0)
            Lk0 = np.flatnonzero(self.l_alive)
            crowd = np.zeros(len(K))
            if len(Lk0):
                lt = cKDTree(np.stack([self.lx[Lk0], self.ly[Lk0]], 1))
                for q, i in enumerate(K):
                    crowd[q] = len(lt.query_ball_point([float(self.kx[i]), float(self.ky[i])], float(self.KG[i, 1]) + 26.0))
            for q, i in enumerate(K):
                # product inhibition: a catalyst slows down when its shell is full (a membrane's worth of links)
                full = 2 * math.pi * (float(self.KG[i, 1]) + 16.0) / REST * 1.9
                if crowd[q] > full:
                    continue
                if len(near[q]) >= 2 and rng.random() < self.KG[i, 0]:
                    a, b = S[near[q][0]], S[near[q][1]]
                    if not (self.s_alive[a] and self.s_alive[b]):
                        continue
                    self.s_alive[a] = self.s_alive[b] = False
                    ang, r = rng.uniform(0, 2 * math.pi), self.KG[i, 1]
                    self._new_l(self.kx[i] + r * math.cos(ang), self.ky[i] + r * math.sin(ang))
        # bonding: free ends meet
        Lk = np.flatnonzero(self.l_alive)
        if len(Lk) > 1:
            free_end = Lk[(self.nb[Lk] < 0).any(1)]
            if len(free_end) > 1:
                ft = cKDTree(np.stack([self.lx[free_end], self.ly[free_end]], 1))
                pairs = ft.query_pairs(REST * 2.1, output_type="ndarray")
                rng.shuffle(pairs)
                stick = 0.5
                if len(K):
                    stick = float(self.KG[K, 2].mean())
                for a, b in pairs[:200]:
                    ia, ib = int(free_end[a]), int(free_end[b])
                    if ib in self.nb[ia] or rng.random() > 0.6 * stick:
                        continue
                    # no tiny triangles: the two must not share a neighbour
                    na, nbb = set(self.nb[ia]) - {-1}, set(self.nb[ib]) - {-1}
                    if na & nbb:
                        continue
                    if self._bond(ia, ib):
                        if self.ring_of[ia] >= 0 or self.ring_of[ib] >= 0 or (na and nbb):
                            self.repairs += 1
        # decay: links fall apart into substrate, bonded ones more slowly
        Lk = np.flatnonzero(self.l_alive)
        if len(Lk):
            bonded = (self.nb[Lk] >= 0).sum(1)
            p = np.where(bonded == 2, 0.0005, np.where(bonded == 1, 0.0012, 0.002))
            die = Lk[rng.random(len(Lk)) < p]
            for i in die:
                self._unbond(int(i))
                self.l_alive[i] = False
                free = np.flatnonzero(~self.s_alive)[:2]
                self.s_alive[free] = True
                self.sx[free], self.sy[free] = self.lx[i], self.ly[i]
        # catalysts wear out, fast when exposed
        if len(K):
            p = np.where(self.kshel[K], 0.00003, 0.00015)
            for i in K[rng.random(len(K)) < p]:
                self.k_alive[i] = False
        if self.k_alive.sum() < 14 and rng.random() < 0.01:     # now and then a catalyst drifts in from outside
            g = LO + (HI - LO) * rng.random(K_GENES).astype(np.float32)
            self._new_k(rng.uniform(100, W - 100), rng.uniform(100, H - 100), g, None)
        if self.k_alive.sum() < 3:
            for _ in range(4):
                g = LO + (HI - LO) * rng.random(K_GENES).astype(np.float32)
                self._new_k(rng.uniform(100, W - 100), rng.uniform(100, H - 100), g, None)
            self.event("reseed", "The last catalysts were nearly gone; new ones drift in.")

    # ── rings and cells ──────────────────────────────────────────────────
    def _find_cells(self):
        Lk = np.flatnonzero(self.l_alive)
        two = Lk[(self.nb[Lk] >= 0).all(1)]
        seen = np.zeros(CAP_L, bool)
        rings = []
        for s in two:
            if seen[s]:
                continue
            ring, prev, cur, ok = [int(s)], -1, int(s), False
            seen[s] = True
            for _ in range(600):
                nxt = int(self.nb[cur, 0]) if int(self.nb[cur, 0]) != prev else int(self.nb[cur, 1])
                if nxt < 0 or (self.nb[nxt] < 0).any():
                    break
                if nxt == s:
                    ok = True
                    break
                if seen[nxt]:
                    break
                seen[nxt] = True
                ring.append(nxt)
                prev, cur = cur, nxt
            if ok and len(ring) >= 8:
                rings.append(ring)
        self.rings = rings
        self.ring_of[:] = -1
        for r_i, r in enumerate(rings):
            self.ring_of[r] = r_i
        if rings:
            self.milestone("first_ring", "A chain of links has closed on itself: the first ring.")
        # which catalysts sit inside a ring
        K = np.flatnonzero(self.k_alive)
        self.kin[K] = -1
        inside_count = {}
        for r_i, r in enumerate(rings):
            px, py = self.lx[r], self.ly[r]
            for i in K:
                if _inside(float(self.kx[i]), float(self.ky[i]), px, py):
                    self.kin[i] = r_i
                    inside_count.setdefault(r_i, []).append(int(i))
        # cells live as long as their catalyst stays enclosed
        alive_keys = set()
        for r_i, ks in inside_count.items():
            for i in ks:
                key = int(self.kid[i])
                alive_keys.add(key)
                if key not in self.cells:
                    self.cells[key] = {"born": int(self.tick)}
                    self.milestone("first_cell", "A ring has closed around a catalyst: the first cell, making its own boundary.")
                self.cells[key]["seen"] = int(self.tick)
                age = self.tick - self.cells[key]["born"]
                self.best_age = max(self.best_age, age)
                if age >= 2000:
                    self.milestone("cell2000", "A cell has kept itself whole for two thousand steps, repairing its membrane as it decays.")
                if age >= 20000:
                    self.milestone("cell20000", "A cell has kept itself whole for twenty thousand steps.")
        live_k = {int(self.kid[i]): i for i in K}
        self.kshel[K] = self.kin[K] >= 0
        for key in list(self.cells):
            # a gap that decay opens is closed again within moments; the cell is the same cell while it repairs
            if key in live_k and key not in alive_keys and self.tick - self.cells[key].get("seen", 0) < 600:
                self.kshel[live_k[key]] = True
                continue
            if key not in alive_keys:
                age = self.tick - self.cells[key]["born"]
                if age > 1500:
                    self.event("cell lost", f"A cell that held together for {age:,} steps has opened and lost its catalyst.")
                del self.cells[key]
        # division: a large ring with one well-fed catalyst splits
        for r_i, ks in inside_count.items():
            r = rings[r_i]
            key = int(self.kid[ks[0]])
            age = self.tick - self.cells.get(key, {"born": self.tick})["born"]
            if len(ks) == 1 and len(r) >= 16 and age > 1200 and self.rng.random() < 0.06 * self.KG[ks[0], 0]:
                self._divide(r, ks[0])

    def _divide(self, ring, k):
        rng = self.rng
        n = len(ring)
        i = int(rng.integers(n))
        j = (i + n // 2) % n
        a, b = ring[i], ring[(i + 1) % n]
        c, d = ring[j], ring[(j + 1) % n]
        for (u, v) in ((a, b), (c, d)):
            self.nb[u][self.nb[u] == v] = -1
            self.nb[v][self.nb[v] == u] = -1
        self._bond(a, d)
        self._bond(c, b)
        # the two halves; place a daughter catalyst in each
        half1 = ring[(i + 1) % n:] + ring[:(i + 1) % n] if (i + 1) % n else ring[:]
        side = [ring[(i + 1 + t) % n] for t in range((j - i) % n)]
        other = [x for x in ring if x not in set(side)]
        for grp, kk in ((side, k), (other, None)):
            cx, cy = float(self.lx[grp].mean()), float(self.ly[grp].mean())
            if kk is None:
                g = self.KG[k] + rng.normal(0, 1, K_GENES).astype(np.float32) * STEP
                kk = self._new_k(cx, cy, g, int(self.kfam[k]))
                if kk is None:
                    return
            else:
                self.KG[k] = np.clip(self.KG[k] + rng.normal(0, 1, K_GENES).astype(np.float32) * STEP * 0.5, LO, HI)
            self.kx[kk], self.ky[kk] = cx, cy
        self.divisions += 1
        self.milestone("first_division", "A cell has pinched in two, a catalyst in each half: self-production has become reproduction.")

    # ── measurement ──────────────────────────────────────────────────────
    def stats(self):
        K = np.flatnonzero(self.k_alive)
        Lk = np.flatnonzero(self.l_alive)
        ages = [self.tick - c["born"] for c in self.cells.values()]
        out = {"substrate": int(self.s_alive.sum()), "links": int(len(Lk)),
               "bonds": int((self.nb[Lk] >= 0).sum() // 2) if len(Lk) else 0, "rings": len(self.rings),
               "cells": len(self.cells), "catalysts": int(len(K)),
               "sheltered": int(round(100 * self.kshel[K].mean())) if len(K) else 0,
               "oldest_cell": int(max(ages)) if ages else 0, "mean_cell_age": int(np.mean(ages)) if ages else 0,
               "best_cell_age": int(self.best_age), "repairs": int(self.repairs), "divisions": int(self.divisions)}
        if len(K):
            out.update({"produce_mean": round(float(self.KG[K, 0].mean()), 3), "throw_mean": round(float(self.KG[K, 1].mean()), 2),
                        "stick_mean": round(float(self.KG[K, 2].mean()), 3), "families": int(len(np.unique(self.kfam[K])))})
        return out

    def stratum(self):
        K = np.flatnonzero(self.k_alive)
        cols = []
        if len(K):
            fams, n = np.unique(self.kfam[K], return_counts=True)
            for f in np.argsort(-n)[:6]:
                i = K[self.kfam[K] == fams[f]][0]
                cols.append([round(float(self.KG[i, 3]), 3), 0.8 if self.kin[i] >= 0 else 0.3, int(n[f]) * 10])
        cols.append([0.08, 0.6, max(1, len(self.rings))])
        return {"cols": cols}

    def frame(self):
        S = np.flatnonzero(self.s_alive)[:1200]
        Lk = np.flatnonzero(self.l_alive)
        remap = np.full(CAP_L, -1, np.int64)
        remap[Lk] = np.arange(len(Lk))
        bonds = []
        for i in Lk:
            for j in self.nb[i]:
                if j > i:
                    bonds += [int(remap[i]), int(remap[j])]
        K = np.flatnonzero(self.k_alive)
        cells = []
        for r in self.rings:
            ks = [int(self.kid[k]) for k in K if self.kin[k] >= 0 and self.rings[self.kin[k]] is r]
            hue = float(self.KG[[k for k in K if self.kin[k] >= 0 and self.rings[self.kin[k]] is r][0], 3]) if ks else -1
            cells.append([[int(remap[x]) for x in r], round(hue, 3)])
        return {"w": W, "h": H,
                "substrate": np.stack([np.round(self.sx[S]), np.round(self.sy[S])], 1).astype(int).ravel().tolist(),
                "links": np.stack([np.round(self.lx[Lk], 1), np.round(self.ly[Lk], 1)], 1).ravel().tolist(),
                "bonds": bonds,
                "catalysts": [[int(self.kid[k]), round(float(self.kx[k]), 1), round(float(self.ky[k]), 1),
                               round(float(self.KG[k, 3]), 3), int(self.kin[k] >= 0)] for k in K],
                "rings": cells}


def _inside(x, y, px, py):
    """Point in polygon (ray casting)."""
    n = len(px)
    j = n - 1
    c = False
    for i in range(n):
        if ((py[i] > y) != (py[j] > y)) and (x < (px[j] - px[i]) * (y - py[i]) / (py[j] - py[i] + 1e-9) + px[i]):
            c = not c
        j = i
    return c
