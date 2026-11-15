"""ALGOLYSIS on the Coast: the underworld of decay and return (v1.3).

The dead are not deleted. A fallen flower and the rotting remains of a carcass become leaf litter in the soil.
Fungal colonies spread mycelium through the ground wherever there is something to digest; what they digest
returns as nutrients that make the soil rich, so flowers grow best where things have died. Well-fed colonies fruit
(mostly in spring and autumn) and scatter spores, which take only where there is fresh litter. Animals may graze
the mushrooms; some colonies evolve poison against them, some evolve foxfire (a glow that draws spore carriers).

Genesis -> stasis -> lysis -> genesis: the counters here feed the panel's three-needle gauge.
"""
from __future__ import annotations

import math

import numpy as np

CAP_M = 160                                    # fungal colonies
(M_HUE, M_CAP, M_SIZE, M_GLOW, M_RATE, M_COLD, M_SPORE, M_TOX, M_SPOTS, M_HUE2) = range(10)
NMG = 10
MLO = np.array([0, 0, 0.5, 0, 0.2, 0, 0, 0, 0, 0], np.float32)
MHI = np.array([1, 1, 1.6, 1, 1, 1, 1, 1, 1, 1], np.float32)
MSTEP = np.array([.03, .06, .06, .05, .05, .04, .05, .05, .06, .04], np.float32)
MCIRC = (M_HUE, M_HUE2)
MLOOK_KEYS = ["hue", "cap", "size", "glow", "rate", "cold", "spore", "tox", "spots", "hue2"]
_ROOT_M = ["Myc", "Agar", "Lepi", "Coprin", "Marasm", "Psil", "Russ", "Lacc", "Hygr", "Clitoc"]


def _mlook(g):
    return [round(float(g[M_HUE]), 3), round(float(g[M_CAP]), 2), round(float(g[M_SIZE]), 2), round(float(g[M_GLOW]), 2),
            round(float(g[M_RATE]), 2), round(float(g[M_COLD]), 2), round(float(g[M_SPORE]), 2), round(float(g[M_TOX]), 2),
            round(float(g[M_SPOTS]), 2), round(float(g[M_HUE2]), 3)]


def fungus_name(h, g, ep):
    root = "Lumin" if g[M_GLOW] > 0.5 else "Amanit" if g[M_TOX] > 0.6 else _ROOT_M[(h >> 9) % len(_ROOT_M)]
    suf = "ella" if g[M_CAP] < 0.35 else "ius" if g[M_CAP] < 0.7 else "ota"
    return f"{root}{suf} {ep}"


class FungiMixin:
    """Mixed into the Coast's World. Needs: rng, tick, W/H, coarse grid helpers, temp(), height(), sea, species."""

    def _fungi_init(self, seed_colonies=True):
        from .engine import GX, GY
        cg = (GY // 3, GX // 3)
        self.litter = np.zeros(cg, np.float32)        # dead leaves, flowers, the remains of the dead
        self.soil = np.zeros(cg, np.float32)          # nutrients returned by decay: the flowers' next meal
        if not hasattr(self, "carrion"):
            self.carrion = np.zeros(cg, np.float32)
        self.m_alive = np.zeros(CAP_M, bool)
        self.m_id = np.zeros(CAP_M, np.int64)
        self.mx = np.zeros(CAP_M, np.float32)
        self.my = np.zeros(CAP_M, np.float32)
        self.me = np.zeros(CAP_M, np.float32)
        self.mage = np.zeros(CAP_M, np.int32)
        self.mlife = np.zeros(CAP_M, np.int32)
        self.mfruit = np.zeros(CAP_M, np.float32)      # 0 = underground only; rises to 1 as mushrooms grow, then sheds spores
        self.mgen = np.zeros(CAP_M, np.int32)
        self.msp = np.zeros(CAP_M, np.int64)
        self.M = np.zeros((CAP_M, NMG), np.float32)
        self.lysis = {"born": 0, "died": 0, "decomposed": 0.0, "returned": 0.0, "spores": 0, "eaten": 0, "poisoned": 0}
        self._gsl_prev = None
        self.gsl = [0.3, 0.6, 0.3]
        if seed_colonies:
            for _ in range(14):
                self._seed_fungus()

    # ── helpers ──────────────────────────────────────────────────────────
    def _cell(self, x, y):
        from .engine import GX, GY, W, H
        cx = np.clip((np.asarray(x) / W * (GX // 3)).astype(int), 0, GX // 3 - 1)
        cy = np.clip((np.asarray(y) / H * (GY // 3)).astype(int), 0, GY // 3 - 1)
        return cy, cx

    def litter_add(self, x, y, amount):
        if not hasattr(self, "litter") or not len(np.atleast_1d(x)):
            return
        cy, cx = self._cell(x, y)
        np.add.at(self.litter, (cy, cx), np.broadcast_to(np.asarray(amount, np.float32), np.shape(cy)).astype(np.float32))

    def _m_emax(self, g):
        return 30.0 * float(g[M_SIZE])

    def _seed_fungus(self, x=None, y=None):
        from .engine import W, H
        rng = self.rng
        g = np.zeros(NMG, np.float32)
        g[M_HUE], g[M_HUE2] = rng.uniform(0.02, 0.14), rng.uniform(0, 1)      # browns, tans and ochres to begin
        g[M_CAP], g[M_SIZE], g[M_GLOW] = rng.uniform(0.2, 0.6), rng.uniform(0.7, 1.1), rng.uniform(0, 0.08)
        g[M_RATE], g[M_COLD], g[M_SPORE] = rng.uniform(0.35, 0.6), rng.uniform(0, 0.2), rng.uniform(0.3, 0.6)
        g[M_TOX], g[M_SPOTS] = rng.uniform(0, 0.1), rng.uniform(0, 0.4)
        for _ in range(30):
            px = rng.uniform(40, W - 40) if x is None else x
            py = rng.uniform(40, H - 40) if y is None else y
            if self.height(np.array([px]), np.array([py]))[0] - self.sea > 0.02:
                return self._spawn_fungus(g, px, py, 0, None, 8.0)
        return None

    def _spawn_fungus(self, g, x, y, gen, parent, energy):
        from .engine import W, H
        free = np.flatnonzero(~self.m_alive)
        if not len(free):
            return None
        i = int(free[0])
        self.m_alive[i] = True
        self.m_id[i] = self.next_id; self.next_id += 1
        self.M[i] = g
        self.mx[i], self.my[i] = np.clip(x, 4, W - 4), np.clip(y, 4, H - 4)
        self.me[i] = min(energy, self._m_emax(g))
        self.mage[i] = 0
        self.mlife[i] = int(self.rng.uniform(6, 14) * 2400)
        self.mfruit[i] = 0
        self.mgen[i] = gen
        self.msp[i] = self._species_of("fungus", g, parent, gen)
        self.lysis["born"] += 1
        return i

    # ── a step underground (every 4 ticks) ───────────────────────────────
    def _fungi_step(self, light):
        from .engine import W, H, DAY, _clip
        rng = self.rng
        if not hasattr(self, "m_alive"):
            return
        L = self.lysis
        # the carcass rots: what the scavengers leave becomes litter; old litter slowly crumbles on its own
        rot = self.carrion * 0.015
        self.carrion -= rot
        self.litter += 0.8 * rot
        self.litter *= 0.9994
        self.soil *= 0.9992                                           # rain leaches the soil
        idx = np.flatnonzero(self.m_alive)
        if (len(idx) < 3 and self.tick % 600 == 0) or not getattr(self, "_m_seeded", False):
            self._m_seeded = True
            for _ in range(4 if len(idx) else 14):
                self._seed_fungus()
            idx = np.flatnonzero(self.m_alive)
        if not len(idx):
            return
        gy, gx = self.litter.shape
        cw, ch = W / gx, H / gy
        Mg = self.M[idx]
        T = self.temp(self.height(self.mx[idx], self.my[idx]) - self.sea, light)
        tf = np.clip((T - (2 - 12 * Mg[:, M_COLD])) / 14, 0.08, 1)
        emax = 30.0 * Mg[:, M_SIZE]
        reach = 26 + 52 * np.sqrt(np.clip(self.me[idx] / emax, 0, 1))      # the mycelium spreads as the colony grows
        for k, i in enumerate(idx):
            x0, y0, r = float(self.mx[i]), float(self.my[i]), float(reach[k])
            c0, c1 = max(0, int((x0 - r) / cw)), min(gx - 1, int((x0 + r) / cw))
            r0, r1 = max(0, int((y0 - r) / ch)), min(gy - 1, int((y0 + r) / ch))
            eat = 0.0
            rate = 0.022 * float(Mg[k, M_RATE]) * float(tf[k])
            for cy in range(r0, r1 + 1):
                for cx in range(c0, c1 + 1):
                    take = min(float(self.litter[cy, cx]), rate * float(self.litter[cy, cx]) + 0.004 * float(Mg[k, M_RATE]))
                    meat = float(self.carrion[cy, cx]) * rate * 0.35
                    if take <= 0 and meat <= 0:
                        continue
                    self.litter[cy, cx] -= take
                    self.carrion[cy, cx] -= meat
                    got = take + meat
                    self.soil[cy, cx] += 0.7 * got                             # the return: digested dead become rich soil
                    eat += got
            L["decomposed"] += eat
            L["returned"] += 0.7 * eat
            g = Mg[k]
            upkeep = 0.010 * g[M_SIZE] + 0.012 * g[M_RATE] * tf[k] + 0.006 * g[M_GLOW] + 0.006 * g[M_TOX] + 0.003 * g[M_COLD]
            self.me[i] = min(self.me[i] + 1.6 * eat - upkeep, emax[k])
            self.mage[i] += 4
            # the mycelium creeps outward underground: a full colony buds a new one at the edge of its reach (fairy rings)
            if self.me[i] > 0.85 * emax[k] and rng.random() < 0.02:
                a_ = rng.uniform(0, 2 * math.pi)
                x1, y1 = x0 + math.cos(a_) * r * 1.1, y0 + math.sin(a_) * r * 1.1
                if 4 < x1 < W - 4 and 4 < y1 < H - 4 and self.height(np.array([x1]), np.array([y1]))[0] - self.sea > 0.01:
                    j = self._spawn_fungus(self._mutate(g, MLO, MHI, MSTEP * 0.5, MCIRC), x1, y1, int(self.mgen[i]) + 1, int(self.msp[i]), 0.35 * float(self.me[i]))
                    if j is not None:
                        self.me[i] *= 0.6
            # fruiting: a well-fed colony puts up mushrooms, most of all in spring and autumn
            spring_autumn = abs(math.cos(2 * math.pi * (self.tick % (36 * DAY)) / (36 * DAY)))
            if self.mfruit[i] <= 0 and self.me[i] > 0.6 * emax[k] and rng.random() < 0.03 * (0.3 + 0.7 * spring_autumn) * tf[k]:
                self.mfruit[i] = 0.02
                self.me[i] *= 0.65
            elif self.mfruit[i] > 0:
                self.mfruit[i] += 4 / (0.35 * DAY)
                if self.mfruit[i] >= 1.0 + 4.0 * 1.0:                          # about a day and a half above ground, then spores
                    self._shed_spores(i)
                    self.mfruit[i] = 0
        # grazers: an animal that eats plants may eat a mushroom; a poisonous one makes it ill
        fr = idx[self.mfruit[idx] > 0.4]
        F = np.flatnonzero(self.f_alive)
        if len(fr) and len(F):
            from .engine import DIET
            herb = np.clip(1 - self.G[F, DIET] * 1.3, 0, 1)
            for i in fr:
                d = np.hypot(self.fx[F] - self.mx[i], self.fy[F] - self.my[i])
                near = F[(d < 12) & (herb > 0.3)]
                if not len(near) or rng.random() > 0.1:
                    continue
                a = int(near[0])
                tox = float(self.M[i, M_TOX])
                self.fe[a] += 5.0 * float(self.M[i, M_SIZE]) * (1 - tox) - 14.0 * tox * tox
                self.mfruit[i] = max(0.0, self.mfruit[i] - 0.6)             # a grazed mushroom loses many of its spores
                L["eaten"] += 1
                if tox > 0.5:
                    L["poisoned"] += 1
        dead = idx[(self.me[idx] <= 0) | (self.mage[idx] > self.mlife[idx])]
        if len(dead):
            self.m_alive[dead] = False
            self.litter_add(self.mx[dead], self.my[dead], 2.0 * self.M[dead, M_SIZE])   # even the decomposers decompose
            L["died"] += len(dead)

    def _shed_spores(self, i):
        from .engine import W, H, _clip
        rng = self.rng
        g0 = self.M[i]
        n = int(2 + round(7 * g0[M_SPORE]))
        self.me[i] -= 1.5 * n * 0.3
        mates = np.flatnonzero(self.m_alive & (self.msp == self.msp[i]))
        mates = mates[(mates != i) & (np.hypot(self.mx[mates] - self.mx[i], self.my[mates] - self.my[i]) < 160)]
        for _ in range(n):
            self.lysis["spores"] += 1
            ang, dist = rng.uniform(0, 2 * math.pi), rng.uniform(40, 220 * (0.6 + 0.4 * g0[M_SPORE]))
            x, y = float(self.mx[i]) + math.cos(ang) * dist, float(self.my[i]) + math.sin(ang) * dist
            if not (4 < x < W - 4 and 4 < y < H - 4) or self.height(np.array([x]), np.array([y]))[0] - self.sea < 0.01:
                continue
            cy, cx = self._cell(x, y)
            food = float(self.litter[cy, cx] + self.carrion[cy, cx])
            # a spore takes only on fresh litter; foxfire draws night insects that carry spores to better ground
            p = (food / (food + 3.0)) * (0.5 + 0.5 * g0[M_SPORE]) * (1 + 1.2 * g0[M_GLOW]) * 0.9
            if rng.random() > p:
                continue
            g = g0
            if len(mates) and rng.random() < 0.6:                          # mycelia of one kind fuse and mix their genes
                g = self._cross(g0, self.M[int(rng.choice(mates))])
            from .engine import _clip as clip
            g = self._mutate(g, MLO, MHI, MSTEP, MCIRC)
            self._spawn_fungus(g, x, y, int(self.mgen[i]) + 1, int(self.msp[i]), 4.0)

    # ── the soil feeds the flowers ───────────────────────────────────────
    def soil_boost(self, px, py, gain):
        """Rich soil makes a plant grow faster; it takes what it uses from the soil."""
        if not hasattr(self, "soil") or not len(px):
            return gain
        cy, cx = self._cell(px, py)
        s = self.soil[cy, cx]
        boost = 1 + 0.9 * s / (s + 2.5)
        use = gain * (boost - 1) * 0.5
        np.subtract.at(self.soil, (cy, cx), use.astype(np.float32))
        np.maximum(self.soil, 0, out=self.soil)
        return gain * boost

    # ── what the panel shows ─────────────────────────────────────────────
    def fungi_frame(self):
        if not hasattr(self, "m_alive"):
            return [], None
        idx = np.flatnonzero(self.m_alive)
        emax = 30.0 * self.M[idx, M_SIZE]
        reach = 26 + 52 * np.sqrt(np.clip(self.me[idx] / np.maximum(emax, 1e-6), 0, 1))
        rows = [[int(self.m_id[i]), round(float(self.mx[i]), 1), round(float(self.my[i]), 1), round(float(reach[k]), 1),
                 int(self.msp[i]), round(min(1.0, float(self.mfruit[i])) if self.mfruit[i] < 1 else max(0.0, 1 - (float(self.mfruit[i]) - 1) / 4), 2),
                 *_mlook(self.M[i])] for k, i in enumerate(idx)]
        q = lambda a, s: bytes(np.clip(a * s, 0, 255).astype(np.uint8).ravel()).hex()
        under = {"gx": int(self.litter.shape[1]), "gy": int(self.litter.shape[0]),
                 "litter": q(self.litter, 12.0), "soil": q(self.soil, 12.0), "carrion": q(self.carrion, 6.0)}
        return rows, under

    def fungi_stats(self):
        if not hasattr(self, "m_alive"):
            return {}
        idx = np.flatnonzero(self.m_alive)
        out = {"fungi": int(len(idx)), "fruiting": int((self.mfruit[idx] > 0.3).sum()),
               "fungus_species": int(len(np.unique(self.msp[idx]))) if len(idx) else 0,
               "litter": round(float(self.litter.sum()), 1), "soil": round(float(self.soil.sum()), 1),
               "carrion_left": round(float(self.carrion.sum()), 1),
               "decomposed": round(float(self.lysis["decomposed"]), 1), "spores": int(self.lysis["spores"]),
               "mushrooms_eaten": int(self.lysis["eaten"]), "poisoned": int(self.lysis["poisoned"]),
               "gsl": [round(float(v), 3) for v in getattr(self, "gsl", [0, 0, 0])]}
        if len(idx):
            Mg = self.M[idx]
            out.update({"foxfire": round(float((Mg[:, M_GLOW] > 0.5).mean()), 3), "toxic": round(float((Mg[:, M_TOX] > 0.5).mean()), 3),
                        "fungus_cold": round(float(Mg[:, M_COLD].mean()), 3)})
        return out

    def update_gsl(self, n_alive, born_total, died_total, minutes_ticks):
        """The three needles: genesis (new life per head), lysis (death and decay per head), stasis (what persists)."""
        cur = (born_total, died_total, float(self.lysis["decomposed"]), self.tick)
        prev = getattr(self, "_gsl_prev", None)
        self._gsl_prev = cur
        if prev is None or cur[3] <= prev[3]:
            return
        days = (cur[3] - prev[3]) / 2400.0
        n = max(1.0, float(n_alive))
        b = (cur[0] - prev[0]) / n / days
        d = (cur[1] - prev[1]) / n / days
        dec = (cur[2] - prev[2]) / n / days
        g = 1 - math.exp(-b * 1.2)
        l = 1 - math.exp(-(d * 1.2 + dec * 0.15))
        s = math.exp(-(b + d) * 0.6)
        old = getattr(self, "gsl", [g, s, l])
        self.gsl = [round(0.7 * o + 0.3 * v, 4) for o, v in zip(old, (g, s, l))]
