"""Cost accounting (Brief s.21-23 and the mandatory LLM token section).

Two kinds of cost are kept strictly apart:

* ESTIMATED compute: CPU seconds and memory-time priced at the hosting
  provider's published usage rate. Railway does not bill per experiment, so
  these are estimates of the marginal resource use, never invoices.
* BILLED (provider-reported) LLM usage: token counts come from the API
  response; dollars are computed from the price table below, which is stored
  alongside every call so historical costs stay reproducible if prices change.
"""
from __future__ import annotations

import os
import resource
import time

# Railway "Resource usage pricing" for standard container services
# (docs.railway.com/pricing/plans, read 2026-10-13):
#   vCPU  $20 / vCPU / month  = $0.000463 per vCPU-minute
#   RAM   $10 / GB / month    = $0.000231 per GB-minute
COMPUTE_RATES = {
    "provider": "Railway",
    "source": "https://docs.railway.com/pricing/plans",
    "read_on": "2026-10-13",
    "usd_per_vcpu_second": 0.000463 / 60,
    "usd_per_gb_second": 0.000231 / 60,
    "watts_per_vcpu_estimate": 10.0,   # rough server draw per busy vCPU, for the electricity estimate
}

# Anthropic list prices, USD per million tokens. Stored with every call.
LLM_PRICES = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "cache_write": 1.25, "cache_read": 0.10},
}
LLM_PRICES_NOTE = "List prices as configured in darwin/costs.py; confirm against the provider's pricing page."

BUDGET_PRESETS = [0.10, 1.0, 10.0, 100.0, 1000.0]

# Hard caps for experiments started without the owner passphrase.
PUBLIC_LIMITS = {
    "max_cpu_s": 45.0,            # per experiment
    "per_ip_per_hour": 3,
    "daily_cpu_s": 1800.0,        # all public experiments combined, per UTC day
    "max_queue": 4,
    "max_population": 60,
    "max_generations": 60,
}
OWNER_LIMITS = {"max_cpu_s": 3600.0, "max_population": 200, "max_generations": 400}


def compute_usd(cpu_s: float, rss_gb: float = 0.0, wall_s: float = 0.0) -> float:
    return (cpu_s * COMPUTE_RATES["usd_per_vcpu_second"]
            + rss_gb * wall_s * COMPUTE_RATES["usd_per_gb_second"])


def electricity_kwh(cpu_s: float) -> float:
    return cpu_s * COMPUTE_RATES["watts_per_vcpu_estimate"] / 3600.0 / 1000.0


def llm_usd(model: str, usage: dict) -> float:
    p = LLM_PRICES.get(model)
    if not p:
        return 0.0
    return (usage.get("input_tokens", 0) * p["input"]
            + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1e6


class Meter:
    """Measures this process's CPU and wall time from a starting point."""

    def __init__(self):
        self.cpu0 = time.process_time()
        self.wall0 = time.time()
        self.sim_steps = 0
        self.evaluations = 0
        self.candidates = 0

    def cpu_s(self) -> float:
        return time.process_time() - self.cpu0

    def wall_s(self) -> float:
        return time.time() - self.wall0

    @staticmethod
    def rss_gb() -> float:
        # ru_maxrss is KB on Linux
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024

    def snapshot(self) -> dict:
        cpu, wall, rss = self.cpu_s(), self.wall_s(), self.rss_gb()
        return {
            "cpu_s": round(cpu, 3),
            "wall_s": round(wall, 3),
            "peak_rss_gb": round(rss, 3),
            "sim_steps": int(self.sim_steps),
            "evaluations": int(self.evaluations),
            "candidates": int(self.candidates),
            "compute_usd_estimated": round(compute_usd(cpu, rss, wall), 8),
            "electricity_kwh_estimated": round(electricity_kwh(cpu), 9),
            "llm_usd_billed": 0.0,
            "rates": {k: COMPUTE_RATES[k] for k in ("provider", "source", "read_on")},
        }
