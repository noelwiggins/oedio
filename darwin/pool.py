"""THE TIDAL POOL (life-3.0): an open-ended world built so complexity can evolve.

Nothing in here describes a complex creature. The world only supplies the
conditions under which, in nature, complexity paid off:

  * Genomes that can grow. A body is grown from a list of genes by a small
    developmental program; genes can be duplicated, deleted, inserted and
    repurposed, so bodies are not limited to a fixed size or plan.
  * Cells that can specialise. Nine cell types: skin, photo (light to energy),
    mouth (eat dead matter or other creatures), flagellum (movement), eye
    (sensing at a distance), armour, store (energy capacity), neuron (more
    hidden units in the creature's neural controller) and gonad (sex).
  * A food web. Light feeds producers; dead matter feeds grazers; any creature
    with a mouth can try to eat another (success depends on attack vs defence).
  * Sex with recombination, within a species, for creatures that carry gonads.
  * Nested environmental change: day/night, seasons, a drifting climate (light
    band, temperature, ocean current, nutrient upwellings), slow orbital-style
    cycles and rare catastrophes. No single strategy wins forever.
  * Niche construction: waste and corpses fertilise the water, so what lives
    somewhere changes what can live there next.
  * Shading and crowding: producers compete for light, so being flat, tall or
    mobile matters.

Time. One "generation" is one step down a line of descent. The clock is
defined as 1 generation = 1,000 years, so a billion years = a million
generations. That is a declared scale, not a claim about real biology.

Everything measured here (cells per body, cell types, food-chain depth,
species, genome length, milestones) is computed from the population; nothing
is scripted. Milestones are logged to the Ledger when they first hold for
three consecutive samples.

The pool runs in its own process (python -m darwin.pool run), holds an
advisory lock so only one copy runs, checkpoints every 30 s and writes the
latest frames to darwin_pool_live for the web to read.
"""
from __future__ import annotations

import difflib
import json
import math
import os
import pickle
import random
import signal
import sys
import time
import zlib

import numpy as np
import sqlalchemy as sa

from . import costs, store

S = store
VERSION = "life-3.0"
YEARS_PER_GEN = 1000

# ── world constants ──────────────────────────────────────────────────────
ARENA = 240.0              # north-south extent of the world (y wraps around)
WORLD_W = 400.0            # west-east extent: deep ocean, open sea, reef shallows, tidal flats, land
WORLD_H = ARENA
GRID = 48                  # field cells north-south
GRID_X = 80                # field cells west-east
CELL = ARENA / GRID
CAP = 1100
START = 160
MAX_CELLS = 64
DAY = 300
YEAR = 6000
ORBIT = 2_000_000
CLIMATE_EVERY = 1000
STATS_EVERY = 2400
K_NEAR = 8
SENSE_MAX = 30.0
MIN_AGE = 30
BASINS = 5                 # five habitats west to east (the name predates the deep and the land)
BASIN_W = WORLD_W / BASINS
GAP_H = 18.0               # height of each strait in the reef
JUVENILE = 300
# Five habitats along a coast, west to east. The deep ocean slopes down from the open sea into darkness, fed by
# sinking dead matter and two hydrothermal vents. Two reefs with drifting straits separate the open sea, the reef
# shallows and the tidal flats. Beyond the flats lies land: always out of water, strong sun, poor soil, wide
# temperature swings, no currents. The world's west and east edges (abyss and inland) are a solid boundary.
DEEP, SEA, SHALLOWS, TIDAL, LAND = 0, 1, 2, 3, 4
HABITATS = ["deep ocean", "open sea", "reef shallows", "tidal flats", "land"]
# what stands at the west edge of each zone: 0 = solid (the world's edge), 1 = open water or open shore, 2 = reef with a strait
WALL_KIND = [0, 1, 2, 2, 1]
REGION = np.array([0, 0, 1, 2, 2])   # zones joined by open boundaries see, hunt and mate across them
TIDE = 900                 # ticks per tide cycle (three days)             # ticks during which a parent with care can feed its young

SKIN, PHOTO, MOUTH, FLAG, EYE, ARMOR, STORE, NEURON, GONAD = range(9)
NT = 9
CELL_NAMES = ["skin", "photo", "mouth", "flagellum", "eye", "armour", "store", "neuron", "gonad"]
DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]

IN, H, OUT = 16, 8, 4
MHC = 4                    # immune "lock" genes; pathogens evolve keys that fit the commonest locks (the Red Queen)
STRAINS = 3
PATH_R = 0.22              # how close a key must be to a lock to infect
NW = IN * H + H + H * OUT + OUT


# ── genomes and development ──────────────────────────────────────────────
def random_brain(rng):
    return (rng.standard_normal(NW) * 0.6).astype(np.float32)


def new_genome(rng, root=None):
    """A founder: a single cell (photo or mouth), a random small brain, default traits."""
    root = root if root is not None else (PHOTO if rng.random() < 0.7 else MOUTH)
    return {"body": [[root, 0, 0, 1]], "brain": random_brain(rng),
            "repro": float(rng.uniform(0.45, 0.65)), "temp": float(rng.uniform(-0.3, 0.3)),
            "mut": 1.0, "hue": float(rng.random()), "warm": 0.0, "care": 0.0,
            "mhc": [float(v) for v in rng.random(MHC)]}


def develop(body):
    """Grow a body from its genes. Gene = [cell type, attach-to (index into cells so far), direction, repeat]."""
    cells = {(0, 0): int(body[0][0]) % NT}
    order = [(0, 0)]
    for t, ref, d, rep in body[1:]:
        if len(order) >= MAX_CELLS:
            break
        px, py = order[int(ref) % len(order)]
        dx, dy = DIRS[int(d) % 4]
        for _ in range(max(1, min(4, int(rep)))):
            px, py = px + dx, py + dy
            if (px, py) in cells or len(order) >= MAX_CELLS:
                break
            cells[(px, py)] = int(t) % NT
            order.append((px, py))
    cx = round(sum(p[0] for p in order) / len(order))
    cy = round(sum(p[1] for p in order) / len(order))
    return [(x - cx, y - cy, cells[(x, y)]) for x, y in order]


def phenotype(cells):
    n = len(cells)
    cnt = np.zeros(NT, np.int16)
    for _, _, t in cells:
        cnt[t] += 1
    occ = {(x, y) for x, y, _ in cells}
    expo = 0.0
    for x, y, t in cells:
        if t == PHOTO:
            expo += 0.5 + 0.5 * sum((x + dx, y + dy) not in occ for dx, dy in DIRS) / 4.0
    return n, cnt, expo


def mutate(g, rng):
    """Copy with mutations. Rates scale with the genome's own (evolvable) mutation multiplier."""
    m = g["mut"]
    body = [list(x) for x in g["body"]]
    r = lambda p: rng.random() < p * m
    if r(0.12):                                            # cell type change
        i = rng.integers(len(body)); body[i][0] = int(rng.integers(NT))
    if r(0.10):
        i = rng.integers(len(body)); body[i][1] = int(rng.integers(0, 64))
    if r(0.10):
        i = rng.integers(len(body)); body[i][2] = int(rng.integers(4))
    if r(0.05):
        i = rng.integers(len(body)); body[i][3] = int(rng.integers(1, 4))
    if r(0.05) and len(body) < 48:                         # duplication: the raw material of new structure
        i = int(rng.integers(len(body))); k = int(rng.integers(1, 4))
        seg = [list(x) for x in body[i:i + k]]
        j = int(rng.integers(1, len(body) + 1))
        body[j:j] = seg
    if r(0.04) and len(body) > 1:                          # deletion
        del body[int(rng.integers(1, len(body)))]
    if r(0.03) and len(body) < 48:                         # insertion of a new random gene
        body.insert(int(rng.integers(1, len(body) + 1)),
                    [int(rng.integers(NT)), int(rng.integers(64)), int(rng.integers(4)), 1])
    brain = g["brain"].copy()
    mask = rng.random(NW) < 0.06 * m
    brain[mask] += rng.standard_normal(int(mask.sum())).astype(np.float32) * 0.3
    return {"body": body, "brain": brain,
            "repro": float(np.clip(g["repro"] + rng.normal(0, 0.02), 0.3, 0.95)),
            "temp": float(np.clip(g["temp"] + rng.normal(0, 0.04), -1.5, 1.5)),
            "mut": float(np.clip(g["mut"] * math.exp(rng.normal(0, 0.05)), 0.25, 4.0)),
            "hue": float((g["hue"] + rng.normal(0, 0.01)) % 1.0),
            # warm-bloodedness and parental care: costly traits that start at zero and must pay their way
            "warm": float(np.clip(g.get("warm", 0.0) + (rng.normal(0, 0.04) if r(0.15) else 0.0), 0.0, 1.0)),
            "care": float(np.clip(g.get("care", 0.0) + (rng.normal(0, 0.04) if r(0.15) else 0.0), 0.0, 1.0)),
            "mhc": [float((v + rng.normal(0, 0.015)) % 1.0) for v in _mhc(g, rng)]}


def _mhc(g, rng):
    m = g.get("mhc")
    if m is None:                   # genomes from before the immune genes: seed them from the colour gene
        m = [(g.get("hue", 0.5) * (k + 1.618)) % 1.0 for k in range(MHC)]
        g["mhc"] = m
    return m


def crossover(a, b, rng):
    # homologous crossover: both parents are cut at the same relative point, so a child gets one copy
    # of each stretch of the developmental program instead of a duplicated or missing middle
    ia = int(rng.integers(1, len(a["body"]) + 1))
    ib = min(len(b["body"]), max(0, round(ia * len(b["body"]) / max(1, len(a["body"])))))
    body = [list(x) for x in a["body"][:ia]] + [list(x) for x in b["body"][ib:]]
    body = body[:48] or [list(a["body"][0])]
    pick = rng.random(NW) < 0.5
    return {"body": body, "brain": np.where(pick, a["brain"], b["brain"]).astype(np.float32),
            "repro": (a["repro"] + b["repro"]) / 2, "temp": (a["temp"] + b["temp"]) / 2,
            "mut": math.sqrt(a["mut"] * b["mut"]), "hue": a["hue"],
            "warm": (a.get("warm", 0.0) + b.get("warm", 0.0)) / 2, "care": (a.get("care", 0.0) + b.get("care", 0.0)) / 2,
            "mhc": [x if rng.random() < 0.5 else y for x, y in zip(_mhc(a, rng), _mhc(b, rng))]}


# ── names ────────────────────────────────────────────────────────────────
ROOTS = {SKIN: "Derm", PHOTO: "Phyto", MOUTH: "Stoma", FLAG: "Flagell", EYE: "Ophthalm",
         ARMOR: "Thorac", STORE: "Lipo", NEURON: "Neur", GONAD: "Gam"}
SYL = ["ra", "lo", "mi", "sen", "tu", "vex", "an", "il", "or", "ca", "bri", "nu", "pel", "zo", "ty", "qua", "fe", "dor"]


def species_name(sid, cnt, n):
    cnt = np.asarray(cnt)
    order = [int(i) for i in np.argsort(-cnt) if cnt[i] > 0]
    root = ROOTS[order[0]] + (ROOTS[order[1]].lower() if len(order) > 1 and cnt[order[1]] * 3 >= cnt[order[0]] else "")
    suf = "cyta" if n == 1 else "cola" if n <= 4 else ("zoa" if cnt[FLAG] else "phyta" if cnt[PHOTO] * 2 >= n else "morpha")
    h = sid * 2654435761 % 2 ** 32
    ep = SYL[h % 18] + SYL[(h >> 5) % 18] + ("us" if h & 1 else "a")
    return f"{root}{suf} {ep}"


# ── the world ────────────────────────────────────────────────────────────
def _new_vents(rng):
    """Two hydrothermal vents on the floor of the deep ocean, well away from the light."""
    return [[float(rng.uniform(10, 0.5 * BASIN_W)), float(rng.uniform(0, ARENA))] for _ in range(2)]


_ZONE_OF_COL = (np.arange(GRID_X) * (WORLD_W / GRID_X) // BASIN_W).astype(int)
_N_TARGET = np.tile(np.array([4.0, 5.0, 2.0, 2.0, 0.8], np.float32)[_ZONE_OF_COL][None, :], (GRID, 1))   # rich deep water, poor soil


def basin_of(x):
    return (np.asarray(x) // BASIN_W).astype(np.int64) % BASINS


def region_of(x):
    return REGION[basin_of(x)]


def _wrap(d):          # north-south
    return (d + ARENA / 2) % ARENA - ARENA / 2


def _wx(d):            # west-east
    return (d + WORLD_W / 2) % WORLD_W - WORLD_W / 2


def _water_x(rng, n=None):
    """A random position in the shallow water where life starts (open sea to tidal flats)."""
    return rng.uniform(SEA * BASIN_W, LAND * BASIN_W, n)


class Pool:
    def __init__(self, era: int, seed: int):
        self.era, self.seed = era, seed
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.next_uid = 1
        self.births = self.deaths = self.kills = 0
        z = lambda dt=np.float32: np.zeros(CAP, dt)
        self.alive = np.zeros(CAP, bool)
        self.uid, self.gen, self.species, self.plan = z(np.int64), z(np.int64), z(np.int64), z(np.int64)
        self.x, self.y, self.hd, self.energy, self.age, self.life = z(), z(), z(), z(), z(np.int32), z(np.int32)
        self.tl, self.s_photo, self.s_det, self.s_pred = z(), z(), z(), z()
        self.n, self.cnt, self.expo = z(np.int16), np.zeros((CAP, NT), np.int16), z()
        self.emax, self.metab, self.vmax, self.sense, self.att, self.dfn, self.rad = z(), z(), z(), z(), z(), z(), z()
        self.repro, self.temp, self.hidden = z(), z(), z(np.int8)
        self.W = np.zeros((CAP, NW), np.float32)
        self.warm, self.care = z(), z()
        self.sus = z()             # how well the current pathogen strains fit this creature's immune genes (0..1)
        self.pathogens = [[float(v) for v in self.rng.random(MHC)] for _ in range(STRAINS)]
        self.mom, self.mom_uid, self.fed_until = np.full(CAP, -1, np.int64), z(np.int64), z(np.int64)
        self.genomes = [None] * CAP
        self.plans, self.plan_ids, self.next_pid = {}, {}, 1
        self.clock_gen, self.last_mg, self.restarts, self.bank, self.seg_peak = 0.0, 0.0, 0, 0.0, 0.0
        self.spec = {}          # species id -> {founder cnt, brain, name, born_tick, born_gen, parent}
        self.next_sid = 1
        self.N = np.full((GRID, GRID_X), 3.0, np.float32)    # dissolved nutrient
        self.D = np.zeros((GRID, GRID_X), np.float32)        # dead matter (detritus)
        self.world_v = 2
        self.clim = {"band": ARENA / 2, "width": 55.0, "temp": 0.0, "cur": float(self.rng.uniform(0, 6.283)),
                     "up": [[float(_water_x(self.rng)), float(self.rng.uniform(0, ARENA))] for _ in range(4)],
                     "vents": _new_vents(self.rng),
                     "shock_temp": 0.0, "shock_until": 0,
                     "gaps": [float(self.rng.uniform(0, ARENA)) for _ in range(BASINS)]}
        self.milestones = {}
        self.ms_streak = {}
        self.events = []        # catastrophes etc., kept in state for the timeline
        self.last_stats = None
        for _ in range(START):
            self._spawn(new_genome(self.rng), _water_x(self.rng), self.rng.uniform(0, ARENA), 0, None, 6.0)

    # ── bookkeeping ───────────────────────────────────────────────────
    def _plan_id(self, cells):
        key = tuple(sorted(cells))
        pid = self.plan_ids.get(key)
        if pid is None:
            pid = self.next_pid
            self.next_pid += 1
            self.plan_ids[key] = pid
            self.plans[pid] = [list(c) for c in cells]
        return pid

    def _species_for(self, g, cnt, parent_sid, gen):
        if parent_sid:
            f = self.spec.get(parent_sid)
            if f is not None:
                d = np.abs(cnt - f["cnt"]).sum() / max(cnt.sum(), f["cnt"].sum(), 1) + \
                    float(np.abs(g["brain"] - f["brain"]).mean()) * 0.8
                if d < 0.55:
                    return parent_sid
        sid = self.next_sid
        self.next_sid += 1
        self.spec[sid] = {"cnt": cnt.copy(), "brain": g["brain"].copy(), "name": species_name(sid, cnt, int(cnt.sum())),
                          "born": self.tick, "born_gen": int(gen), "parent": parent_sid}
        return sid

    def _spawn(self, g, x, y, gen, parent_sid, energy, tl=1.0, mom=-1):
        free = np.flatnonzero(~self.alive)
        if not len(free):
            return None
        i = int(free[0])
        cells = develop(g["body"])
        n, cnt, expo = phenotype(cells)
        self.genomes[i] = g
        self.alive[i] = True
        self.uid[i] = self.next_uid; self.next_uid += 1
        self.gen[i] = gen
        self.x[i], self.y[i] = x % WORLD_W, y % ARENA
        self.hd[i] = self.rng.uniform(0, 6.283)
        self.age[i] = 0
        self.n[i], self.cnt[i], self.expo[i] = n, cnt, expo
        c = cnt.astype(np.float32)
        self.emax[i] = 12.0 * n + 45.0 * c[STORE]
        self.energy[i] = min(energy, self.emax[i])
        self.metab[i] = (0.018 * n ** 0.75 + 0.012 * c[FLAG] + 0.012 * c[NEURON] + 0.010 * c[EYE] + 0.012 * c[ARMOR]
                         + 0.004 * c[STORE] + 0.006 * c[GONAD])
        self.vmax[i] = min(1.6, 0.55 * c[FLAG] / math.sqrt(n)) / (1.0 + 0.08 * c[ARMOR])   # plates are heavy
        self.sense[i] = 1.5 + (min(SENSE_MAX - 1.5, 7.0 * c[EYE] ** 0.7) if c[EYE] else 0.0)
        self.att[i] = (c[MOUTH] * 1.0 + 1.0 * math.sqrt(n)) if c[MOUTH] else 0.0   # size helps, with diminishing returns
        self.dfn[i] = 0.5 + 3.0 * math.sqrt(c[ARMOR]) + 1.1 * math.sqrt(n)   # each extra plate adds less
        self.rad[i] = 0.5 + 0.55 * math.sqrt(n)
        self.life[i] = int((1500 + 150 * n) * self.rng.uniform(0.7, 1.3))
        self.repro[i] = g["repro"]
        self.temp[i] = g["temp"]
        self.hidden[i] = min(H, 2 + 2 * int(c[NEURON]))
        # dormant hidden units (no neuron cells to run them) fade toward silence, so when a neuron cell does
        # appear its new units start nearly neutral instead of scrambling a working controller
        h = int(self.hidden[i])
        if h < H:
            W2 = g["brain"][IN * H + H:IN * H + H + H * OUT].reshape(H, OUT)
            W2[h:] *= 0.7
        self.W[i] = g["brain"]
        self.sus[i] = self._susceptibility(_mhc(g, self.rng))
        self.warm[i], self.care[i] = g.get("warm", 0.0), g.get("care", 0.0)
        self.mom[i] = mom
        self.mom_uid[i] = self.uid[mom] if mom >= 0 else 0
        self.fed_until[i] = 0
        self.tl[i] = tl
        self.s_photo[i], self.s_det[i], self.s_pred[i] = (1.0, 0.0, 0.0) if c[PHOTO] else (0.0, 1.0, 0.0)  # priors; real income takes over
        self.plan[i] = self._plan_id(cells)
        self.species[i] = self._species_for(g, cnt, parent_sid, gen)
        self.births += 1
        return i

    def _susceptibility(self, mhc):
        m = np.asarray(mhc, np.float32)
        best = 0.0
        for key in self.pathogens:
            d = np.abs(m - np.asarray(key, np.float32))
            d = np.minimum(d, 1.0 - d)                       # the lock space wraps around
            best = max(best, float(math.exp(-(np.sqrt((d * d).sum()) / PATH_R) ** 2)))
        return best

    def _evolve_pathogens(self):
        """Each strain drifts toward the immune genes of the hosts it already fits best: whatever genotype is
        common gets hunted. Rare genotypes escape, which is the advantage sex gives (it shuffles the locks)."""
        a = np.flatnonzero(self.alive)
        if len(a) < 10:
            return
        M = np.array([_mhc(self.genomes[i], self.rng) for i in a], np.float32)
        for k, key in enumerate(self.pathogens):
            kk = np.asarray(key, np.float32)
            d = np.abs(M - kk)
            d = np.minimum(d, 1.0 - d)
            dist = np.sqrt((d * d).sum(1))
            near = M[np.argsort(dist)[:max(5, len(a) // 8)]]
            # circular mean of the closest hosts, then step toward it
            ang = near * 2 * math.pi
            tgt = (np.arctan2(np.sin(ang).mean(0), np.cos(ang).mean(0)) / (2 * math.pi)) % 1.0
            step = ((tgt - kk + 0.5) % 1.0) - 0.5
            self.pathogens[k] = [float(v) for v in (kk + 0.35 * step + self.rng.normal(0, 0.02, MHC)) % 1.0]
        self.sus[a] = [self._susceptibility(m) for m in M]

    def _die(self, idx):
        if not len(idx):
            return
        gx = (self.x[idx] / CELL).astype(int) % GRID_X
        gy = (self.y[idx] / CELL).astype(int) % GRID
        np.add.at(self.D, (gy, gx), np.maximum(self.energy[idx], 0) + 2.0 * self.n[idx])
        np.add.at(self.N, (gy, gx), 0.8 * self.n[idx])
        self.alive[idx] = False
        for i in idx:
            self.genomes[int(i)] = None
        self.deaths += len(idx)

    # ── environment ───────────────────────────────────────────────────
    def tide(self, t=None):
        """0 = low water, 1 = high water."""
        t = self.tick if t is None else t
        return 0.5 + 0.5 * math.sin(2 * math.pi * t / TIDE)

    def waterline(self, t=None):
        """How far up the tidal flats (0 = seaward edge, 1 = beach) the water reaches."""
        return 0.4 + 0.55 * self.tide(t)

    def habitat(self, x, t=None):
        """Per position: habitat index, light factor, current factor, temperature factor, exposed (out of water),
        depth (0..1, deep ocean only) and inland distance (0..1, land only)."""
        x = np.asarray(x)
        h = basin_of(x)
        within = (x - h * BASIN_W) / BASIN_W                    # 0 at a zone's west edge, 1 at its east edge
        depth = np.where(h == DEEP, 1.0 - within, 0.0)          # the deep gets deeper toward the abyss (west)
        inland = np.where(h == LAND, within, 0.0)
        exposed = ((h == TIDAL) & (within > self.waterline(t))) | (h == LAND)
        lightf = np.select([h == DEEP, h == SEA, h == LAND, exposed], [0.9 * np.exp(-3.6 * depth), 0.9, 1.35, 1.3], 1.0)
        curf = np.select([h == DEEP, h == SEA, h == TIDAL, h == LAND], [0.4, 1.5, 1.25, 0.0], 1.0)
        tempf = np.select([h == DEEP, h == SEA, h == LAND, exposed], [0.25, 0.6, 1.9, 1.6], 1.0)
        return h, lightf, curf, tempf, exposed, depth, inland

    def vent_heat(self, x, y):
        """Hydrothermal vents warm the water around them (and feed the bacterial mats that grow there)."""
        heat = np.zeros(len(x), np.float32)
        for vx, vy in self.clim.get("vents", []):
            d = np.hypot(_wx(x - vx), _wrap(y - vy))
            heat += 0.9 * np.exp(-(d / 9.0) ** 2)
        return heat

    def light(self, y, t):
        day = 0.03 + 0.97 * max(0.0, math.sin(2 * math.pi * t / DAY))
        season = 0.85 + 0.15 * math.sin(2 * math.pi * t / YEAR)
        band = np.exp(-(_wrap(y - self.clim["band"]) / self.clim["width"]) ** 2)
        return day * season * (0.15 + 0.85 * band)

    def temperature(self, y, t):
        orbit = 0.45 * math.sin(2 * math.pi * t / ORBIT)
        season = 0.15 * math.sin(2 * math.pi * t / YEAR)
        lat = 0.7 * np.cos(2 * math.pi * _wrap(y - self.clim["band"]) / ARENA)
        return lat + season + orbit + self.clim["temp"] + self.clim["shock_temp"]

    def _climate(self):
        c, rng = self.clim, self.rng
        c["band"] = (c["band"] + rng.normal(0, 0.8)) % ARENA
        c["width"] = float(np.clip(c["width"] + rng.normal(0, 0.8), 30, 90))
        c["temp"] = float(np.clip(0.995 * c["temp"] + rng.normal(0, 0.02), -1, 1))
        c["cur"] = float((c["cur"] + rng.normal(0, 0.06)) % 6.283)
        c.setdefault("gaps", [float(rng.uniform(0, ARENA)) for _ in range(BASINS)])
        c["gaps"] = [float((gp + rng.normal(0, 2.0)) % ARENA) for gp in c["gaps"]]
        for k, u in enumerate(c["up"]):
            u[0] = (u[0] + rng.normal(0, 1.5)) % WORLD_W
            u[1] = (u[1] + rng.normal(0, 1.5)) % ARENA
            if k < 2:                       # two upwellings belong to the open sea: deep water rising
                u[0] = float(np.clip(u[0], SEA * BASIN_W + 4, SHALLOWS * BASIN_W - 4))
            else:                           # the others wander the shallow water, never onto land
                u[0] = float(np.clip(u[0], SEA * BASIN_W + 4, LAND * BASIN_W - 4))
        c.setdefault("vents", _new_vents(rng))
        for v in c["vents"]:                # vents shift very slowly along the deep floor
            v[0] = float(np.clip(v[0] + rng.normal(0, 0.3), 6, 0.55 * BASIN_W))
            v[1] = float((v[1] + rng.normal(0, 0.3)) % ARENA)
        if self.tick > c["shock_until"]:
            c["shock_temp"] *= 0.9
        self._evolve_pathogens()
        # catastrophes: rare, mostly small, occasionally severe (log-uniform)
        if rng.random() < CLIMATE_EVERY / 3_000_000:
            self._catastrophe()

    def _catastrophe(self):
        rng = self.rng
        kind = rng.choice(["impact", "ice age", "anoxia", "hothouse"])
        sev = float(math.exp(rng.uniform(math.log(0.2), math.log(0.95))))
        a = np.flatnonzero(self.alive)
        killed = 0
        if kind == "impact":
            cx, cy, r = rng.uniform(0, WORLD_W), rng.uniform(0, ARENA), 20 + 80 * sev
            d = np.hypot(_wx(self.x[a] - cx), _wrap(self.y[a] - cy))
            hit = a[(d < r) & (rng.random(len(a)) < sev)]
            killed = len(hit)
            self._die(hit)
        elif kind == "ice age":
            self.clim["shock_temp"] = -0.6 * sev
            self.clim["shock_until"] = self.tick + int(60000 * sev)
        elif kind == "hothouse":
            self.clim["shock_temp"] = 0.5 * sev
            self.clim["shock_until"] = self.tick + int(60000 * sev)
        else:
            self.N *= (1 - 0.8 * sev)
        ev = {"tick": int(self.tick), "kind": str(kind), "severity": round(sev, 2), "killed": int(killed),
              "geo_ma": self.geo_ma()}
        self.events.append(ev)
        self.events = self.events[-200:]
        _ledger("pool.catastrophe", {"era": self.era, **ev})

    def _fields(self):
        c = self.clim
        for ux, uy in c["up"]:
            gx, gy = int(ux / CELL), int(uy / CELL)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    self.N[(gy + dy) % GRID, (gx + dx) % GRID_X] += 0.04
        for vx, vy in c.get("vents", []):   # chemosynthetic bacterial mats: food that needs no sunlight
            gx, gy = int(vx / CELL), int(vy / CELL)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    self.D[(gy + dy) % GRID, (gx + dx) % GRID_X] += 0.05
                    self.N[(gy + dy) % GRID, (gx + dx) % GRID_X] += 0.02
        if self.tick % 5 == 0:
            N, D = self.N, self.D
            self.N = 0.6 * N + 0.1 * (np.roll(N, 1, 0) + np.roll(N, -1, 0) + np.roll(N, 1, 1) + np.roll(N, -1, 1))
            decay = 0.01 * D
            self.D = D - decay
            self.N += decay * 0.8
            self.N += 0.003 * (_N_TARGET - self.N)   # exchange with deep water: richer in the open sea
            self.D = 0.8 * self.D + 0.05 * (np.roll(self.D, 1, 0) + np.roll(self.D, -1, 0) + np.roll(self.D, 1, 1) + np.roll(self.D, -1, 1))
            # marine snow: a little of the open sea's dead matter sinks down the slope into the deep
            s0, s1 = SEA * GRID_X // BASINS, SHALLOWS * GRID_X // BASINS
            snow = 0.03 * self.D[:, s0:s1]
            self.D[:, s0:s1] -= snow
            self.D[:, :s0] += snow.sum(1, keepdims=True) / s0

    # ── one tick ──────────────────────────────────────────────────────
    def step(self):
        from scipy.spatial import cKDTree
        rng, t = self.rng, self.tick
        if t % CLIMATE_EVERY == 0:
            self._climate()
        self._fields()
        a = np.flatnonzero(self.alive)
        if len(a) < 4:
            for _ in range(30):
                self._spawn(new_genome(rng), _water_x(rng), rng.uniform(0, ARENA), 0, None, 6.0)
            self.restarts += 1
            self.bank += self.seg_peak          # bank the time evolved before the near-extinction
            self.seg_peak = 0.0
            ev = {"tick": int(t), "kind": "near-extinction · life re-seeded", "severity": 1.0, "killed": 0,
                  "geo_ma": self.geo_ma()}
            self.events.append(ev)
            _ledger("pool.reseeded", {"era": self.era, "tick": int(t), "survivors": int(len(a)), "geo_ma": ev["geo_ma"]})
            a = np.flatnonzero(self.alive)
        n = len(a)
        x, y, hd = self.x[a], self.y[a], self.hd[a]
        gx = (x / CELL).astype(int) % GRID_X
        gy = (y / CELL).astype(int) % GRID
        hab, lightf, curf, tempf, exposed, depth, inland = self.habitat(x, t)
        on_land = hab == LAND
        L = self.light(y, t) * lightf
        # the deep is cold and steady except beside the vents
        Tm = self.temperature(y, t) * tempf - 0.55 * depth + self.vent_heat(x, y) * (hab == DEEP)
        Nc, Dc = self.N[gy, gx], self.D[gy, gx]
        photo = self.cnt[a, PHOTO].astype(np.float32)
        # producers compete for light within ~10-unit patches
        sx, sy = gx // 2, gy // 2
        shade_tot = np.zeros((GRID // 2, GRID_X // 2), np.float32)
        own = self.expo[a]                       # a body's own cells are already accounted for by their exposure
        np.add.at(shade_tot, (sy, sx), own)
        shade = 1.0 / (1.0 + (shade_tot[sy, sx] - own) / 2.0)
        occ = np.zeros((GRID // 2, GRID_X // 2), np.float32)
        np.add.at(occ, (sy, sx), self.n[a].astype(np.float32))
        crowd = 1.0 + 0.1 * np.maximum(0.0, occ[sy, sx] - 3.0)   # space and oxygen get scarce in a packed patch
        sus = self.sus[a]
        load = np.zeros((GRID // 2, GRID_X // 2), np.float32)
        np.add.at(load, (sy, sx), sus)
        sick = 1.0 + 0.5 * sus * np.minimum(np.maximum(load[sy, sx] - sus, 0.0) / 2.0, 1.5)   # infection needs other hosts nearby

        # neighbours (periodic)
        box = np.array([WORLD_W, ARENA])
        pos = np.mod(np.stack([x, y], 1).astype(np.float64), box)
        pos[pos >= box] = 0.0
        tree = cKDTree(pos, boxsize=box)
        k = min(K_NEAR + 1, n)
        dist, idx = tree.query(pos, k=k, distance_upper_bound=SENSE_MAX)
        dist, idx = dist[:, 1:], idx[:, 1:]
        valid = idx < n
        idx = np.where(valid, idx, 0)
        # eyes need light: in the dark deep they see almost nothing. Neurons add a short-range sense of movement
        # in the water around the body (a lateral line), which works in any light.
        nh = np.minimum(self.cnt[a, NEURON], 3).astype(np.float32)
        ce = self.cnt[a, EYE].astype(np.float32)
        eye_r = np.where(ce > 0, np.minimum(SENSE_MAX - 1.5, 7.0 * ce ** 0.7), 0.0)
        sense = np.minimum(SENSE_MAX, 1.5 + eye_r * np.clip(lightf / 0.6, 0, 1) + 3.0 * nh)[:, None]
        att, dfn, sp = self.att[a], self.dfn[a], self.species[a]
        rad = self.rad[a]
        bas = basin_of(x)
        reg = REGION[bas]
        within = valid & (dist <= sense + rad[idx]) & (reg[idx] == reg[:, None])   # reefs block sight and reach
        can_eat = within & (att[:, None] > dfn[idx])
        threat = within & (att[idx] > dfn[:, None])
        mate = within & (sp[idx] == sp[:, None]) & (self.cnt[a][idx][..., GONAD] > 0)

        def nearest(mask):
            dd = np.where(mask, dist, np.inf)
            j = dd.argmin(1)
            has = np.isfinite(dd[np.arange(n), j])
            return idx[np.arange(n), j], has, dd[np.arange(n), j]

        jp, hp, dp = nearest(can_eat)
        jt, ht, dt_ = nearest(threat)
        jm, hm, dm = nearest(mate)
        c, s_ = np.cos(hd), np.sin(hd)

        def local(j, has, d):
            dx, dy = _wx(x[j] - x), _wrap(y[j] - y)
            lx = (dx * c + dy * s_) / np.maximum(d, 1e-3)
            ly = (-dx * s_ + dy * c) / np.maximum(d, 1e-3)
            prox = np.where(has, 1.0 - np.minimum(d, SENSE_MAX) / SENSE_MAX, 0.0)
            return np.where(has, lx, 0), np.where(has, ly, 0), prox

        plx, ply, pp = local(jp, hp, dp)
        tlx, tly, tp = local(jt, ht, dt_)
        gyL = (self.light(y + 3, t) - self.light(y - 3, t)) * 3
        warm = self.warm[a]
        temp_mis = (Tm - self.temp[a]) * (1.0 - 0.9 * warm)       # warm-blooded bodies hold their own temperature
        efrac = self.energy[a] / self.emax[a]
        inp = np.stack([np.ones(n), efrac, L, np.tanh(Nc / 5), np.tanh(Dc / 10), np.tanh(temp_mis),
                        gyL * s_, gyL * c, plx, ply, pp, tlx, tly, tp,
                        np.where(hm, 1 - dm / SENSE_MAX, 0), rng.standard_normal(n) * 0.5], 1).astype(np.float32)
        Wa = self.W[a]
        W1 = Wa[:, :IN * H].reshape(n, IN, H)
        b1 = Wa[:, IN * H:IN * H + H]
        W2 = Wa[:, IN * H + H:IN * H + H + H * OUT].reshape(n, H, OUT)
        b2 = Wa[:, -OUT:]
        hmask = (np.arange(H)[None, :] < self.hidden[a][:, None]).astype(np.float32)
        hid = np.tanh(np.einsum("ni,nih->nh", inp, W1) + b1) * hmask
        out = np.einsum("nh,nho->no", hid, W2) + b2
        turn = np.tanh(out[:, 0])
        throttle = 1 / (1 + np.exp(-out[:, 1]))
        eat = 1 / (1 + np.exp(-out[:, 2]))
        breed = 1 / (1 + np.exp(-out[:, 3]))

        # movement: own thrust plus a slow ocean current and jitter
        hd = (hd + 0.35 * (1 + 0.3 * nh) * turn) % 6.283              # neurons: faster, finer reflexes
        # out of water flagella barely work; on land, stiff cells (armour, a skeleton) worked by flagella
        # (muscle) make legs
        n_f = self.n[a].astype(np.float32)
        legs = np.minimum(self.cnt[a, ARMOR], self.cnt[a, FLAG]).astype(np.float32)
        v_land = np.minimum(1.2, 0.25 * self.vmax[a] + 0.5 * legs / np.sqrt(n_f))
        v = throttle * np.where(on_land, v_land, self.vmax[a] * np.where(exposed, 0.25, 1.0))   # stranded at low tide
        cur = self.clim["cur"]
        nx = (x + v * np.cos(hd) + rng.normal(0, 0.05, n)) % WORLD_W    # currents run along the coast, so nothing piles up on a reef
        y = (y + v * np.sin(hd) + 0.012 * curf * math.sin(cur) + rng.normal(0, 0.05, n)) % ARENA
        crossed = basin_of(nx) != bas
        if crossed.any():
            # which boundary: moving east crosses the next zone's west edge, moving west this zone's own
            right = _wx(nx - x) > 0
            wall = np.where(right, (bas + 1) % BASINS, bas)
            kind = np.array(WALL_KIND)[wall]
            gaps = np.array(self.clim["gaps"], np.float32)
            through = (kind == 1) | ((kind == 2) & (np.abs(_wrap(y - gaps[wall])) < GAP_H / 2) & (self.rad[a] < 2.3))   # giants don't fit the straits
            blocked = crossed & ~through
            nx = np.where(blocked, x, nx)
            hd = np.where(blocked, (math.pi - hd) % 6.283, hd)    # bounce off the reef
        x = nx
        self.x[a], self.y[a], self.hd[a] = x, y, hd

        # energy: light, dead matter, metabolism (temperature-dependent), waste back into the water
        nutf = Nc / (Nc + 2.0)
        g_photo = 0.9 * self.expo[a] * L * nutf * shade
        mouth = self.cnt[a, MOUTH].astype(np.float32)
        g_det = np.where(eat > 0.3, np.minimum(Dc * 0.15, 0.06 * mouth), 0.0)
        # drying out of water: skin cells hold water in (about 40% skin protects fully); land dries harder further inland
        protect = np.clip(2.5 * self.cnt[a, SKIN] / n_f, 0, 1)
        dry = 1.0 + (1.0 - protect) * np.where(on_land, 0.9 + 0.9 * inland, np.where(exposed, 0.4, 0.0))
        # on land nothing floats: big bodies need a skeleton (armour cells) to carry their own weight
        support = np.where(on_land & (n_f > 8), 1.0 + 0.03 * (n_f - 8) * (1 - np.clip(self.cnt[a, ARMOR] / n_f / 0.15, 0, 1)), 1.0)
        cost = (self.metab[a] * (1 + 0.4 * np.minimum(temp_mis ** 2, 1.5)) * (1 + 0.5 * warm) * crowd * dry * support * sick
                + 0.004 * v * self.n[a])
        np.subtract.at(self.N, (gy, gx), g_photo * 0.5)
        np.subtract.at(self.D, (gy, gx), g_det)
        np.add.at(self.N, (gy, gx), cost * 0.6)
        np.maximum(self.N, 0, out=self.N)
        np.maximum(self.D, 0, out=self.D)
        self.energy[a] = np.minimum(self.energy[a] + g_photo + 0.7 * g_det - cost, self.emax[a])
        # diet = where the energy actually came from (decaying sums, so a kill counts by its size)
        self.s_photo[a] = 0.998 * self.s_photo[a] + g_photo
        self.s_det[a] = 0.998 * self.s_det[a] + 0.7 * g_det
        self.s_pred[a] *= 0.998
        self.age[a] += 1

        # predation: one attempt per hunter per tick; a creature is eaten at most once
        # hunters that are full, or still digesting their last meal, do not attack (handling time)
        hungry = (self.energy[a] < 0.85 * self.emax[a]) & (self.fed_until[a] <= t)
        hunt = np.flatnonzero(hp & hungry & (eat > 0.5) & (mouth > 0) & (dp <= rad + rad[jp] + 0.6))
        if len(hunt):
            rng.shuffle(hunt)
            taken = set()
            dead = []
            for h in hunt:
                pr = int(jp[h])
                if pr in taken or h in taken:
                    continue
                ih, ip = a[h], a[pr]
                self.energy[ih] -= 0.05
                ah, dp_ = att[h] * (1 + 0.12 * nh[h]), dfn[pr] * (1 + 0.12 * nh[pr])   # coordination: strike and dodge
                if rng.random() < ah / (ah + dp_):
                    taken.add(pr)
                    food = max(0.0, float(self.energy[ip])) + 2.0 * float(self.n[ip])
                    gain = min(0.6 * food, float(self.emax[ih] - self.energy[ih]))
                    self.fed_until[ih] = t + 40 + 4 * int(self.n[ip])
                    self.energy[ih] += gain
                    self.s_pred[ih] += gain
                    self.tl[ih] = 0.9 * self.tl[ih] + 0.1 * (self.tl[ip] + 1)
                    self.D[gy[pr], gx[pr]] += food - gain
                    self.energy[ip] = 0
                    dead.append(ip)
                    self.kills += 1
            if dead:
                self.alive[np.array(dead)] = False
                for i in dead:
                    self.genomes[int(i)] = None
                self.deaths += len(dead)
        # trophic level drifts toward what each creature actually eats (prey level + 1 is set at each kill)
        tot = self.s_photo[a] + self.s_det[a] + self.s_pred[a] + 1e-6
        prod, detr = self.s_photo[a] / tot, self.s_det[a] / tot
        self.tl[a] = 0.995 * self.tl[a] + 0.005 * (prod * 1.0 + detr * 2.0 + (1 - prod - detr) * self.tl[a])

        # deaths: starvation, old age
        al = self.alive[a]
        die = a[al & ((self.energy[a] <= 0) | (self.age[a] > self.life[a]))]
        self._die(die)

        # parental care: a parent with "care" keeps feeding its young while they are near
        kids = np.flatnonzero(self.alive & (self.age < JUVENILE) & (self.mom >= 0))
        if len(kids):
            m = self.mom[kids]
            ok = self.alive[m] & (self.uid[m] == self.mom_uid[kids]) & (self.care[m] > 0.02)
            if ok.any():
                kids, m = kids[ok], m[ok]
                near = (np.hypot(_wx(self.x[kids] - self.x[m]), _wrap(self.y[kids] - self.y[m])) < 10) & \
                       (region_of(self.x[kids]) == region_of(self.x[m]))
                kids, m = kids[near], m[near]
                if len(kids):
                    give = np.minimum(self.care[m] * 0.05, 0.02 * np.maximum(self.energy[m], 0))
                    give = np.minimum(give, np.maximum(self.emax[kids] - self.energy[kids], 0))
                    np.subtract.at(self.energy, m, give)
                    np.add.at(self.energy, kids, give * 0.9)

        # reproduction
        ready = np.flatnonzero(self.alive[a] & (self.energy[a] >= self.repro[a] * self.emax[a]) & (breed > 0.5)
                               & (self.age[a] >= MIN_AGE))
        if len(ready):
            rng.shuffle(ready)
            gon = a[(self.cnt[a, GONAD] > 0) & ~exposed]       # gametes need water: no broadcast spawning on land
            spawners = {}
            if len(gon):
                for j, b_ in zip(gon.tolist(), region_of(self.x[gon]).tolist()):
                    spawners.setdefault((int(self.species[j]), b_), []).append(j)
            for r_ in ready[:40]:
                i = int(a[r_])
                if not self.alive[i]:
                    continue
                g = self.genomes[i]
                mate_i = None
                if self.cnt[i, GONAD] and hm[r_]:
                    j = int(a[jm[r_]])
                    if self.alive[j] and self.energy[j] > 0.3 * self.emax[j]:
                        mate_i = j
                broadcast = False
                if mate_i is None and self.cnt[i, GONAD] and not exposed[r_]:
                    # broadcast spawning: gametes released into the water can reach a distant conspecific
                    # in the same basin (how sex works for corals, urchins and most early animals)
                    key = (int(self.species[i]), int(region_of(np.array([self.x[i]]))[0]))
                    pool_ = [j for j in spawners.get(key, []) if j != i and self.alive[j]]
                    if pool_ and rng.random() < 0.6:
                        mate_i = pool_[int(rng.integers(len(pool_)))]
                        broadcast = True
                if mate_i is not None:
                    child = mutate(crossover(g, self.genomes[mate_i], rng), rng)
                    gift = 0.0 if broadcast else 0.15 * float(self.energy[mate_i])
                    self.energy[mate_i] -= gift
                else:
                    child = mutate(g, rng)
                    gift = 0.0
                build = 3.0 * float(self.n[i])
                if self.energy[i] <= build:
                    continue
                self.energy[i] -= build
                share = 0.5 * float(self.energy[i])
                self.energy[i] -= share
                ang = rng.uniform(0, 6.283)
                off = float(self.rad[i]) + 1 + rng.uniform(0, 3)
                if region_of(np.array([(self.x[i] + math.cos(ang) * off) % WORLD_W]))[0] != region_of(np.array([self.x[i]]))[0]:
                    ang = math.pi - ang                 # born on the parent's side of the reef
                k_ = self._spawn(child, self.x[i] + math.cos(ang) * off, self.y[i] + math.sin(ang) * off,
                                 int(self.gen[i]) + 1, int(self.species[i]), share + gift, float(self.tl[i]), mom=i)
                if k_ is None:
                    self.energy[i] += share
                    break
        self.tick += 1
        if self.tick % STATS_EVERY == 0:
            self._advance_clock()
            self._prune()
            self.last_stats = self.stats()
            self._milestones(self.last_stats)
            return self.last_stats
        return None

    # ── measurement ───────────────────────────────────────────────────
    def _advance_clock(self):
        """Deep time only moves forward: the furthest the mean generation has reached since the last re-seed,
        plus the time banked before each near-extinction (founders restart at generation 0)."""
        a = self.alive
        mg = float(self.gen[a].mean()) if a.any() else 0.0
        self.seg_peak = max(self.seg_peak, mg)
        self.clock_gen = self.bank + self.seg_peak
        self.last_mg = mg

    def _prune(self):
        """Forget body plans and species nobody alive (or any milestone) refers to, so state stays small."""
        a = np.flatnonzero(self.alive)
        keep = set(int(x) for x in np.unique(self.plan[a]))
        for m in self.milestones.values():
            if m.get("exemplar"):
                keep.add(int(m["exemplar"]["plan"]))
        if len(self.plans) > len(keep) * 2 + 500:
            self.plans = {k: v for k, v in self.plans.items() if k in keep}
            self.plan_ids = {k: v for k, v in self.plan_ids.items() if v in keep}
        alive_sp = set(int(x) for x in np.unique(self.species[a]))
        keep_sp = alive_sp | {self.spec[s_]["parent"] for s_ in alive_sp if s_ in self.spec and self.spec[s_]["parent"]}
        if len(self.spec) > len(keep_sp) * 2 + 500:
            self.spec = {k: v for k, v in self.spec.items() if k in keep_sp}

    def geo_ma(self):
        return round(self.clock_gen * YEARS_PER_GEN / 1e6, 3)

    def stats(self):
        a = np.flatnonzero(self.alive)
        n = len(a)
        out = {"era": self.era, "tick": int(self.tick), "population": n, "births": self.births, "deaths": self.deaths,
               "kills": self.kills, "version": VERSION}
        if not n:
            return out
        cnt = self.cnt[a].astype(np.int32)
        ncell = self.n[a].astype(np.int32)
        types = (cnt > 0).sum(1)
        sp, counts = np.unique(self.species[a], return_counts=True)
        p = counts / counts.sum()
        tot = self.s_photo[a] + self.s_det[a] + self.s_pred[a] + 1e-6
        role = np.where(self.s_pred[a] / tot > 0.5, 2, np.where(self.s_det[a] > self.s_photo[a], 1, 0))
        glen = np.array([len(self.genomes[i]["body"]) for i in a])
        out.update({
            "mean_generation": round(float(self.gen[a].mean()), 2), "max_generation": int(self.gen[a].max()),
            "geo_ma": self.geo_ma(), "clock_generations": round(self.clock_gen, 1), "restarts": self.restarts,
            "cells_mean": round(float(ncell.mean()), 3), "cells_max": int(ncell.max()),
            "cells_p90": float(np.percentile(ncell, 90)),
            "types_max": int(types.max()), "types_mean": round(float(types.mean()), 3),
            "multicellular": round(float((ncell >= 2).mean()), 4),
            "genome_mean": round(float(glen.mean()), 2), "genome_max": int(glen.max()),
            "neurons_max": int(cnt[:, NEURON].max()), "eyes_share": round(float((cnt[:, EYE] > 0).mean()), 4),
            "motile_share": round(float((cnt[:, FLAG] > 0).mean()), 4),
            "armour_share": round(float((cnt[:, ARMOR] > 0).mean()), 4),
            "sexual_share": round(float((cnt[:, GONAD] > 0).mean()), 4),
            "neurons_mean": round(float(cnt[:, NEURON].mean()), 3), "neural_share": round(float((cnt[:, NEURON] > 0).mean()), 4),
            "disease": round(float(self.sus[a].mean()), 4),
            "producers": round(float((role == 0).mean()), 4), "grazers": round(float((role == 1).mean()), 4),
            "predators": round(float((role == 2).mean()), 4), "predator_count": int((role == 2).sum()),
            "trophic_max": round(float(np.percentile(self.tl[a], 98)), 3),
            "species": int(len(sp)), "species_eff": round(float(math.exp(-(p * np.log(p)).sum())), 2),
            "cell_mix": {CELL_NAMES[t]: int(cnt[:, t].sum()) for t in range(NT)},
            "biomass": int(ncell.sum()), "nutrient": round(float(self.N.mean()), 3), "detritus": round(float(self.D.mean()), 3),
            "temp": round(float(self.clim["temp"] + self.clim["shock_temp"]), 3),
            "warm_mean": round(float(self.warm[a].mean()), 4), "warm_share": round(float((self.warm[a] >= 0.5).mean()), 4),
            "care_mean": round(float(self.care[a].mean()), 4), "care_share": round(float((self.care[a] >= 0.3).mean()), 4),
            "basins": np.bincount(basin_of(self.x[a]), minlength=BASINS).astype(int).tolist(),
            "skin_share": round(float((cnt[:, SKIN] > 0).mean()), 4),
            "habitats": {HABITATS[h]: {"population": int((basin_of(self.x[a]) == h).sum()),
                                       "cells_mean": round(float(ncell[basin_of(self.x[a]) == h].mean()), 2) if (basin_of(self.x[a]) == h).any() else None}
                         for h in range(BASINS)},
        })
        out["complexity"] = round(float(np.percentile(ncell * types, 95)), 2)
        return out

    # Each needs to be established, not a lucky mutant: a share of the population and/or a whole species,
    # holding for MS_STREAK samples in a row. Diversity milestones only count once the founders' lineages
    # have had time to sort out (mean generation >= 500).
    MILESTONES = [
        ("first_multicellular", "First multicellular species", lambda s, p: p["sp_cells2"] >= 1 and s["multicellular"] >= 0.05),
        ("first_motile", "First swimmers (flagella)", lambda s, p: s["motile_share"] >= 0.05),
        ("first_predators", "First predators", lambda s, p: s["predators"] >= 0.02 and s["predator_count"] >= 10),
        ("differentiated", "Bodies with three or more cell types", lambda s, p: p["types3"] >= 0.03 * s["population"] and p["types3"] >= 10),
        ("first_eyes", "First eyes", lambda s, p: s["eyes_share"] >= 0.03),
        ("sex", "Sexual reproduction takes hold", lambda s, p: s["sexual_share"] >= 0.2),
        ("armour", "Armour in an arms race with predators", lambda s, p: s["armour_share"] >= 0.1 and s["predators"] >= 0.05),
        ("bodies_10", "A species with bodies of 10+ cells", lambda s, p: p["sp_cells10"] >= 1),
        ("nervous", "Nervous systems (3+ neurons)", lambda s, p: p["neur3"] >= 0.02 * s["population"] and p["neur3"] >= 10),
        ("food_chain_3", "A food chain three levels deep", lambda s, p: s["trophic_max"] >= 2.9),
        ("species_10", "Ten coexisting species", lambda s, p: s["mean_generation"] >= 500 and s["species_eff"] >= 10),
        ("bodies_20", "A species with bodies of 20+ cells", lambda s, p: p["sp_cells20"] >= 1),
        ("five_types", "Bodies with five cell types", lambda s, p: p["types5"] >= 10),
        ("bodies_40", "A species with bodies of 40+ cells", lambda s, p: p["sp_cells40"] >= 1),
        ("species_25", "Twenty-five coexisting species", lambda s, p: s["mean_generation"] >= 500 and s["species_eff"] >= 25),
        ("parental_care", "Parental care (parents feeding their young)", lambda s, p: p["sp_care"] >= 1),
        ("warm_blood", "Warm-blooded lineages", lambda s, p: p["sp_warm"] >= 1),
        ("warm_care_brain", "Warm-blooded, caring, big-brained species (the mammal-like package)", lambda s, p: p["sp_mammal"] >= 1),
        ("deep_life", "Life settles the deep ocean", lambda s, p: p["deep"] >= 15),
        ("vent_community", "A community living off the hydrothermal vents", lambda s, p: p["vent"] >= 10),
        ("land_life", "Life on land", lambda s, p: p["land"] >= 10),
        ("land_species", "A species that lives mostly on land", lambda s, p: p["sp_land"] >= 1),
    ]
    MS_STREAK = 5

    def _milestones(self, s):
        if not s.get("population"):
            return
        a = np.flatnonzero(self.alive)
        cnt = self.cnt[a]
        nc = self.n[a]
        types = (cnt > 0).sum(1)
        p = {"types3": int((types >= 3).sum()), "types5": int((types >= 5).sum()), "c10": int((nc >= 10).sum()),
             "c20": int((nc >= 20).sum()), "c40": int((nc >= 40).sum()), "neur3": int((cnt[:, NEURON] >= 3).sum())}
        xs, ys = self.x[a], self.y[a]
        zone = basin_of(xs)
        p["deep"] = int(((zone == DEEP) & (xs < 0.5 * BASIN_W)).sum())
        p["vent"] = int(((zone == DEEP) & (self.vent_heat(xs, ys) > 0.3)).sum())
        p["land"] = int((zone == LAND).sum())
        sp_ids, sp_n = np.unique(self.species[a], return_counts=True)
        land_n = np.array([int(((self.species[a] == sid) & (zone == LAND)).sum()) for sid in sp_ids]) if len(sp_ids) else np.array([])
        p["sp_land"] = int(((sp_n >= 8) & (land_n >= 0.6 * sp_n)).sum()) if len(sp_ids) else 0
        sp, inv, counts = np.unique(self.species[a], return_inverse=True, return_counts=True)
        mean_cells = np.bincount(inv, weights=nc.astype(float)) / counts
        big = counts >= 10                       # a species, not a handful of mutants
        for k in (2, 10, 20, 40):
            p[f"sp_cells{k}"] = int((big & (mean_cells >= k)).sum())
        mw = np.bincount(inv, weights=self.warm[a].astype(float)) / counts
        mc = np.bincount(inv, weights=self.care[a].astype(float)) / counts
        mn = np.bincount(inv, weights=cnt[:, NEURON].astype(float)) / counts
        p["sp_warm"] = int((big & (mw >= 0.5)).sum())
        p["sp_care"] = int((big & (mc >= 0.3)).sum())
        p["sp_mammal"] = int((big & (mw >= 0.5) & (mc >= 0.3) & (mn >= 2)).sum())
        for key, title, test in self.MILESTONES:
            if key in self.milestones:
                continue
            if s.get("mean_generation", 0) >= 20 and test(s, p):
                self.ms_streak[key] = self.ms_streak.get(key, 0) + 1
                if self.ms_streak[key] >= self.MS_STREAK:
                    ex = self.exemplar(key)
                    self.milestones[key] = {"key": key, "title": title, "tick": int(self.tick), "geo_ma": s["geo_ma"],
                                            "mean_generation": s["mean_generation"], "exemplar": ex}
                    _ledger("pool.milestone", {"era": self.era, **self.milestones[key]})
            else:
                self.ms_streak[key] = 0

    def exemplar(self, key=None):
        """The most complex living creature (cells x cell types), for milestone records and the UI."""
        a = np.flatnonzero(self.alive)
        if not len(a):
            return None
        score = self.n[a].astype(np.int32) * ((self.cnt[a] > 0).sum(1))
        i = int(a[score.argmax()])
        sid = int(self.species[i])
        return {"species": sid, "name": self.spec.get(sid, {}).get("name"), "cells": int(self.n[i]),
                "plan": int(self.plan[i]), "body": self.plans[int(self.plan[i])],
                "cell_counts": {CELL_NAMES[t]: int(self.cnt[i, t]) for t in range(NT) if self.cnt[i, t]},
                "generation": int(self.gen[i]), "trophic": round(float(self.tl[i]), 2)}

    def species_table(self, top=14):
        a = np.flatnonzero(self.alive)
        if not len(a):
            return []
        sp, counts = np.unique(self.species[a], return_counts=True)
        out = []
        for sid, cn in sorted(zip(sp.tolist(), counts.tolist()), key=lambda z: -z[1])[:top]:
            m = a[self.species[a] == sid]
            j = int(m[self.n[m].argmax()])
            tot = self.s_photo[m].sum() + self.s_det[m].sum() + self.s_pred[m].sum() + 1e-6
            role = "predator" if self.s_pred[m].sum() / tot > 0.4 else "grazer" if self.s_det[m].sum() > self.s_photo[m].sum() else "producer"
            f = self.spec.get(sid, {})
            out.append({"id": sid, "name": f.get("name"), "count": cn, "cells": round(float(self.n[m].mean()), 1),
                        "plan": int(self.plan[j]), "role": role, "hue": float(self.genomes[j]["hue"]),
                        "trophic": round(float(self.tl[m].mean()), 2),
                        "age_ma": round((float(self.gen[m].mean()) - f.get("born_gen", 0)) * YEARS_PER_GEN / 1e6, 3)})
        return out

    def frame(self):
        a = np.flatnonzero(self.alive)
        hue = np.array([self.genomes[i]["hue"] for i in a])
        return {"t": int(self.tick), "c": np.stack([self.uid[a], np.round(self.x[a] * 10), np.round(self.y[a] * 10),
                                                    np.round(self.hd[a] * 100), self.plan[a], np.round(hue * 360),
                                                    np.round(np.clip(self.energy[a] / self.emax[a], 0, 1) * 100), self.species[a]],
                                                   1).astype(np.int64).tolist()}

    def env(self):
        return {"band": round(float(self.clim["band"]), 1), "width": round(float(self.clim["width"]), 1),
                "light": round(float(self.light(np.array([self.clim["band"]]), self.tick)[0]), 3),
                "upwellings": [[round(u[0], 1), round(u[1], 1)] for u in self.clim["up"]],
                "current": round(float(self.clim["cur"]), 3),
                "reefs": [round(k * BASIN_W, 1) for k in range(BASINS)], "walls": WALL_KIND,
                "world": [WORLD_W, ARENA], "vents": [[round(v[0], 1), round(v[1], 1)] for v in self.clim.get("vents", [])],
                "habitats": HABITATS, "basin_w": BASIN_W, "tide": round(self.tide(), 3), "waterline": round(self.waterline(), 3),
                "day": round(max(0.0, math.sin(2 * math.pi * self.tick / DAY)), 3),
                "season": round(math.sin(2 * math.pi * self.tick / YEAR), 3),
                "straits": [round(float(g_), 1) for g_ in self.clim.get("gaps", [])], "strait_h": GAP_H,
                "detritus": np.round(np.clip(self.D[::4, ::4] / 20, 0, 1) * 100).astype(int).tolist(),
                "nutrient": np.round(np.clip(self.N[::4, ::4] / 12, 0, 1) * 100).astype(int).tolist()}


# ── persistence ──────────────────────────────────────────────────────────
def to_blob(p: Pool) -> bytes:
    return zlib.compress(pickle.dumps(p, protocol=4), 6)


def from_blob(b: bytes) -> Pool:
    p = pickle.loads(zlib.decompress(b))
    # migrate checkpoints written by older code
    if not hasattr(p, "next_pid"):
        p.next_pid = max(p.plans, default=0) + 1
    if not hasattr(p, "warm"):                 # Oct 25: basins, warm blood, parental care, handling time
        p.warm = np.array([(g or {}).get("warm", 0.0) for g in p.genomes], np.float32)
        p.care = np.array([(g or {}).get("care", 0.0) for g in p.genomes], np.float32)
        p.mom, p.mom_uid, p.fed_until = np.full(CAP, -1, np.int64), np.zeros(CAP, np.int64), np.zeros(CAP, np.int64)
        p.clim.setdefault("gaps", [float(p.rng.uniform(0, ARENA)) for _ in range(BASINS)])
    if not hasattr(p, "pathogens"):            # Oct 27: immune genes and evolving pathogens
        p.pathogens = [[float(v) for v in p.rng.random(MHC)] for _ in range(STRAINS)]
        p.sus = np.zeros(CAP, np.float32)
        for i in np.flatnonzero(p.alive):
            p.sus[i] = p._susceptibility(_mhc(p.genomes[i], p.rng))
    if getattr(p, "world_v", 1) < 2:           # Oct 29: the world grows a deep ocean (west) and land (east)
        a = p.alive
        p.x[a] = p.x[a] + BASIN_W               # the old bay (open sea, shallows, flats) keeps its place in the middle
        oldN, oldD = p.N, p.D
        p.N = _N_TARGET.copy(); p.D = np.zeros((GRID, GRID_X), np.float32)
        c0 = GRID_X // BASINS
        p.N[:, c0:c0 + oldN.shape[1]] = oldN; p.D[:, c0:c0 + oldD.shape[1]] = oldD
        g = p.clim.get("gaps", [])
        p.clim["gaps"] = [float(p.rng.uniform(0, ARENA)), float(p.rng.uniform(0, ARENA))] + [float(v) for v in g[1:3]] + [float(p.rng.uniform(0, ARENA))]
        for u in p.clim["up"]:
            u[0] = float(u[0] + BASIN_W)
        p.clim["vents"] = _new_vents(p.rng)
        p.world_v = 2
        _ledger("pool.world_expanded", {"era": p.era, "tick": int(p.tick), "habitats": HABITATS,
                                        "note": "deep ocean and land added; the bay keeps its creatures"})
    if not hasattr(p, "bank"):
        p.bank, p.seg_peak = _clock_from_history(p.era)
        p.clock_gen = p.bank + p.seg_peak
        p.restarts = getattr(p, "restarts", 0)
        a = p.alive
        p.last_mg = float(p.gen[a].mean()) if a.any() else 0.0
    return p


def _clock_from_history(era):
    """Rebuild deep time from the recorded stats: the peak mean generation of each stretch between re-seeds, added up."""
    try:
        with S.engine().connect() as c:
            rows = c.execute(sa.select(S.pool_stats.c.stats).where(S.pool_stats.c.era == era)
                             .order_by(S.pool_stats.c.id)).scalars().all()
    except Exception:
        return 0.0, 0.0
    bank, peak = 0.0, 0.0
    for r in rows:
        mg = (json.loads(r) or {}).get("mean_generation") or 0.0
        if peak > 50 and mg < 0.3 * peak:      # a re-seed: bank the segment
            bank, peak = bank + peak, mg
        else:
            peak = max(peak, mg)
    return bank, peak


def _ledger(kind, payload, **kw):
    try:
        S.append(kind, payload, **kw)
    except Exception as e:
        print(f"[pool] ledger write failed: {e!r}", flush=True)


def checkpoint(p: Pool):
    blob = to_blob(p)
    with S.engine().begin() as c:
        c.execute(S.pool_checkpoints.insert().values(ts=S.now(), era=p.era, tick=p.tick, blob=blob))
        old = c.execute(sa.select(S.pool_checkpoints.c.id).order_by(S.pool_checkpoints.c.id.desc()).offset(3)).scalars().all()
        if old:
            c.execute(S.pool_checkpoints.delete().where(S.pool_checkpoints.c.id.in_(old)))


def load_or_create() -> Pool:
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.pool_checkpoints).order_by(S.pool_checkpoints.c.id.desc()).limit(1)).mappings().first()
    if row is not None:
        try:
            p = from_blob(row["blob"])
            _ledger("pool.resumed", {"era": p.era, "tick": int(p.tick)})
            return p
        except Exception as e:
            _ledger("failure.pool_checkpoint", {"error": repr(e)})
    with S.engine().connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(S.events).where(S.events.c.type == "world.genesis")).scalar() or 0
    era = n + 1
    seed = int(time.time() * 1000) % (2 ** 31)
    p = Pool(era, seed)
    _ledger("world.genesis", {"era": era, "seed": seed, "world_version": VERSION, "founders": START, "capacity": CAP,
                              "years_per_generation": YEARS_PER_GEN,
                              "note": "life-3.0 tidal pool: developmental bodies, nine cell types, food web, sex, nested climate"})
    return p


def write_live(p: Pool, frames):
    data = {"frames": frames[-3:], "plans": {}, "env": p.env(), "stats": p.last_stats, "era": p.era,
            "version": VERSION, "tick": int(p.tick), "arena": ARENA, "world": [WORLD_W, ARENA], "years_per_generation": YEARS_PER_GEN,
            "geo_ma": p.geo_ma(), "milestones": sorted(p.milestones.values(), key=lambda m: m["tick"]),
            "catastrophes": p.events[-12:], "species": p.species_table(), "exemplar": p.exemplar(),
            "names": {str(int(k)): p.spec.get(int(k), {}).get("name") for k in np.unique(p.species[p.alive])},
            "cell_names": CELL_NAMES}
    used = {c[4] for f in data["frames"] for c in f["c"]} | {s["plan"] for s in data["species"]}
    if data["exemplar"]:
        used.add(data["exemplar"]["plan"])
    for m in data["milestones"]:
        if m.get("exemplar"):
            used.add(m["exemplar"]["plan"])
    data["plans"] = {str(k): p.plans[k] for k in used if k in p.plans}
    js = json.dumps(data, separators=(",", ":"))
    with S.engine().begin() as c:
        r = c.execute(S.pool_live.update().where(S.pool_live.c.id == 1).values(ts=S.now(), data=js))
        if r.rowcount == 0:
            c.execute(S.pool_live.insert().values(id=1, ts=S.now(), data=js))


def read_live():
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.pool_live.c.ts, S.pool_live.c.data).where(S.pool_live.c.id == 1)).first()
    if not row:
        return None
    d = json.loads(row[1])
    d["written_at"] = row[0]
    return d


def history(limit=600, every=1):
    with S.engine().connect() as c:
        era = c.execute(sa.select(S.pool_stats.c.era).order_by(S.pool_stats.c.id.desc()).limit(1)).scalar()
        if era is None:
            return []
        total = c.execute(sa.select(sa.func.count()).select_from(S.pool_stats).where(S.pool_stats.c.era == era)).scalar()
        step = max(1, int(math.ceil(total / limit)))
        rows = c.execute(sa.select(S.pool_stats.c.id, S.pool_stats.c.tick, S.pool_stats.c.ts, S.pool_stats.c.stats)
                         .where(S.pool_stats.c.era == era).order_by(S.pool_stats.c.id)).all()
    rows = rows[::step] + ([rows[-1]] if rows and (len(rows) - 1) % step else [])
    return [{"tick": r[1], "ts": r[2], **json.loads(r[3])} for r in rows]


# ── the process ──────────────────────────────────────────────────────────
LEADER_KEY = 774414
TPS = float(os.environ.get("DARWIN_POOL_TPS", "200"))   # a ceiling; about one vCPU flat out


def _leader():
    eng = S.engine()
    if eng.dialect.name == "postgresql":
        conn = eng.connect()
        ok = bool(conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({LEADER_KEY})").scalar())
        conn.commit()
        if not ok:
            conn.close()
            return None
        return conn
    import fcntl
    fh = open(S.db_url()[len("sqlite:///"):] + ".pool-leader", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def run():
    lock = _leader()
    if lock is None:
        print("[pool] another process holds the pool; exiting", flush=True)
        return
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    p = load_or_create()
    frames = []
    last_live = last_ck = last_cost = time.time()
    cpu0, tick0 = time.process_time(), p.tick
    budget = 1.0 / TPS
    print(f"[pool] era {p.era} running from tick {p.tick} at up to {TPS:g} ticks/s", flush=True)
    while not stop["now"]:
        t0 = time.time()
        s = p.step()
        if s is not None:
            try:
                with S.engine().begin() as c:
                    c.execute(S.pool_stats.insert().values(ts=S.now(), era=p.era, tick=p.tick, stats=S.canon(s)))
            except Exception as e:
                print(f"[pool] stats write failed: {e!r}", flush=True)
        if p.tick % 8 == 0:
            frames.append(p.frame())
            frames = frames[-3:]
        now = time.time()
        if now - last_live >= 0.5:
            last_live = now
            try:
                write_live(p, frames)
            except Exception as e:
                print(f"[pool] live write failed: {e!r}", flush=True)
        if now - last_ck >= 30:
            last_ck = now
            try:
                checkpoint(p)
            except Exception as e:
                print(f"[pool] checkpoint failed: {e!r}", flush=True)
        if now - last_cost >= 3600:
            cpu = time.process_time() - cpu0
            _ledger("pool.compute", {"cpu_s": round(cpu, 1), "ticks": int(p.tick - tick0), "period_s": round(now - last_cost)},
                    cost_usd=costs.compute_usd(cpu), cost_kind="estimated")
            cpu0, tick0, last_cost = time.process_time(), p.tick, now
        rest = budget - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)
    checkpoint(p)
    print(f"[pool] stopped at tick {p.tick}; checkpoint written", flush=True)


def bench(ticks=20000, seed=1):
    """Local calibration: run headless and print the trajectory."""
    p = Pool(1, seed)
    t0 = time.time()
    for _ in range(ticks):
        s = p.step()
        if s:
            print(json.dumps({k: s.get(k) for k in ("tick", "population", "species", "species_eff", "mean_generation",
                                                     "geo_ma", "cells_mean", "cells_max", "types_max", "predators",
                                                     "grazers", "motile_share", "eyes_share", "sexual_share",
                                                     "trophic_max", "genome_mean", "nutrient", "detritus")}), flush=True)
    dt = time.time() - t0
    print(f"{ticks} ticks in {dt:.1f}s = {ticks / dt:.0f} ticks/s; milestones: {list(p.milestones)}")
    return p


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run()
    elif cmd == "bench":
        bench(int(sys.argv[2]) if len(sys.argv) > 2 else 20000, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
