"""Minimal Codestroller API client (session-cookie auth, submit, poll).

Darwin uses its own Codestroller account (DARWIN_CODESTROLLER_EMAIL /
DARWIN_CODESTROLLER_PASSWORD). It submits at most one audit at a time, and only
when Codestroller's shared queue is idle, so real users are never delayed.
Codestroller does not report token usage, so the cost of an audit is
ESTIMATED from its step count at the published model price.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request

BASE = os.environ.get("DARWIN_CODESTROLLER_URL", "https://app.codestroller.com").rstrip("/")
# claude-sonnet-5 list price (third-party listing, read 2026-10-16): $2 / $10 per million tokens.
# One agent step ~ 4k input tokens (screenshot + element list + prompt) and ~400 output tokens.
USD_PER_STEP = 4000 * 2.0 / 1e6 + 400 * 10.0 / 1e6
USD_PER_SUMMARY = 0.01
USD_PER_MOBILE_PAGE = 0.01
PRICE_NOTE = ("estimated: Codestroller does not report tokens; ~4k in / 400 out tokens per step at claude-sonnet-5 "
              "list price $2/$10 per MTok (third-party listing)")


class CodestrollerError(Exception):
    pass


class Client:
    def __init__(self, email=None, password=None, base=None):
        self.base = (base or BASE).rstrip("/")
        self.email = email or os.environ.get("DARWIN_CODESTROLLER_EMAIL", "")
        self.password = password or os.environ.get("DARWIN_CODESTROLLER_PASSWORD", "")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self._logged_in = False

    def configured(self):
        return bool(self.email and self.password)

    def _req(self, method, path, body=None, timeout=60):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=timeout) as r:
                txt = r.read().decode()
                return r.status, (json.loads(txt) if txt else {})
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode() or "{}")
            except Exception:
                payload = {}
            return e.code, payload

    def login(self):
        if not self.configured():
            raise CodestrollerError("DARWIN_CODESTROLLER_EMAIL / _PASSWORD are not set")
        st, d = self._req("POST", "/api/auth/login", {"email": self.email, "password": self.password})
        if st != 200:
            raise CodestrollerError(f"login failed ({st}): {d.get('error', '')}")
        self._logged_in = True

    def _authed(self, method, path, body=None):
        if not self._logged_in:
            self.login()
        st, d = self._req(method, path, body)
        if st == 401:
            self.login()
            st, d = self._req(method, path, body)
        return st, d

    def queue_idle(self):
        st, d = self._authed("GET", "/api/queue-status")
        if st != 200:
            return True
        return d.get("running", 0) + d.get("queued", 0) == 0

    def submit(self, url, persona, goal, max_steps, mobile):
        st, d = self._authed("POST", "/api/qa-jobs", {"url": url, "persona": persona, "goal": goal,
                                                      "maxSteps": int(max_steps), "mobileCheck": bool(mobile)})
        if st not in (200, 202) or not d.get("jobId"):
            raise CodestrollerError(f"submit failed ({st}): {d.get('error', '')}")
        return d["jobId"]

    def job(self, job_id):
        st, d = self._authed("GET", f"/api/qa-jobs/{job_id}")
        if st != 200:
            raise CodestrollerError(f"job fetch failed ({st})")
        return d

    def wait(self, job_id, heartbeat=None, timeout_s=1800, every=15):
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            j = self.job(job_id)
            if heartbeat:
                heartbeat(j)
            if j.get("status") in ("complete", "failed"):
                return j
            time.sleep(every)
        raise CodestrollerError(f"job {job_id} did not finish within {timeout_s}s")


def estimate_cost(job, mobile=False):
    """Steps x per-step estimate + report synthesis + one mobile pass (up to 3 screenshots, one call)."""
    steps = len(job.get("steps") or [])
    return round(steps * USD_PER_STEP + USD_PER_SUMMARY + (3 * USD_PER_MOBILE_PAGE if mobile else 0.0), 4)
