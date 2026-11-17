"""ALGOGENESIS — an evolving world for one display panel.

This module is the whole world and depends only on numpy and scipy, so the same file runs in the cloud (Oedio's
server) and on a small computer behind the panel. Nothing is scripted: what the panel shows is what evolved.

The world, in brief
- A coast on a 3:2 panel: deep water, shallows, a shoreline, meadows inland. The sea rises and falls over weeks.
- Flowering plants grow where light, water and space allow. To set seed they need pollen, which only animals
  carry, and an animal carries pollen only between flowers it is drawn to. Flowers and their pollinators co-evolve.
- Animals are grown from genes: segments, limb pairs, size, tail, crest, fins, colour, a second colour laid out
  as stripes or spots, and bioluminescence. They also carry a diet (nectar to meat), a flower preference, a mate
  preference and how choosy they are, plus the weights of a simple brain (food, fear, mates, wandering).
- Beauty has a reason. Mates are chosen by colour and conspicuousness (sexual selection, as in birds and
  flowers), and the same conspicuousness makes an animal easier for predators to find. By day colour shows;
  at night only light does. So colour, pattern and glow evolve under a real trade-off, not as decoration.
- Lessons from the tidal pool are built in: every species pays more upkeep the more of the world it holds
  (its own parasites and specialist enemies), and the world keeps a bank of past lineages (refugia) that
  recolonise after a near-extinction instead of restarting from nothing.
- A fossil record: every epoch the leading species are laid down as a stratum.
- Seasons and warm blood (v1.2): a 36-day year, cold nights, cold uplands, a mild sea. Cold-blooded animals slow
  down in the cold but live cheaply; an animal can evolve endothermy (it stays active in any weather, at a high
  running cost, and small bodies lose heat fastest) and insulation (fur or feathers: less heat lost, but it overheats
  in summer). Warm parents keep their young warm. Flowers can evolve frost-hardiness. The sea grows plankton,
  so swimmers have food of their own; and animals recognise their own kin by colour and do not hunt them.
- The underworld (v1.3, fungi.py): the dead become litter, fungi digest it and return it as rich soil, mushrooms
  fruit and spread spores. Genesis, stasis and lysis are measured for the panel's gauge.
"""
from __future__ import annotations

import math
import pickle
import zlib

import numpy as np

from .dials import D, DialsMixin, mult
from .fungi import FungiMixin, _mlook, fungus_name, M_HUE, M_CAP, M_TOX, M_GLOW, M_COLD, M_RATE, M_SIZE, MLOOK_KEYS

VERSION = "algogenesis-1.4"
W, H = 1200.0, 800.0              # world units; a 4' x 6' panel is 3:2
GX, GY = 90, 60                   # terrain grid
DAY = 2400                        # ticks per day (about two minutes at 20 ticks/s)
EPOCH = 12 * DAY                  # a fossil stratum and a chronicle entry
YEAR = 36 * DAY                   # one turn of the seasons (about 72 minutes at 20 ticks/s)
LAPSE = 26.0                      # degrees lost per unit of height above the sea
STATS_EVERY = 600
CAP_F, CAP_P = 420, 900           # animals, plants
SENSE = 60.0
BANK_MAX = 40
MATURE = 700                      # ticks until an animal is grown: before that it is small, slow and easy prey

# animal genes
(HUE, SAT, HUE2, PATTERN, GLOW, SEGS, LIMBS, SIZE, TAIL, CREST, FIN, DIET,
 PREF_FLOWER, PREF_MATE, CHOOSY, W_FOOD, W_FLEE, W_MATE, WANDER, REPRO, CARE, ENDO, INSUL,
 EYES, SHELL, WING, SPEC) = range(27)
NG = 27
# Nov 17, the open kit: four organs that can evolve from nothing, each with a job and a price.
#   EYES  sharp eyes: hunters spot prey further off and in poor light; prey see hunters coming
#   SHELL armour plates: hard to bite, heavy to carry
#   WING  wings: on land, a glide that outruns hunters and lets walkers cross water
#   SPEC  a body in regions (head, thorax, abdomen): jaws for the hunter, a better gut for the grazer;
#         only works on bodies of three or more segments
ORGANS = (EYES, SHELL, WING, SPEC)
CIRC = {HUE, HUE2, PREF_FLOWER, PREF_MATE}
LO = np.array([0, 0, 0, 0, 0, 1, 0, 0.6, 0, 0, 0, 0, 0, 0, 0, -1, -1, -1, 0, 0.45, 0, 0, 0, 0, 0, 0, 0], np.float32)
HI = np.array([1, 1, 1, 1, 1, 12, 6, 2.6, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 1, 0.9, 1, 1, 1, 1, 1, 1, 1], np.float32)
STEP = np.array([.03, .04, .04, .06, .04, .35, .25, .08, .05, .05, .05, .04, .03, .03, .04, .15, .15, .15, .05, .02,
                 .04, .04, .05, .05, .05, .05, .05], np.float32)
# plant genes
P_HUE, P_PETALS, P_SIZE, P_NECTAR, P_HEIGHT, P_SAT, P_HUE2, P_COLD = range(8)
NPG = 8
PLO = np.array([0, 3, 0.6, 0.05, 0.3, 0.2, 0, 0], np.float32)
PHI = np.array([1, 9, 2.0, 1.0, 1.6, 1.0, 1, 1], np.float32)
PSTEP = np.array([.025, .3, .05, .05, .05, .04, .04, .04], np.float32)

JC, JC_FREE = 1.2, 0.18           # specialist enemies of the commonest species


def _hd(a, b):
    """Distance between two hues (the colour wheel wraps)."""
    d = np.abs(a - b) % 1.0
    return np.minimum(d, 1.0 - d)


def _clip(g, lo, hi, circ=()):
    for k in circ:
        g[..., k] %= 1.0
    return np.clip(g, lo, hi)


class World(DialsMixin, FungiMixin):
    TPS = 20.0
    DIALS = [D("flora", "Flora", "leaf", "#a8c94a", "Sparse", "Lush",
               "Feeds the flowers: turned up, plants grow faster, spread more and their seeds vary more; turned down, the meadows thin out and change slowly."),
             D("fauna", "Fauna", "fish", "#e5602a", "Lean", "Teeming",
               "Feeds the animals: turned up, life is cheaper to live and their young vary more; turned down, every animal must earn its keep.")]

    def __init__(self, seed: int = 1, name: str = "Panel I"):
        self.seed, self.name, self.version = seed, name, VERSION
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.terrain = self._make_terrain()
        self.sea = 0.0
        # animals
        self.f_alive = np.zeros(CAP_F, bool)
        self.f_id = np.zeros(CAP_F, np.int64)
        self.fx, self.fy, self.fh = (np.zeros(CAP_F, np.float32) for _ in range(3))
        self.fe, self.fage, self.flife = np.zeros(CAP_F, np.float32), np.zeros(CAP_F, np.int32), np.zeros(CAP_F, np.int32)
        self.fgen, self.fsp = np.zeros(CAP_F, np.int64), np.zeros(CAP_F, np.int64)
        # vigour: inherited condition. Copying errors wear it down every generation; a choosy parent that picks
        # the brightest display (which only a vigorous animal can afford) passes good condition on. This is
        # the "good genes" reason colour and choosiness pay, as in birds of paradise.
        self.fvig = np.ones(CAP_F, np.float32)
        # families: each young animal knows its parent. A parent with the CARE gene shares food with its
        # young and guards them; young of caring parents follow them. Care costs the parent and pays only
        # if more of its young live to grow up.
        self.fpar = np.full(CAP_F, -1, np.int64)
        self.fparid = np.zeros(CAP_F, np.int64)
        self.fed_young = 0
        self.fpollen = np.full((CAP_F, NPG), np.nan, np.float32)   # pollen carried (the donor's genes)
        self.fpsp = np.zeros(CAP_F, np.int64)                         # donor plant's species
        self.G = np.zeros((CAP_F, NG), np.float32)
        # plants
        self.p_alive = np.zeros(CAP_P, bool)
        self.p_id = np.zeros(CAP_P, np.int64)
        self.px, self.py = np.zeros(CAP_P, np.float32), np.zeros(CAP_P, np.float32)
        self.pe, self.page, self.plife = np.zeros(CAP_P, np.float32), np.zeros(CAP_P, np.int32), np.zeros(CAP_P, np.int32)
        self.pnec = np.zeros(CAP_P, np.float32)
        self.psp, self.pgen = np.zeros(CAP_P, np.int64), np.zeros(CAP_P, np.int64)
        self.ppollen = np.full((CAP_P, NPG), np.nan, np.float32)
        self.P = np.zeros((CAP_P, NPG), np.float32)
        self.plank = np.zeros((GY // 3, GX // 3), np.float32)        # plankton in the sea, food for swimmers
        self.carrion = np.zeros((GY // 3, GX // 3), np.float32)      # the dead, food for scavengers
        self.firsts = set()
        self._fungi_init(seed_colonies=False)
        self.next_id = 1
        self.species = {}          # sid -> {kind, founder genes, name, born, parent, peak}
        self.next_sid = 1
        self.births = self.deaths = self.kills = self.pollinations = 0
        self.strata, self.events, self.bank = [], [], []
        self.history = []          # compact stats, one per STATS_EVERY
        self.extinct = 0
        self.restarts = 0
        self.last_stats = None
        self.max_gen = 0
        for _ in range(140):
            self._seed_plant()
        for _ in range(10):              # ten founding kinds, a small band of each
            self._seed_animal(band=7)

    # ── terrain ──────────────────────────────────────────────────────────
    def _make_terrain(self):
        rng = self.rng
        yy, xx = np.mgrid[0:GY, 0:GX].astype(np.float32)
        u, v = xx / GX, yy / GY
        h = 0.9 * (u - 0.42)                                   # a coast: sea to the west, land to the east
        for _ in range(14):                                    # islands, bays, hills
            cx, cy, r = rng.uniform(0, 1), rng.uniform(0, 1), rng.uniform(0.05, 0.22)
            h += rng.normal(0, 0.28) * np.exp(-(((u - cx) * 1.5) ** 2 + (v - cy) ** 2) / (2 * r * r))
        for k in range(1, 5):
            h += 0.05 / k * np.sin(2 * math.pi * (k * u * rng.uniform(1, 2) + rng.random())) * \
                np.cos(2 * math.pi * (k * v * rng.uniform(1, 2) + rng.random()))
        h = (h - np.median(h)) / (np.abs(h).max() + 1e-6)
        return h.astype(np.float32)

    def height(self, x, y):
        gx = np.clip((np.asarray(x) / W * GX).astype(int), 0, GX - 1)
        gy = np.clip((np.asarray(y) / H * GY).astype(int), 0, GY - 1)
        return self.terrain[gy, gx]

    def daylight(self, t=None):
        t = self.tick if t is None else t
        return float(np.clip(0.5 + 0.75 * math.sin(2 * math.pi * t / DAY), 0, 1))

    # ── climate ──────────────────────────────────────────────────────────
    def season(self, t=None):
        """+1 at midsummer, -1 at midwinter."""
        t = self.tick if t is None else t
        return math.sin(2 * math.pi * t / YEAR)

    def air(self, light=None):
        """Air temperature at sea level on land, in degrees: the season, and the warmth of the day."""
        light = self.daylight() if light is None else light
        return 15.0 + 10.0 * self.season() + 10.0 * (light - 0.5)

    def water_temp(self):
        return 13.0 + 4.0 * self.season()          # the sea is slow to warm and slow to cool

    def temp(self, depth, light=None):
        return np.where(depth < 0, self.water_temp(), self.air(light) - LAPSE * np.maximum(depth, 0)).astype(np.float32)

    def season_name(self):
        ph = (self.tick % YEAR) / YEAR
        return ["spring", "summer", "autumn", "winter"][int(((ph + 0.125) % 1.0) * 4) % 4]

    def _sea_level(self):
        t = self.tick
        return 0.10 * math.sin(2 * math.pi * t / (DAY * 120)) + 0.04 * math.sin(2 * math.pi * t / (DAY * 23) + 1.3)

    # ── births ───────────────────────────────────────────────────────────
    def _new_species(self, kind, genes, parent, gen):
        sid = self.next_sid
        self.next_sid += 1
        self.species[sid] = {"kind": kind, "g": genes.copy(), "name": species_name(sid, kind, genes),
                             "born": int(self.tick), "parent": parent, "peak": 0, "gen": int(gen)}
        self._fossil(sid)
        return sid

    def _species_of(self, kind, genes, parent, gen):
        f = self.species.get(parent)
        if f is not None:
            if kind == "animal":
                d = _hd(genes[HUE], f["g"][HUE]) * 3 + _hd(genes[PREF_MATE], f["g"][PREF_MATE]) * 2 + \
                    abs(genes[SEGS] - f["g"][SEGS]) / 3 + abs(genes[LIMBS] - f["g"][LIMBS]) / 2 + \
                    abs(genes[DIET] - f["g"][DIET]) * 2 + abs(genes[FIN] - f["g"][FIN]) + abs(genes[GLOW] - f["g"][GLOW]) + \
                    abs(genes[ENDO] - f["g"][ENDO]) * 2 + abs(genes[INSUL] - f["g"][INSUL])
            elif kind == "fungus":
                d = _hd(genes[M_HUE], f["g"][M_HUE]) * 4 + abs(genes[M_CAP] - f["g"][M_CAP]) * 1.5 + \
                    abs(genes[M_TOX] - f["g"][M_TOX]) * 2 + abs(genes[M_GLOW] - f["g"][M_GLOW]) * 1.5 + \
                    abs(genes[M_COLD] - f["g"][M_COLD]) * 1.5 + abs(genes[M_SIZE] - f["g"][M_SIZE])
            else:
                d = _hd(genes[P_HUE], f["g"][P_HUE]) * 4 + abs(genes[P_PETALS] - f["g"][P_PETALS]) / 3 + \
                    abs(genes[P_SIZE] - f["g"][P_SIZE]) + abs(genes[P_COLD] - f["g"][P_COLD]) * 1.5
            if d < 0.9:
                return parent
        return self._new_species(kind, genes, parent, gen)

    def _spawn_animal(self, g, x, y, gen, parent, energy, vig=1.0, mother=-1):
        free = np.flatnonzero(~self.f_alive)
        if not len(free):
            return None
        i = int(free[0])
        self.f_alive[i] = True
        self.f_id[i] = self.next_id; self.next_id += 1
        self.G[i] = g
        self.fx[i], self.fy[i] = np.clip(x, 2, W - 2), np.clip(y, 2, H - 2)
        self.fh[i] = self.rng.uniform(0, 2 * math.pi)
        self.fage[i] = 0
        self.flife[i] = int((2600 + 500 * g[SIZE]) * self.rng.uniform(0.75, 1.25))
        self.fe[i] = min(energy, self._emax(g))
        self.fgen[i] = gen
        self.max_gen = max(self.max_gen, int(gen))
        self.fpollen[i] = np.nan
        self.fvig[i] = float(np.clip(vig, 0.5, 1.25))
        self.fpar[i] = mother
        self.fparid[i] = int(self.f_id[mother]) if mother >= 0 else 0
        self.fsp[i] = self._species_of("animal", g, parent, gen)
        self.births += 1
        return i

    def _spawn_plant(self, g, x, y, gen, parent, energy):
        free = np.flatnonzero(~self.p_alive)
        if not len(free):
            return None
        if not (0 < x < W and 0 < y < H) or self._fertility(np.array([x]), np.array([y]))[0] < 0.05:
            return None
        i = int(free[0])
        self.p_alive[i] = True
        self.p_id[i] = self.next_id; self.next_id += 1
        self.P[i] = g
        self.px[i], self.py[i] = x, y
        self.pe[i], self.page[i] = energy, 0
        self.plife[i] = int(9000 * self.rng.uniform(0.6, 1.4))
        self.pnec[i] = 0
        self.ppollen[i] = np.nan
        self.pgen[i] = gen
        self.psp[i] = self._species_of("plant", g, parent, gen)
        self.plant_births = getattr(self, "plant_births", 0) + 1
        return i

    def _seed_plant(self):
        rng = self.rng
        g = PLO + (PHI - PLO) * rng.random(NPG).astype(np.float32)
        g[P_PETALS] = rng.integers(3, 7)
        g[P_SAT] = rng.uniform(0.3, 0.7)
        g[P_COLD] = rng.uniform(0, 0.15)
        for _ in range(40):
            x, y = rng.uniform(10, W - 10), rng.uniform(10, H - 10)
            if self._spawn_plant(g, x, y, 0, None, 3.0) is not None:
                return

    def _seed_animal(self, band=1):
        rng = self.rng
        g = np.zeros(NG, np.float32)
        g[HUE], g[SAT], g[HUE2], g[PATTERN] = rng.random(), rng.uniform(0.1, 0.35), rng.random(), rng.random()
        g[GLOW], g[SEGS], g[LIMBS], g[SIZE] = 0.0, rng.integers(1, 3), 0, rng.uniform(0.7, 1.1)
        g[TAIL], g[CREST], g[FIN], g[DIET] = rng.uniform(0.2, 0.6), 0, rng.uniform(0.3, 0.7), rng.uniform(0, 0.35)
        g[PREF_FLOWER], g[PREF_MATE], g[CHOOSY] = rng.random(), g[HUE] + rng.normal(0, 0.05), 0.1
        g[W_FOOD], g[W_FLEE], g[W_MATE], g[WANDER], g[REPRO], g[CARE] = 1.5, 1.0, 1.0, 0.4, 0.6, 0.05
        g[ENDO], g[INSUL] = rng.uniform(0, 0.08), rng.uniform(0, 0.08)      # every founder is cold-blooded and bare
        g = _clip(g, LO, HI, CIRC)
        x, y = self._water_spot()
        first = None
        for _ in range(band):
            i = self._spawn_animal(g, x + rng.normal(0, 6), y + rng.normal(0, 6), 0,
                                   int(self.fsp[first]) if first is not None else None, 12.0)
            first = i if first is None else first

    def _water_spot(self):
        for _ in range(60):
            x, y = self.rng.uniform(10, W - 10), self.rng.uniform(10, H - 10)
            h = float(self.height(x, y)) - self.sea
            if -0.25 < h < 0.05:
                return x, y
        return self.rng.uniform(10, W - 10), self.rng.uniform(10, H - 10)

    # ── genetics ─────────────────────────────────────────────────────────
    def _mutate(self, g, lo, hi, step, circ):
        rng = self.rng
        g = g.copy()
        mm = mult(self.dial("flora" if step is PSTEP else "fauna"), 2.5)
        m = rng.random(len(g)) < min(0.6, 0.25 * mm)
        g[m] += rng.normal(0, 1, int(m.sum())).astype(np.float32) * step[m] * mm
        if rng.random() < 0.01:            # a rare big jump: a gene duplicated or lost
            k = int(rng.integers(len(g)))
            g[k] += rng.normal(0, 6) * step[k]
        return _clip(g, lo, hi, circ)

    def _cross(self, a, b):
        pick = self.rng.random(len(a)) < 0.5
        return np.where(pick, a, b).astype(np.float32)

    @staticmethod
    def _emax(g):
        return 18.0 * g[SIZE] * math.sqrt(g[SEGS])

    # ── fields ───────────────────────────────────────────────────────────
    def _fertility(self, x, y):
        d = self.height(x, y) - self.sea
        f = 0.25 + 0.75 * np.exp(-((d - 0.08) / 0.22) ** 2)
        return np.where(d < -0.18, 0.0, np.where(d < 0, 0.85 * f, f)).astype(np.float32)

    # ── one tick ─────────────────────────────────────────────────────────
    def step(self):
        from scipy.spatial import cKDTree
        rng = self.rng
        self.tick += 1
        self.ease_dials()
        t = self.tick
        if t % 50 == 0:
            self.sea = self._sea_level()
        light = self.daylight()
        F = np.flatnonzero(self.f_alive)
        Pi = np.flatnonzero(self.p_alive)
        if len(F) < 4 or len(Pi) < 12:
            self._recolonise(len(F) < 4, len(Pi) < 12)
            F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)

        # plants: light, water, crowding; flowers make nectar from the plant's own energy
        if t % 4 == 0 and len(Pi):
            px, py, Pg = self.px[Pi], self.py[Pi], self.P[Pi]
            cg = np.zeros((GY // 3, GX // 3), np.float32)
            cx = np.clip((px / W * (GX // 3)).astype(int), 0, GX // 3 - 1)
            cy = np.clip((py / H * (GY // 3)).astype(int), 0, GY // 3 - 1)
            np.add.at(cg, (cy, cx), Pg[:, P_SIZE])
            shade = 1.0 / (1.0 + np.maximum(cg[cy, cx] - Pg[:, P_SIZE], 0) / 6.0)
            fert = self._fertility(px, py)
            gain = 4 * mult(self.dial("flora"), 1.7) * (0.022 * light * fert * shade * Pg[:, P_SIZE] * (0.7 + 0.3 * Pg[:, P_HEIGHT]))
            # warmth: a hardy plant grows in the cold but more slowly; frost hurts the tender ones
            Tp = self.temp(self.height(px, py) - self.sea, light)
            hard = Pg[:, P_COLD]
            gt = np.clip((Tp - (1 - 12 * hard)) / 16, 0.12, 1)
            gain = gain * gt * (1 - 0.2 * hard)
            gain = self.soil_boost(px, py, gain)                              # flowers grow best where things have died
            upkeep = 4 * (0.0035 * Pg[:, P_SIZE] * (0.6 + 0.4 * Pg[:, P_HEIGHT]) + 0.0025 * Pg[:, P_NECTAR]
                          + 0.0006 * Pg[:, P_SAT] * Pg[:, P_PETALS])
            _, inv, cnt = np.unique(self.psp[Pi], return_inverse=True, return_counts=True)
            upkeep = upkeep * (1 + JC * np.maximum(0, cnt[inv] / len(Pi) - JC_FREE)) * (0.3 + 0.7 * light)  # plants idle at night
            upkeep = upkeep * (0.35 + 0.65 * gt)                              # and lie dormant in the cold
            frost = 4 * 0.003 * (1 - hard) * np.maximum(0, 2 - Tp)
            self.pe[Pi] += gain - upkeep - frost
            make = np.minimum(Pg[:, P_NECTAR] * 0.08 * min(1.0, 0.3 + light), np.maximum(self.pe[Pi] * 0.02, 0))
            room = np.maximum(Pg[:, P_NECTAR] * 2.0 - self.pnec[Pi], 0)
            make = np.minimum(make, room)
            self.pnec[Pi] += make
            self.pe[Pi] -= make
            self.page[Pi] += 4
            dead = Pi[(self.pe[Pi] <= 0) | (self.page[Pi] > self.plife[Pi]) | (fert < 0.02)]
            self.p_alive[dead] = False
            if len(dead):
                self.litter_add(self.px[dead], self.py[dead], 1.5 + 2.5 * self.P[dead, P_SIZE])   # a fallen flower becomes litter
                self.plant_deaths = getattr(self, "plant_deaths", 0) + len(dead)
            # setting seed: pollinated flowers seed nearby; unpollinated plants sometimes spread by runners
            for i in Pi[(self.pe[Pi] > 5 * self.P[Pi, P_SIZE])]:
                if not self.p_alive[i]:
                    continue
                pol = self.ppollen[i]
                if not np.isnan(pol[0]):
                    g = self._mutate(self._cross(self.P[i], pol), PLO, PHI, PSTEP, (P_HUE, P_HUE2))
                    seeds = 3
                    self.ppollen[i] = np.nan
                elif rng.random() < 0.12 * mult(self.dial("flora"), 1.7):
                    g = self._mutate(self.P[i], PLO, PHI, PSTEP, (P_HUE, P_HUE2))
                    seeds = 1
                else:
                    continue
                for _ in range(seeds):
                    a, r = rng.uniform(0, 2 * math.pi), rng.uniform(8, 45)
                    if self._spawn_plant(g, self.px[i] + r * math.cos(a), self.py[i] + r * math.sin(a),
                                         int(self.pgen[i]) + 1, int(self.psp[i]), 1.5) is not None:
                        self.pe[i] -= 1.8
            Pi = np.flatnonzero(self.p_alive)

        # plankton: grows in the sea with light and warmth, richest in the shallows
        if t % 4 == 0:
            self._grow_plankton(light)
            self._fungi_step(light)                                       # the underworld: decay and return

        if not len(F):
            self._after_tick()
            return self.last_stats if t % STATS_EVERY == 0 else None

        # animals
        n = len(F)
        x, y, hd, G = self.fx[F], self.fy[F], self.fh[F], self.G[F]
        depth = self.height(x, y) - self.sea
        water = depth < 0
        consp = light * (0.25 + 0.75 * G[:, SAT]) + (1 - light) * (0.08 + 0.92 * G[:, GLOW])
        # warmth: a cold-blooded animal is as lively as the air around it; a warm-blooded one is always lively
        Tamb = self.temp(depth, light)
        Eg, Ig = G[:, ENDO], G[:, INSUL]
        warm_e = np.clip((Tamb - 2.0) / 20.0, 0.08, 1.0)
        act = 1.2 * Eg + (1 - Eg) * warm_e        # warm blood also brings stamina: a little more speed in any weather
        vig = self.fvig[F]
        grown = np.clip(0.4 + 0.6 * self.fage[F] / MATURE, 0.4, 1.0)
        size = G[:, SIZE] * np.sqrt(G[:, SEGS]) * grown
        par = self.fpar[F]
        has_par = (par >= 0) & (self.fage[F] < MATURE)
        pidx = np.where(has_par, par, 0)
        has_par &= self.f_alive[pidx] & (self.f_id[pidx] == self.fparid[F])
        pcare = np.where(has_par, self.G[pidx, CARE], 0.0)
        pdist = np.where(has_par, np.hypot(self.fx[pidx] - x, self.fy[pidx] - y), np.inf)
        # a warm parent keeps its young warm (brooding, nursing)
        act = np.where(has_par & (pdist < 20), np.maximum(act, self.G[pidx, ENDO] * (0.4 + 0.6 * pcare)), act)
        herb = np.clip(1 - G[:, DIET] * 1.4, 0, 1)
        meat = np.clip((G[:, DIET] - 0.3) / 0.7, 0, 1)
        eyes, shell, wing = G[:, EYES], G[:, SHELL], G[:, WING]
        regions = G[:, SPEC] * np.clip((G[:, SEGS] - 2) / 3, 0, 1)       # regions need segments to divide
        aloft = (~(self.height(x, y) - self.sea < 0)) * np.clip((wing - 0.35) / 0.4, 0, 1)   # gliding needs air under it
        emax = 18.0 * G[:, SIZE] * np.sqrt(G[:, SEGS])
        efrac = self.fe[F] / emax
        display = consp * vig * np.clip(efrac, 0.2, 1)     # only an animal in good condition can put on a show

        posF = np.stack([x, y], 1).astype(np.float64)
        treeF = cKDTree(posF)
        k = min(7, n)
        dF, iF = treeF.query(posF, k=k, distance_upper_bound=SENSE)
        dF, iF = dF[:, 1:], iF[:, 1:]
        validF = iF < n
        iF = np.where(validF, iF, 0)
        # threats: anything that eats meat, is bigger, and is close; prey: smaller, and seen
        # the blind notice a hunter only when it is close; sharp eyes see it coming across the whole sense range
        threat = validF & (meat[iF] > 0.2) & (size[iF] > 0.8 * size[:, None]) & (dF < SENSE * (0.4 + 0.6 * eyes[:, None]))
        seen = (0.35 + 0.65 * consp[iF]) * (0.55 + 0.45 * light + 0.45 * eyes[:, None] * (1 - 0.4 * light))
        prey = validF & (meat[:, None] > 0.2) & (size[iF] < 1.25 * size[:, None]) & \
            (rng.random(dF.shape) < seen) & (self.fsp[F][iF] != self.fsp[F][:, None]) & \
            (_hd(G[iF, HUE], G[:, HUE][:, None]) > 0.07)          # kin, known by colour, are not hunted

        def nearest(mask):
            dd = np.where(mask, dF, np.inf)
            j = dd.argmin(1)
            has = np.isfinite(dd[np.arange(n), j])
            return iF[np.arange(n), j], has, dd[np.arange(n), j]

        jt, ht, _ = nearest(threat)
        jp, hp, dpp = nearest(prey)

        # flowers: each forager is drawn to the nearest flower whose colour it likes
        jf, hf, dfl = np.zeros(n, int), np.zeros(n, bool), np.full(n, np.inf)
        if len(Pi):
            posP = np.stack([self.px[Pi], self.py[Pi]], 1).astype(np.float64)
            dP, iP = cKDTree(posP).query(posF, k=min(10, len(Pi)), distance_upper_bound=1.6 * SENSE)
            if dP.ndim == 1:
                dP, iP = dP[:, None], iP[:, None]
            okP = iP < len(Pi)
            iP0 = np.where(okP, iP, 0)
            like = np.exp(-(_hd(self.P[Pi][iP0, P_HUE], G[:, PREF_FLOWER][:, None]) / 0.12) ** 2)
            # the colour of a flower is seen by day; its nectar is smelt at any hour
            full = np.clip(self.pnec[Pi][iP0] / np.maximum(0.05, 2 * self.P[Pi][iP0, P_NECTAR]), 0, 1)
            score = np.where(okP & (herb[:, None] > 0.1),
                             (0.15 + like) * (0.4 + 0.6 * light) * (0.05 + full) / (dP + 4), -1)
            j = score.argmax(1)
            hf = score[np.arange(n), j] > 0
            jf = iP0[np.arange(n), j]
            dfl = np.where(hf, dP[np.arange(n), j], np.inf)

        mate_ready = (efrac > G[:, REPRO]) & (self.fage[F] > MATURE) & \
            (rng.random(n) < np.clip((act - 0.2) / 0.5, 0, 1))        # cold-blooded animals breed when it is warm
        mate = validF & mate_ready[:, None] & mate_ready[iF] & (self.fsp[F][iF] == self.fsp[F][:, None])
        jm, hm, _ = nearest(mate)

        def toward(px_, py_, has):
            dx, dy = px_ - x, py_ - y
            d = np.hypot(dx, dy) + 1e-3
            return np.where(has, dx / d, 0), np.where(has, dy / d, 0)

        hungry = 1.2 - np.clip(efrac, 0, 1)
        fx_food, fy_food = toward(self.px[Pi][jf] if len(Pi) else x, self.py[Pi][jf] if len(Pi) else y, hf)
        fx_prey, fy_prey = toward(x[jp], y[jp], hp)
        fx_th, fy_th = toward(x[jt], y[jt], ht)
        fx_m, fy_m = toward(x[jm], y[jm], hm)
        fx_par, fy_par = toward(self.fx[pidx], self.fy[pidx], has_par & (pdist > 8))
        wf, wfl, wm = G[:, W_FOOD], G[:, W_FLEE], G[:, W_MATE]
        vx = (wf * hungry * (herb * fx_food + meat * fx_prey) - wfl * fx_th + wm * mate_ready * fx_m
              + G[:, WANDER] * np.cos(hd) + 2.5 * pcare * fx_par)
        vy = (wf * hungry * (herb * fy_food + meat * fy_prey) - wfl * fy_th + wm * mate_ready * fy_m
              + G[:, WANDER] * np.sin(hd) + 2.5 * pcare * fy_par)
        # swimmers keep to the water, walkers to the land
        h_ahead = self.height(x + 12 * np.cos(hd), y + 12 * np.sin(hd)) - self.sea
        wrong = np.where(G[:, FIN] > 0.5, h_ahead > 0.02, (h_ahead < -0.02) & (wing < 0.6))   # gliders cross water
        vx -= 0.6 * wrong * np.cos(hd)
        vy -= 0.6 * wrong * np.sin(hd)
        want = np.arctan2(vy, vx)
        turn = ((want - hd + math.pi) % (2 * math.pi)) - math.pi
        hd = (hd + np.clip(turn, -0.25, 0.25) + rng.normal(0, 0.06, n)) % (2 * math.pi)
        sp_water = (0.35 + 1.1 * G[:, FIN] * (0.5 + 0.5 * G[:, TAIL]))
        sp_land = (0.15 + 0.32 * G[:, LIMBS] * (1 - 0.7 * G[:, FIN]))
        sp_land = sp_land + 0.9 * aloft                     # a glide outruns any walker
        speed = np.where(water, sp_water, sp_land) / np.sqrt(G[:, SIZE]) * (0.6 + 0.4 * grown) * np.clip(0.4 + np.hypot(vx, vy) / 2, 0.4, 1.0)
        speed = speed * (0.3 + 0.7 * act) / (1 + 0.45 * shell)    # plates are heavy
        nx, ny = x + speed * np.cos(hd), y + speed * np.sin(hd)
        bounce_x = (nx < 2) | (nx > W - 2)
        bounce_y = (ny < 2) | (ny > H - 2)
        hd = np.where(bounce_x, math.pi - hd, hd)
        hd = np.where(bounce_y, -hd, hd) % (2 * math.pi)
        self.fx[F], self.fy[F], self.fh[F] = np.clip(nx, 2, W - 2), np.clip(ny, 2, H - 2), hd

        # upkeep: body, glow, colour, crest, limbs; out of one's element costs more; common species pay their enemies
        _, inv, cnt = np.unique(self.fsp[F], return_inverse=True, return_counts=True)
        jc = 1 + JC * np.maximum(0, cnt[inv] / n - JC_FREE)
        cost = (0.003 * G[:, SIZE] ** 0.75 * np.sqrt(G[:, SEGS]) + 0.009 * G[:, GLOW] * (1 - light)
                + 0.0012 * G[:, SAT] + 0.0018 * G[:, CREST] + 0.0012 * G[:, LIMBS] + 0.0009 * G[:, CHOOSY]
                + 0.0015 * speed * G[:, SIZE]
                + 0.0005 * eyes + 0.0007 * shell * G[:, SIZE] + 0.0008 * wing * G[:, SIZE] + 0.0002 * regions * G[:, SEGS]) * grown
        # the price of warmth: a warm body burns far more, and loses heat to cold air (water steals it twice as fast,
        # small bodies faster than big ones) unless it is insulated; a coat overheats in summer
        bulk = np.cbrt(G[:, SIZE] * np.sqrt(G[:, SEGS]))
        metab = (1 - Eg) * (0.15 + 0.85 * warm_e) + Eg * 1.5        # a cold reptile all but stops; a mammal never does
        heat = 0.003 * Eg * np.maximum(0, 30 - Tamb) / 30 * (1 - 0.85 * Ig) * (1 + water) / bulk
        hot = 0.002 * Ig * np.maximum(0, Tamb - 21) / 10 + 0.0004 * Ig
        cost = (cost * metab + (heat + hot) * grown) * jc / vig / mult(self.dial("fauna"), 1.5) * \
            (1 + 0.8 * np.where(water, (1 - G[:, FIN]) * (1 - 0.6 * np.clip((wing - 0.35) / 0.4, 0, 1)),   # a glider skims the water
                                G[:, FIN] * (G[:, LIMBS] < 1)))
        self.fe[F] -= cost
        # the young of cold-blooded animals develop with the warmth (degree-days); warm young grow at their own pace
        young = self.fage[F] < MATURE
        self.fage[F] += np.where(young, rng.random(n) < 0.25 + 0.75 * act, 1).astype(np.int32)

        # parents feed the young that stay close
        fed = np.flatnonzero(has_par & (pdist < 30) & (pcare > 0.05))
        if len(fed):
            pe = self.fe[par[fed]] / (18.0 * self.G[par[fed], SIZE] * np.sqrt(self.G[par[fed], SEGS]))
            give = np.where(pe > 0.3, 0.02 * pcare[fed] * self.G[par[fed], SIZE], 0.0).astype(np.float32)
            np.subtract.at(self.fe, par[fed], give)
            self.fe[F[fed]] = np.minimum(self.fe[F[fed]] + 0.9 * give, emax[fed])
            self.fed_young += int((give > 0).sum())

        # feeding at flowers: nectar, and pollen carried from flower to flower
        if len(Pi):
            at = np.flatnonzero(hf & (dfl < 4 + 2 * G[:, SIZE]))
            for a in at:
                i, pi = int(F[a]), int(Pi[jf[a]])
                if not self.p_alive[pi]:
                    continue
                take = min(float(self.pnec[pi]), 1.2 * float(herb[a]) * (1 + 0.6 * float(Eg[a])))   # warm bodies feed faster
                self.pnec[pi] -= take
                self.fe[i] = min(self.fe[i] + 4.0 * take * (0.25 + 0.75 * act[a]) * (1 + 0.3 * regions[a]), emax[a])
                if take < 0.05 and herb[a] > 0.5 and efrac[a] < 0.5:     # no nectar: graze the leaves
                    bite = min(max(float(self.pe[pi]) - 1.5, 0.0), 0.08 * float(G[a, SIZE]))
                    self.pe[pi] -= bite
                    self.fe[i] = min(self.fe[i] + 0.8 * bite, emax[a])
                pol = self.fpollen[i]
                if not np.isnan(pol[0]) and self.fpsp[i] != 0:
                    # pollen only takes on a flower of the same kind (a close colour match)
                    if _hd(pol[P_HUE], self.P[pi, P_HUE]) < 0.09 and np.isnan(self.ppollen[pi, 0]):
                        self.ppollen[pi] = pol
                        self.pollinations += 1
                self.fpollen[i] = self.P[pi]
                self.fpsp[i] = self.psp[pi]

        # swimmers that eat plants graze the plankton where they are
        if t % 4 == 0:
            sw = np.flatnonzero(water & (herb > 0.1))
            if len(sw):
                cx = np.clip((x[sw] / W * (GX // 3)).astype(int), 0, GX // 3 - 1)
                cy = np.clip((y[sw] / H * (GY // 3)).astype(int), 0, GY // 3 - 1)
                for k, a in enumerate(sw):
                    bite = min(float(self.plank[cy[k], cx[k]]), 0.07 * float(herb[a]) * float(G[a, SIZE]) * (0.4 + 0.6 * float(G[a, FIN])) * (1 + 0.6 * float(Eg[a])))
                    if bite <= 0:
                        continue
                    self.plank[cy[k], cx[k]] -= bite
                    i = int(F[a])
                    self.fe[i] = min(self.fe[i] + 3.0 * bite * (0.25 + 0.75 * float(act[a])) * (1 + 0.3 * float(regions[a])), emax[a])

        # scavengers: anything with a taste for meat eats the dead where it finds them
        if t % 4 == 0:
            if not hasattr(self, "carrion"):
                self.carrion = np.zeros_like(self.plank)
            if not hasattr(self, "litter"):
                self.carrion *= 0.985                                    # rot (the underworld turns it into litter)
            sc = np.flatnonzero(meat > 0.02)
            if len(sc):
                cx = np.clip((x[sc] / W * (GX // 3)).astype(int), 0, GX // 3 - 1)
                cy = np.clip((y[sc] / H * (GY // 3)).astype(int), 0, GY // 3 - 1)
                for k, a in enumerate(sc):
                    bite = min(float(self.carrion[cy[k], cx[k]]), 0.25 * float(meat[a]) * float(G[a, SIZE]))
                    if bite <= 0:
                        continue
                    self.carrion[cy[k], cx[k]] -= bite
                    i = int(F[a])
                    self.fe[i] = min(self.fe[i] + 2.5 * bite * (0.25 + 0.75 * float(act[a])), emax[a])

        # predation
        hunt = np.flatnonzero(hp & (meat > 0.2) & (dpp < 3 + 2 * size) & (efrac < 0.9))
        if len(hunt):
            rng.shuffle(hunt)
            taken = set()
            for a in hunt:
                b = int(jp[a])
                if b in taken or a in taken:
                    continue
                att = size[a] * (1 + 0.25 * G[a, LIMBS]) * meat[a] * (0.4 + 0.6 * act[a]) * (1 + 0.6 * regions[a])   # jaws
                dfn = size[b] * (1 + 0.8 * G[b, CREST]) * (0.5 + 0.5 * act[b]) * (1 + 1.3 * shell[b]) * (1 + 1.2 * aloft[b])
                if has_par[b] and pdist[b] < 25:      # a parent stands over its young
                    dfn += 2.0 * float(pcare[b]) * float(self.G[pidx[b], SIZE] * np.sqrt(self.G[pidx[b], SEGS]))
                if rng.random() < att / (att + dfn):
                    i, j = int(F[a]), int(F[b])
                    food = max(float(self.fe[j]), 0) + 6 * float(size[b])
                    self.fe[i] = min(self.fe[i] + 0.7 * food * meat[a], emax[a])
                    self.f_alive[j] = False
                    taken.add(b)
                    self.kills += 1
                    self.deaths += 1
                else:
                    self.fe[int(F[a])] -= 0.3

        # deaths
        al = self.f_alive[F]
        die = F[al & ((self.fe[F] <= 0) | (self.fage[F] > self.flife[F]))]
        self.f_alive[die] = False
        self.animal_deaths = getattr(self, "animal_deaths", 0) + len(die)
        if len(die) and hasattr(self, "carrion"):                         # the body stays where it fell
            cx = np.clip((self.fx[die] / W * (GX // 3)).astype(int), 0, GX // 3 - 1)
            cy = np.clip((self.fy[die] / H * (GY // 3)).astype(int), 0, GY // 3 - 1)
            np.add.at(self.carrion, (cy, cx), (4.0 * self.G[die, SIZE] * np.sqrt(self.G[die, SEGS])).astype(np.float32))
        self.deaths += len(die)

        # courtship and birth: the choosy pick by colour and display; asexual budding is a slow fallback
        for a in np.flatnonzero(mate_ready & self.f_alive[F])[:30]:
            i = int(F[a])
            if not self.f_alive[i] or self.fe[i] < G[a, REPRO] * emax[a]:
                continue
            partner = None
            if hm[a]:
                # every ready suitor in sight is judged by colour match, display and crest; the best one wins
                cands = iF[a][mate[a]]
                cands = cands[np.hypot(x[cands] - x[a], y[cands] - y[a]) < 18 + 3 * size[a]]
                cands = cands[self.f_alive[F[cands]]] if len(cands) else cands
                if len(cands):
                    appeal = np.exp(-(_hd(G[cands, HUE], G[a, PREF_MATE]) / 0.15) ** 2) * \
                        (0.2 + 0.8 * display[cands]) * (1 + 0.4 * G[cands, CREST])
                    k_best = int(np.argmax(appeal))
                    if appeal[k_best] > 0.5 * float(G[a, CHOOSY]) or rng.random() < 0.02:
                        b = int(cands[k_best]); partner = int(F[b])
            if partner is not None:
                g = self._mutate(self._cross(self.G[i], self.G[partner]), LO, HI, STEP, CIRC)
                self.fe[partner] -= 0.15 * self.fe[partner]
                cv = 0.5 * (self.fvig[i] + self.fvig[partner]) * 0.985 + rng.normal(0, 0.04) + \
                    0.05 * float(G[a, CHOOSY]) * (float(display[b]) - 0.5)
            elif self.fage[i] > 800 and rng.random() < 0.01:
                g = self._mutate(self.G[i], LO, HI, STEP, CIRC)
                cv = float(self.fvig[i]) * 0.97 + rng.normal(0, 0.04)
            else:
                continue
            build = 4.0 * float(size[a])
            if self.fe[i] <= build + 2:
                continue
            gift = 0.45 * (float(self.fe[i]) - build)
            self.fe[i] -= build + gift
            k_ = self._spawn_animal(g, x[a] + rng.normal(0, 3), y[a] + rng.normal(0, 3), int(self.fgen[i]) + 1,
                                    int(self.fsp[i]), gift, cv, i)
            if k_ is None:
                self.fe[i] += gift
                break
        self._after_tick()
        return self.last_stats if t % STATS_EVERY == 0 else None

    def _after_tick(self):
        t = self.tick
        if t % (DAY // 4) == 0 or t % YEAR in (0, YEAR // 4, YEAR // 2, 3 * YEAR // 4):
            self._climate_events()
        if t % STATS_EVERY == 0:
            self.last_stats = self.stats()
            self.history.append(self.last_stats)
            self.history = self.history[-2000:]
            self._prune()
        if t % EPOCH == 0:
            self._lay_stratum()
            self._bank_lineages()

    def _grow_plankton(self, light):
        if not hasattr(self, "_pk_depth"):
            gy, gx = self.plank.shape
            yy, xx = np.mgrid[0:gy, 0:gx]
            self._pk_xy = ((xx + 0.5) * W / gx, (yy + 0.5) * H / gy)
        d = self.height(*self._pk_xy) - self.sea
        wet = d < 0
        cap = np.where(d > -0.2, 1.2, 0.6) * wet
        rate = 0.02 * (0.3 + 0.7 * light) * (0.6 + 0.4 * (self.water_temp() - 9) / 8)
        self.plank = np.where(wet, self.plank + rate * (cap - self.plank), 0).astype(np.float32)

    def _climate_events(self):
        t = self.tick
        ph = t % YEAR
        for frac, text in ((0.0, "Spring comes to the coast"), (0.25, "Midsummer: the long warm days"),
                           (0.5, "Autumn: the days cool"), (0.75, "Midwinter: frost on the uplands, the meadows still")):
            if ph == int(frac * YEAR):
                self._event("season", text)
        F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)
        firsts = self.__dict__.setdefault("firsts", set())
        if len(F):
            sp, inv, cnt = np.unique(self.fsp[F], return_inverse=True, return_counts=True)
            for k in np.flatnonzero(cnt >= 8):
                m = F[inv == k]
                e, ins = float(self.G[m, ENDO].mean()), float(self.G[m, INSUL].mean())
                name = self.species[int(sp[k])]["name"]
                if e > 0.5 and "warm" not in firsts:
                    firsts.add("warm"); self._event("milestone", f"The first warm-blooded animals: {name}")
                if ins > 0.5 and "coat" not in firsts:
                    firsts.add("coat"); self._event("milestone", f"The first fur and feathers: {name} keeps its warmth in a coat")
                if e > 0.5 and ins > 0.5 and "both" not in firsts and "warm" in firsts:
                    firsts.add("both"); self._event("milestone", f"Warm blood and a warm coat together: {name} can live through the winter")
        if hasattr(self, "m_alive"):
            Mi = np.flatnonzero(self.m_alive)
            if len(Mi):
                sp, inv, cnt = np.unique(self.msp[Mi], return_inverse=True, return_counts=True)
                for k in np.flatnonzero(cnt >= 5):
                    m = Mi[inv == k]; name = self.species[int(sp[k])]["name"]
                    if float(self.M[m, M_GLOW].mean()) > 0.5 and "foxfire" not in firsts:
                        firsts.add("foxfire"); self._event("milestone", f"Foxfire: {name} glows in the dark to draw its spore-carriers")
                    if float(self.M[m, M_TOX].mean()) > 0.5 and "poison" not in firsts:
                        firsts.add("poison"); self._event("milestone", f"The first poisonous mushrooms: {name}")
                    if float(self.M[m, M_COLD].mean()) > 0.6 and "snowcap" not in firsts:
                        firsts.add("snowcap"); self._event("milestone", f"Mushrooms that fruit in the snow: {name}")
        if len(Pi):
            sp, inv, cnt = np.unique(self.psp[Pi], return_inverse=True, return_counts=True)
            for k in np.flatnonzero(cnt >= 12):
                if float(self.P[Pi[inv == k], P_COLD].mean()) > 0.6 and "hardy" not in firsts:
                    firsts.add("hardy"); self._event("milestone", f"Flowers that survive frost: {self.species[int(sp[k])]['name']}")

    # ── refugia ──────────────────────────────────────────────────────────
    def _bank_lineages(self):
        F = np.flatnonzero(self.f_alive)
        if len(F) < 8:
            return
        sp, inv, cnt = np.unique(self.fsp[F], return_inverse=True, return_counts=True)
        by = {e["sid"]: e for e in self.bank}
        for k in np.argsort(-cnt)[:6]:
            if cnt[k] < 4:
                break
            m = F[inv == k]
            score = self.G[m, SEGS] + self.G[m, LIMBS] + 2 * self.G[m, GLOW] + self.G[m, CREST]
            i = int(m[int(np.argmax(score))])
            by[int(sp[k])] = {"sid": int(sp[k]), "g": self.G[i].copy(), "tick": int(self.tick), "score": float(score.max())}
        allv = sorted(by.values(), key=lambda e: -e["tick"])
        self.bank = allv[:BANK_MAX]

    def _recolonise(self, animals, plants):
        rng = self.rng
        refuge = 0
        if animals:
            for e in (self.bank[:16] if self.bank else []):
                g = self._mutate(e["g"], LO, HI, STEP, CIRC)
                x, y = self._water_spot()
                for _ in range(2):
                    self._spawn_animal(g, x + rng.normal(0, 4), y + rng.normal(0, 4), 0, e["sid"], 12.0)
                refuge += 1
            for _ in range(max(10, 40 - 2 * refuge)):
                self._seed_animal()
        if plants:
            for _ in range(80):
                self._seed_plant()
        self.restarts += 1
        self._event("near-extinction", f"{refuge} animal lineages return from refugia" if refuge else "life re-seeded")

    def event(self, kind, text):
        self._event(kind, text)

    def _event(self, kind, text):
        self.events.append({"tick": int(self.tick), "day": self.day(), "kind": kind, "text": text})
        self.events = self.events[-300:]

    # ── the fossil record ────────────────────────────────────────────────
    def _lay_stratum(self):
        F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)
        layer = {"tick": int(self.tick), "day": self.day(), "sea": round(self.sea, 3), "animals": [], "plants": []}
        if len(F):
            sp, inv, cnt = np.unique(self.fsp[F], return_inverse=True, return_counts=True)
            for k in np.argsort(-cnt)[:5]:
                g = self.G[F[inv == k]].mean(0)
                layer["animals"].append({"sid": int(sp[k]), "n": int(cnt[k]), "name": self.species[int(sp[k])]["name"],
                                         "look": _look(g)})
        if len(Pi):
            sp, inv, cnt = np.unique(self.psp[Pi], return_inverse=True, return_counts=True)
            for k in np.argsort(-cnt)[:4]:
                g = self.P[Pi[inv == k]].mean(0)
                layer["plants"].append({"sid": int(sp[k]), "n": int(cnt[k]), "name": self.species[int(sp[k])]["name"],
                                        "hue": round(float(g[P_HUE]), 3), "petals": round(float(g[P_PETALS]), 1)})
        self.strata.append(layer)
        self.strata = self.strata[-1500:]

    def _prune(self):
        live = set(np.unique(self.fsp[self.f_alive]).tolist()) | set(np.unique(self.psp[self.p_alive]).tolist())
        if hasattr(self, "m_alive"):
            live |= set(np.unique(self.msp[self.m_alive]).tolist())
        for sid, s in list(self.species.items()):
            if sid in live:
                continue
            if s.get("peak", 0) >= 8 and not s.get("extinct"):
                s["extinct"] = int(self.tick)
                self.extinct += 1
                self._event("extinction", f"{s['name']} ({s['kind']}) is gone after {self._days(self.tick - s['born'])} days")
        for sid, s in self.species.items():           # the archive notes when every kind, however small, disappears
            if sid not in live and s.get("gone") is None:
                s["gone"] = int(self.tick)
                self._fossil(sid)
        kinds = [("animal", self.fsp, self.f_alive, self.fx, self.fy, self.G),
                 ("plant", self.psp, self.p_alive, self.px, self.py, self.P)]
        if hasattr(self, "m_alive"):
            kinds.append(("fungus", self.msp, self.m_alive, self.mx, self.my, self.M))
        for kind, arr, alive, X, Y, Gm in kinds:
            idx = np.flatnonzero(alive)
            if not len(idx):
                continue
            sp, inv, cnt = np.unique(arr[idx], return_inverse=True, return_counts=True)
            for k, (sid, c) in enumerate(zip(sp.tolist(), cnt.tolist())):
                s = self.species[sid]
                if s.get("peak", 0) < (5 if kind == "fungus" else 8) <= c:
                    self._event("new species", f"{s['name']} ({s['kind']}) is established")
                if s.get("gone") is not None:           # back from refugia
                    s["gone"] = None
                    self._fossil(sid)
                if c > s.get("peak", 0):
                    m = idx[inv == k]
                    s["peak"], s["peak_tick"] = c, int(self.tick)
                    s["pg"] = Gm[m].mean(0)                # its portrait: the average member at its height
                    s["zone"] = zone_name(float(np.median(self.height(X[m], Y[m]))) - self.sea)
                    self._fossil(sid)
        keep = live | {s["parent"] for sid, s in self.species.items() if sid in live and s["parent"]}
        if len(self.species) > 3 * len(keep) + 600:
            self.species = {k: v for k, v in self.species.items() if k in keep or v.get("extinct", 0) > self.tick - 20 * EPOCH}

    # ── the archive: every kind that has ever lived ──────────────────────
    def _fossil(self, sid):
        """Queue the archive record of one species; the runner writes the queue to the database."""
        s = self.species.get(sid)
        if s is None:
            return
        q = self.__dict__.setdefault("fossil_q", {})
        g = s.get("pg", s["g"])
        q[int(sid)] = {"sid": int(sid), "kind": s["kind"], "name": s["name"],
                       "parent": int(s["parent"]) if s.get("parent") is not None else None,
                       "born": int(s["born"]), "gone": s.get("gone"), "peak": int(s.get("peak", 0)),
                       "peak_tick": s.get("peak_tick"), "gen": int(s.get("gen", 0)),
                       "look": _look(g) if s["kind"] == "animal" else _mlook(g) if s["kind"] == "fungus" else _plook(g), "zone": s.get("zone")}

    def take_fossils(self):
        return list((self.__dict__.get("fossil_q") or {}).values())

    def clear_fossils(self, rows):
        """Forget queued records once they are safely written (a record re-queued since then stays)."""
        q = self.__dict__.get("fossil_q") or {}
        for r in rows:
            if q.get(r["sid"]) is r:
                del q[r["sid"]]

    def fossil_backfill(self):
        """Once, for a world that ran before the archive existed: every kind still on file, and every kind that
        ever led a fossil layer (the strata reach back to the first epoch)."""
        live = set(np.unique(self.fsp[self.f_alive]).tolist()) | set(np.unique(self.psp[self.p_alive]).tolist())
        seen = {}
        for L in self.strata:
            for kind, key in (("animal", "animals"), ("plant", "plants")):
                for e in L.get(key, []):
                    r = seen.setdefault(e["sid"], {"kind": kind, "name": e["name"], "first": L["tick"], "last": L["tick"],
                                                   "peak": 0, "peak_tick": L["tick"], "e": e})
                    r["last"] = L["tick"]
                    if e["n"] > r["peak"]:
                        r["peak"], r["peak_tick"], r["e"] = e["n"], L["tick"], e
        for kind, arr, alive, X, Y, Gm in (("animal", self.fsp, self.f_alive, self.fx, self.fy, self.G),
                                           ("plant", self.psp, self.p_alive, self.px, self.py, self.P)):
            idx = np.flatnonzero(alive)
            for sid in np.unique(arr[idx]).tolist():
                s = self.species[sid]
                if "pg" not in s:                      # a portrait and a home for the living, from how they are now
                    m = idx[arr[idx] == sid]
                    s["pg"] = Gm[m].mean(0)
                    s["zone"] = zone_name(float(np.median(self.height(X[m], Y[m]))) - self.sea)
        for sid, s in self.species.items():
            if sid not in live and s.get("gone") is None:
                s["gone"] = int(s.get("extinct") or self.tick)
            if "peak_tick" not in s and sid in seen:
                s["peak_tick"] = int(seen[sid]["peak_tick"])
            self._fossil(sid)
        q = self.__dict__.setdefault("fossil_q", {})
        for sid, r in seen.items():
            if sid in self.species:
                continue
            e = r["e"]
            look = e["look"] if r["kind"] == "animal" else \
                [e["hue"], e["petals"], 0.5, 0.5, 0.6, round((e["hue"] + 0.12) % 1, 3), 0.5]
            q[int(sid)] = {"sid": int(sid), "kind": r["kind"], "name": r["name"], "parent": None,
                           "born": int(max(0, r["first"] - EPOCH)), "gone": int(r["last"] + EPOCH), "peak": int(r["peak"]),
                           "peak_tick": int(r["peak_tick"]), "gen": 0, "look": look, "zone": None}
        self.fossil_backfilled = True

    # ── measurement ──────────────────────────────────────────────────────
    def day(self):
        return self._days(self.tick)

    @staticmethod
    def _days(ticks):
        return round(ticks / DAY, 1)

    def stats(self):
        F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)
        out = {"tick": int(self.tick), "day": self.day(), "animals": int(len(F)), "plants": int(len(Pi)),
               "births": self.births, "kills": self.kills, "pollinations": self.pollinations, "restarts": self.restarts,
               "extinctions": self.extinct, "sea": round(self.sea, 3), "max_generation": self.max_gen}
        if len(F):
            G = self.G[F]
            sp, cnt = np.unique(self.fsp[F], return_counts=True)
            p = cnt / cnt.sum()
            # body complexity: distinct structures, a rough count of parts
            reg = G[:, SPEC] * np.clip((G[:, SEGS] - 2) / 3, 0, 1)
            parts = G[:, SEGS] + 2 * G[:, LIMBS] + (G[:, TAIL] > 0.5) + (G[:, CREST] > 0.4) + (G[:, GLOW] > 0.3) + \
                (G[:, SAT] > 0.5) + (G[:, PATTERN] > 0.33) + 2 * (G[:, EYES] > 0.5) + (G[:, SHELL] > 0.4) + \
                2 * (G[:, WING] > 0.5) + 2 * (reg > 0.5)
            self.cx_record = max(float(getattr(self, "cx_record", 0.0)), float(parts.max()))
            out.update({
                "animal_species": int(len(sp)), "animal_species_eff": round(float(1 / (p * p).sum()), 2),
                "complexity_mean": round(float(parts.mean()), 2), "complexity_max": round(float(parts.max()), 2),
                "segments_mean": round(float(G[:, SEGS].mean()), 2), "limbs_mean": round(float(G[:, LIMBS].mean()), 2),
                "glow_mean": round(float(G[:, GLOW].mean()), 3), "colour_mean": round(float(G[:, SAT].mean()), 3),
                "choosy_mean": round(float(G[:, CHOOSY].mean()), 3), "crest_mean": round(float(G[:, CREST].mean()), 3),
                "predators": round(float((G[:, DIET] > 0.6).mean()), 3),
                "pollinators": round(float((G[:, DIET] < 0.35).mean()), 3),
                "on_land": round(float((self.height(self.fx[F], self.fy[F]) - self.sea >= 0).mean()), 3),
                "mean_generation": round(float(self.fgen[F].mean()), 1),
                "care_mean": round(float(G[:, CARE].mean()), 3),
                "young": round(float((self.fage[F] < MATURE).mean()), 3),
                "families": int(((self.fpar[F] >= 0) & (self.fage[F] < MATURE)).sum()),
                "warm_blooded": round(float((G[:, ENDO] > 0.5).mean()), 3), "endo_mean": round(float(G[:, ENDO].mean()), 3),
                "insul_mean": round(float(G[:, INSUL].mean()), 3),
                "eyes": round(float((G[:, EYES] > 0.5).mean()), 3), "shelled": round(float((G[:, SHELL] > 0.4).mean()), 3),
                "winged": round(float((G[:, WING] > 0.5).mean()), 3), "regioned": round(float((reg > 0.5).mean()), 3),
                "complexity_record": round(self.cx_record, 2),
                "in_sea": int((self.height(self.fx[F], self.fy[F]) - self.sea < 0).sum()),
                "scavengers": round(float(((G[:, DIET] > 0.32) & (G[:, DIET] <= 0.6)).mean()), 3),
            })
        if len(Pi):
            sp, cnt = np.unique(self.psp[Pi], return_counts=True)
            p = cnt / cnt.sum()
            out.update({"plant_species": int(len(sp)), "plant_species_eff": round(float(1 / (p * p).sum()), 2),
                        "petals_mean": round(float(self.P[Pi, P_PETALS].mean()), 2),
                        "nectar_mean": round(float(self.P[Pi, P_NECTAR].mean()), 3),
                        "hardy": round(float((self.P[Pi, P_COLD] > 0.5).mean()), 3)})
        if hasattr(self, "m_alive"):
            born = self.births + getattr(self, "plant_births", 0) + self.lysis["born"]
            died = getattr(self, "animal_deaths", 0) + getattr(self, "plant_deaths", 0) + self.lysis["died"]
            self.update_gsl(len(F) + len(Pi) / 4 + int(self.m_alive.sum()), born, died, STATS_EVERY)
            out.update(self.fungi_stats())
        out.update({"season": round(self.season(), 3), "season_name": self.season_name(), "year": int(self.tick // YEAR) + 1,
                    "air": round(self.air(), 1), "water_temp": round(self.water_temp(), 1),
                    "plankton": round(float(self.plank.mean()), 3) if hasattr(self, "plank") else 0})
        return out

    # ── what the panel draws ─────────────────────────────────────────────
    def frame(self):
        F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)
        animals = [[int(self.f_id[i]), round(float(self.fx[i]), 1), round(float(self.fy[i]), 1), round(float(self.fh[i]), 2),
                    int(self.fsp[i]), round(min(1.0, 0.4 + 0.6 * float(self.fage[i]) / MATURE), 2),
                    int(self.fparid[i]) if self.fage[i] < MATURE else 0, *_look(self.G[i])] for i in F]
        plants = [[int(self.p_id[i]), round(float(self.px[i]), 1), round(float(self.py[i]), 1),
                   round(float(self.P[i, P_HUE]), 3), round(float(self.P[i, P_PETALS]), 1), round(float(self.P[i, P_SIZE]), 2),
                   round(float(self.P[i, P_HEIGHT]), 2), round(float(self.P[i, P_SAT]), 2), round(float(self.P[i, P_HUE2]), 3),
                   round(min(1.0, float(self.pnec[i]) / max(0.05, 2 * float(self.P[i, P_NECTAR]))), 2),
                   int(self.psp[i])]
                  for i in Pi]
        fungi, under = self.fungi_frame()
        names = {}
        for sid in set(int(s) for s in self.fsp[F]) | set(int(s) for s in self.psp[Pi]) | set(int(r[4]) for r in fungi):
            names[sid] = self.species[sid]["name"]
        return {"tick": int(self.tick), "day": self.day(), "light": round(self.daylight(), 3), "sea": round(self.sea, 3),
                "season": round(self.season(), 3), "air": round(self.air(), 1), "water_temp": round(self.water_temp(), 1), "lapse": LAPSE,
                "animals": animals, "plants": plants, "names": names, "dials": self.dials_payload(),
                "fungi": fungi, "under": under, "gsl": list(getattr(self, "gsl", [0, 0, 0]))}

    def terrain_payload(self):
        return {"w": W, "h": H, "gx": GX, "gy": GY, "h_": [round(float(v), 3) for v in self.terrain.ravel()],
                "day_ticks": DAY, "epoch_ticks": EPOCH, "name": self.name, "seed": self.seed, "version": self.version}

    # ── migration between panels (for networked editions) ────────────────
    def emigrants(self, n=2):
        """Genomes of a few living animals and plants, to send to another panel."""
        F, Pi = np.flatnonzero(self.f_alive), np.flatnonzero(self.p_alive)
        a = [self.G[i].tolist() for i in self.rng.choice(F, min(n, len(F)), replace=False)] if len(F) else []
        p = [self.P[i].tolist() for i in self.rng.choice(Pi, min(n, len(Pi)), replace=False)] if len(Pi) else []
        return {"from": self.name, "tick": int(self.tick), "animals": a, "plants": p}

    def immigrate(self, packet):
        for g in packet.get("animals", [])[:4]:
            g = list(g)[:NG] + [0.05] * max(0, NG - len(g))
            x, y = self._water_spot()
            self._spawn_animal(_clip(np.array(g, np.float32), LO, HI, CIRC), x, y, 0, None, 12.0)
        for g in packet.get("plants", [])[:4]:
            for _ in range(10):
                if self._spawn_plant(_clip(np.array(g, np.float32), PLO, PHI), self.rng.uniform(10, W - 10),
                                     self.rng.uniform(10, H - 10), 0, None, 3.0) is not None:
                    break
        self._event("migrants", f"travellers arrived from {packet.get('from', 'another world')}")


def _look(g):
    """The genes the renderer needs, rounded."""
    return [round(float(g[HUE]), 3), round(float(g[SAT]), 2), round(float(g[HUE2]), 3), round(float(g[PATTERN]), 2),
            round(float(g[GLOW]), 2), int(round(float(g[SEGS]))), int(round(float(g[LIMBS]))), round(float(g[SIZE]), 2),
            round(float(g[TAIL]), 2), round(float(g[CREST]), 2), round(float(g[FIN]), 2), round(float(g[DIET]), 2),
            round(float(g[ENDO]), 2), round(float(g[INSUL]), 2),
            round(float(g[EYES]), 2), round(float(g[SHELL]), 2), round(float(g[WING]), 2),
            round(float(g[SPEC]) * min(1.0, max(0.0, (float(g[SEGS]) - 2) / 3)), 2)]


def _plook(g):
    return [round(float(g[P_HUE]), 3), round(float(g[P_PETALS]), 1), round(float(g[P_SIZE]), 2), round(float(g[P_HEIGHT]), 2),
            round(float(g[P_SAT]), 2), round(float(g[P_HUE2]), 3), round(float(g[P_NECTAR]), 2), round(float(g[P_COLD]), 2)]


PLOOK_KEYS = ["hue", "petals", "size", "height", "sat", "hue2", "nectar", "cold"]
ZONES = [(-0.42, "the deep"), (-0.16, "the open sea"), (0.0, "the shallows"), (0.045, "the shore"), (0.30, "the meadow"),
         (0.58, "the uplands"), (9e9, "the heights")]


def zone_name(d):
    for lim, name in ZONES:
        if d <= lim:
            return name
    return ZONES[-1][1]


LOOK_KEYS = ["hue", "sat", "hue2", "pattern", "glow", "segs", "limbs", "size", "tail", "crest", "fin", "diet", "endo", "insul",
             "eyes", "shell", "wings", "regions"]

_SYL = ["la", "mi", "or", "ve", "sa", "lu", "ten", "ca", "ri", "no", "phe", "ly", "ae", "zo", "qui", "ar", "el", "thy"]
_ROOT_A = ["Lumin", "Chrom", "Vel", "Pisc", "Ambul", "Pteryg", "Lept", "Nect"]
_ROOT_P = ["Flor", "Anth", "Petal", "Calyc", "Corol", "Stell"]


def species_name(sid, kind, g):
    h = (sid * 2654435761) % 2 ** 32
    ep = _SYL[h % 18] + _SYL[(h >> 5) % 18] + ("us" if h & 1 else "a")
    if kind == "fungus":
        return fungus_name(h, g, ep)
    if kind == "plant":
        root = _ROOT_P[(h >> 9) % len(_ROOT_P)]
        return f"{root}{'ia' if g[P_PETALS] < 5 else 'ella'} {ep}"
    if g[GLOW] > 0.4:
        root = "Lumin"
    elif g[DIET] > 0.6:
        root = "Lept"
    elif g[DIET] < 0.35:
        root = "Nect"
    elif g[FIN] < 0.4:
        root = "Ambul"
    else:
        root = _ROOT_A[(h >> 9) % len(_ROOT_A)]
    suf = "ella" if g[SEGS] < 3 else "opod" if g[LIMBS] >= 2 else "oid"
    return f"{root}{suf} {ep}"


def to_bytes(w: World) -> bytes:
    return zlib.compress(pickle.dumps(w, protocol=4), 6)


def from_bytes(b: bytes) -> World:
    w = pickle.loads(zlib.decompress(b))
    if w.G.shape[1] < NG:                     # older worlds: new genes start as a trace, so they can evolve
        pad = np.full((w.G.shape[0], NG - w.G.shape[1]), 0.05, np.float32)
        w.G = np.concatenate([w.G, pad], 1)
        for e in w.bank:
            if len(e["g"]) < NG:
                e["g"] = np.concatenate([e["g"], np.full(NG - len(e["g"]), 0.05, np.float32)])
        for sp in w.species.values():
            if sp["kind"] == "animal":
                for k in ("g", "pg"):
                    if k in sp and len(sp[k]) < NG:
                        sp[k] = np.concatenate([sp[k], np.full(NG - len(sp[k]), 0.05, np.float32)])
    if w.P.shape[1] < NPG:                    # v1.1 worlds: frost-hardiness, a little of it, so it can evolve
        rng = w.rng
        def padp(a, nan_rows=False):
            col = rng.uniform(0, 0.15, (a.shape[0], NPG - a.shape[1])).astype(np.float32)
            if nan_rows:
                col[np.isnan(a[:, 0])] = np.nan
            return np.concatenate([a, col], 1)
        w.P, w.ppollen, w.fpollen = padp(w.P), padp(w.ppollen, True), padp(w.fpollen, True)
        for sp in w.species.values():
            if sp["kind"] == "plant":
                for k in ("g", "pg"):
                    if k in sp and len(sp[k]) < NPG:
                        sp[k] = np.concatenate([sp[k], np.float32([0.05])])
    if not hasattr(w, "carrion"):
        w.carrion = np.zeros((GY // 3, GX // 3), np.float32)
    if not hasattr(w, "m_alive"):
        w._fungi_init(seed_colonies=True)
        w.litter += w.carrion * 0.5
        w._event("lysis", "The underworld wakes: from now on the dead become soil, and fungi carry them back to life")
    if not hasattr(w, "plank"):
        w.plank = np.zeros((GY // 3, GX // 3), np.float32)
        w.firsts = set()
        w._event("climate", "The seasons begin: from now on the coast has summers and winters, cold nights and cold heights")
    if not hasattr(w, "fpar"):
        w.fpar = np.full(CAP_F, -1, np.int64)
        w.fparid = np.zeros(CAP_F, np.int64)
        w.fed_young = 0
    w.version = VERSION
    return w
