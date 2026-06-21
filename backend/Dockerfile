# SiteIQ backend — multi-stage build with uv.
#
# Stage 1 (builder): install deps into /app/.venv via uv. Building deps
# in a stage we throw away keeps the runtime image lean.
# Stage 2 (runtime): only the system libs OpenCV needs + the venv.
#
# Run with:  docker build -t siteiq-backend ./backend
#            docker run --rm -p 8000:8000 -e SITEIQ_DATABASE_URL=… siteiq-backend
#
FROM python:3.13-slim AS builder

# uv is small and dramatically faster than pip; install the released bin
# from the official image instead of pip-bootstrapping it.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# App source goes in last so dep installs cache.
COPY . .
RUN uv sync --frozen --no-dev


FROM python:3.13-slim AS runtime

# OpenCV + glib + libgomp are required by ultralytics/opencv-headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libgl1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SITEIQ_LOG_FORMAT=json

WORKDIR /app
COPY --from=builder /app /app

# Stamp commit + build time into a file the /api/version endpoint
# reads. Env vars take precedence at runtime if you'd rather inject
# them via the orchestrator.
ARG SITEIQ_COMMIT_SHA=dev
ARG SITEIQ_BUILT_AT
RUN printf "%s\n%s\n" "$SITEIQ_COMMIT_SHA" "${SITEIQ_BUILT_AT:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}" > /app/version.txt

# Non-root by default.
RUN useradd --no-create-home --uid 10001 siteiq && chown -R siteiq:siteiq /app
USER siteiq

EXPOSE 8000

# Migrations run on container start, then uvicorn boots. Override
# SITEIQ_DATABASE_URL to point at Postgres (or another SQLite path).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/readyz >/dev/null || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
