"""The Algogenesis concept panels. LIVE lists the worlds that run now; the rest are announced in the gallery."""
from __future__ import annotations

import importlib

CONCEPTS = [
    ("protogenesis", "Protogenesis", "First origin or initial formation"),
    ("epigenesis", "Epigenesis", "Development through successive stages of differentiation"),
    ("noogenesis", "Noogenesis", "Emergence or evolution of mind and consciousness"),
    ("biogenesis", "Biogenesis", "Life arising from preexisting life"),
    ("morphogenesis", "Morphogenesis", "The process by which form and structure develop"),
    ("cosmogenesis", "Cosmogenesis", "The coming into existence of the cosmos"),
    ("anthropogenesis", "Anthropogenesis", "The origin and development of humanity"),
    ("psychogenesis", "Psychogenesis", "The origin and development of psychological processes"),
    ("autopoiesis", "Autopoiesis", "A system's ability to produce and maintain itself"),
    ("palingenesis", "Palingenesis", "Rebirth, regeneration, or recreation"),
    ("anagenesis", "Anagenesis", "Evolutionary transformation within a lineage"),
    ("ontogeny", "Ontogeny", "The development of an organism from its earliest stages"),
]

LIVE = {
    "protogenesis": ("darwin.algogenesis.worlds.protogenesis", "Protogenesis"),
    "morphogenesis": ("darwin.algogenesis.worlds.morphogenesis", "Morphogenesis"),
    "autopoiesis": ("darwin.algogenesis.worlds.autopoiesis", "Autopoiesis"),
}


def world_class(slug):
    mod, cls = LIVE[slug]
    return getattr(importlib.import_module(mod), cls)


def concept(slug):
    for s, t, d in CONCEPTS:
        if s == slug:
            return {"slug": s, "title": t, "definition": d, "live": s in LIVE}
    return None
