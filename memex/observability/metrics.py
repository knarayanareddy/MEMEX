"""
Local metrics collector for MEMEX.

Tracks counters, gauges, and histograms for SLO reporting.
All metrics are local-only — no external telemetry.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class MetricEntry:
    """A single metric measurement."""
    name: str
    value: float
    timestamp: float


class MetricsCollector:
    """Thread-safe local metrics collector."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: float = 1.0) -> None:
        """Increment a counter."""
        with self._lock:
            self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        """Record a histogram observation."""
        with self._lock:
            self._histograms[name].append(value)
            # Keep last 1000 observations
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]

    def timer(self, name: str) -> "_TimerContext":
        """Get a timer context manager."""
        return _TimerContext(self, name)

    def get_counter(self, name: str) -> float:
        """Get a counter value."""
        with self._lock:
            return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float:
        """Get a gauge value."""
        with self._lock:
            return self._gauges.get(name, 0)

    def get_percentile(self, name: str, percentile: float) -> float:
        """Get a histogram percentile."""
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return 0.0
            sorted_values = sorted(values)
            idx = int(len(sorted_values) * percentile / 100)
            return sorted_values[min(idx, len(sorted_values) - 1)]

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of all metrics."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    name: {
                        "count": len(values),
                        "p50": self._percentile(values, 50),
                        "p95": self._percentile(values, 95),
                        "p99": self._percentile(values, 99),
                    }
                    for name, values in self._histograms.items()
                },
            }

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = int(len(sorted_v) * pct / 100)
        return sorted_v[min(idx, len(sorted_v) - 1)]


class _TimerContext:
    """Timer context manager for measuring durations."""

    def __init__(self, collector: MetricsCollector, name: str):
        self._collector = collector
        self._name = name
        self._start: float = 0

    def __enter__(self) -> "_TimerContext":
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        self._collector.observe(self._name, duration_ms)


# Global metrics instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
