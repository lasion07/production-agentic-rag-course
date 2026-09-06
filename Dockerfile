FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base

WORKDIR /app

# Copy configuration files
COPY pyproject.toml uv.lock ./

# Avoid precompiling thousands of dependency files in the image. The small
# startup trade-off is preferable on constrained Docker Desktop environments.
# UV_LINK_MODE=copy silences cross-filesystem hard-link warnings.
ENV UV_COMPILE_BYTECODE=0 UV_LINK_MODE=copy

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev

# Copy source code
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations

FROM python:3.12.8-slim AS final

EXPOSE 8000

# PYTHONUNBUFFERED=1 to disable output buffering
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/home/rag
ARG VERSION=0.1.0
ENV APP_VERSION=$VERSION

WORKDIR /app

# The runtime has no reason to run as root. Keep a fixed UID/GID so mounted
# files and orchestrator securityContext settings remain predictable.
RUN groupadd --gid 10001 rag && \
    useradd --uid 10001 --gid 10001 --create-home --home-dir /home/rag --shell /usr/sbin/nologin --no-log-init rag && \
    mkdir -p /app/data/arxiv_pdfs && \
    chown -R 10001:10001 /app /home/rag

# Copy the virtual environment from the base stage
COPY --from=base --chown=10001:10001 /app /app
COPY --chmod=0555 deploy/docker-entrypoint.sh /usr/local/bin/rag-entrypoint

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

USER 10001:10001

# Run the application
ENTRYPOINT ["/usr/local/bin/rag-entrypoint"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
