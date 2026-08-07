#!/usr/bin/env bash
# Copy the local Postgres database into the Docker one.
#
#   ./docker/migrate-local-data.sh
#
# The container starts with an empty volume, so `compose up` gives you the
# schema via alembic but none of your existing orders, products or accounts.
# This moves them across. Run it once, after the stack is up.
set -euo pipefail

LOCAL_HOST="${LOCAL_HOST:-localhost}"
LOCAL_PORT="${LOCAL_PORT:-5432}"
DB="${DB:-wrenza-db}"
USER="${USER_NAME:-postgres}"
PASS="${PGPASSWORD:-postgres}"

# The container publishes 5434 on the host — 5432 and 5433 are already taken
# by local Postgres instances.
DOCKER_PORT="${DOCKER_PORT:-5434}"

DUMP="/tmp/wrenza-db-$(date +%Y%m%d-%H%M%S).sql"

echo "→ dumping ${LOCAL_HOST}:${LOCAL_PORT}/${DB}"
PGPASSWORD="$PASS" pg_dump \
  -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$USER" -d "$DB" \
  --clean --if-exists --no-owner --no-privileges \
  > "$DUMP"

echo "✓ dumped $(wc -l < "$DUMP") lines to $DUMP"

echo "→ restoring into the container on port ${DOCKER_PORT}"
PGPASSWORD="$PASS" psql \
  -h localhost -p "$DOCKER_PORT" -U "$USER" -d "$DB" \
  -v ON_ERROR_STOP=0 \
  -f "$DUMP" > /dev/null

echo "✓ restored"
echo
PGPASSWORD="$PASS" psql -h localhost -p "$DOCKER_PORT" -U "$USER" -d "$DB" -tAc "
SELECT '  products    '||count(*) FROM products UNION ALL
SELECT '  orders      '||count(*) FROM orders UNION ALL
SELECT '  users       '||count(*) FROM users;"

echo
echo "The dump is kept at $DUMP — delete it once you are satisfied."
