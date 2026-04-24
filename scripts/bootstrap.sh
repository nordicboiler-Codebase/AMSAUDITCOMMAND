#!/usr/bin/env bash
# One-shot setup for a fresh Codespace / dev box.
# Starts Postgres, installs deps, runs migrations, creates admin, imports sample data.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> [1/6] Starting Postgres via docker compose"
docker compose up -d db

echo "==> [2/6] Waiting for Postgres"
for _ in {1..30}; do
  if docker compose exec -T db pg_isready -U audit >/dev/null 2>&1; then
    echo "    Postgres ready"
    break
  fi
  sleep 1
done

echo "==> [3/6] Installing Python dependencies"
pip install -q -e ".[dev]"
pip install -q "bcrypt<4.1"

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://audit:audit@127.0.0.1:5432/audit}"
export SECRET_KEY="${SECRET_KEY:-dev-secret-change-me}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
mkdir -p "$DATA_DIR"/{uploads,parquet,reports,reference}

echo "==> [4/6] Running Alembic migrations (schema + 143 templates + 10 packs)"
alembic upgrade head

echo "==> [5/6] Creating admin user (username=admin password=admin123) and Pilot project"
python3 scripts/seed_admin.py

echo "==> [6/6] Importing sample AP dataset with planted fraud signals"
python3 scripts/sample_data.py

cat <<'EOF'

============================================================
Bootstrap complete.

Next:
  ./scripts/run.sh        # starts API (8000) + Streamlit UI (8501)

Login:
  username: admin
  password: admin123

Smoke test:
  ./scripts/smoke.sh
============================================================
EOF
