"""
Production Readiness & Resilience Test Suite.
Verifies:
1. Pydantic-settings configuration loading & resolution.
2. SQLite Write-Ahead Logging (WAL) mode & multi-threaded concurrency.
3. OWASP Security headers, X-Request-ID tracing, and execution timing.
4. Kubernetes Liveness (/health/live) and Readiness (/health/ready) probes.
5. RFC 7807 Problem Details compliant error handling.
6. Prometheus & JSON Metrics Registry endpoints.
7. Gunicorn configuration and Kubernetes manifests syntax.
"""

import os
import sys
import unittest
import threading
import yaml
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import Settings, settings
from api.main import app
from knowledge_base.storage import SchemeKnowledgeStore
from api.metrics import metrics


class TestProductionReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.store = SchemeKnowledgeStore()

    # 1. Configuration & Settings Tests
    def test_settings_and_defaults(self):
        self.assertIsNotNone(settings.PROJECT_NAME)
        self.assertIsNotNone(settings.VERSION)
        self.assertTrue(os.path.exists(settings.resolved_db_path))
        self.assertTrue(os.path.exists(settings.resolved_vector_path))

        # Test CORS parsing
        custom_settings = Settings(CORS_ORIGINS="https://portal.gov.in, https://msme.gov.in")
        self.assertEqual(custom_settings.CORS_ORIGINS, ["https://portal.gov.in", "https://msme.gov.in"])

    # 2. SQLite WAL Mode & Concurrency
    def test_sqlite_wal_mode_and_concurrency(self):
        with self.store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")

            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]
            self.assertGreaterEqual(busy_timeout, 5000)

        # Multi-threaded concurrency read test
        errors = []

        def worker(thread_idx: int):
            try:
                schemes = self.store.list_schemes(limit=10)
                if not schemes:
                    errors.append(f"Thread {thread_idx} found no schemes")
            except Exception as e:
                errors.append(f"Thread {thread_idx} failed: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors occurred: {errors}")

    # 3. Security Headers & Request Tracing Middleware
    def test_security_headers_and_tracing(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)

        # OWASP Security Headers
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(res.headers.get("x-frame-options"), "DENY")
        self.assertEqual(res.headers.get("x-xss-protection"), "1; mode=block")
        self.assertEqual(res.headers.get("referrer-policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", res.headers.get("permissions-policy", ""))

        # Tracing & Timing Headers
        self.assertIn("x-request-id", res.headers)
        self.assertIn("x-process-time-ms", res.headers)
        self.assertTrue(res.headers["x-process-time-ms"].endswith("ms"))

    def test_custom_request_id_propagation(self):
        custom_id = "trace-uuid-prod-987654321"
        res = self.client.get("/health", headers={"X-Request-ID": custom_id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("x-request-id"), custom_id)

    # 4. Kubernetes Probes (/health/live, /health/ready, /health)
    def test_kubernetes_probes(self):
        # Liveness probe
        res_live = self.client.get("/health/live")
        self.assertEqual(res_live.status_code, 200)
        self.assertEqual(res_live.json().get("status"), "alive")

        # Readiness probe
        res_ready = self.client.get("/health/ready")
        self.assertEqual(res_ready.status_code, 200)
        self.assertEqual(res_ready.json().get("status"), "ready")
        self.assertGreater(res_ready.json().get("schemes_ready", 0), 0)

        # Full health status
        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        data = res_health.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertGreater(data["knowledge_base"]["total_schemes"], 0)

    # 5. Metrics & Telemetry Endpoint
    def test_metrics_telemetry(self):
        # Plaintext Prometheus format
        res_prom = self.client.get("/metrics")
        self.assertEqual(res_prom.status_code, 200)
        self.assertIn("text/plain", res_prom.headers.get("content-type", ""))
        self.assertIn("gov_schemes_uptime_seconds", res_prom.text)
        self.assertIn("gov_schemes_requests_total", res_prom.text)

        # JSON format via query param
        res_json = self.client.get("/metrics?format=json")
        self.assertEqual(res_json.status_code, 200)
        data = res_json.json()
        self.assertIn("uptime_seconds", data)
        self.assertIn("total_requests", data)
        self.assertGreaterEqual(data["total_requests"], 1)

    # 6. RFC 7807 Problem Details Error Formatting
    def test_rfc7807_not_found_handling(self):
        res = self.client.get("/api/non-existent-endpoint-xyz")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.headers.get("content-type"), "application/problem+json")
        data = res.json()
        self.assertEqual(data.get("status"), 404)
        self.assertEqual(data.get("title"), "Resource Not Found")
        self.assertIn("request_id", data)
        self.assertIn("timestamp", data)
        self.assertEqual(data.get("instance"), "/api/non-existent-endpoint-xyz")

    def test_rfc7807_validation_error_handling(self):
        # Invalid payload missing required BusinessProfile fields
        res = self.client.post("/api/schemes/deliberate", json={"profile": {"legal_name": ""}})
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.headers.get("content-type"), "application/problem+json")
        data = res.json()
        self.assertEqual(data.get("status"), 422)
        self.assertEqual(data.get("title"), "Validation Error")
        self.assertIn("invalid_params", data)
        self.assertGreater(len(data["invalid_params"]), 0)

    # 7. Gunicorn Configuration & Kubernetes Manifests Validation
    def test_gunicorn_and_k8s_manifests(self):
        gunicorn_file = os.path.join(PROJECT_ROOT, "gunicorn_conf.py")
        self.assertTrue(os.path.exists(gunicorn_file))

        import gunicorn_conf
        self.assertIn("0.0.0.0:8000", gunicorn_conf.bind)
        self.assertEqual(gunicorn_conf.worker_class, "uvicorn.workers.UvicornWorker")
        self.assertGreaterEqual(gunicorn_conf.workers, 2)

        # Validate K8s YAML files syntax
        k8s_dir = os.path.join(PROJECT_ROOT, "k8s")
        for filename in ["namespace.yaml", "configmap.yaml", "deployment.yaml", "service.yaml", "ingress.yaml", "hpa.yaml"]:
            filepath = os.path.join(k8s_dir, filename)
            self.assertTrue(os.path.exists(filepath), f"{filename} must exist")
            with open(filepath, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)
                self.assertIsNotNone(content, f"{filename} should parse as valid YAML")
                self.assertIn("metadata", content)


if __name__ == "__main__":
    unittest.main()
