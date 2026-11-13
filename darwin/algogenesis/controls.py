"""The dial channel: the web app records a visitor's dial setting; the world's runner picks it up within seconds."""
from __future__ import annotations

import json
import time

import sqlalchemy as sa

from .. import store as S


def write(key: str, dial: str, value: float) -> dict:
    value = max(-1.0, min(1.0, float(value)))
    with S.engine().begin() as c:
        row = c.execute(sa.select(S.algo_controls.c.data).where(S.algo_controls.c.key == key)).first()
        data = json.loads(row[0]) if row and row[0] else {}
        data = {**data, dial: [round(value, 3), time.time()]}
        js = json.dumps(data)
        if row is None:
            c.execute(S.algo_controls.insert().values(key=key, ts=S.now(), data=js))
        else:
            c.execute(S.algo_controls.update().where(S.algo_controls.c.key == key).values(ts=S.now(), data=js))
    return data


def read(key: str) -> dict:
    with S.engine().connect() as c:
        row = c.execute(sa.select(S.algo_controls.c.data).where(S.algo_controls.c.key == key)).first()
    return json.loads(row[0]) if row and row[0] else {}


class Applier:
    """Used by a runner: applies settings newer than the last one it applied, once each."""

    def __init__(self, key: str):
        self.key = key
        self.seen = {}
        self.first = True

    def apply(self, world):
        try:
            data = read(self.key)
        except Exception:
            return
        for dial, (value, ts) in data.items():
            if ts > self.seen.get(dial, 0):
                self.seen[dial] = ts
                if self.first and time.time() - ts > 600:
                    continue                 # an old setting from before a restart: it has worn off already
                world.set_dial(dial, value)
        self.first = False
