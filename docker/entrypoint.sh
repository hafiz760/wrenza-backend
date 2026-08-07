#!/usr/bin/env bash
# Runs before the API or the worker starts.
#
# Waits for Postgres, then applies migrations. Both matter on `compose up`:
# the database accepts connections a moment after the container reports
# healthy, and a fresh volume has no schema at all.
set -euo pipefail

# The worker must not run migrations or seed — two containers starting
# together would race on the same alembic lock and the same insert.
RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"
SEED_ADMIN="${SEED_ADMIN:-1}"

wait_for_postgres() {
  local host="${POSTGRES_HOST:-postgres}"
  local port="${POSTGRES_PORT:-5432}"
  local attempts=0

  echo "→ waiting for postgres at ${host}:${port}"
  until python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${host}', ${port}))
except OSError:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
      echo "✗ postgres did not become reachable after 60s" >&2
      exit 1
    fi
    sleep 2
  done
  echo "✓ postgres reachable"
}

wait_for_postgres

if [ "$RUN_MIGRATIONS" = "1" ]; then
  echo "→ applying migrations"
  alembic upgrade head
  echo "✓ schema up to date"
fi

if [ "$SEED_ADMIN" = "1" ]; then
  # A fresh database has no accounts and the dashboard has no sign-up, so
  # without this there is no way into a new deployment. Idempotent, and quiet
  # when unconfigured — a missing admin password should not stop the API from
  # starting.
  echo "→ checking for an admin user"
  python -m scripts.seed_admin --quiet-if-unconfigured
fi

exec "$@"
