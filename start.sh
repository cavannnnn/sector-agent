#!/bin/bash
# Render.com start script
set -euo pipefail

# Use persistent disk path if available, otherwise local data dir
export DATABASE_PATH="${RENDER_DATA_DIR:-$(pwd)/data}/sector_agent.db"
mkdir -p "$(dirname "$DATABASE_PATH")"

# If no database exists yet, run initial pipeline
if [ ! -f "$DATABASE_PATH" ]; then
    echo "=== No database found. Running initial data pipeline... ==="
    python3 scheduler.py || echo "Initial pipeline failed, will retry on first refresh."
fi

echo "=== Starting gunicorn server on port ${PORT:-5050} ==="
exec gunicorn -c gunicorn.conf.py app:app
