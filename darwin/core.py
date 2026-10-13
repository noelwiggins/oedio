"""Darwin Core (Brief s.8-10, 44-47): generate, evaluate, select, vary,
preserve diversity, repeat, stop, validate.

The loop is world-agnostic in shape but Phase 1 ships one World (Life Lab), so
the variation operators below are the ones that fit its representation, a
fixed-length real vector. Operators that do not fit that representation
(gene duplication/deletion, structural change) are listed as not applicable
rather than faked.

Storage is injected through `on_generation` / `should_stop` callbacks so the
loop can run under test, in the worker, or as a replay without a database.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict

import numpy as np

from . import life
from .costs import Meter, compute_usd

OPERATORS = {
    "random": "random generation (initial population and immigrants)",
    "elite": "unchanged copy of a top candidate",
    "point_mutation": "one gene perturbed (Gaussian, scaled to gene range)",
    "multi_mutation": "each gene perturbed with probability = mutation rate",
    "uniform_crossover": "each gene taken from either parent",
    "blend_crossover": "genes interpolated between parents, then mutated",
    "distant_recombination": "crossover with the most genetically distant island member",
    "migration": "copy of another island's best, introduced every k generations",
    "mutation_burst": "disturbance: heavy mutation applied to the whole population",
}
NOT_APPLICABLE = {
    "duplication": "fixed-length vector genome has no variable-length segments to duplicate",
    "deletion": "same reason; every gene is required by the controller",
    "structural_change": "controller structure is fixed in Life World 1.0",
}

DISTURBANCES = {
    "none": "no disturbance",
    "scarcity_shock": "food regrowth slows 2.2x from the shock generation onward",
    "hazard_shock": "hazard zones increase by 4 from the shock generation onward",
    "diet_shift": "food mix flips toward the minority type from the shock generation onward",
    "mutation_burst": "the whole population is heavily mutated once, at the shock generation",
}


@dataclass
class Config:
    objective: str = "forage"
    population: int = 40
    generations: int = 30
    islands: int = 2
    migration_every: int = 5
    tournament: int = 3
    elite: int = 2
    mutation_rate: float = 0.25
    mutation_sigma: float = 0.08
    crossover_rate: float = 0.6
    distant_rate: float = 0.1
    immigrant_rate: float = 0.05
    train_seeds: int = 2
    holdout_seeds: int = 8
    ticks: int = 300
    cohort: int = 8
    stagnation: int = 15
    conditions: dict = field(default_factory=lambda: life.Conditions().to_dict())
    disturbance: str = "none"
    disturbance_gen: int = 15
    baseline_random: bool = False
    seed: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        c = cls(**known)
        c.conditions = {**life.Conditions().to_dict(), **(d.get("conditions") or {})}
        return c

    def to_dict(self):
        return asdict(self)

    def validate(self, limits: dict) -> list:
        errs = []
        if self.objective not in life.OBJECTIVES:
            errs.append(f"unknown objective {self.objective!r}")
        if self.disturbance not in DISTURBANCES:
            errs.append(f"unknown disturbance {self.disturbance!r}")
        if not (6 <= self.population <= limits.get("max_population", 200)):
            errs.append(f"population must be 6..{limits.get('max_population', 200)}")
        if not (1 <= self.generations <= limits.get("max_generations", 400)):
            errs.append(f"generations must be 1..{limits.get('max_generations', 400)}")
        if not (1 <= self.islands <= 4) or self.population // self.islands < 4:
            errs.append("islands must be 1..4 with at least 4 candidates per island")
        if not (1 <= self.train_seeds <= 5):
            errs.append("training seeds must be 1..5")
        if not (4 <= self.holdout_seeds <= 16):
            errs.append("holdout seeds must be 4..16")
        if not (100 <= self.ticks <= 600):
            errs.append("episode length must be 100..600 ticks")
        if not (2 <= self.cohort <= 16):
            errs.append("cohort must be 2..16")
        c = self.conditions
        if not (5 <= int(c.get("food", 0)) <= 200):
            errs.append("food must be 5..200")
        if not (0 <= int(c.get("hazards", 0)) <= 8):
            errs.append("hazards must be 0..8")
        if not (0.3 <= float(c.get("scarcity", 1)) <= 4):
            errs.append("scarcity must be 0.3..4")
        if not (0 <= float(c.get("green_share", 0.5)) <= 1):
            errs.append("green share must be 0..1")
        return errs

    # Seeds: training and holdout sets are disjoint by construction (s.62).
    def train_seed_list(self):
        return [int(self.seed) * 10007 + i for i in range(self.train_seeds)]

    def holdout_seed_list(self):
        return [int(self.seed) * 10007 + 5003 + i for i in range(self.holdout_seeds)]


def conditions_at(cfg: Config, gen: int) -> life.Conditions:
    c = dict(cfg.conditions)
    if gen >= cfg.disturbance_gen:
        if cfg.disturbance == "scarcity_shock":
            c["scarcity"] = float(c["scarcity"]) * 2.2
        elif cfg.disturbance == "hazard_shock":
            c["hazards"] = int(c["hazards"]) + 4
        elif cfg.disturbance == "diet_shift":
            c["green_share"] = 1.0 - float(c["green_share"])
    return life.Conditions(**{k: v for k, v in c.items() if k in life.Conditions.__dataclass_fields__})


def perturbed(cond: life.Conditions) -> life.Conditions:
    """Adversarial conditions for robustness tests (s.18)."""
    d = cond.to_dict()
    d["scarcity"] = d["scarcity"] * 1.6
    d["hazards"] = d["hazards"] + 2
    d["green_share"] = min(1.0, max(0.0, 1.0 - d["green_share"] * 0.8))
    return life.Conditions(**d)


@dataclass
class Cand:
    cid: str
    gen: int
    island: int
    genome: np.ndarray
    parents: list
    root: str
    operator: str
    params: dict
    fitness: float = float("nan")
    fitness_seeds: list = field(default_factory=list)
    selected: bool = False

    def record(self):
        return {"cid": self.cid, "gen": self.gen, "island": self.island,
                "genome": [round(float(x), 6) for x in self.genome], "parents": self.parents,
                "root": self.root, "operator": self.operator, "params": self.params,
                "fitness": None if np.isnan(self.fitness) else round(float(self.fitness), 6),
                "fitness_seeds": [round(float(x), 6) for x in self.fitness_seeds],
                "selected": bool(self.selected)}


def diversity(genomes: np.ndarray) -> float:
    """Mean pairwise distance between genomes, each gene normalised to its range."""
    if len(genomes) < 2:
        return 0.0
    z = (genomes - life.LOW) / life.SPAN
    d = np.sqrt(((z[:, None, :] - z[None, :, :]) ** 2).sum(-1))
    n = len(z)
    return float(d.sum() / (n * (n - 1)) / np.sqrt(life.G))


class Evolution:
    def __init__(self, cfg: Config, meter: Meter | None = None, on_generation=None, should_stop=None,
                 budget_usd: float | None = None, max_cpu_s: float | None = None):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.meter = meter or Meter()
        self.on_generation = on_generation or (lambda *a, **k: None)
        self.should_stop = should_stop or (lambda: False)
        self.budget_usd = budget_usd
        self.max_cpu_s = max_cpu_s
        self.serial = 0
        self.history = []          # per-generation stats
        self.op_stats = {k: {"produced": 0, "improved_on_parent": 0} for k in OPERATORS}
        self.best_by_gen = []
        self.stop_reason = None
        self.gen0_best = None
        self.best = None

    def _new(self, gen, island, genome, parents, root, op, params) -> Cand:
        self.serial += 1
        self.op_stats[op]["produced"] += 1
        self.meter.candidates += 1
        return Cand(f"g{gen}-{self.serial}", gen, island, life.clip_genome(genome), parents, root, op, params)

    # ── variation ─────────────────────────────────────────────────────
    def _mutate(self, g, rate, sigma):
        mask = self.rng.random(life.G) < rate
        if not mask.any():
            mask[self.rng.integers(life.G)] = True
        return g + mask * self.rng.normal(0, sigma, life.G) * life.SPAN, int(mask.sum())

    def _tournament(self, pop):
        idx = self.rng.choice(len(pop), size=min(self.cfg.tournament, len(pop)), replace=False)
        return max((pop[i] for i in idx), key=lambda c: c.fitness)

    def _offspring(self, island_pop, gen, island, burst=False) -> list:
        cfg, rng = self.cfg, self.rng
        n = len(island_pop)
        ranked = sorted(island_pop, key=lambda c: c.fitness, reverse=True)
        out = []
        for e in ranked[:cfg.elite]:
            out.append(self._new(gen, island, e.genome.copy(), [e.cid], e.root, "elite", {}))
        while len(out) < n:
            r = rng.random()
            if r < cfg.immigrant_rate:
                g = life.random_genomes(rng, 1)[0]
                c = self._new(gen, island, g, [], None, "random", {})
                c.root = c.cid
            elif r < cfg.immigrant_rate + cfg.distant_rate:
                a = self._tournament(island_pop)
                z = lambda x: (x.genome - life.LOW) / life.SPAN
                b = max(island_pop, key=lambda o: float(((z(o) - z(a)) ** 2).sum()))
                mask = rng.random(life.G) < 0.5
                g, k = self._mutate(np.where(mask, a.genome, b.genome), cfg.mutation_rate * 0.5,
                                    cfg.mutation_sigma)
                c = self._new(gen, island, g, [a.cid, b.cid], a.root, "distant_recombination",
                              {"genes_mutated": k})
            elif r < cfg.immigrant_rate + cfg.distant_rate + cfg.crossover_rate:
                a, b = self._tournament(island_pop), self._tournament(island_pop)
                if rng.random() < 0.5:
                    mask = rng.random(life.G) < 0.5
                    g, k = self._mutate(np.where(mask, a.genome, b.genome), cfg.mutation_rate * 0.5,
                                        cfg.mutation_sigma)
                    op = "uniform_crossover"
                else:
                    t = rng.random(life.G)
                    g, k = self._mutate(t * a.genome + (1 - t) * b.genome, cfg.mutation_rate * 0.5,
                                        cfg.mutation_sigma)
                    op = "blend_crossover"
                c = self._new(gen, island, g, [a.cid, b.cid], a.root, op, {"genes_mutated": k})
            else:
                a = self._tournament(island_pop)
                if rng.random() < 0.4:
                    g = a.genome.copy()
                    i = int(rng.integers(life.G))
                    g[i] += rng.normal(0, cfg.mutation_sigma * 1.5) * life.SPAN[i]
                    c = self._new(gen, island, g, [a.cid], a.root, "point_mutation", {"gene": life.GENE_NAMES[i]})
                else:
                    g, k = self._mutate(a.genome, cfg.mutation_rate, cfg.mutation_sigma)
                    c = self._new(gen, island, g, [a.cid], a.root, "multi_mutation", {"genes_mutated": k})
            out.append(c)
        if burst:
            for c in out[cfg.elite:]:
                c.genome = life.clip_genome(c.genome + self.rng.normal(0, 0.25, life.G) * life.SPAN)
                c.params = {**c.params, "burst": True}
                self.op_stats["mutation_burst"]["produced"] += 1
        return out

    # ── evaluation ────────────────────────────────────────────────────
    def _evaluate(self, pop, gen):
        """Evaluate unscored candidates. A genome's score is a pure function of
        (genome, seeds, conditions), so identical genomes (elites, migrants)
        reuse the recorded score instead of being re-simulated."""
        cond = conditions_at(self.cfg, gen)
        ckey = tuple(sorted(cond.to_dict().items()))
        cache = self.__dict__.setdefault("_cache", {})
        todo = []
        for c in pop:
            if not np.isnan(c.fitness):
                continue
            hit = cache.get((ckey, c.genome.tobytes()))
            if hit:
                c.fitness_seeds, c.fitness = list(hit[0]), hit[1]
            else:
                todo.append(c)
        if not todo:
            return 0
        fit, steps = life.evaluate(np.stack([c.genome for c in todo]), self.cfg.objective, cond,
                                   self.cfg.train_seed_list(), self.cfg.ticks, self.cfg.cohort)
        for c, f in zip(todo, fit):
            c.fitness_seeds = list(f)
            c.fitness = float(f.mean())
            cache[(ckey, c.genome.tobytes())] = (c.fitness_seeds, c.fitness)
        self.meter.sim_steps += steps
        self.meter.evaluations += len(todo) * len(self.cfg.train_seed_list())
        return steps

    # ── main loop ─────────────────────────────────────────────────────
    def run(self):
        cfg, rng = self.cfg, self.rng
        per = cfg.population // cfg.islands
        islands = []
        for i in range(cfg.islands):
            pop = []
            for g in life.random_genomes(rng, per):
                c = self._new(0, i, g, [], None, "random", {})
                c.root = c.cid
                pop.append(c)
            islands.append(pop)

        best_so_far, stale = -np.inf, 0
        prev_cond = None
        for gen in range(cfg.generations):
            cond = conditions_at(cfg, gen)
            if prev_cond is not None and cond != prev_cond:
                # Conditions changed: scores are re-earned under the new world
                # (the cache is keyed by conditions), and stagnation restarts.
                best_so_far, stale = -np.inf, 0
            prev_cond = cond
            flat = [c for pop in islands for c in pop]
            cpu_before = self.meter.cpu_s()
            steps = self._evaluate(flat, gen)

            # Operator effectiveness: did the child beat its best parent?
            byid = getattr(self, "_prev_by_id", {})
            for c in flat:
                ps = [byid[p] for p in c.parents if p in byid]
                if ps and c.operator != "elite":
                    if c.fitness > max(p.fitness for p in ps):
                        self.op_stats[c.operator]["improved_on_parent"] += 1

            fits = np.array([c.fitness for c in flat])
            genomes = np.stack([c.genome for c in flat])
            best = max(flat, key=lambda c: c.fitness)
            roots = {}
            for c in flat:
                roots[c.root] = roots.get(c.root, 0) + 1
            dom_root, dom_n = max(roots.items(), key=lambda kv: kv[1])
            div = diversity(genomes)
            if gen == 0:
                self.gen0_best = best
            stats = {
                "gen": gen, "best": round(float(best.fitness), 6), "best_cid": best.cid,
                "mean": round(float(fits.mean()), 6), "median": round(float(np.median(fits)), 6),
                "worst": round(float(fits.min()), 6), "std": round(float(fits.std()), 6),
                "diversity": round(div, 6), "lineages": len(roots),
                "dominant_lineage": dom_root, "dominant_share": round(dom_n / len(flat), 4),
                "collapsed_cohorts": int((fits <= 0).sum()),
                "conditions": cond.to_dict(),
                "operators": {k: sum(1 for c in flat if c.operator == k) for k in OPERATORS},
                "mean_genome": life.genome_dict(genomes.mean(0)),
                "best_genome": life.genome_dict(best.genome),
                "island_best": [round(float(max(p, key=lambda c: c.fitness).fitness), 6) for p in islands],
                "cpu_s": round(self.meter.cpu_s() - cpu_before, 4), "sim_steps": int(steps),
            }
            warnings = []
            if div < 0.05:
                warnings.append("low diversity: population has nearly converged")
            if dom_n / len(flat) > 0.9 and gen < cfg.generations // 2:
                warnings.append("one initial lineage holds >90% of the population (premature convergence risk)")
            stats["warnings"] = warnings
            self.history.append(stats)
            self.best_by_gen.append(float(best.fitness))

            if best.fitness > best_so_far + 1e-9:
                best_so_far, stale = best.fitness, 0
            else:
                stale += 1

            # Selection outcome is recorded on the candidates before they are stored.
            for pop in islands:
                for c in sorted(pop, key=lambda c: c.fitness, reverse=True)[:max(cfg.elite, len(pop) // 2)]:
                    c.selected = True
            self.best = best
            self.on_generation(gen, stats, flat, self.meter.snapshot())

            # Stopping conditions (s.46). Stopping is never equated with success.
            snap = self.meter.snapshot()
            per_gen_cpu = self.meter.cpu_s() / (gen + 1)
            if self.should_stop():
                self.stop_reason = "cancelled by request"
            elif gen + 1 >= cfg.generations:
                self.stop_reason = "generation limit reached"
            elif stale >= cfg.stagnation:
                self.stop_reason = f"stagnation: no improvement for {stale} generations"
            elif self.max_cpu_s and self.meter.cpu_s() + per_gen_cpu * 1.5 > self.max_cpu_s * 0.6:
                # 40% of the CPU cap is reserved for validation.
                self.stop_reason = "compute cap: next generation would exceed the evolution share of the cap"
            elif self.budget_usd and snap["compute_usd_estimated"] + compute_usd(per_gen_cpu * 1.5) > self.budget_usd * 0.6:
                self.stop_reason = "budget: next generation would exceed the evolution share of the budget"
            if self.stop_reason:
                break

            self._prev_by_id = {c.cid: c for c in flat}
            burst = cfg.disturbance == "mutation_burst" and gen + 1 == cfg.disturbance_gen
            new_islands = [self._offspring(pop, gen + 1, i, burst) for i, pop in enumerate(islands)]
            if cfg.islands > 1 and cfg.migration_every and (gen + 1) % cfg.migration_every == 0:
                for i in range(cfg.islands):
                    src = islands[(i + 1) % cfg.islands]
                    b = max(src, key=lambda c: c.fitness)
                    new_islands[i][-1] = self._new(gen + 1, i, b.genome.copy(), [b.cid], b.root,
                                                   "migration", {"from_island": (i + 1) % cfg.islands})
            islands = new_islands

        self.final_population = [c for pop in islands for c in pop]
        return self

    def digest(self) -> str:
        """Fingerprint used by REPLAY to check exact reproduction (s.54)."""
        h = hashlib.sha256()
        h.update(np.asarray(self.best_by_gen, dtype=np.float64).tobytes())
        h.update(np.asarray(self.best.genome, dtype=np.float64).tobytes())
        return h.hexdigest()


# ── validation (s.18-20, 61-63) ──────────────────────────────────────────
def sign_test_p(wins: int, n: int) -> float:
    """One-sided exact binomial p-value for >= wins successes out of n at p=0.5 (ties excluded)."""
    from math import comb
    if n == 0:
        return 1.0
    return sum(comb(n, k) for k in range(wins, n + 1)) / 2 ** n


def head_to_head(a: np.ndarray, b: np.ndarray, objective: str, cond: life.Conditions, seeds,
                 ticks: int, cohort: int, meter: Meter | None = None) -> dict:
    """Evaluate genomes a and b on the same seeds; report wins of a over b."""
    fit, steps = life.evaluate(np.stack([a, b]), objective, cond, seeds, ticks, cohort)
    if meter:
        meter.sim_steps += steps
        meter.evaluations += 2 * len(seeds)
    fa, fb = fit[0], fit[1]
    wins = int((fa > fb).sum())
    losses = int((fa < fb).sum())
    ties = len(seeds) - wins - losses
    n = wins + losses
    rel = float((fa.mean() - fb.mean()) / abs(fb.mean())) if abs(fb.mean()) > 1e-9 else None
    return {
        "seeds": list(map(int, seeds)), "a": [round(float(x), 6) for x in fa],
        "b": [round(float(x), 6) for x in fb], "a_mean": round(float(fa.mean()), 6),
        "b_mean": round(float(fb.mean()), 6), "wins": wins, "losses": losses, "ties": ties,
        "relative_gain": None if rel is None else round(rel, 4),
        "p_sign_test": round(sign_test_p(wins, n), 5) if n else 1.0,
        "conditions": cond.to_dict(),
    }


def random_search(cfg: Config, n: int, meter: Meter | None = None) -> tuple:
    """Baseline (s.61): best of n random genomes on the training seeds, same evaluator."""
    rng = np.random.default_rng(cfg.seed + 7_777_777)
    best_g, best_f = None, -np.inf
    cond = conditions_at(cfg, cfg.generations)
    chunk = 60
    done = 0
    while done < n:
        k = min(chunk, n - done)
        gs = life.random_genomes(rng, k)
        fit, steps = life.evaluate(gs, cfg.objective, cond, cfg.train_seed_list(), cfg.ticks, cfg.cohort)
        if meter:
            meter.sim_steps += steps
            meter.evaluations += k * cfg.train_seeds
        m = fit.mean(1)
        i = int(m.argmax())
        if m[i] > best_f:
            best_f, best_g = float(m[i]), gs[i]
        done += k
    return best_g, best_f
