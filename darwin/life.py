"""Life Lab world: a vectorised artificial-life terrarium.

One simulator serves two purposes:

* the shared, open-ended DARWIN WORLD (one world, many mixed genomes,
  reproduction with inheritance and mutation), and
* the evaluation environment for Darwin Core experiments (many independent
  worlds in parallel, one per candidate, each holding a cohort of clones).

Everything that happens here comes from the mechanics below. No behaviour is
scripted: steering is a linear controller whose weights are genes, and any
grouping, specialisation or avoidance seen in the world has to arise from
selection acting on those genes (Brief s.26-29).

Determinism: all randomness comes from one numpy Generator seeded by the
caller, and only element-wise float64 operations are used, so a run with the
same seed, config and WORLD_VERSION reproduces exactly on the same platform.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

WORLD_ID = "life"
WORLD_VERSION = "life-1.0"

# ── Genome ────────────────────────────────────────────────────────────────
# A fixed-length real vector. (name, low, high, description)
GENES = [
    ("speed", 0.2, 3.0, "distance moved per tick"),
    ("sense", 2.0, 25.0, "radius within which food, hazards and others are perceived"),
    ("size", 0.5, 2.0, "body size: wins contested food, costs more energy"),
    ("pref", 0.0, 1.0, "diet: 1 = specialist on green food, 0 = on amber food"),
    ("w_food", 0.0, 3.0, "controller weight: steer toward perceived food"),
    ("w_hazard", 0.0, 3.0, "controller weight: steer away from perceived hazards"),
    ("w_crowd", -2.0, 2.0, "controller weight: + approach others, - avoid others"),
    ("wander", 0.0, 1.0, "controller weight: persistence of own heading"),
    ("repro_at", 20.0, 120.0, "energy level at which it reproduces"),
    ("repro_share", 0.2, 0.7, "share of energy given to offspring"),
]
G = len(GENES)
GENE_NAMES = [g[0] for g in GENES]
LOW = np.array([g[1] for g in GENES], dtype=np.float64)
HIGH = np.array([g[2] for g in GENES], dtype=np.float64)
SPAN = HIGH - LOW

# ── Physics constants (part of WORLD_VERSION; change => bump version) ────
ARENA = 100.0
FOOD_VALUE = np.array([14.0, 22.0])   # amber (type 0), green (type 1)
BASE_COST = 0.10
SIZE_COST = 0.05
MOVE_COST = 0.02
SENSE_COST = 0.004
REPRO_COST = 4.0
ENERGY_CAP_BASE = 60.0                # energy a body can store: base + per unit of size
ENERGY_CAP_SIZE = 50.0
HAZARD_RADIUS = 7.0
HAZARD_DAMAGE = 2.5
MAX_AGE = 900
START_ENERGY = 40.0
REGROW_MEAN = 90.0                    # ticks before an eaten food item returns


def clip_genome(g: np.ndarray) -> np.ndarray:
    return np.clip(g, LOW, HIGH)


def random_genomes(rng: np.random.Generator, n: int) -> np.ndarray:
    return LOW + rng.random((n, G)) * SPAN


def genome_dict(g) -> dict:
    return {name: round(float(v), 4) for name, v in zip(GENE_NAMES, g)}


@dataclass
class Conditions:
    """Environment parameters. Disturbances (Brief s.10) are expressed by
    changing these between generations."""
    food: int = 30              # food items per world
    green_share: float = 0.5     # fraction of food that is green (type 1)
    scarcity: float = 1.0        # >1 slows regrowth (resource scarcity)
    hazards: int = 2             # hazard zones per world
    hazard_drift: float = 0.15   # hazard movement per tick
    reproduction: bool = False   # whether creatures reproduce during an episode
    mutation_sigma: float = 0.06 # within-world mutation (only if reproduction)

    def to_dict(self):
        return asdict(self)


@dataclass
class EpisodeResult:
    energy_gathered: np.ndarray   # (W,) total energy eaten by everything in world
    alive_ticks: np.ndarray       # (W,) sum over slots of ticks alive
    final_alive: np.ndarray       # (W,)
    births: np.ndarray            # (W,)
    ticks: int
    sim_steps: int                # W * ticks, for cost accounting


class LifeSim:
    """Vectorised simulation of W independent worlds with up to M creature slots each."""

    def __init__(self, rng: np.random.Generator, W: int, M: int, cond: Conditions):
        self.rng, self.W, self.M, self.cond = rng, W, M, cond
        F, H = cond.food, cond.hazards
        self.px = np.zeros((W, M)); self.py = np.zeros((W, M))
        # Every random field is drawn without the world axis and broadcast, so
        # each world sees the same random stream: a genome's evaluation depends
        # only on (genome, seed, conditions), never on its batch position.
        # Headings are unit vectors, turned each tick by rotation factors computed on
        # per-slot arrays. Transcendental functions are never applied to world-shaped
        # arrays, because SIMD sin/cos can round differently with array length, which
        # would make a world's result depend on how many worlds run beside it.
        a0 = rng.random(M) * 2 * np.pi
        self.hvx = np.broadcast_to(np.cos(a0), (W, M)).copy()
        self.hvy = np.broadcast_to(np.sin(a0), (W, M)).copy()
        self.energy = np.zeros((W, M))
        self.alive = np.zeros((W, M), dtype=bool)
        self.age = np.zeros((W, M), dtype=np.int64)
        self.genome = np.zeros((W, M, G))
        self.uid = np.full((W, M), -1, dtype=np.int64)
        self.next_uid = 0
        self.fx = np.broadcast_to(rng.random(F) * ARENA, (W, F)).copy()
        self.fy = np.broadcast_to(rng.random(F) * ARENA, (W, F)).copy()
        self.ftype = np.broadcast_to((rng.random(F) < cond.green_share).astype(np.int64), (W, F)).copy()
        self.favail = np.ones((W, F), dtype=bool)
        self.fregrow = np.zeros((W, F))
        self.hx = np.broadcast_to(rng.random(H) * ARENA, (W, H)).copy()
        self.hy = np.broadcast_to(rng.random(H) * ARENA, (W, H)).copy()
        h0 = rng.random(H) * 2 * np.pi
        self.hzx = np.broadcast_to(np.cos(h0), (W, H)).copy()
        self.hzy = np.broadcast_to(np.sin(h0), (W, H)).copy()
        self.tick = 0
        self.energy_gathered = np.zeros(W)
        self.alive_ticks = np.zeros(W)
        self.births = np.zeros(W)
        self.deaths = np.zeros(W)
        self.events = []          # (kind, world, uid, parent_uid) when tracking
        self.track_events = False

    # ── population setup ──────────────────────────────────────────────
    def place(self, world: int, genomes: np.ndarray, energy: float = START_ENERGY,
              parents=None, positions=None) -> list:
        """Put genomes into free slots of one world. Returns assigned uids."""
        free = np.flatnonzero(~self.alive[world])
        n = min(len(free), len(genomes))
        uids = []
        for k in range(n):
            s = free[k]
            self.genome[world, s] = clip_genome(genomes[k])
            if positions is not None:
                self.px[world, s], self.py[world, s] = positions[k]
            else:
                self.px[world, s], self.py[world, s] = self.rng.random(2) * ARENA
            self.energy[world, s] = energy
            self.alive[world, s] = True
            self.age[world, s] = 0
            self.uid[world, s] = self.next_uid
            uids.append(self.next_uid)
            if self.track_events:
                self.events.append(("birth", world, self.next_uid,
                                    None if parents is None else parents[k]))
            self.next_uid += 1
        return uids

    def set_conditions(self, cond: Conditions):
        """Apply new conditions mid-run (live-world seasons, shocks)."""
        self.cond = cond

    @staticmethod
    def _unit(x, y):
        n = np.sqrt(x * x + y * y)
        n = np.where(n > 1e-9, n, 1.0)
        return x / n, y / n

    # ── one tick ──────────────────────────────────────────────────────
    def step(self):
        rng, cond = self.rng, self.cond
        W, M = self.W, self.M
        alive = self.alive
        g = self.genome
        speed, sense, size, pref = g[..., 0], g[..., 1], g[..., 2], g[..., 3]
        w_food, w_haz, w_crowd, wander = g[..., 4], g[..., 5], g[..., 6], g[..., 7]
        sense2 = sense * sense
        F, H = self.fx.shape[1], self.hx.shape[1]
        # Per-tick random fields, constant size whatever happens in the worlds.
        r_head = rng.normal(0, 0.35, M)
        r_tie = rng.random(M)
        r_regrow = rng.exponential(REGROW_MEAN * cond.scarcity, F)
        r_fx, r_fy, r_ft = rng.random(F) * ARENA, rng.random(F) * ARENA, rng.random(F)
        r_hang = rng.normal(0, 0.15, H)
        r_mut = rng.normal(0, 1.0, (M, G))
        r_off = rng.normal(0, 1.5, (M, 2))
        r_hd = rng.random(M) * 2 * np.pi
        hd_c, hd_s = np.cos(r_hd), np.sin(r_hd)

        # Food perception: distance scaled by diet efficiency, so a specialist
        # prefers its own food type when both are in view.
        dx = self.fx[:, None, :] - self.px[:, :, None]                    # (W,M,F)
        dy = self.fy[:, None, :] - self.py[:, :, None]
        d2 = dx * dx + dy * dy
        green = self.ftype[:, None, :] == 1
        eff = 0.35 + 0.65 * np.where(green, pref[..., None], 1.0 - pref[..., None])
        ok = self.favail[:, None, :] & (d2 <= sense2[..., None])
        if F:
            attract = np.where(ok, d2 / (eff * eff), np.inf)
            tgt = attract.argmin(-1)                                      # (W,M)
            tg = tgt[..., None]
            has_tgt = np.isfinite(np.take_along_axis(attract, tg, -1)[..., 0]) & alive
            tdx = np.take_along_axis(dx, tg, -1)[..., 0]
            tdy = np.take_along_axis(dy, tg, -1)[..., 0]
            teff = np.take_along_axis(eff, tg, -1)[..., 0]
        else:                                                             # a world with no food at all
            tgt = np.zeros((W, M), dtype=np.int64)
            has_tgt = np.zeros((W, M), dtype=bool)
            tdx = tdy = np.zeros((W, M))
            teff = np.ones((W, M))
        fdx, fdy = self._unit(tdx, tdy)
        fdx, fdy = fdx * has_tgt, fdy * has_tgt

        # Hazard perception: steer away from hazards within sense range.
        hzx = np.zeros((W, M)); hzy = np.zeros((W, M))
        if cond.hazards:
            hx = self.px[:, :, None] - self.hx[:, None, :]
            hy = self.py[:, :, None] - self.hy[:, None, :]
            hr = sense[..., None] + HAZARD_RADIUS
            near = (hx * hx + hy * hy) <= hr * hr
            hzx, hzy = self._unit((hx * near).sum(-1), (hy * near).sum(-1))

        # Crowd perception: direction to the centroid of visible neighbours.
        cx = self.px[:, None, :] - self.px[:, :, None]                    # (W,M,M) j - i
        cy = self.py[:, None, :] - self.py[:, :, None]
        c2 = cx * cx + cy * cy
        neigh = (c2 <= sense2[..., None]) & alive[:, None, :] & (c2 > 0)
        crx, cry = self._unit((cx * neigh).sum(-1), (cy * neigh).sum(-1))

        # Own heading: a slow random walk (rotation by a per-slot random angle).
        rc, rs = np.cos(r_head), np.sin(r_head)
        hdx, hdy = self._unit(self.hvx * rc - self.hvy * rs, self.hvx * rs + self.hvy * rc)

        wa = wander + 0.05
        vx = w_food * fdx + w_haz * hzx + w_crowd * crx + wa * hdx
        vy = w_food * fdy + w_haz * hzy + w_crowd * cry + wa * hdy
        vx, vy = self._unit(vx, vy)
        step_len = np.minimum(speed, np.where(has_tgt, np.sqrt(tdx * tdx + tdy * tdy), np.inf))
        step_len = np.where(has_tgt & (w_food > 0.3), step_len, speed) * alive
        nx = self.px + vx * step_len
        ny = self.py + vy * step_len
        # Reflect off the walls and turn back inward.
        bounce = (nx < 0) | (nx > ARENA) | (ny < 0) | (ny > ARENA)
        nx = np.where(nx < 0, -nx, np.where(nx > ARENA, 2 * ARENA - nx, nx))
        ny = np.where(ny < 0, -ny, np.where(ny > ARENA, 2 * ARENA - ny, ny))
        self.px, self.py = np.clip(nx, 0, ARENA), np.clip(ny, 0, ARENA)
        self.hvx = np.where(bounce, -hdx, hdx)
        self.hvy = np.where(bounce, -hdy, hdy)

        # Energy cost of living.
        cost = BASE_COST + SIZE_COST * size + MOVE_COST * size * speed ** 2 + SENSE_COST * sense
        self.energy -= cost * alive

        # Eating: a creature that reaches the item it was steering toward eats it.
        # When several reach the same item the largest body wins (ties: random).
        reach = 1.0 + 0.6 * size
        if F:
            ex = np.take_along_axis(self.fx, tgt, -1) - self.px
            ey = np.take_along_axis(self.fy, tgt, -1) - self.py
            eats = has_tgt & ((ex * ex + ey * ey) <= reach * reach)
        else:
            eats = has_tgt
        if eats.any():
            ww, ss = np.nonzero(eats)
            ff = tgt[ww, ss]
            key = ww * self.fx.shape[1] + ff
            order = np.lexsort((r_tie[ss], -size[ww, ss], key))
            first = np.ones(len(order), dtype=bool)
            first[1:] = key[order][1:] != key[order][:-1]
            win = order[first]
            ww, ss, ff = ww[win], ss[win], ff[win]
            gross = FOOD_VALUE[self.ftype[ww, ff]] * teff[ww, ss]
            cap = ENERGY_CAP_BASE + ENERGY_CAP_SIZE * size[ww, ss]
            got = np.minimum(gross, np.maximum(cap - self.energy[ww, ss], 0.0))   # stores are finite
            self.energy[ww, ss] += got
            np.add.at(self.energy_gathered, ww, gross)    # food eaten, whether or not stores were full
            self.favail[ww, ff] = False
            self.fregrow[ww, ff] = r_regrow[ff]

        # Food regrowth at a fresh random spot.
        self.fregrow -= 1
        back = (~self.favail) & (self.fregrow <= 0)
        if back.any():
            self.favail |= back
            self.fx = np.where(back, r_fx, self.fx)
            self.fy = np.where(back, r_fy, self.fy)
            self.ftype = np.where(back, (r_ft < cond.green_share).astype(np.int64), self.ftype)

        # Hazards drift and drain energy.
        if cond.hazards:
            hc, hs = np.cos(r_hang), np.sin(r_hang)
            zx, zy = self._unit(self.hzx * hc - self.hzy * hs, self.hzx * hs + self.hzy * hc)
            self.hx = self.hx + zx * cond.hazard_drift
            self.hy = self.hy + zy * cond.hazard_drift
            out = (self.hx < 0) | (self.hx > ARENA) | (self.hy < 0) | (self.hy > ARENA)
            self.hzx, self.hzy = np.where(out, -zx, zx), np.where(out, -zy, zy)
            self.hx, self.hy = np.clip(self.hx, 0, ARENA), np.clip(self.hy, 0, ARENA)
            hx = self.px[:, :, None] - self.hx[:, None, :]
            hy = self.py[:, :, None] - self.hy[:, None, :]
            inside = ((hx * hx + hy * hy) <= HAZARD_RADIUS ** 2).any(-1)
            self.energy -= HAZARD_DAMAGE * inside * alive

        # Ageing and death.
        self.age += alive
        dead = alive & ((self.energy <= 0) | (self.age > MAX_AGE))
        if dead.any():
            if self.track_events:
                for w, s in zip(*np.nonzero(dead)):
                    self.events.append(("death", int(w), int(self.uid[w, s]), None))
            self.alive &= ~dead
            self.deaths += dead.sum(-1)
        self.alive_ticks += self.alive.sum(-1)

        # Reproduction (asexual, with mutation) into free slots of the same world.
        if cond.reproduction:
            ready = self.alive & (self.energy >= g[..., 8])
            for w in np.flatnonzero(ready.any(-1)):
                for s in np.flatnonzero(ready[w]):
                    free = np.flatnonzero(~self.alive[w])
                    if not len(free):
                        break
                    c = free[0]
                    share = self.energy[w, s] * g[w, s, 9]
                    self.energy[w, s] -= share + REPRO_COST
                    child = clip_genome(g[w, s] + r_mut[s] * cond.mutation_sigma * SPAN)
                    self.genome[w, c] = child
                    self.px[w, c] = np.clip(self.px[w, s] + r_off[s, 0], 0, ARENA)
                    self.py[w, c] = np.clip(self.py[w, s] + r_off[s, 1], 0, ARENA)
                    self.energy[w, c] = share
                    self.alive[w, c] = True
                    self.age[w, c] = 0
                    self.hvx[w, c], self.hvy[w, c] = hd_c[s], hd_s[s]
                    self.uid[w, c] = self.next_uid
                    if self.track_events:
                        self.events.append(("birth", int(w), self.next_uid, int(self.uid[w, s])))
                    self.next_uid += 1
                    self.births[w] += 1
        self.tick += 1


# ── Standard World Interface (Brief s.7) ─────────────────────────────────
OBJECTIVES = {
    "forage": "Total energy gathered by the cohort over the episode",
    "survive": "Endurance through a famine (regrowth stops at 60% of the episode): ticks survived plus the ticks each survivor's remaining store would last at its own burn rate, per creature, as a multiple of the episode length",
    "thrive": "Cohort population at the end, with reproduction on",
}

WORLD_SPEC = {
    "id": WORLD_ID,
    "version": WORLD_VERSION,
    "goal": "Evolve creature genomes that perform well on a chosen objective",
    "entities": ["creatures (genome, energy, position, age)", "food (amber/green)", "hazard zones"],
    "actions": "linear steering from perceived food, hazards and neighbours; eat; reproduce",
    "constraints": "energy budget with finite stores (larger bodies store more); arena walls; contested food goes to the larger body",
    "candidate_representation": f"fixed-length real vector, {G} genes: " + ", ".join(GENE_NAMES),
    "evaluation": "cohort of clones run in an independent world per candidate, averaged over seeds",
    "uncertainty": "seed-to-seed variance reported; validation on held-out seeds",
    "fidelity": "abstract 2-D ecology; not a model of any real organism",
    "validation": "held-out seeds, perturbed conditions, comparison to initial best",
    "cost_model": "CPU seconds and simulation steps, priced at the hosting rate",
    "objectives": OBJECTIVES,
    "genes": [{"name": n, "low": lo, "high": hi, "meaning": m} for n, lo, hi, m in GENES],
}


def burn_rate(genome: np.ndarray) -> np.ndarray:
    """Energy a creature spends per tick, from its genes (same formula as LifeSim.step)."""
    speed, sense, size = genome[..., 0], genome[..., 1], genome[..., 2]
    return BASE_COST + SIZE_COST * size + MOVE_COST * size * speed ** 2 + SENSE_COST * sense


def endurance(sim: "LifeSim", cohort: int, ticks: int) -> np.ndarray:
    """Survive score per world: observed alive-ticks plus the further ticks each
    survivor's stored energy would last with no more food, per creature, divided
    by the episode length. Uncapped, so a better survivor always scores higher."""
    left = np.where(sim.alive, sim.energy / burn_rate(sim.genome), 0.0).sum(-1)
    return (sim.alive_ticks + left) / (cohort * ticks)


def famine(cond: Conditions, t: int, ticks: int) -> Conditions:
    """The 'survive' objective's built-in pressure: regrowth slows steadily and has
    effectively stopped by 60% of the episode, so creatures must last on stores."""
    k = max(0.01, 1.0 - t / (0.6 * max(1, ticks)))
    return Conditions(**{**cond.to_dict(), "scarcity": cond.scarcity / k})


def evaluate(genomes: np.ndarray, objective: str, cond: Conditions, seeds, ticks: int = 300,
             cohort: int = 8):
    """Evaluate each genome (P,G) on each seed. Returns (fitness (P,S), sim_steps).

    Each candidate gets its own world containing `cohort` clones. Worlds are
    simulated together in one vectorised pass per seed.
    """
    P = len(genomes)
    out = np.zeros((P, len(seeds)))
    steps = 0
    cond_run = Conditions(**{**cond.to_dict(), "reproduction": objective == "thrive"})
    M = cohort * 4 if objective == "thrive" else cohort
    for j, seed in enumerate(seeds):
        rng = np.random.default_rng(seed)
        sim = LifeSim(rng, P, M, cond_run)
        start = rng.random((cohort, 2)) * ARENA
        for w in range(P):
            sim.place(w, np.repeat(genomes[w][None, :], cohort, 0), positions=start)
        for t in range(ticks):
            if objective == "survive":
                sim.cond = famine(cond_run, t, ticks)
            sim.step()
            if not sim.alive.any():
                break
        steps += P * sim.tick
        if objective == "forage":
            out[:, j] = sim.energy_gathered / cohort
        elif objective == "survive":
            out[:, j] = endurance(sim, cohort, ticks)
        else:
            out[:, j] = sim.alive.sum(-1) / cohort
    return out, steps
