"""Dials: how visitors change a panel's environment, the way fish food changes a tank.

A dial never touches a genome or picks a winner. It changes the conditions (how much food falls, how bright the
light is, how often copying slips), and selection carries on under the new conditions. Three rules keep that honest:
- every dial moves the world slowly: the setting eases in over a minute or so, never in one step;
- every turn wears off: like food that gets eaten, a dial drifts back to neutral (half-life about 20 minutes),
  so one visitor cannot fix a world in place, and an untended panel returns to its own course;
- every turn is recorded: a noticeable change is written into the world's events, and so into its journal.
Values run from -1 (least) through 0 (the world's own setting) to +1 (most).
"""
from __future__ import annotations

HALF_LIFE_S = 20 * 60       # a turned dial loses half its effect in twenty minutes of real time
EASE_S = 45                 # and takes about this long to take full effect


class DialsMixin:
    DIALS: list[dict] = []   # [{"key", "label", "icon", "colour", "low", "high", "help"}]

    def _dials(self):
        d = getattr(self, "_dial_state", None)
        if d is None:
            d = self._dial_state = {"cur": {}, "target": {}, "logged": {}}
        for spec in self.DIALS:
            d["cur"].setdefault(spec["key"], 0.0)
            d["target"].setdefault(spec["key"], 0.0)
        return d

    def dial(self, key: str) -> float:
        """The dial's current effect, -1..1 (0 = untouched)."""
        return float(self._dials()["cur"].get(key, 0.0))

    def set_dial(self, key: str, value: float, who: str = "a visitor"):
        spec = next((s for s in self.DIALS if s["key"] == key), None)
        if spec is None:
            return False
        d = self._dials()
        value = max(-1.0, min(1.0, float(value)))
        old = d["target"].get(key, 0.0)
        d["target"][key] = value
        last = d["logged"].get(key, -10 ** 9)
        if abs(value - old) >= 0.25 and self.tick - last > self._dial_ticks(300):
            d["logged"][key] = self.tick
            word = spec["high"] if value > old else spec["low"]
            self.event("dial", f"{who.capitalize()} turned the {spec['label'].lower()} dial toward {word.lower()}.")
        return True

    def _dial_ticks(self, seconds):
        return int(seconds * getattr(self, "TPS", 10.0))

    def ease_dials(self):
        """Call once a tick: the setting eases toward its target, and the target drifts home."""
        if not self.DIALS:
            return
        d = self._dials()
        tps = getattr(self, "TPS", 10.0)
        k_ease = 1.0 / max(1.0, EASE_S * tps)
        k_home = 0.6931 / max(1.0, HALF_LIFE_S * tps)
        for spec in self.DIALS:
            key = spec["key"]
            t = d["target"][key] * (1 - k_home)
            if abs(t) < 0.005:
                t = 0.0
            d["target"][key] = t
            d["cur"][key] += (t - d["cur"][key]) * k_ease

    def dials_payload(self):
        if not self.DIALS:
            return {}
        d = self._dials()
        return {s["key"]: [round(d["cur"][s["key"]], 3), round(d["target"][s["key"]], 3)] for s in self.DIALS}


def D(key, label, icon, colour, low, high, help_):
    return {"key": key, "label": label, "icon": icon, "colour": colour, "low": low, "high": high, "help": help_}


def mult(v, span=2.0):
    """A multiplier for dial value v in -1..1: 1/span at -1, 1 at 0, span at +1."""
    return float(span ** v)
