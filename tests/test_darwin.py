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
os.environ["DARWIN_POOL"] = "off"        # the tidal pool process is never spawned by tests

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
    from darwin.weblab.shop import bp as shop_bp
    app.register_blueprint(shop_bp)
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
    # the life-1.0 world is archived (the tidal pool replaced it): it still answers, but no longer advances
    assert d2["stats"]["tick"] == d["stats"]["tick"]


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


def test_scheduler_queues_cycle_practice_then_benchmark(monkeypatch):
    from datetime import datetime, timezone
    from darwin import curriculum, schedule
    monkeypatch.setenv("DARWIN_SCHEDULER", "on")
    monkeypatch.setattr("darwin.web.ensure_worker", lambda: None)
    t = datetime(2031, 5, 4, 9, 30, tzinfo=timezone.utc)          # slot starts 08:00
    with store.engine().begin() as c:
        c.execute(store.experiments.update().where(store.experiments.c.status == "queued").values(status="stopped"))
    monkeypatch.setattr(store, "now", lambda: "2031-05-04T09:30:00.000+00:00")
    schedule.tick(t)
    schedule.tick(t)   # idempotent within the slot
    with store.engine().connect() as c:
        rows = c.execute(sa.select(store.experiments.c.source, store.experiments.c.config).where(
            store.experiments.c.created_at >= "2031-05-04")).all()
    srcs = sorted(r[0] for r in rows)
    assert srcs.count("practice") == curriculum.PRACTICE_PER_CYCLE and srcs.count("benchmark") == 1
    assert any((json.loads(cfg) or {}).get("series") == 2 for src, cfg in rows if src == "benchmark")


# ── Phase 2b ─────────────────────────────────────────────────────────────
def test_fresh_problems_unique_and_deterministic():
    a, b = suite.fresh_problems(101), suite.fresh_problems(101)
    assert a == b and len({p["id"] for p in a}) == len(a)
    assert suite.fresh_problems(102)[0]["conditions"] != a[0]["conditions"]


def test_curriculum_plan_respects_leakage_guard():
    from darwin import curriculum
    plan = curriculum.plan(55)
    assert len(plan) == curriculum.PRACTICE_PER_CYCLE and plan[0][0] == "fixed"
    for kind, label, obj, cond in plan:
        near = suite.protected_near(obj, cond)
        assert near[1] >= suite.LEAK_DISTANCE


def test_memory_dedupe_and_retirement():
    cond = suite.get("T3")["conditions"]
    g = life.random_genomes(np.random.default_rng(9), 1, life.NEURAL)[0]
    m1, _ = memory.admit(None, None, "a", "life-2.0", "forage", cond, g, 1.0, {}, "test", "replicated")
    m2, why = memory.admit(None, None, "b", "life-2.0", "forage", cond, g + 1e-4, 1.0, {}, "test", "replicated")
    assert m1 and m2 is None and "duplicate" in why
    for _ in range(memory.RETIRE_MIN_USES):
        memory.record_uses(None, "forage", cond, [{"memory_id": m1, "distance": 0.0}], None, 1.0)
    retired = memory.consolidate()
    assert any(r["memory"] == store.fmt_mem(m1) for r in retired)
    assert all(e["memory_id"] != m1 for e in memory.retrieve("life-2.0", "forage", cond))


def test_learned_retrieval_trains_and_never_crashes():
    cond = suite.get("T6")["conditions"]
    g = life.random_genomes(np.random.default_rng(11), 1, life.NEURAL)[0]
    mid, _ = memory.admit(None, None, "c", "life-2.0", "forage", cond, g, 1.0, {}, "test", "robust")
    for i in range(memory.LEARN_MIN_ROWS):
        memory.record_uses(None, "forage", cond, [{"memory_id": mid, "distance": 0.05 * (i % 4)}],
                           mid if i % 3 == 0 else None, 1.0)
    info = memory.model_info()
    assert info["ready"] and 0.0 <= info["train_accuracy"] <= 1.0
    got = memory.retrieve("life-2.0", "forage", cond, mode="learned")
    assert got and got[0]["retrieval"] == "learned" and 0.0 <= got[0]["weight"] <= 1.0


def test_series2_cycle_end_to_end_tiny(monkeypatch):
    from darwin import bench2, schedule
    monkeypatch.setattr(bench2, "PARAMS", {"max_evals": 30, "population": 10, "train_seeds": 1})
    monkeypatch.setattr(suite, "TICKS", 60)
    monkeypatch.setattr(suite, "SCORING_SEEDS", 3)
    monkeypatch.setattr(suite, "FRESH_CALIBRATION_N", 20)
    monkeypatch.setitem(bench.DEFAULTS, "calibration_n", 20)
    monkeypatch.setattr(suite, "fresh_problems", lambda cid, n=2: [
        {**p, "scoring_seeds": p["scoring_seeds"][:3]} for p in suite.__dict__["_fp_orig"](cid, 2)])
    monkeypatch.setattr(suite, "anchors", lambda: suite.__dict__["_an_orig"]()[:1])
    monkeypatch.setattr(bench, "_llm_reference", lambda *a, **k: None)
    with store.engine().begin() as c:
        c.execute(store.experiments.update().where(store.experiments.c.status == "queued").values(status="stopped"))
        eid = schedule.queue_benchmark("cycle", store.now()[:10], c, series=2)
    assert runner.claim_next() == eid
    runner.run_experiment(eid)
    with store.engine().connect() as c:
        row = dict(c.execute(sa.select(store.experiments).where(store.experiments.c.id == eid)).mappings().one())
    assert row["status"] == "completed", row["stop_reason"]
    b = json.loads(row["summary"])["benchmark"]
    assert b["series"] == 2 and set(b["contestants"]) == set(bench2.SEARCH if hasattr(bench2, "SEARCH") else
                                                             ["random", "hillclimb", "darwin", "darwin_memory",
                                                              "darwin_memory_fw", "darwin_memory_learned"])
    assert b["comparisons"]["darwin__vs__random"]["n"] == 2 * suite.FRESH_REPLICATES
    assert set(b["claims"]) == {"memory", "learned", "random", "hillclimb"}
    assert bench2.history()[-1]["label"] == store.fmt_exp(eid)


suite._fp_orig = suite.fresh_problems
suite._an_orig = suite.anchors


# ── Web Lab ──────────────────────────────────────────────────────────────
from darwin.weblab import defects as WD, evolve as WE, judge as WJ, shop as WS, strategy as WST  # noqa: E402


def _shop_client():
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(WS.bp)
    return app.test_client()


def test_shop_specs_answer_keys_and_holdout_types():
    tr = WS.make_spec(5, "train")
    ho = WS.make_spec(6, "holdout")
    assert 3 <= len(tr["defects"]) <= 6 and not set(tr["defects"]) & set(WD.HOLDOUT_ONLY)
    assert set(ho["defects"]) & set(WD.HOLDOUT_ONLY)
    assert WS.make_spec(5, "train") == tr
    assert all(k["id"] in WD.DEFECTS for k in WS.answer_key(tr))


def test_shop_pages_hide_the_answer_key_and_log_coverage():
    spec = WS.make_spec(7, "train", n_defects=6)
    sid, tok = WS.create_instance(spec)
    c = _shop_client()
    B = f"/darwin/weblab/s/{tok}"
    page = c.get(B + "/").data.decode()
    for d in spec["defects"]:
        assert d not in page and WD.DEFECTS[d][0] not in page
    p = spec["products"][0]
    v = next(k for k, s in p["stock"].items() if s > 0)
    c.get(B + f"/p/{p['id']}")
    c.post(B + "/api/cart/add", json={"pid": p["id"], "variant": v, "qty": 1})
    c.get(B + "/search?q=" + p["name"].split()[0][:-1] + "q")
    c.get(B + "/checkout")
    inter = WS.interactions(sid)
    assert {"home", "product", "add", "checkout", "search"} <= set(inter["areas"])
    assert inter["safety"]["purchase_attempts"] == 0
    c.post(B + "/checkout", data={"email": "x"})
    assert WS.interactions(sid)["safety"]["purchase_attempts"] == 1


def test_defect_behaviours_differ_from_clean_shop():
    clean = dict(WS.make_spec(8, "train"), defects=[], fee=0.0, dead_link=None)
    bad = dict(clean, defects=["D03", "D05"])
    c = _shop_client()
    word = clean["products"][0]["name"].split()[0]
    typo = word[:-1] + ("x" if word[-1] != "x" else "y")
    outs = []
    for spec in (clean, bad):
        sid, tok = WS.create_instance(spec)
        outs.append(c.get(f"/darwin/weblab/s/{tok}/search?q={typo}").data.decode())
    assert "Showing results for" in outs[0] and "No results" in outs[1]


def test_score_rewards_finds_and_penalises_decoys_and_purchases():
    ans = [WD.card("D01"), WD.card("D03")]
    judged = {"issues": [{"text": "a", "severity": "bug"}, {"text": "b", "severity": "friction"}],
              "labels": [{"issue": 0, "label": "D01"}, {"issue": 1, "label": "decoy"}]}
    ok = WJ.score(ans, judged, {"areas": ["home", "add"], "safety": {}})
    assert ok["found"] == ["D01"] and ok["precision"] == 0.5 and ok["fitness"] > 0
    bad = WJ.score(ans, judged, {"areas": ["home"], "safety": {"purchase_attempts": 1}})
    assert bad["fitness"] == 0 and bad["safety"] == "purchase attempted"


def test_strategy_render_always_has_safety_rules():
    import random as _r
    rng = _r.Random(3)
    for _ in range(20):
        g = WST.random_genome(rng)
        g2, _ = WST.mutate(g, rng)
        assert WST.SAFETY in WST.render(g2)["goal_text"] and 2 <= len(g2["probes"])


class FakeCodestroller:
    """Browses the shop through the Flask test client and reports one real finding and one decoy complaint."""

    def __init__(self):
        self.c = _shop_client()
        self.jobs = {}

    def configured(self):
        return True

    def queue_idle(self):
        return True

    def submit(self, url, persona, goal, steps, mobile):
        path = url.split("://", 1)[1].split("/", 1)[1]
        base = "/" + path.rstrip("/")
        self.c.get(base + "/")
        self.c.get(base + "/cart")
        jid = f"job{len(self.jobs) + 1}"
        self.jobs[jid] = {"id": jid, "status": "complete",
                          "steps": [{"step": 1, "url": url, "narration": "looking", "action": {"type": "click"},
                                     "issues_found": [{"severity": "bug", "description": "nothing happened when I added"},
                                                      {"severity": "friction", "description": "the colours are odd"}]}],
                          "report": {"critical_bugs": [], "ux_friction": []}}
        return jid

    def wait(self, jid, heartbeat=None, **kw):
        return self.jobs[jid]


def test_weblab_generation_end_to_end(monkeypatch):
    def fake_call(system, user, max_tokens, purpose, experiment_id=None, temperature=None, model=None, timeout=60):
        first = user.split("PLANTED DEFECTS:\n", 1)[1].split()[0]
        return {"status": "ok", "text": json.dumps({"labels": [{"issue": 1, "label": first, "why": "match"},
                                                              {"issue": 2, "label": "decoy", "why": "taste"}]}),
                "stop": "end_turn", "usage": {"input_tokens": 100, "output_tokens": 50}, "usd": 0.0005, "latency": 1,
                "call_id": 1}
    monkeypatch.setattr("darwin.openlab._call", fake_call)
    monkeypatch.setattr(WE, "SHOPS_PER_GEN", 1)
    monkeypatch.setattr(WE, "preflight", lambda url, tries=3: True)
    fake = FakeCodestroller()
    for gen in (1, 2, 3):
        with store.engine().begin() as c:
            eid = c.execute(store.experiments.insert().values(
                created_at=store.now(), kind="weblab", lab="web", title=f"g{gen}", config=store.canon(
                    {"generation": gen, "holdout": gen == 3, "shops": 1}), seed=0, status="running", owner=True,
                requester="t", stop_requested=False, source="weblab")).inserted_primary_key[0]
        exp = dict(store.engine().connect().execute(
            sa.select(store.experiments).where(store.experiments.c.id == eid)).mappings().one())
        summ = WE.run(exp, lambda p: None, cl=fake)
        assert summ["generation"] == gen and summ["failed_audits"] == 0
    board = WE.leaderboard()
    assert any(b["kind"] == "evolved" for b in board) and any(b["label"] == "nielsen_prompt" for b in board)
    assert all(b["audits"] >= 1 for b in board)
    assert set(summ["claims"]) == {"vs_default", "vs_nielsen"}
    a = WE._audits(store.weblab_audits.c.status == "judged")[-1]
    assert a["score"]["found"] and a["score"]["decoy_hits"] == 1 and "home" in a["score"]["areas"]


def test_weblab_budget_pause(monkeypatch):
    monkeypatch.setattr(WE, "daily_cap", lambda: 0.0)
    with store.engine().begin() as c:
        eid = c.execute(store.experiments.insert().values(
            created_at=store.now(), kind="weblab", lab="web", title="gb", config=store.canon({"generation": 9, "shops": 1}),
            seed=0, status="running", owner=True, requester="t", stop_requested=False, source="weblab")).inserted_primary_key[0]
    exp = dict(store.engine().connect().execute(sa.select(store.experiments).where(store.experiments.c.id == eid)).mappings().one())
    out = WE.run(exp, lambda p: None, cl=FakeCodestroller())
    assert out.get("paused")


def test_weblab_unusable_audits_are_invalid_not_scored():
    down = {"status": "complete", "steps": [{"narration": "the page says Application failed to respond",
                                             "issues_found": [{"description": "site is completely down"}]}]}
    assert WE.unusable(down, {"events": 3})
    ok = {"status": "complete", "steps": [{"narration": "browsing"}] * 5}
    assert not WE.unusable(ok, {"events": 12})


def test_weblab_pages_render(client):
    import darwin.weblab.pages  # noqa: F401
    for path in ("/darwin/lab/web",):
        assert client.get(path).status_code == 200
    d = client.get("/darwin/api/weblab").get_json()
    assert "leaderboard" in d and "curve" in d
    r = client.post("/darwin/api/weblab/sample-shop")
    assert r.status_code == 200 and "answer_key" not in r.get_json()


def test_weblab_shop2_catalog_is_coherent():
    from darwin.weblab import shop as SH
    for seed in range(40):
        for split in ("train", "holdout"):
            spec = SH.make_spec(seed, split)
            assert spec["version"] == SH.SHOP_VERSION
            names = [p["name"] for p in spec["products"]]
            assert len(names) == len(set(names))
            for p in spec["products"]:
                kinds = SH.DOMAINS[spec["domain"]]["cats"][p["cat"]]
                assert any(p["name"].endswith(k[0]) and set(p["stock"]) == set(k[2][1]) for k in kinds)
                assert p["icon"] and any(v == 0 for v in p["stock"].values())


def test_pool_development_and_mutation():
    from darwin import pool as P
    rng = np.random.default_rng(0)
    cells = P.develop([[P.PHOTO, 0, 0, 1], [P.MOUTH, 0, 0, 2], [P.EYE, 1, 1, 1], [P.FLAG, 0, 2, 1]])
    assert len(cells) == 5 and len({(x, y) for x, y, _ in cells}) == 5
    n, cnt, expo = P.phenotype(cells)
    assert n == 5 and cnt[P.MOUTH] == 2 and 0 < expo <= 1
    g = P.new_genome(rng)
    lens = set()
    for _ in range(300):
        g = P.mutate(g, rng)
        lens.add(len(g["body"]))
        assert len(P.develop(g["body"])) <= P.MAX_CELLS
    assert max(lens) > 1                       # duplication/insertion can grow genomes
    k = P.crossover(g, P.new_genome(rng), rng)
    assert k["brain"].shape == (P.NW,)


def test_pool_runs_checkpoints_and_serves(client):
    from darwin import pool as P
    p = P.Pool(1, 7)
    for _ in range(P.STATS_EVERY):
        p.step()
    assert p.last_stats and p.last_stats["population"] > 0 and p.births > P.START
    q = P.from_blob(P.to_blob(p))
    assert q.tick == p.tick and int(q.alive.sum()) == int(p.alive.sum())
    q.step()
    P.write_live(p, [p.frame()])
    d = client.get("/darwin/api/pool").get_json()
    assert d["tick"] == p.tick and d["frames"][0]["c"] and str(d["frames"][0]["c"][0][4]) in d["plans"]
    assert client.get("/darwin/pool").status_code == 200
    assert isinstance(client.get("/darwin/api/pool/history").get_json(), list)
