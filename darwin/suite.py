"""Problem suite (Brief s.61-62): Life World problems split into
training, development, held-out and final never-seen sets.

* train   — practice problems. Darwin runs on these every day; validated
            winners enter Discovery Memory.
* dev     — for tuning Darwin itself. The owner may benchmark on these any time.
* holdout — the daily benchmark. Results never enter memory and memory-use
            statistics are not updated from them, so nothing learned here can
            leak back into the search that is being measured.
* final   — never seen. Owner-only, every use is recorded in the Ledger; use it
            rarely, to check that improvements on holdout were not tuned to it.

All suite problems use the life-2.0 neural world. Changing any problem or seed
rule requires a new SUITE_VERSION; results are never compared across versions.
"""
from __future__ import annotations

import math

from . import life

SUITE_VERSION = "suite-1"
WORLD = "life-2.0"
TICKS = 300
COHORT = 8
SCORING_SEEDS = 8           # seeds a final genome is scored on (never used in search)
LEAK_DISTANCE = 0.12        # memory admission is refused this close to a holdout/final problem

PROBLEMS = [
    # id, split, objective, conditions, note
    ("T1", "train", "forage", dict(food=30, green_share=0.5, scarcity=1.0, hazards=2), "baseline world"),
    ("T2", "train", "forage", dict(food=18, green_share=0.5, scarcity=2.0, hazards=1), "sparse, slow regrowth"),
    ("T3", "train", "forage", dict(food=45, green_share=0.85, scarcity=1.0, hazards=3), "green-rich"),
    ("T4", "train", "survive", dict(food=30, green_share=0.5, scarcity=1.0, hazards=5), "hazard-heavy famine"),
    ("T5", "train", "survive", dict(food=25, green_share=0.15, scarcity=1.5, hazards=2), "amber-rich famine"),
    ("T6", "train", "forage", dict(food=80, green_share=0.3, scarcity=0.7, hazards=0), "abundant, no hazards"),
    ("D1", "dev", "forage", dict(food=40, green_share=0.3, scarcity=1.2, hazards=4), ""),
    ("D2", "dev", "survive", dict(food=25, green_share=0.7, scarcity=1.3, hazards=2), ""),
    ("H1", "holdout", "forage", dict(food=22, green_share=0.65, scarcity=1.6, hazards=3), ""),
    ("H2", "holdout", "survive", dict(food=35, green_share=0.35, scarcity=0.8, hazards=4), ""),
    ("H3", "holdout", "forage", dict(food=60, green_share=0.2, scarcity=1.0, hazards=5), ""),
    ("F1", "final", "survive", dict(food=18, green_share=0.55, scarcity=2.2, hazards=2), ""),
    ("F2", "final", "forage", dict(food=40, green_share=0.9, scarcity=1.2, hazards=1), ""),
]
SPLITS = ("train", "dev", "holdout", "final")


def problems(split=None):
    out = []
    for i, (pid, sp, obj, cond, note) in enumerate(PROBLEMS):
        if split is None or sp == split:
            out.append({"id": pid, "index": i, "split": sp, "objective": obj,
                        "conditions": {**life.Conditions().to_dict(), **cond}, "note": note})
    return out


def get(pid):
    return next((p for p in problems() if p["id"] == pid), None)


def features(cond: dict):
    """Conditions mapped to roughly [0, 1] per axis."""
    food = max(5.0, float(cond.get("food", 30)))
    sc = max(0.3, float(cond.get("scarcity", 1.0)))
    return (math.log(food / 5.0) / math.log(40.0),
            float(cond.get("green_share", 0.5)),
            (math.log(sc) - math.log(0.3)) / (math.log(4.0) - math.log(0.3)),
            float(cond.get("hazards", 2)) / 8.0)


def distance(obj_a, cond_a, obj_b, cond_b) -> float:
    """Problem distance used for memory retrieval and the leakage guard.
    Different objectives add 0.5: cross-objective transfer is a hypothesis to test."""
    fa, fb = features(cond_a), features(cond_b)
    d = math.sqrt(sum((x - y) ** 2 for x, y in zip(fa, fb)))
    return d + (0.0 if obj_a == obj_b else 0.5)


def protected_near(objective, cond):
    """Nearest holdout/final problem and its distance (for the leakage guard)."""
    best = None
    for p in problems():
        if p["split"] in ("holdout", "final"):
            d = distance(objective, cond, p["objective"], p["conditions"])
            if best is None or d < best[1]:
                best = (p["id"], d)
    return best


def search_seed(problem_index: int, replicate: int) -> int:
    """Config seed for a benchmark search; fixed so control contestants repeat exactly each day."""
    return 7_000_000 + 1000 * problem_index + replicate


def scoring_seeds(problem_index: int):
    return [9_000_000 + 100 * problem_index + i for i in range(SCORING_SEEDS)]


# ── Series 2 (Phase 2b): fresh problems every cycle ─────────────────────
# Each benchmark cycle draws FRESH_PER_CYCLE never-reused problems from the
# distribution below and searches them with fresh seeds, so every cycle is
# independent evidence. The suite-1 holdout problems H1-H3 stay as a fixed
# "anchor" (replicate 0, fixed seeds) for the exact-reproducibility check.
SUITE2 = "suite-2"
FRESH_PER_CYCLE = 6
FRESH_REPLICATES = 2
FRESH_CALIBRATION_N = 200
DISTRIBUTION = {
    "objective": ["forage", "survive"],
    "food": (12, 90),             # log-uniform, integer
    "green_share": (0.1, 0.9),    # uniform
    "scarcity": (0.6, 2.4),       # log-uniform
    "hazards": (0, 6),            # integer uniform
}


def sample_problem(rng):
    """One problem from the series-2 distribution (shared by fresh tests and curriculum practice)."""
    D = DISTRIBUTION
    obj = D["objective"][int(rng.integers(len(D["objective"])))]
    cond = {**life.Conditions().to_dict(),
            "food": int(round(math.exp(rng.uniform(math.log(D["food"][0]), math.log(D["food"][1]))))),
            "green_share": round(float(rng.uniform(*D["green_share"])), 3),
            "scarcity": round(math.exp(rng.uniform(math.log(D["scarcity"][0]), math.log(D["scarcity"][1]))), 3),
            "hazards": int(rng.integers(D["hazards"][0], D["hazards"][1] + 1))}
    return obj, cond


def fresh_problems(cycle_id: int, n: int = FRESH_PER_CYCLE):
    """Never-reused test problems for one benchmark cycle, with their own search and scoring seeds."""
    import numpy as np
    out = []
    for k in range(n):
        rng = np.random.default_rng([2, int(cycle_id), k])
        obj, cond = sample_problem(rng)
        seeds = rng.integers(1, 2 ** 31 - 1, size=FRESH_REPLICATES + SCORING_SEEDS)
        out.append({"id": f"X{cycle_id}-{k + 1}", "index": None, "split": "fresh", "objective": obj,
                    "conditions": cond, "note": "fresh, never reused",
                    "search_seeds": [int(x) for x in seeds[:FRESH_REPLICATES]],
                    "scoring_seeds": [int(x) for x in seeds[FRESH_REPLICATES:]]})
    return out


def anchors():
    out = []
    for p in problems("holdout"):
        out.append({**p, "split": "anchor", "search_seeds": [search_seed(p["index"], 0)],
                    "scoring_seeds": scoring_seeds(p["index"])})
    return out
