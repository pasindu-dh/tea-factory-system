#!/bin/sh
set -eu

# Render mounts a persistent disk at /data as root. Fix its ownership, then
# drop privileges so the SQLite database and its -wal/-shm files stay app-owned.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /data
    chown -R app:app /data
    exec setpriv --reuid=app --regid=app --init-groups \
        env HOME=/app PATH="$PATH" /app/docker-entrypoint.sh "$@"
fi

export TEA_FACTORY_DB="${TEA_FACTORY_DB:-/data/tea_factory.sqlite3}"
PORT="${PORT:-8000}"

# Idempotent: creates a missing schema, applies pending migrations, and inserts
# the default rate row. Safe to run on every boot.
flask --app app init-db

exec waitress-serve --host=0.0.0.0 --port="$PORT" --threads=8 app:app
