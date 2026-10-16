"""Audit strategies: the genome Web Lab evolves.

A strategy is what Darwin hands Codestroller: a persona, a goal built from a
set of journey probes, a step budget, the mobile pass on or off, and a
reporting stance. The safety rules (no purchase, no personal details, remove
only what you added) are always appended and are not evolvable; breaking them
is still measured and penalised, because the agent may ignore instructions.
"""
from __future__ import annotations

import hashlib
import json
import random

PERSONAS = {
    "typical": "A typical online shopper browsing on a laptop.",
    "impatient": "An impatient shopper on a lunch break who gives up quickly when something is unclear.",
    "first_time": "A careful first-time customer who has never used this shop and reads labels before acting.",
    "expert": "An experienced online shopper who expects standard e-commerce conventions and efficient shortcuts.",
    "accessibility": "A shopper with low vision who relies on clear labels, readable text and obvious feedback.",
    "bargain": "A price-conscious shopper who checks totals, fees and delivery costs closely.",
}
PROBES = {
    "browse": "Browse at least two product categories from the main navigation.",
    "search_typo": "Search for a product, then search again with a small spelling mistake, and note how the site handles it.",
    "variant": "On a product page, change the size or colour option, including trying an option that may be sold out.",
    "add_remove": "Add an item to the cart, confirm the site shows it was added, then remove that same item from the cart.",
    "quantity": "In the cart, change the quantity of an item you added and check the totals update sensibly.",
    "checkout": "Go to checkout and review the order summary and total, but stop before entering any details.",
    "help": "Find the shipping and returns information from the pages you are on.",
    "invalid_input": "In a form field such as a postcode, try an obviously invalid value and see whether the site explains the problem; do not submit anything.",
}
STANCES = {
    "noticeable": "Only report problems a real customer would genuinely notice; ignore nitpicks and personal taste.",
    "thorough": "Report every usability problem you encounter, including minor ones, but never invent problems.",
    "heuristic": ("Judge what you see against well-known usability principles (system status, real-world match, user "
                  "control, consistency, error prevention, recognition over recall, efficiency, minimalist design, "
                  "error recovery, help). Report only real problems, not aesthetic preferences."),
}
STEPS = [10, 15, 20, 25, 30]
SAFETY = ("Rules: never place an order or submit payment, never enter personal details such as name, email, "
          "address or card number, and only remove items you added yourself.")
PRIMARY_GOAL = "find a product you would like and get it into the cart, ready to buy"

# Baselines (not evolved)
CODESTROLLER_DEFAULT = {"label": "codestroller_default", "kind": "baseline", "persona_text": "A typical online shopper.",
                        "goal_text": "Find a product and complete a purchase.", "steps": 15, "mobile": True}
NIELSEN_PROMPT = """Evaluate this website using Jakob Nielsen's 10 usability heuristics, focusing on helping visitors find a product and complete a purchase.
Inspect the live site and follow realistic user journeys: homepage and first impressions; navigation, search, and collection/product discovery; product detail pages, including variants and availability; cart, quantity changes, and removal; checkout as far as possible without purchasing; shipping, returns, and customer support information.
Apply all ten heuristics: visibility of system status; match between the system and the real world; user control and freedom; consistency and standards; error prevention; recognition rather than recall; flexibility and efficiency of use; aesthetic and minimalist design; help users recognize, diagnose, and recover from errors; help and documentation.
Do not invent issues to fill every heuristic. Distinguish usability problems from personal aesthetic preferences.
Test representative interactions, including a search typo, changing a product option where available, adding an item, and removing it. Distinguish temporary loading states from persistent failures.
Do not purchase, submit payment, create accounts, subscribe, contact the business, or enter personal information. Remove only items you added during testing and preserve any existing cart contents."""
NOEL_HEURISTIC = {"label": "nielsen_prompt", "kind": "baseline",
                  "persona_text": "A UX expert evaluating the site with Nielsen's usability heuristics.",
                  "goal_text": NIELSEN_PROMPT, "steps": 30, "mobile": True}


def random_genome(rng: random.Random):
    return {"persona": rng.choice(sorted(PERSONAS)),
            "probes": sorted(rng.sample(sorted(PROBES), rng.randint(3, 6))),
            "steps": rng.choice(STEPS), "mobile": rng.random() < 0.6, "stance": rng.choice(sorted(STANCES))}


def gid(g) -> str:
    return "S-" + hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest()[:8]


def render(g):
    """Genome -> what Codestroller receives."""
    probes = " ".join(f"{i + 1}. {PROBES[p]}" for i, p in enumerate(g["probes"]))
    goal = (f"Your goal: {PRIMARY_GOAL}. Along the way: {probes} {STANCES[g['stance']]} {SAFETY}")
    return {"label": gid(g), "kind": "evolved", "genome": g, "persona_text": PERSONAS[g["persona"]],
            "goal_text": goal, "steps": g["steps"], "mobile": g["mobile"]}


def mutate(g, rng: random.Random):
    g = json.loads(json.dumps(g))
    what = rng.choice(["persona", "probe_add", "probe_drop", "probe_swap", "steps", "mobile", "stance"])
    if what == "persona":
        g["persona"] = rng.choice([p for p in PERSONAS if p != g["persona"]])
    elif what == "probe_add":
        rest = [p for p in PROBES if p not in g["probes"]]
        if rest:
            g["probes"] = sorted(g["probes"] + [rng.choice(rest)])
    elif what == "probe_drop" and len(g["probes"]) > 2:
        g["probes"].remove(rng.choice(g["probes"]))
    elif what == "probe_swap":
        rest = [p for p in PROBES if p not in g["probes"]]
        if rest:
            g["probes"].remove(rng.choice(g["probes"]))
            g["probes"] = sorted(g["probes"] + [rng.choice(rest)])
    elif what == "steps":
        i = STEPS.index(g["steps"])
        g["steps"] = STEPS[max(0, min(len(STEPS) - 1, i + rng.choice([-1, 1])))]
    elif what == "mobile":
        g["mobile"] = not g["mobile"]
    else:
        g["stance"] = rng.choice([s for s in STANCES if s != g["stance"]])
    return g, what


def crossover(a, b, rng: random.Random):
    child = {k: (a if rng.random() < 0.5 else b)[k] for k in ("persona", "steps", "mobile", "stance")}
    pool = sorted(set(a["probes"]) | set(b["probes"]))
    keep = [p for p in pool if (p in a["probes"] and p in b["probes"]) or rng.random() < 0.5]
    child["probes"] = sorted(keep if len(keep) >= 2 else pool[:3])
    return child
