"""Baseline competitors (Brief s.61), run at the same evaluation budget as Darwin.

* random search: best of n random genomes
* hill climber: (1 + lambda) evolution strategy with the 1/5th success rule,
  a standard local optimiser
Both use the same evaluator, conditions and search seeds as Darwin, and report
exactly how many genome evaluations they used.
"""
from __future__ import annotations

import numpy as np

from . import life


def random_search(spec, objective, cond, seeds, n, rng_seed, ticks=300, cohort=8, chunk=60):
    rng = np.random.default_rng(rng_seed)
    best, best_f, used = None, -np.inf, 0
    while used < n:
        k = min(chunk, n - used)
        gs = life.random_genomes(rng, k, spec)
        f, _ = life.evaluate(gs, objective, cond, seeds, ticks, cohort, spec)
        m = f.mean(1)
        i = int(m.argmax())
        if m[i] > best_f:
            best, best_f = gs[i], float(m[i])
        used += k
    return best, best_f, used


def hill_climb(spec, objective, cond, seeds, n, rng_seed, ticks=300, cohort=8, lam=20, sigma0=0.1):
    rng = np.random.default_rng(rng_seed)
    lam = max(2, min(lam, n))
    gs = life.random_genomes(rng, lam, spec)
    f, _ = life.evaluate(gs, objective, cond, seeds, ticks, cohort, spec)
    m = f.mean(1)
    best, best_f, used, sig = gs[int(m.argmax())], float(m.max()), lam, sigma0
    while used + lam <= n:
        kids = life.clip_genome(best + rng.normal(0, 1, (lam, spec.G)) * sig * spec.SPAN, spec)
        f, _ = life.evaluate(kids, objective, cond, seeds, ticks, cohort, spec)
        m = f.mean(1)
        used += lam
        success = float((m > best_f).mean())
        if m.max() > best_f:
            best, best_f = kids[int(m.argmax())], float(m.max())
        sig = min(max(sig * (1.22 if success > 0.2 else 0.82), 0.01), 0.5)
    rest = n - used
    if rest > 0:  # spend the remainder so the budget is exactly n
        kids = life.clip_genome(best + rng.normal(0, 1, (rest, spec.G)) * sig * spec.SPAN, spec)
        f, _ = life.evaluate(kids, objective, cond, seeds, ticks, cohort, spec)
        m = f.mean(1)
        used += rest
        if m.max() > best_f:
            best, best_f = kids[int(m.argmax())], float(m.max())
    return best, best_f, used
