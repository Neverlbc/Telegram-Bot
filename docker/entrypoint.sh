#!/bin/bash
set -e

echo "Running Alembic migrations..."
alembic upgrade head 2>&1 || echo "WARNING: Alembic migration failed (may need manual intervention)"

echo "Starting bot..."
exec python -m bot "$@"
