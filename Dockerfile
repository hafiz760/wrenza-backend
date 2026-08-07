# Wrenza API and worker.
#
# One image, two targets. `dev` mounts your source and reloads; `prod` bakes
# the code in. Both run the same Python and the same dependency lockfile, so
# something that works in development is not a different program in production.

# ── Base ────────────────────────────────────────────────────────
FROM python:3.14-slim AS base

# uv resolves and installs from the lockfile — same tool used locally, so the
# container cannot drift to different package versions than your machine.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ── Dependencies ────────────────────────────────────────────────
# Its own layer, keyed on the lockfile alone. Editing application code does
# not reinstall packages; changing a dependency does.
FROM base AS deps

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ── Development ─────────────────────────────────────────────────
# Source is bind-mounted by compose rather than copied, so edits take effect
# without a rebuild.
FROM deps AS dev

# psql and pg_isready, for debugging inside the container
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production ──────────────────────────────────────────────────
FROM deps AS prod

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

# Non-root: a container escape should not land on a root shell. Files are
# owned by the app user so the venv stays writable for nothing in particular
# but the ownership is consistent.
RUN useradd --create-home --uid 1000 wrenza \
    && chown -R wrenza:wrenza /app
USER wrenza

EXPOSE 8000

ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
