# ==============================================================================
# Multi-Stage Production Dockerfile: Government Schemes Discovery & RAG Platform
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies into wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------------------
# Final Runtime Image (Lightweight & Security-Hardened)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN useradd -u 1001 -m -s /bin/bash appuser

# Copy installed python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application source code
COPY --chown=appuser:appuser api/ /app/api/
COPY --chown=appuser:appuser engine/ /app/engine/
COPY --chown=appuser:appuser knowledge_base/ /app/knowledge_base/
COPY --chown=appuser:appuser parsers/ /app/parsers/
COPY --chown=appuser:appuser schemas/ /app/schemas/
COPY --chown=appuser:appuser core/ /app/core/
COPY --chown=appuser:appuser guardrails/ /app/guardrails/
COPY --chown=appuser:appuser evaluation/ /app/evaluation/
COPY --chown=appuser:appuser crawlers/ /app/crawlers/
COPY --chown=appuser:appuser data/ /app/data/
COPY --chown=appuser:appuser samples/ /app/samples/
COPY --chown=appuser:appuser gunicorn_conf.py /app/gunicorn_conf.py
COPY --chown=appuser:appuser pipeline.py /app/pipeline.py
COPY --chown=appuser:appuser cli.py /app/cli.py
COPY --chown=appuser:appuser requirements.txt /app/requirements.txt

# Ensure permissions on data directory for SQLite
RUN chown -R appuser:appuser /app/data

# Environment configuration
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Switch to non-root user
USER appuser

# Expose HTTP port
EXPOSE 8000

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server start command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
