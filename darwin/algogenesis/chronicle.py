"""The naturalist: turns what happened in an epoch into a short field note.

The language model never decides what evolves. It only describes facts the engine measured, so the
chronicle stays true to the world. Providers:
- ALGO_LLM_URL set (an OpenAI-compatible endpoint, e.g. Ollama or llama.cpp on the panel's own computer):
  ALGO_LLM_MODEL names the model. This is the on-site setup.
- otherwise a caller-supplied function (the cloud passes one that calls Anthropic and records the cost).
- with neither, a plain written summary, so the panel never stops chronicling.
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import engine as E

SYSTEM = """You are the naturalist keeping the field journal of ALGOGENESIS, a living world evolving on a wall panel.
Write ONE journal entry of 2-4 sentences (at most 80 words) about the epoch described in the facts.
Rules: describe only what the facts state; never invent creatures, numbers or events. Use the species names given.
Prefer the most striking change (a new kind of body, a colour or glow spreading, an extinction, a shift between
water and land, flowers and pollinators changing together). Plain, vivid, unhurried prose in the voice of a
careful 19th-century naturalist, but no archaic spelling. No title, no date, no lists, no exclamation marks."""


def describe_look(look):
    k = dict(zip(E.LOOK_KEYS, look))
    hue = _hue_word(k["hue"])
    parts = [f"{'vivid ' if k['sat'] > 0.55 else 'pale ' if k['sat'] < 0.25 else ''}{hue}"]
    if k["pattern"] > 0.66:
        parts.append(f"spotted with {_hue_word(k['hue2'])}")
    elif k["pattern"] > 0.33:
        parts.append(f"striped with {_hue_word(k['hue2'])}")
    parts.append(f"{k['segs']} segment{'s' if k['segs'] != 1 else ''}")
    if k["limbs"]:
        parts.append(f"{k['limbs']} pair{'s' if k['limbs'] != 1 else ''} of legs")
    if k["glow"] > 0.35:
        parts.append("luminous at night")
    if k["crest"] > 0.4:
        parts.append("crested")
    parts.append("swimmer" if k["fin"] > 0.6 else "walker" if k["fin"] < 0.4 else "amphibious")
    parts.append("drinks nectar" if k["diet"] < 0.35 else "hunts" if k["diet"] > 0.6 else "grazes and scavenges")
    return ", ".join(parts)


def _hue_word(h):
    names = ["red", "orange", "amber", "yellow", "lime", "green", "jade", "teal", "cyan", "azure", "blue",
             "indigo", "violet", "magenta", "rose", "crimson"]
    return names[int(round(h * 16)) % 16]


def facts_for_epoch(world: E.World, prev_stats: dict | None, since_tick: int) -> dict:
    s = world.stats()
    layer = world.strata[-1] if world.strata else {"animals": [], "plants": []}
    ev = [e for e in world.events if e["tick"] > since_tick]
    keys = ["animals", "plants", "animal_species", "plant_species", "complexity_mean", "complexity_max", "glow_mean",
            "colour_mean", "choosy_mean", "predators", "pollinators", "on_land", "mean_generation", "care_mean",
            "families", "young"]
    change = {}
    if prev_stats:
        for k in keys:
            if k in s and k in prev_stats and isinstance(s[k], (int, float)):
                change[k] = [prev_stats[k], s[k]]
    return {
        "world": world.name, "day": world.day(), "epoch": len(world.strata),
        "visitors_dials_now": {k: v[0] for k, v in world.dials_payload().items() if abs(v[0]) > 0.05},
        "leading_animals": [{"name": a["name"], "count": a["n"], "looks": describe_look(a["look"])} for a in layer["animals"]],
        "leading_flowers": [{"name": p["name"], "count": p["n"], "colour": _hue_word(p["hue"]), "petals": round(p["petals"])}
                            for p in layer["plants"]],
        "now": {k: s.get(k) for k in keys}, "change_since_last_epoch": change,
        "events": [e["text"] for e in ev if e["kind"] != "extinction"][-8:] +
                  [e["text"] for e in ev if e["kind"] == "extinction"][-4:],
        "sea_level": "rising" if prev_stats and s["sea"] > prev_stats.get("sea", 0) + 0.005 else
                     "falling" if prev_stats and s["sea"] < prev_stats.get("sea", 0) - 0.005 else "steady",
    }


def plain_entry(f: dict) -> str:
    a = f["leading_animals"][:1]
    lead = f"The commonest animal is {a[0]['name']}, {a[0]['looks']}." if a else "No animal is common enough to name."
    ev = f" {f['events'][0]}." if f["events"] else ""
    now = f["now"]
    return (f"Day {f['day']:g}. {now.get('animals', 0)} animals of {now.get('animal_species', 0)} species and "
            f"{now.get('plants', 0)} flowering plants. {lead}{ev}")


def _openai_compatible(system, user):
    url = os.environ["ALGO_LLM_URL"].rstrip("/") + "/chat/completions"
    body = {"model": os.environ.get("ALGO_LLM_MODEL", "llama3.1:8b"), "max_tokens": 220, "temperature": 0.7,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=90).read())
    return r["choices"][0]["message"]["content"]


def write_entry(facts: dict, call=None) -> tuple[str, str]:
    """Return (text, source). call(system, user) -> text is the cloud's model, used when no local model is set."""
    user = "Facts for this epoch (JSON):\n" + json.dumps(facts, ensure_ascii=False)
    try:
        if os.environ.get("ALGO_LLM_URL"):
            text, src = _openai_compatible(SYSTEM, user), "local model"
        elif call is not None:
            text, src = call(SYSTEM, user), "cloud model"
        else:
            text, src = "", ""
        text = (text or "").strip()
        if text:
            return text, src
    except Exception:
        pass
    return plain_entry(facts), "summary"


WORLD_SYSTEM = """You keep the field journal of {title}, one panel of ALGOGENESIS, a set of living simulations shown on wall panels.
The panel's subject: {title}, "{definition}". {hint}
Write ONE journal entry of 2-4 sentences (at most 80 words) about the epoch described in the facts.
Describe only what the facts state; never invent events or numbers. Prefer the most telling change, and connect it,
lightly, to the panel's subject. Plain, vivid, unhurried prose, in the voice of a careful naturalist. No title, no
date, no lists, no exclamation marks."""


def world_entry(facts: dict, title: str, definition: str, hint: str, call=None) -> tuple[str, str]:
    system = WORLD_SYSTEM.format(title=title, definition=definition, hint=hint)
    user = "Facts for this epoch (JSON):\n" + json.dumps(facts, ensure_ascii=False)
    try:
        if os.environ.get("ALGO_LLM_URL"):
            text, src = _openai_compatible(system, user), "local model"
        elif call is not None:
            text, src = call(system, user), "cloud model"
        else:
            text, src = "", ""
        text = (text or "").strip()
        if text:
            return text, src
    except Exception:
        pass
    now = facts.get("now", {})
    bits = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in list(now.items())[:5])
    ev = facts.get("events") or []
    return f"Epoch {facts.get('epoch')}. {bits}." + (f" {ev[-1]}" if ev else ""), "summary"
