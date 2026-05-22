#!/bin/sh
set -e

# Wait for Postgres; healthcheck on the db service already gates startup,
# but a small retry guards against the very-first-boot race.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if alembic upgrade head; then
    break
  fi
  echo "alembic upgrade failed (attempt $i) — retrying in 1s" >&2
  sleep 1
done

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
