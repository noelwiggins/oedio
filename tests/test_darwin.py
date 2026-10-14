"""Darwin Phase 1 tests. Run: python -m pytest tests/test_darwin.py -q

Uses a throwaway SQLite database, so it never touches production data.
"""
import io
import json
import os
import sys
import tempfile
import zipfile

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp()
os.environ["DARWIN_DB_URL"] = "sqlite:///" + os.path.join(_tmp, "t.sqlite")
os.environ.pop("DATABASE_URL", None)
os.environ["DARWIN_SCHEDULER"] = "off"   # tests drive the scheduler explicitly

from darwin import core, life, runner, snapshot, store  # noqa: E402
import sqlalchemy as sa  # noqa: E402

SMALL = dict(objective="forage", population=12, generations=6, islands=2, train_seeds=1, holdout_seeds=8,
             ticks=150, cohort=4, seed=11)


# ── world ────────────────────────────────────────────────────────────────
def test_world_is_deterministic_and_position_independent():
    rng = np.random.default_rng(0)
    g = life.random_genomes(rng, 5)
    a, _ = life.evaluate(g, "forage", life.Conditions(), [3, 4], ticks=120, cohort=4)
    b, _ = life.evaluate(g, "forage", life.Conditions(), [3, 4], ticks=120, cohort=4)
    assert np.array_equal(a, b)
    c, _ = life.evaluate(g[::-1], "forage", life.Conditions(), [3, 4], ticks=120, cohort=4)
    assert np.array_equal(a, c[::-1]), "a genome's score must not depend on its batch position"
    for i in range(len(g)):
        solo, _ = life.evaluate(g[i:i + 1], "forage", life.Conditions(), [3, 4], ticks=120, cohort=4)
        assert np.array_equal(solo[0], a[i]), "a genome evaluated alone must score exactly as in a batch"


def test_world_mechanics_cost_energy_and_feed():
    rng = np.random.default_rng(1)
    sim = life.LifeSim(rng, 1, 4, life.Conditions(food=0, hazards=0))
    sim.place(0, life.random_genomes(rng, 4))
    e0 = sim.energy.copy()
    sim.step()
    assert (sim.energy[sim.alive] < e0[sim.alive]).all(), "living costs energy"
    for _ in range(2000):
        sim.step()
    assert not sim.alive.any(), "with no food every creature eventually starves"


def test_genomes_clip_to_ranges():
    g = life.clip_genome(np.full(life.G, 1e9))
    assert np.allclose(g, life.HIGH)


def test_reproduction_inherits_with_mutation():
    rng = np.random.default_rng(2)
    sim = life.LifeSim(rng, 1, 40, life.Conditions(food=150, hazards=0, reproduction=True))
    sim.track_events = True
    sim.place(0, life.random_genomes(rng, 6))
    for _ in range(400):
        sim.step()
    births = [e for e in sim.events if e[0] == "birth" and e[3] is not None]
    assert births, "creatures should reproduce when food is plentiful"


# ── core ─────────────────────────────────────────────────────────────────
def test_config_validation_enforces_limits():
    cfg = core.Config.from_dict({**SMALL, "population": 500})
    assert any("population" in e for e in cfg.validate({"max_population": 60, "max_generations": 60}))
    assert not core.Config.from_dict(SMALL).validate({"max_population": 60, "max_generations": 60})


def test_seed_sets_are_disjoint():
    cfg = core.Config.from_dict({**SMALL, "train_seeds": 5, "holdout_seeds": 16})
    assert not set(cfg.train_seed_list()) & set(cfg.holdout_seed_list())


def test_evolution_runs_records_lineage_and_replays_exactly():
    cfg = core.Config.from_dict(SMALL)
    ev = core.Evolution(cfg).run()
    assert len(ev.history) == cfg.generations
    assert ev.best.fitness >= ev.gen0_best.fitness
    pop = ev.final_population
    assert all(c.root for c in pop), "every candidate traces back to a founder"
    assert any(c.operator != "random" for c in pop)
    ev2 = core.Evolution(core.Config.from_dict(SMALL)).run()
    assert ev.digest() == ev2.digest(), "same seed + config must reproduce exactly"
    ev3 = core.Evolution(core.Config.from_dict({**SMALL, "seed": 12})).run()
    assert ev.digest() != ev3.digest()


def test_stop_request_is_honoured():
    ev = core.Evolution(core.Config.from_dict({**SMALL, "generations": 50}), should_stop=lambda: True).run()
    assert ev.stop_reason == "cancelled by request" and len(ev.history) == 1


def test_disturbance_changes_conditions():
    cfg = core.Config.from_dict({**SMALL, "disturbance": "hazard_shock", "disturbance_gen": 3})
    assert core.conditions_at(cfg, 2).hazards + 4 == core.conditions_at(cfg, 3).hazards


def test_sign_test():
    assert core.sign_test_p(8, 8) == pytest.approx(1 / 256)
    assert core.sign_test_p(0, 8) == 1.0


# ── ledger ───────────────────────────────────────────────────────────────
def test_ledger_chain_and_append_only():
    a = store.append("test.one", {"x": 1})
    store.append("test.two", {"x": 2}, parent_id=a)
    assert store.verify_chain()["ok"]
    with pytest.raises(Exception):
        with store.engine().begin() as c:
            c.execute(store.events.update().where(store.events.c.id == a).values(payload="{}"))
    with pytest.raises(Exception):
        with store.engine().begin() as c:
            c.execute(store.events.delete().where(store.events.c.id == a))


def test_ledger_detects_forged_event():
    eng = store.engine()
    with eng.begin() as c:  # insert an event with a wrong hash, bypassing append()
        c.execute(store.events.insert().values(ts=store.now(), type="forged", payload="{}", cost_usd=0.0,
                                               cost_kind="none", provenance="{}", prev_hash="x", hash="y"))
    v = store.verify_chain()
    assert not v["ok"]
    # Restore a clean ledger for the remaining tests (test-only: drop and recreate tables).
    store.md.drop_all(eng)
    with eng.begin() as c:
        for t in store.APPEND_ONLY:
            for op in ("update", "delete"):
                c.exec_driver_sql(f"DROP TRIGGER IF EXISTS {t}_no_{op}")
    store.init(eng)
    assert store.verify_chain()["ok"]


# ── worker end to end ────────────────────────────────────────────────────
def _queue(cfg, kind="evolve", replay_of=None):
    with store.engine().begin() as c:
        return c.execute(store.experiments.insert().values(
            created_at=store.now(), kind=kind, replay_of=replay_of, lab="life", title="t",
            objective=cfg["objective"], config=store.canon(core.Config.from_dict(cfg).to_dict()),
            seed=cfg["seed"], status="queued", owner=True, requester="test", budget_usd=1.0,
            max_cpu_s=None, stop_requested=False)).inserted_primary_key[0]


def test_runner_end_to_end_claims_and_replay():
    exp = _queue({**SMALL, "baseline_random": True})
    assert runner.claim_next() == exp
    runner.run_experiment(exp)
    with store.engine().connect() as c:
        row = dict(c.execute(sa.select(store.experiments).where(store.experiments.c.id == exp)).mappings().one())
        n_gen = c.execute(sa.select(sa.func.count()).select_from(store.generations).where(
            store.generations.c.experiment_id == exp)).scalar()
        n_cand = c.execute(sa.select(sa.func.count()).select_from(store.candidates).where(
            store.candidates.c.experiment_id == exp)).scalar()
    assert row["status"] == "completed", row["stop_reason"]
    assert n_gen == SMALL["generations"] and n_cand == SMALL["population"] * SMALL["generations"]
    claims = store.all_claims(exp)
    assert claims and all(c["history"][0]["status"] == "candidate" for c in claims)
    allowed = {"candidate", "observed", "replicated", "robust", "failed replication"}
    assert all(c["status"] in allowed for c in claims)
    summary = json.loads(row["summary"])
    if summary["final_best"]["fitness"] > summary["gen0_best"]["fitness"]:
        assert "holdout" in summary["validation"]
    assert "baseline_random" in summary["validation"]
    assert store.verify_chain()["ok"]

    rep = _queue({**SMALL, "baseline_random": True}, kind="replay", replay_of=exp)
    assert runner.claim_next() == rep
    runner.run_experiment(rep)
    with store.engine().connect() as c:
        r = dict(c.execute(sa.select(store.experiments).where(store.experiments.c.id == rep)).mappings().one())
    assert json.loads(r["summary"])["replay"]["match"] is True


def test_cpu_cap_stops_evolution_early():
    cfg = core.Config.from_dict({**SMALL, "generations": 400, "stagnation": 400})
    ev = core.Evolution(cfg, max_cpu_s=0.5).run()
    assert ev.stop_reason.startswith("compute cap") and len(ev.history) < 400


# ── snapshot ─────────────────────────────────────────────────────────────
def test_snapshot_package_and_redaction():
    store.append("note", {"leak": "sk-ant-api03-abcdefghijklmnop and ghp_abcdefghijklmnopqrstuvwxyz0123"})
    snap = snapshot.build()
    assert snap["schema"] == snapshot.SCHEMA_VERSION and snap["ledger"]["ok"]
    with store.engine().connect() as c:
        rows = [dict(r) for r in c.execute(sa.select(store.events).order_by(store.events.c.id)).mappings()]
    z = zipfile.ZipFile(io.BytesIO(snapshot.package(snap, rows)))
    names = set(z.namelist())
    for f in ("DARWIN_SNAPSHOT.md", "DARWIN_SNAPSHOT.json", "DARWIN_LEDGER_EXPORT.csv", "DARWIN_BENCHMARKS.csv"):
        assert f in names
    led = z.read("DARWIN_LEDGER_EXPORT.csv").decode()
    assert "sk-ant-api03-abc" not in led and "ghp_abc" not in led and "[REDACTED]" in led
    cmp = snapshot.compare(snap, snapshot.build())
    assert "totals" in cmp


# ── web ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from flask import Flask
    from darwin.web import bp
    app = Flask(__name__, template_folder=os.path.join(ROOT, "templates"),
                static_folder=os.path.join(ROOT, "static"))
    app.register_blueprint(bp)
    return app.test_client()


def test_pages_render(client):
    for path in ("/darwin/", "/darwin/lab/life", "/darwin/ledger", "/darwin/history", "/darwin/snapshots",
                 "/darwin/system", "/darwin/owner"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert b"Noel Wiggins. All rights reserved." in r.data
        assert r.headers.get("X-Robots-Tag", "").startswith("noindex")


def test_world_api_streams_frames(client):
    import time
    d = client.get("/darwin/api/world/frames?since=-1").get_json()
    assert d["stats"]["population"] > 0
    time.sleep(0.6)
    d2 = client.get("/darwin/api/world/frames?since=-1").get_json()
    assert d2["stats"]["tick"] > d["stats"]["tick"] or d2["frames"]


def test_visitor_caps_are_enforced(client):
    r = client.post("/darwin/api/experiments", json={"budget_usd": 1.0, "config": SMALL})
    assert r.status_code == 400 and "owner" in json.dumps(r.get_json())
    r = client.post("/darwin/api/experiments", json={"budget_usd": 0.1, "config": {**SMALL, "population": 500}})
    assert r.status_code == 400


def test_assess_routes_without_llm(client):
    d = client.post("/darwin/api/assess", json={"goal": "organize my kitchen"}).get_json()
    assert d["routing"]["lab"] == "space" and "assessment" not in d
    d = client.post("/darwin/api/assess", json={"goal": "evolve creatures that survive hazards"}).get_json()
    assert d["routing"]["lab"] == "life" and d["routing"]["suggested"]["objective"] == "survive"


def test_survive_objective_is_not_saturated():
    rng = np.random.default_rng(3)
    f, _ = life.evaluate(life.random_genomes(rng, 40), "survive", life.Conditions(), [1, 2])
    m = f.mean(1)
    assert m.max() > m.min() * 1.2, "the survive objective must separate good from poor survivors"
    s = np.sort(m)
    assert s[-1] > s[-2], "no ceiling: the best random genome must be strictly ahead"


# ── Phase 2 ──────────────────────────────────────────────────────────────
from darwin import baselines, bench, memory, suite  # noqa: E402


def test_neural_world_is_batch_independent():
    S_ = life.NEURAL
    g = life.random_genomes(np.random.default_rng(4), 9, S_)
    a, _ = life.evaluate(g, "forage", life.Conditions(hazards=3), [5], ticks=120, cohort=4, spec=S_)
    for i in range(len(g)):
        solo, _ = life.evaluate(g[i:i + 1], "forage", life.Conditions(hazards=3), [5], ticks=120, cohort=4, spec=S_)
        assert np.array_equal(solo[0], a[i])


def test_phase1_configs_replay_unchanged():
    # A Phase 1 config (no world/memory keys) must still produce the Phase 1 digest.
    ev = core.Evolution(core.Config(objective="forage", population=40, generations=30, seed=7)).run()
    assert ev.digest()[:12] == "36e985e14e88"


def test_suite_splits_and_leakage_geometry():
    assert {p["split"] for p in suite.problems()} == set(suite.SPLITS)
    for p in suite.problems("train"):
        assert suite.protected_near(p["objective"], p["conditions"])[1] >= suite.LEAK_DISTANCE


def test_max_evals_budget_and_baselines_exact():
    cfg = core.Config.from_dict({**SMALL, "world": "life-2.0", "generations": 400, "stagnation": 400, "max_evals": 60})
    ev = core.Evolution(cfg).run()
    assert ev.stop_reason.startswith("evaluation budget") and len(ev._cache) <= 60
    S_ = life.NEURAL
    for fn in (baselines.random_search, baselines.hill_climb):
        g, f, used = fn(S_, "forage", life.Conditions(), [1], 37, 3, ticks=60, cohort=2)
        assert used == 37 and len(g) == S_.G


def test_memory_admit_retrieve_seed_and_guard():
    cond = suite.get("T1")["conditions"]
    g = life.random_genomes(np.random.default_rng(1), 1, life.NEURAL)[0]
    mid, why = memory.admit(None, None, "x", "life-2.0", "forage", cond, g, 1.0, {}, "test", "replicated")
    assert mid and why == "admitted"
    near = suite.get("H1")
    mid2, why2 = memory.admit(None, None, "y", "life-2.0", near["objective"], near["conditions"], g, 1.0, {}, "test", "robust")
    assert mid2 is None and "protected" in why2
    mid3, _ = memory.admit(None, None, "z", "life-2.0", "forage", cond, g, 1.0, {}, "test", "observed")
    assert mid3 is None
    got = memory.retrieve("life-2.0", "forage", cond)
    assert got and got[0]["memory_id"] == mid and got[0]["distance"] == 0.0
    cfg = core.Config.from_dict({**SMALL, "world": "life-2.0", "memory": True,
                                 "seed_genomes": [{"memory_id": mid, "genome": got[0]["genome"]}]})
    ev = core.Evolution(cfg).run()
    ops = [c.operator for c in ev.final_population] + [h["operators"].get("memory", 0) for h in ev.history[:1]]
    assert ev.history[0]["operators"]["memory"] == round(0.25 * SMALL["population"])
    assert core.Evolution(core.Config.from_dict(cfg.to_dict())).run().digest() == ev.digest()
    memory.record_uses(None, "forage", cond, [{"memory_id": mid, "distance": 0.0}], None, 1.0)
    assert memory.stats()[mid] == (1, 0)
    w_fw = memory.retrieve("life-2.0", "forage", cond, failure_weighting=True)[0]["weight"]
    w_no = memory.retrieve("life-2.0", "forage", cond, failure_weighting=False)[0]["weight"]
    assert w_fw < w_no, "a failed transfer lowers the failure-weighted retrieval weight"


def test_benchmark_end_to_end_tiny(monkeypatch):
    monkeypatch.setattr(bench, "DEFAULTS", {"replicates": 2, "max_evals": 40, "population": 10, "train_seeds": 1,
                                            "calibration_n": 30})
    monkeypatch.setattr(suite, "TICKS", 60)
    monkeypatch.setattr(suite, "SCORING_SEEDS", 3)
    monkeypatch.setattr(bench, "_llm_reference", lambda *a, **k: None)
    from darwin import schedule
    with store.engine().begin() as c:
        eid = schedule.queue_benchmark("holdout", store.now()[:10], c)
    with store.engine().begin() as c:
        c.execute(store.experiments.update().where(store.experiments.c.id == eid).values(
            config=store.canon({"split": "holdout", "problems": ["H1"], **bench.DEFAULTS})))
    assert runner.claim_next() == eid
    runner.run_experiment(eid)
    with store.engine().connect() as c:
        row = dict(c.execute(sa.select(store.experiments).where(store.experiments.c.id == eid)).mappings().one())
        n = c.execute(sa.select(sa.func.count()).select_from(store.bench_results).where(
            store.bench_results.c.experiment_id == eid)).scalar()
    assert row["status"] == "completed"
    b = json.loads(row["summary"])["benchmark"]
    assert n == 2 * 5 and set(b["contestants"]) == set(bench.SEARCH)
    assert b["comparisons"]["darwin__vs__random"]["n"] == 2
    assert set(b["claims"]) == {"memory", "random", "hillclimb"}
    # benchmarks never write memory use statistics
    with store.engine().connect() as c:
        assert not c.execute(sa.select(sa.func.count()).select_from(store.memory_uses).where(
            store.memory_uses.c.experiment_id == eid)).scalar()
    # second run: controls must repeat exactly (determinism check)
    with store.engine().begin() as c:
        eid2 = schedule.queue_benchmark("holdout", store.now()[:10], c)
        c.execute(store.experiments.update().where(store.experiments.c.id == eid2).values(
            config=store.canon({"split": "holdout", "problems": ["H1"], **bench.DEFAULTS})))
    assert runner.claim_next() == eid2
    runner.run_experiment(eid2)
    with store.engine().connect() as c:
        b2 = json.loads(c.execute(sa.select(store.experiments.c.summary).where(
            store.experiments.c.id == eid2)).scalar())["benchmark"]
    assert b2["control_drift"]["checked"] and b2["control_drift"]["identical"]


def test_phase2_pages_render(client):
    for path in ("/darwin/intelligence", "/darwin/memory"):
        r = client.get(path)
        assert r.status_code == 200, path
    d = client.get("/darwin/api/benchmark").get_json()
    assert "history" in d and "standing" in d
    r = client.post("/darwin/api/benchmark/run", json={"split": "final"})
    assert r.status_code == 403


def test_scheduler_queues_practice_then_benchmark(monkeypatch):
    from datetime import datetime, timezone
    from darwin import schedule
    monkeypatch.setenv("DARWIN_SCHEDULER", "on")
    monkeypatch.setattr("darwin.web.ensure_worker", lambda: None)
    t = datetime(2031, 5, 4, 7, 0, tzinfo=timezone.utc)
    with store.engine().begin() as c:   # keep the test independent of today's real date
        c.execute(store.experiments.update().where(store.experiments.c.status == "queued").values(status="stopped"))
    monkeypatch.setattr(store, "now", lambda: "2031-05-04T07:00:00.000+00:00")
    schedule.tick(t)
    schedule.tick(t)   # idempotent within the day
    with store.engine().connect() as c:
        rows = c.execute(sa.select(store.experiments.c.source, store.experiments.c.kind).where(
            store.experiments.c.created_at >= "2031-05-04")).all()
    assert sorted(r[0] for r in rows) == ["benchmark", "practice", "practice", "practice"]
