#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export DB_PATH="${DB_PATH:-$(pwd)/data.db}"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
