"""
RFC 7807 Problem Details Global Exception Handlers.
Formats all application errors, validation failures, rate limits, and unhandled
exceptions into standard machine-readable Problem Details JSON payloads.
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger("APIExceptions")


def create_problem_response(
    status_code: int,
    title: str,
    detail: str,
    request: Request,
    problem_type: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Constructs an RFC 7807 compliant JSONResponse.
    """
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id") or str(uuid.uuid4())
    
    payload: Dict[str, Any] = {
        "type": problem_type or f"https://api.schemes.gov.in/errors/{status_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if extra:
        payload.update(extra)
        
    return JSONResponse(
        status_code=status_code,
        content=payload,
        media_type="application/problem+json",
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handler for standard HTTPExceptions.
    """
    title = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Resource Not Found",
        405: "Method Not Allowed",
        413: "Payload Too Large",
        422: "Unprocessable Entity",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }.get(exc.status_code, "HTTP Error")
    
    return create_problem_response(
        status_code=exc.status_code,
        title=title,
        detail=str(exc.detail),
        request=request,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler for Pydantic schema validation failures.
    """
    errors: List[Dict[str, Any]] = []
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err.get("loc", []))
        errors.append({
            "field": loc,
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "value_error"),
        })
        
    return create_problem_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        title="Validation Error",
        detail="The request body or parameters failed schema validation constraints.",
        request=request,
        problem_type="https://api.schemes.gov.in/errors/validation-failed",
        extra={"invalid_params": errors},
    )


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Handler for Slowapi rate limit violations.
    """
    return create_problem_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        title="Rate Limit Exceeded",
        detail=f"Too many requests. Limit exceeded: {exc.detail}",
        request=request,
        problem_type="https://api.schemes.gov.in/errors/rate-limit-exceeded",
        extra={"retry_after_seconds": 60},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected internal exceptions.
    Ensures no raw stack traces leak to external callers.
    """
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    logger.exception(f"Unhandled error processing request {request.method} {request.url.path} [ReqID: {request_id}]: {exc}")
    
    return create_problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="Internal Server Error",
        detail="An unexpected error occurred while processing your request. Please contact support quoting your request_id.",
        request=request,
        problem_type="https://api.schemes.gov.in/errors/internal-server-error",
    )
