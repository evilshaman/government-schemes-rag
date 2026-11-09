"""
Production Smoke Verification Script.
Executes an end-to-end audit verifying:
- Configuration and storage paths
- SQLite WAL mode and multi-threaded concurrency
- OWASP security headers and distributed request tracing
- Kubernetes liveness (/health/live) and readiness (/health/ready) probes
- Prometheus / JSON metrics telemetry
- RFC 7807 Problem Details error handling
- Live end-to-end Scheme Deliberation engine execution
"""

from __future__ import annotations
import os
import sys
import time
import threading
from typing import List, Dict, Any
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import settings
from api.main import app
from knowledge_base.storage import SchemeKnowledgeStore


class ProductionVerifier:
    def __init__(self):
        self.client = TestClient(app)
        self.store = SchemeKnowledgeStore()
        self.results: List[Dict[str, Any]] = []

    def record(self, check_name: str, passed: bool, detail: str) -> None:
        self.results.append({
            "check": check_name,
            "passed": passed,
            "detail": detail,
        })
        status_symbol = "[PASS]" if passed else "[FAIL]"
        print(f" {status_symbol} {check_name:<40} : {detail}")

    def verify_configuration(self) -> None:
        print("\n--- 1. Configuration & Storage Paths ---")
        self.record("Environment Loading", settings.ENVIRONMENT is not None, f"Environment: {settings.ENVIRONMENT}")
        self.record(
            "SQLite Knowledge Store DB Exists",
            os.path.exists(settings.resolved_db_path),
            f"Path: {settings.resolved_db_path} ({os.path.getsize(settings.resolved_db_path)} bytes)",
        )
        self.record(
            "Vector Index File Exists",
            os.path.exists(settings.resolved_vector_path),
            f"Path: {settings.resolved_vector_path} ({os.path.getsize(settings.resolved_vector_path)} bytes)",
        )

    def verify_sqlite_wal_and_concurrency(self) -> None:
        print("\n--- 2. SQLite WAL Concurrency Tuning ---")
        with self.store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal = cursor.fetchone()[0]
            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]

        wal_ok = journal.lower() == "wal"
        self.record("SQLite WAL Journal Mode", wal_ok, f"journal_mode={journal}")
        self.record("SQLite Busy Timeout", busy_timeout >= 5000, f"busy_timeout={busy_timeout}ms")

        # 20 concurrent threads
        errors = []
        def concurrent_reader(idx: int):
            try:
                schemes = self.store.list_schemes(limit=5)
                if not schemes:
                    errors.append(f"T{idx}: Empty result")
            except Exception as e:
                errors.append(f"T{idx}: {e}")

        threads = [threading.Thread(target=concurrent_reader, args=(i,)) for i in range(20)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.record(
            "Concurrent Multi-Thread Reads (20 threads)",
            len(errors) == 0,
            f"Executed in {elapsed_ms:.1f}ms without SQLite lock errors",
        )

    def verify_security_and_tracing(self) -> None:
        print("\n--- 3. OWASP Security Headers & Tracing ---")
        custom_trace_id = "test-prod-smoke-trace-101"
        res = self.client.get("/health", headers={"X-Request-ID": custom_trace_id})
        
        has_nosniff = res.headers.get("x-content-type-options") == "nosniff"
        has_frame_deny = res.headers.get("x-frame-options") == "DENY"
        has_xss = res.headers.get("x-xss-protection") == "1; mode=block"
        has_referrer = res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        has_timing = "x-process-time-ms" in res.headers
        trace_propagated = res.headers.get("x-request-id") == custom_trace_id

        self.record("OWASP Security Headers", has_nosniff and has_frame_deny and has_xss and has_referrer, "nosniff, DENY, 1; mode=block, strict-origin")
        self.record("Distributed X-Request-ID Propagation", trace_propagated, f"Trace ID: {res.headers.get('x-request-id')}")
        self.record("Execution Timing (X-Process-Time-Ms)", has_timing, f"Latency: {res.headers.get('x-process-time-ms')}")

    def verify_kubernetes_probes_and_metrics(self) -> None:
        print("\n--- 4. Kubernetes Probes & Prometheus Observability ---")
        res_live = self.client.get("/health/live")
        self.record("Liveness Probe (/health/live)", res_live.status_code == 200, f"Status: {res_live.json().get('status')}")

        res_ready = self.client.get("/health/ready")
        self.record("Readiness Probe (/health/ready)", res_ready.status_code == 200, f"Schemes ready: {res_ready.json().get('schemes_ready')}")

        res_metrics = self.client.get("/metrics")
        self.record("Prometheus Text Metrics (/metrics)", "gov_schemes_uptime_seconds" in res_metrics.text, f"Content-Type: {res_metrics.headers.get('content-type')}")

        res_json = self.client.get("/metrics?format=json")
        self.record("JSON Telemetry Metrics", "total_requests" in res_json.json(), f"Total requests logged: {res_json.json().get('total_requests')}")

    def verify_rfc7807_problem_details(self) -> None:
        print("\n--- 5. RFC 7807 Error Handling ---")
        res_404 = self.client.get("/api/invalid-resource-404")
        is_rfc7807 = (
            res_404.status_code == 404
            and res_404.headers.get("content-type") == "application/problem+json"
            and "title" in res_404.json()
            and "request_id" in res_404.json()
        )
        self.record("RFC 7807 404 Not Found Problem Details", is_rfc7807, f"Title: {res_404.json().get('title')}")

        res_422 = self.client.post("/api/schemes/deliberate", json={"profile": {}})
        is_rfc422 = (
            res_422.status_code == 422
            and res_422.headers.get("content-type") == "application/problem+json"
            and "invalid_params" in res_422.json()
        )
        self.record("RFC 7807 422 Validation Problem Details", is_rfc422, f"Invalid params logged: {len(res_422.json().get('invalid_params', []))}")

    def verify_live_scheme_deliberation(self) -> None:
        print("\n--- 6. Live End-to-End Deliberation Engine Smoke Check ---")
        # Load sample profile #1
        res_sample = self.client.post("/api/sample-profile/1")
        sample_profile = res_sample.json()
        
        t0 = time.perf_counter()
        deliberate_payload = {
            "profile": sample_profile,
            "query": "Seed capital and robotics automation expansion",
            "top_k": 3,
            "apply_hard_filters": True,
        }
        res_delib = self.client.post("/api/schemes/deliberate", json=deliberate_payload)
        delib_time_ms = (time.perf_counter() - t0) * 1000
        
        ok = res_delib.status_code == 200
        data = res_delib.json() if ok else {}
        schemes_evaluated = len(data.get("top_recommendations", []))

        self.record(
            "End-to-End Hybrid RAG & Deliberation Pipeline",
            ok and schemes_evaluated > 0,
            f"Evaluated {schemes_evaluated} schemes in {delib_time_ms:.1f}ms for '{sample_profile.get('legal_name')}'",
        )

    def run_all(self) -> int:
        print("================================================================================")
        print("  GOVERNMENT SCHEMES DISCOVERY PLATFORM - END-TO-END PRODUCTION VERIFICATION   ")
        print("================================================================================")
        
        self.verify_configuration()
        self.verify_sqlite_wal_and_concurrency()
        self.verify_security_and_tracing()
        self.verify_kubernetes_probes_and_metrics()
        self.verify_rfc7807_problem_details()
        self.verify_live_scheme_deliberation()

        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed

        print("\n================================================================================")
        print(f"  VERIFICATION AUDIT COMPLETE: {passed}/{total} CHECKS PASSED ({failed} FAILED)")
        print("================================================================================")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    verifier = ProductionVerifier()
    sys.exit(verifier.run_all())
