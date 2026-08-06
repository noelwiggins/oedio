"""oedio ingestion queue — the Forge Queue pattern applied to source
ingestion instead of AI translation. Jobs run sequentially in a background
thread on the Railway service itself, independent of any chat session's
tool budget. Each completed job is committed and pushed to GitHub
automatically, so progress is never lost even if nobody is watching.

Runs against a FRESH clone in scratch space rather than the deployed app's
own directory, since Railway's build output is typically a source snapshot
without .git metadata -- this works regardless of how the running
container was built.

Job shape: {"platform": "loc"|"ia"|"ndl", "source": "<item id or url>",
            "slug": "<component slug>", "start": 1, "end": null,
            "label": "<human-readable name for logs>"}

Usage from app.py:
    from ingest_queue import queue_jobs, get_status
    queue_jobs([...])   # starts the background thread if not already running
    get_status()        # current progress
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback

WORK_DIR = "/tmp/oedio-ingest-work"
REPO_URL_TEMPLATE = "https://noelwiggins:{token}@github.com/noelwiggins/oedio.git"

_state = {
    "running": False,
    "queue": [],
    "current": None,
    "done": [],
    "failed": [],
    "started_at": None,
    "log": [],
}
_lock = threading.Lock()


def _log(msg):
    print(f"[ingest_queue] {msg}")
    with _lock:
        _state["log"].append(msg)
        _state["log"] = _state["log"][-200:]  # keep it bounded


def _run(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def _ensure_repo():
    """Clone once; on later jobs just pull to stay current."""
    token = os.environ.get("GITHUB_PUSH_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_PUSH_TOKEN not set")
    remote = REPO_URL_TEMPLATE.format(token=token)
    if not os.path.isdir(os.path.join(WORK_DIR, ".git")):
        if os.path.isdir(WORK_DIR):
            shutil.rmtree(WORK_DIR)
        _log("cloning fresh working copy")
        _run(["git", "clone", "--depth", "1", remote, WORK_DIR])
        _run(["git", "config", "user.email", "noel@harmonyball.com"], cwd=WORK_DIR)
        _run(["git", "config", "user.name", "Noel Wiggins"], cwd=WORK_DIR)
    else:
        _run(["git", "pull", "--no-rebase", remote, "main"], cwd=WORK_DIR, check=False)
    return remote


def _git_commit_and_push(message, remote):
    diff = _run(["git", "diff", "--stat"], cwd=WORK_DIR, check=False)
    _run(["git", "add", "-A"], cwd=WORK_DIR)
    staged = _run(["git", "diff", "--cached", "--stat"], cwd=WORK_DIR, check=False)
    if not staged.stdout.strip():
        return False
    _run(["git", "commit", "-m", message], cwd=WORK_DIR)
    for attempt in range(3):
        r = subprocess.run(["git", "push", remote, "HEAD:main"], cwd=WORK_DIR,
                            capture_output=True, text=True)
        if r.returncode == 0:
            return True
        _run(["git", "pull", "--no-rebase", remote, "main"], cwd=WORK_DIR, check=False)
        time.sleep(5)
    return False


def _run_job(job, remote):
    sys.path.insert(0, os.path.join(WORK_DIR, "scripts"))
    for mod in ("ingest_loc", "ingest_ia", "ingest_ndl"):
        sys.modules.pop(mod, None)  # force fresh import so BASE/__file__ resolve into this clone
    os.chdir(WORK_DIR)  # ingest_loc.py writes relative to cwd, not a BASE var
    platform = job["platform"]
    if platform == "loc":
        import ingest_loc as m
    elif platform == "ia":
        import ingest_ia as m
    elif platform == "ndl":
        import ingest_ndl as m
    else:
        raise ValueError(f"unknown platform: {platform}")
    m.main(job["source"], job["slug"], job.get("start", 1), job.get("end"))


def _worker():
    with _lock:
        _state["running"] = True
        _state["started_at"] = time.time()
    try:
        remote = _ensure_repo()
    except Exception as e:
        _log(f"FATAL: could not set up repo: {e}")
        with _lock:
            _state["running"] = False
        return
    while True:
        with _lock:
            if not _state["queue"]:
                _state["running"] = False
                _state["current"] = None
                break
            job = _state["queue"].pop(0)
            _state["current"] = job
        label = job.get("label", job["slug"])
        try:
            _log(f"running: {label}")
            _run(["git", "pull", "--no-rebase", remote, "main"], cwd=WORK_DIR, check=False)
            _run_job(job, remote)
            pushed = _git_commit_and_push(f"Forge queue: {label}", remote)
            with _lock:
                _state["done"].append({"label": label, "slug": job["slug"], "pushed": pushed})
            _log(f"done: {label} (pushed={pushed})")
        except Exception as e:
            tb = traceback.format_exc()
            _log(f"FAILED: {label}: {e}")
            print(tb)
            with _lock:
                _state["failed"].append({"label": label, "slug": job["slug"], "error": str(e)})
        time.sleep(3)  # be polite to source servers between jobs


def queue_jobs(jobs):
    with _lock:
        _state["queue"].extend(jobs)
        already_running = _state["running"]
    if not already_running:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    return {"queued": len(jobs), "already_running": already_running}


def get_status():
    with _lock:
        return {
            "running": _state["running"],
            "queue_remaining": len(_state["queue"]),
            "current": _state["current"],
            "done": list(_state["done"]),
            "failed": list(_state["failed"]),
            "log_tail": _state["log"][-15:],
        }
