"""
Production Middleware Suite:
1. Request Tracing & Timing Middleware (X-Request-ID, X-Process-Time-Ms)
2. Security Hardening Headers Middleware (OWASP recommended security headers)
3. Rate Limiter instance integration using slowapi
"""

from __future__ import annotations
import time
import uuid
import logging
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import settings
from api.metrics import metrics

logger = logging.getLogger("APIMiddleware")

# Initialize Rate Limiter singleton
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT] if settings.RATE_LIMIT_ENABLED else [],
    enabled=settings.RATE_LIMIT_ENABLED,
    storage_uri=settings.RATE_LIMIT_STORAGE_URL,
)


class RequestTimingAndTracingMiddleware(BaseHTTPMiddleware):
    """
    Assigns or preserves unique X-Request-ID for distributed tracing,
    measures millisecond execution time, logs requests, and updates Prometheus counters.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Trace ID: read from client header if provided, else generate fresh UUID4
        request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
        except Exception:
            # Let the exception handlers handle it, but compute duration for metrics
            duration_ms = (time.perf_counter() - start_time) * 1000
            metrics.record_request(request.method, request.url.path, 500, duration_ms)
            raise

        process_time_ms = (time.perf_counter() - start_time) * 1000
        
        # Inject tracing headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}ms"
        
        # Record metrics telemetry
        metrics.record_request(request.method, request.url.path, response.status_code, process_time_ms)

        # Log request if in dev or if status is not 200/304
        if settings.DEBUG or response.status_code >= 400:
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} "
                f"-> status={response.status_code} in {process_time_ms:.2f}ms"
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects OWASP recommended security headers to harden the platform against
    MIME-sniffing, clickjacking, cross-site scripting, and unwanted embedding.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Essential Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # HSTS in production environments
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
