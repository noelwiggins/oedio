"""COSMOGENESIS — the coming into existence of the cosmos.

A patch of the young universe. It begins as an almost smooth gas with ripples too small to see. Gravity pulls the
denser places denser: the gas draws into threads, the threads into knots, and where a knot is dense enough a
star lights. Big stars burn fast and explode, throwing their gas back out enriched with heavier elements made
inside them; small stars burn for ages and fade gently. Each generation of stars forms from gas the earlier ones
have enriched, and only enriched gas can form planets. Fresh gas keeps falling in from the cosmic web.

Nothing here is alive, and nothing is selected; it is the other kind of genesis, in which order comes out of
gravity, and each generation of stars makes the material for the next.
"""
from __future__ import annotations

import math

import numpy as np

from ..dials import D, mult
from .base import World

W, H = 1200.0, 640.0
NX, NY = 120, 64
CELL = W / NX
CAP_G, CAP_S, CAP_R = 3200, 360, 300


class Cosmogenesis(World):
    SLUG = "cosmogenesis"
    TITLE = "Cosmogenesis"
    DEFINITION = "The coming into existence of the cosmos"
    TAGLINE = "Gravity gathers smooth gas into threads, knots and stars; each generation of stars makes the stuff of the next."
    TPS = 12.0
    STATS_EVERY = 240
    EPOCH = 4800
    ABOUT = [
        "A patch of the young universe, beginning as an almost smooth gas with ripples too small to see.",
        "Gravity pulls the denser places denser: the gas draws into threads, the threads into knots, and where a knot is dense enough a star lights. Big stars burn blue and fast and explode; small red stars burn for ages and fade.",
        "Every explosion throws gas back out, enriched with heavier elements made inside the star (the gas turns from aqua toward orange as it is enriched). Each generation of stars forms from what earlier ones left, and only enriched gas can form planets, shown as tiny worlds circling their stars.",
        "Nothing here is alive, and nothing is selected: this is the other kind of genesis, order out of gravity, each generation of stars making the material for the next.",
    ]
    STAT_LABELS = [("stars", "Shining stars"), ("generation", "Latest stellar generation"), ("supernovae", "Supernovae so far"),
                   ("metals", "Heavy elements in the gas (‰)"), ("planets", "Planets now"), ("planets_total", "Planets ever formed"),
                   ("clusters", "Star clusters"), ("remnants", "Remnants (dead stars)"), ("gas", "Gas clouds")]
    SERIES = [[("stars", "Stars", "#f2b33d"), ("clusters", "Clusters ×10", "#e5602a")],
              [("metals", "Heavy elements ‰", "#e58bb0"), ("generation", "Stellar generation", "#c9b6ff")],
              [("planets", "Planets", "#a8c94a")]]
    DIALS = [D("gravity", "Gravity", "atom", "#c9b6ff", "Weak", "Strong",
               "How hard matter pulls on matter. Strong gravity gathers gas fast into crowded clusters; weak gravity leaves it drifting."),
             D("cooling", "Cooling", "snow", "#8fd3c8", "Hot", "Cold",
               "How fast the gas sheds its heat. Cold gas collapses readily into stars; hot gas resists.")]
    JOURNAL_HINT = ("This is cosmology, not biology: gas, gravity, filaments, stars, supernovae, heavy elements, stellar "
                    "generations, clusters and planets. No life.")

    def __init__(self, seed=1, name=""):
        super().__init__(seed, name)
        rng = self.rng
        self.g_alive = np.zeros(CAP_G, bool)
        self.gx, self.gy, self.gvx, self.gvy = (np.zeros(CAP_G, np.float32) for _ in range(4))
        self.gz = np.zeros(CAP_G, np.float32)           # metallicity
        self.ggen = np.zeros(CAP_G, np.int32)          # the stellar generation that last enriched this gas
        n = 2600
        # an almost smooth start: a few long, faint ripples
        xs, ys = rng.uniform(0, W, n), rng.uniform(0, H, n)
        for _ in range(6):
            kx, ky, ph = rng.uniform(1, 4), rng.uniform(1, 3), rng.uniform(0, 2 * math.pi)
            xs += 18 * np.sin(2 * math.pi * kx * ys / H + ph)
            ys += 14 * np.sin(2 * math.pi * ky * xs / W + ph)
        self.g_alive[:n] = True
        self.gx[:n], self.gy[:n] = xs % W, ys % H
        self.s_alive = np.zeros(CAP_S, bool)
        self.sx, self.sy, self.svx, self.svy = (np.zeros(CAP_S, np.float32) for _ in range(4))
        self.sm, self.sz = np.zeros(CAP_S, np.float32), np.zeros(CAP_S, np.float32)
        self.sage, self.slife = np.zeros(CAP_S, np.int32), np.zeros(CAP_S, np.int32)
        self.sgen, self.splan = np.zeros(CAP_S, np.int32), np.zeros(CAP_S, np.int32)
        self.sid = np.zeros(CAP_S, np.int64)
        self.next_id = 1
        self.rx, self.ry = np.zeros(CAP_R, np.float32), np.zeros(CAP_R, np.float32)
        self.r_n = 0
        self.supernovae = self.planets_total = self.max_gen = 0
        self.flashes = []                               # recent explosions, for the panel
        kx = 2 * np.pi * np.fft.fftfreq(NX, d=CELL)
        ky = 2 * np.pi * np.fft.fftfreq(NY, d=CELL)
        k2 = ky[:, None] ** 2 + kx[None, :] ** 2
        k2[0, 0] = 1.0
        self.inv_k2 = (1.0 / k2).astype(np.float32)
        self.inv_k2[0, 0] = 0.0

    # ── gravity on a mesh ────────────────────────────────────────────────
    def _accel(self):
        G = np.flatnonzero(self.g_alive)
        S = np.flatnonzero(self.s_alive)
        rho = np.zeros((NY, NX), np.float32)
        ig = (self.gy[G] / CELL).astype(int) % NY, (self.gx[G] / CELL).astype(int) % NX
        np.add.at(rho, ig, 1.0)
        is_ = (self.sy[S] / CELL).astype(int) % NY, (self.sx[S] / CELL).astype(int) % NX
        np.add.at(rho, is_, self.sm[S])
        rho -= rho.mean()
        phi = np.real(np.fft.ifft2(-np.fft.fft2(rho) * self.inv_k2)) * 0.9 * mult(self.dial("gravity"), 1.8)
        ax = -(np.roll(phi, -1, 1) - np.roll(phi, 1, 1)) / (2 * CELL)
        ay = -(np.roll(phi, -1, 0) - np.roll(phi, 1, 0)) / (2 * CELL)
        return G, S, ig, is_, ax, ay, rho

    def _step(self):
        rng = self.rng
        G, S, ig, is_, ax, ay, rho = self._accel()
        cool = float(np.clip(0.004 * mult(self.dial("cooling"), 2.5), 0.0005, 0.03))
        self.gvx[G] = (self.gvx[G] + ax[ig]) * (1 - cool) + rng.normal(0, 0.02, len(G))
        self.gvy[G] = (self.gvy[G] + ay[ig]) * (1 - cool) + rng.normal(0, 0.02, len(G))
        np.clip(self.gvx, -4, 4, out=self.gvx); np.clip(self.gvy, -4, 4, out=self.gvy)
        self.gx[G] = (self.gx[G] + self.gvx[G]) % W
        self.gy[G] = (self.gy[G] + self.gvy[G]) % H
        if len(S):
            self.svx[S] = np.clip(self.svx[S] + ax[is_], -3, 3) * 0.999
            self.svy[S] = np.clip(self.svy[S] + ay[is_], -3, 3) * 0.999
            self.sx[S] = (self.sx[S] + self.svx[S]) % W
            self.sy[S] = (self.sy[S] + self.svy[S]) % H
            self.sage[S] += 1
        # fresh gas falls in from the cosmic web
        if self.g_alive.sum() < 2400 and rng.random() < 0.5:
            free = np.flatnonzero(~self.g_alive)[:2]
            self.g_alive[free] = True
            self.gx[free], self.gy[free] = rng.uniform(0, W, len(free)), rng.uniform(0, H, len(free))
            self.gvx[free] = self.gvy[free] = 0
            self.gz[free] = 0
            self.ggen[free] = 0
        if self.tick % 3 == 0:
            self._stars(G, ig)
        self.flashes = [f for f in self.flashes if self.tick - f[2] < 120]

    def _stars(self, G, ig):
        rng = self.rng
        # star birth: where a cell holds enough gas
        cnt = np.zeros((NY, NX), np.int32)
        np.add.at(cnt, ig, 1)
        hot = np.argwhere(cnt >= 20)
        rng.shuffle(hot)
        for cy, cx in hot[:3]:
            if rng.random() > 0.07:
                continue
            members = G[(ig[0] == cy) & (ig[1] == cx)]
            members = members[self.g_alive[members]]
            if len(members) < 20:
                continue
            free = np.flatnonzero(~self.s_alive)
            if not len(free):
                break
            k = int(free[0])
            m = float(len(members))
            z = float(self.gz[members].mean())
            gen = int(self.ggen[members].max()) + 1
            self.s_alive[k] = True
            self.sx[k], self.sy[k] = float(self.gx[members].mean()), float(self.gy[members].mean())
            self.svx[k], self.svy[k] = float(self.gvx[members].mean()), float(self.gvy[members].mean())
            self.sm[k], self.sz[k], self.sgen[k], self.sage[k] = m, z, gen, 0
            self.slife[k] = int(np.clip(26000 * (m / 24) ** -2.2, 2500, 90000))
            self.splan[k] = int(rng.poisson(min(4.0, z * 50))) if z > 0.008 else 0
            self.sid[k] = self.next_id
            self.next_id += 1
            self.planets_total += int(self.splan[k])
            self.g_alive[members] = False
            self.max_gen = max(self.max_gen, gen)
            self.milestone("first_star", "The gas has gathered tight enough for the first star to light.")
            if gen >= 2:
                self.milestone("gen2", "A second-generation star has formed, from gas an earlier star made.")
            if gen >= 5:
                self.milestone("gen5", "Fifth-generation stars are forming from gas cycled through four lifetimes of stars.")
            if self.splan[k]:
                self.milestone("planets", "A star has formed with planets: the first solid worlds, made of elements from older stars.")
        # star death
        S = np.flatnonzero(self.s_alive & (self.sage >= self.slife))
        for k in S:
            k = int(k)
            m = float(self.sm[k])
            big = m >= 27
            back = int(m * (0.8 if big else 0.5))
            free = np.flatnonzero(~self.g_alive)[:back]
            ang = rng.uniform(0, 2 * math.pi, len(free))
            v = (2.4 if big else 0.6) * rng.uniform(0.5, 1.0, len(free))
            self.g_alive[free] = True
            self.gx[free] = (self.sx[k] + np.cos(ang) * 4) % W
            self.gy[free] = (self.sy[k] + np.sin(ang) * 4) % H
            self.gvx[free], self.gvy[free] = np.cos(ang) * v + self.svx[k], np.sin(ang) * v + self.svy[k]
            self.gz[free] = self.sz[k] + (0.012 if big else 0.004)
            self.ggen[free] = self.sgen[k]
            self.s_alive[k] = False
            r = self.r_n % CAP_R
            self.rx[r], self.ry[r] = self.sx[k], self.sy[k]
            self.r_n += 1
            if big:
                self.supernovae += 1
                self.flashes.append([round(float(self.sx[k]), 1), round(float(self.sy[k]), 1), int(self.tick)])
                self.milestone("supernova", "A massive star has exploded, seeding the gas with heavier elements.")

    def _clusters(self):
        S = np.flatnonzero(self.s_alive)
        if len(S) < 6:
            return 0
        from scipy.spatial import cKDTree
        pairs = cKDTree(np.stack([self.sx[S], self.sy[S]], 1)).query_pairs(40.0, output_type="ndarray")
        if not len(pairs):
            return 0
        parent = list(range(len(S)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a, b in pairs:
            parent[find(a)] = find(b)
        roots = np.array([find(a) for a in range(len(S))])
        _, n = np.unique(roots, return_counts=True)
        c = int((n >= 6).sum())
        if c and n.max() >= 20:
            self.milestone("cluster20", "Twenty stars have gathered in one cluster.")
        return c

    def stats(self):
        G = np.flatnonzero(self.g_alive)
        S = np.flatnonzero(self.s_alive)
        c = self._clusters()
        return {"stars": int(len(S)), "gas": int(len(G)), "generation": int(self.max_gen), "supernovae": int(self.supernovae),
                "metals": round(1000 * float(self.gz[G].mean()), 2) if len(G) else 0, "planets": int(self.splan[S].sum()),
                "planets_total": int(self.planets_total), "clusters": c, "remnants": int(min(self.r_n, CAP_R))}

    def stratum(self):
        S = np.flatnonzero(self.s_alive)
        cols = []
        if len(S):
            g, n = np.unique(self.sgen[S], return_counts=True)
            for gg, nn in zip(g[-6:], n[-6:]):
                cols.append([round(0.6 - 0.1 * min(int(gg), 5), 3), 0.8, int(nn)])
        cols.append([0.5, 0.3, max(1, int(self.g_alive.sum()) // 60)])
        return {"cols": cols}

    def frame(self):
        G = np.flatnonzero(self.g_alive)
        S = np.flatnonzero(self.s_alive)
        gas = np.stack([np.round(self.gx[G]), np.round(self.gy[G]), np.minimum(9, np.round(self.gz[G] * 120))], 1).astype(int)
        return {"w": W, "h": H, "gas": gas.ravel().tolist(),
                "stars": [[int(self.sid[k]), round(float(self.sx[k]), 1), round(float(self.sy[k]), 1), round(float(self.sm[k]), 1),
                           int(self.splan[k]), round(float(self.sage[k] / max(1, self.slife[k])), 2), int(self.sgen[k])] for k in S],
                "remnants": np.round(np.stack([self.rx[:min(self.r_n, CAP_R)], self.ry[:min(self.r_n, CAP_R)]], 1)).astype(int).ravel().tolist(),
                "flashes": [[f[0], f[1], int(self.tick - f[2])] for f in self.flashes]}
