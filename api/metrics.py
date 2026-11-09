"""
Observability & Prometheus-compatible Metrics Registry.
Collects real-time runtime counters, latency distributions, and scheme discovery statistics.
"""

from __future__ import annotations
import time
from typing import Dict, Any
from collections import defaultdict
import threading


class MetricsRegistry:
    """
    Lightweight, thread-safe Prometheus & system metrics registry.
    Can be scraped by Prometheus server or consumed via JSON telemetry.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.start_time = time.time()
        self.request_count = defaultdict(int)  # (method, endpoint, status_code) -> count
        self.request_durations = defaultdict(list)  # endpoint -> list of latency ms (sliding window)
        self.error_count = defaultdict(int)  # error_type -> count
        self.active_requests = 0
        self.schemes_evaluated_count = 0
        self.gst_uploads_processed = 0

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            # Group paths to avoid unbounded cardinality
            normalized_path = self._normalize_path(path)
            key = f'{method}_{normalized_path}_{status_code}'
            self.request_count[key] += 1
            durations = self.request_durations[normalized_path]
            durations.append(duration_ms)
            if len(durations) > 200:
                del durations[0]

    def record_scheme_evaluation(self, count: int = 1) -> None:
        with self._lock:
            self.schemes_evaluated_count += count

    def record_gst_upload(self) -> None:
        with self._lock:
            self.gst_uploads_processed += 1

    def _normalize_path(self, path: str) -> str:
        if path.startswith("/api/schemes/") and len(path.split("/")) > 3:
            return "/api/schemes/:id"
        return path

    def get_summary_json(self) -> Dict[str, Any]:
        with self._lock:
            uptime = time.time() - self.start_time
            total_requests = sum(self.request_count.values())
            
            latencies = {}
            for path, durs in self.request_durations.items():
                if durs:
                    latencies[path] = {
                        "p50_ms": round(sorted(durs)[len(durs) // 2], 2),
                        "p95_ms": round(sorted(durs)[int(len(durs) * 0.95)], 2),
                        "avg_ms": round(sum(durs) / len(durs), 2),
                        "count": len(durs),
                    }
                    
            return {
                "uptime_seconds": round(uptime, 2),
                "total_requests": total_requests,
                "requests_breakdown": dict(self.request_count),
                "latency_by_endpoint": latencies,
                "schemes_evaluated_total": self.schemes_evaluated_count,
                "gst_uploads_total": self.gst_uploads_processed,
            }

    def export_prometheus_text(self) -> str:
        """
        Exports standard Prometheus exposition format (text/plain; version=0.0.4).
        """
        with self._lock:
            lines = [
                "# HELP gov_schemes_uptime_seconds Total application uptime in seconds",
                "# TYPE gov_schemes_uptime_seconds gauge",
                f"gov_schemes_uptime_seconds {round(time.time() - self.start_time, 2)}",
                "",
                "# HELP gov_schemes_requests_total Total HTTP requests handled",
                "# TYPE gov_schemes_requests_total counter",
            ]
            for key, count in self.request_count.items():
                parts = key.split("_")
                method = parts[0]
                status = parts[-1]
                path = "_".join(parts[1:-1])
                lines.append(f'gov_schemes_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')
            
            lines.extend([
                "",
                "# HELP gov_schemes_evaluated_total Total candidate scheme evaluations performed",
                "# TYPE gov_schemes_evaluated_total counter",
                f"gov_schemes_evaluated_total {self.schemes_evaluated_count}",
                "",
                "# HELP gov_schemes_gst_uploads_total Total GST certificates ingested",
                "# TYPE gov_schemes_gst_uploads_total counter",
                f"gov_schemes_gst_uploads_total {self.gst_uploads_processed}",
                ""
            ])
            return "\n".join(lines)


# Global singleton metrics collector
metrics = MetricsRegistry()
