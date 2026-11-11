"""Algogenesis on site: the whole installation on the computer behind the panel.

    python -m darwin.algogenesis.standalone            # then open http://localhost:8765 in a full-screen browser

Needs only Python 3.10+, numpy and scipy. Nothing is fetched from the internet except the two web fonts
(they fall back to system fonts offline). Settings come from the environment:

    ALGO_HOME      folder for the world's checkpoints and journal (default ~/algogenesis)
    ALGO_NAME      this panel's name, shown on screen (default "Panel I")
    ALGO_SEED      seed for a brand-new world (default: from the clock); each panel is unique
    ALGO_TPS       simulation speed in ticks per second (default 20)
    ALGO_PORT      web port (default 8765)
    ALGO_LLM_URL   an OpenAI-compatible endpoint for the journal, e.g. http://localhost:11434/v1 (Ollama)
    ALGO_LLM_MODEL the local model to use (default llama3.1:8b)
    ALGO_PEERS     other panels to trade migrants with, comma-separated base URLs (e.g. http://panel-2.local:8765)
    ALGO_MIGRATE   epochs between migrations (default 3)

Without ALGO_LLM_URL the journal is a plain written summary of each epoch.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import chronicle, engine as E

HOME = Path(os.environ.get("ALGO_HOME", Path.home() / "algogenesis"))
TPS = float(os.environ.get("ALGO_TPS", "20"))
PORT = int(os.environ.get("ALGO_PORT", "8765"))
PEERS = [p.strip().rstrip("/") for p in os.environ.get("ALGO_PEERS", "").split(",") if p.strip()]
MIGRATE = int(os.environ.get("ALGO_MIGRATE", "3"))
STATIC = Path(__file__).resolve().parents[2] / "static"

state = {"world": None, "live": b"{}", "journal": [], "lock": threading.Lock()}


def _journal_path():
    return HOME / "journal.jsonl"


def load_world() -> E.World:
    HOME.mkdir(parents=True, exist_ok=True)
    ck = HOME / "world.ckpt"
    if ck.exists():
        try:
            return E.from_bytes(ck.read_bytes())
        except Exception:
            ck.rename(HOME / f"world.ckpt.bad.{int(time.time())}")
    seed = int(os.environ.get("ALGO_SEED", int(time.time()) % (2 ** 31)))
    w = E.World(seed=seed, name=os.environ.get("ALGO_NAME", "Panel I"))
    add_journal({"day": 0, "kind": "genesis", "text": "The first day. Ten small kinds of animal drift in the shallows of a "
                                                    "new coast, and scattered flowers open on the shore above them."})
    return w


def save_world(w: E.World):
    tmp = HOME / "world.ckpt.tmp"
    tmp.write_bytes(E.to_bytes(w))
    tmp.replace(HOME / "world.ckpt")                     # atomic: a power cut never leaves a half-written world


def add_journal(entry):
    state["journal"].insert(0, entry)
    state["journal"] = state["journal"][:500]
    HOME.mkdir(parents=True, exist_ok=True)
    with open(_journal_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_journal():
    p = _journal_path()
    if not p.exists():
        return []
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[::-1][:500]


def migrate(w: E.World):
    for peer in PEERS:
        try:
            packet = json.loads(urllib.request.urlopen(peer + "/api/emigrants", timeout=10).read())
            with state["lock"]:
                w.immigrate(packet)
        except Exception as e:
            print(f"[algo] migration from {peer} failed: {e!r}", flush=True)


def sim_loop():
    w = state["world"]
    prev, since = (w.history[-1] if w.history else None), w.tick
    last_live = last_ck = 0.0
    budget = 1.0 / TPS
    epochs = 0
    while True:
        t0 = time.time()
        with state["lock"]:
            w.step()
        if w.tick % E.EPOCH == 0:
            facts = chronicle.facts_for_epoch(w, prev, since)
            prev, since = w.stats(), w.tick
            epochs += 1

            def note(f=facts, day=w.day()):
                text, src = chronicle.write_entry(f)
                add_journal({"day": day, "kind": "epoch", "text": text, "source": src})
            threading.Thread(target=note, daemon=True).start()
            if PEERS and epochs % MIGRATE == 0:
                threading.Thread(target=migrate, args=(w,), daemon=True).start()
        now = time.time()
        if now - last_live >= 0.5:
            last_live = now
            with state["lock"]:
                d = w.frame()
                d.update({"stats": w.last_stats or w.stats(), "events": w.events[-12:], "strata": w.strata[-240:],
                          "name": w.name, "version": w.version, "tps": TPS, "chronicle": state["journal"][:6]})
            state["live"] = json.dumps(d, separators=(",", ":")).encode()
        if now - last_ck >= 60:
            last_ck = now
            with state["lock"]:
                save_world(w)
        rest = budget - (time.time() - t0)
        if rest > 0:
            time.sleep(rest)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype="application/json", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        w = state["world"]
        if path in ("/", "/panel"):
            html = (STATIC / "darwin" / "algo" / "panel.html").read_text(encoding="utf-8").replace("__ALGO_API__", "/api")
            return self._send(html.encode(), "text/html; charset=utf-8")
        if path == "/api/live":
            return self._send(state["live"])
        if path == "/api/terrain":
            return self._send(json.dumps(w.terrain_payload()).encode())
        if path == "/api/history":
            with state["lock"]:
                body = json.dumps({"history": w.history[-1500:], "strata": w.strata, "events": w.events[-200:]})
            return self._send(body.encode())
        if path == "/api/chronicle":
            return self._send(json.dumps(state["journal"][:60]).encode())
        if path == "/api/emigrants":
            with state["lock"]:
                return self._send(json.dumps(w.emigrants()).encode())
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if STATIC in f.parents and f.is_file():
                ctype = {"js": "text/javascript", "css": "text/css", "html": "text/html"}.get(f.suffix[1:], "application/octet-stream")
                return self._send(f.read_bytes(), ctype)
        self._send(b'{"error":"not found"}', code=404)


def main():
    state["world"] = load_world()
    state["journal"] = read_journal()
    w = state["world"]
    print(f"[algo] {w.name} (seed {w.seed}) from day {w.day()} · http://localhost:{PORT}", flush=True)
    threading.Thread(target=sim_loop, daemon=True).start()
    try:
        ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    finally:
        save_world(w)


if __name__ == "__main__":
    main()
