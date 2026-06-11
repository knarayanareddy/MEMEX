"""
SLO measurement and alerting for MEMEX.

Surfaces p50/p95/p99 latencies and SLO violations via the
/api/stats endpoint and structured logs.

SLO thresholds loaded from Addendum F (slos.toml).
"""

from __future__ import annotations

import time
from typing import Any

from ..config.settings import load_slos
from ..observability.metrics import get_metrics
from ..observability.logging import get_logger

logger = get_logger("observability.slos")


class SLOMonitor:
    """Monitors and reports SLO compliance.

    Reads SLO definitions from Addendum F (slos.toml).
    Checks metric collector percentiles against alert thresholds.
    Logs SLO violations as structured warnings.
    """

    def __init__(self) -> None:
        self._slos = load_slos()
        self._metrics = get_metrics()

    def check_all(self) -> dict[str, Any]:
        """Check all SLOs and return compliance report.

        Returns:
            Dict with per-SLO status (pass/fail) and current values.
        """
        results: dict[str, Any] = {
            "all_pass": True,
            "checks": {},
        }

        # Latency SLOs: check histogram percentiles
        latency_slos = {
            "slo_002_fts_latency": "fts_search_ms",
            "slo_003_vector_latency": "vector_search_ms",
            "slo_004_hybrid_latency": "hybrid_retrieval_ms",
            "slo_010_forget_latency": "forget_doc_ms",
            "slo_011_api_latency": "api_request_ms",
        }

        for slo_key, metric_name in latency_slos.items():
            slo_def = self._slos.get(slo_key, {})
            if not slo_def:
                continue

            target = slo_def.get("target", float("inf"))
            alert = slo_def.get("alert_threshold", float("inf"))

            p95 = self._metrics.get_percentile(metric_name, 95)
            p50 = self._metrics.get_percentile(metric_name, 50)

            passed = p95 <= alert if p95 > 0 else True  # No data = pass

            results["checks"][slo_key] = {
                "metric": metric_name,
                "p50_ms": round(p50, 2),
                "p95_ms": round(p95, 2),
                "target_ms": target,
                "alert_threshold_ms": alert,
                "status": "PASS" if passed else "VIOLATION",
            }

            if not passed:
                results["all_pass"] = False
                logger.warning(
                    "slo_violation",
                    slo=slo_key,
                    p95_ms=round(p95, 2),
                    target_ms=target,
                    alert_ms=alert,
                )

        # Throughput SLOs
        throughput_slos = {
            "slo_008_embed_throughput": {
                "metric": "embed_latency_ms",
                "check": lambda p50: p50 > 0 and (60000 / p50) < 10,  # 10 chunks/min
            },
        }

        for slo_key, config in throughput_slos.items():
            slo_def = self._slos.get(slo_key, {})
            p50 = self._metrics.get_percentile(config["metric"], 50)
            violated = config["check"](p50)

            results["checks"][slo_key] = {
                "metric": config["metric"],
                "p50_ms": round(p50, 2),
                "status": "VIOLATION" if violated else "PASS",
            }
            if violated:
                results["all_pass"] = False

        return results

    def get_dashboard(self) -> dict[str, Any]:
        """Get a full SLO dashboard with metrics snapshot."""
        slo_results = self.check_all()
        metrics_snapshot = self._metrics.snapshot()

        return {
            "slo_compliance": slo_results,
            "metrics": metrics_snapshot,
        }


class SLOTimer:
    """Context manager that records operation latency for SLO tracking.

    Usage:
        with SLOTimer("fts_search_ms") as t:
            # ... do search ...
        # Duration is automatically recorded in metrics collector
    """

    def __init__(self, metric_name: str):
        self._metric_name = metric_name
        self._metrics = get_metrics()
        self._start: float = 0

    def __enter__(self) -> "SLOTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        self._metrics.observe(self._metric_name, duration_ms)
