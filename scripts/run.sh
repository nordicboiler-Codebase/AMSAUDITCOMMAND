#!/usr/bin/env bash
# Start API (:8000) and React dev server (:5173) together.
# Press Ctrl+C once to stop both.
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://audit:audit@127.0.0.1:5432/audit}"
export SECRET_KEY="${SECRET_KEY:-dev-secret-change-me}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"

mkdir -p logs
: > logs/api.log
: > logs/webapp.log

cleanup() {
  echo ""
  echo "==> Stopping API and webapp"
  kill "${API_PID:-0}" "${WEBAPP_PID:-0}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "==> Starting API on :8000 (logs -> logs/api.log)"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info \
  >> logs/api.log 2>&1 &
API_PID=$!

echo "==> Waiting for API to become healthy"
for _ in {1..40}; do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "    API ready (pid=$API_PID)"
    break
  fi
  sleep 0.5
done

# Prefer Vite dev server (live reload) if npm is available; otherwise fall back to
# serving the built dist via python http.server.
if command -v npm >/dev/null 2>&1; then
  if [ ! -d webapp/node_modules ]; then
    echo "==> Installing webapp dependencies (first run)..."
    (cd webapp && npm install --no-audit --no-fund) >> logs/webapp.log 2>&1
  fi
  echo "==> Starting Vite dev server on :5173 (logs -> logs/webapp.log)"
  (cd webapp && npm run dev) >> logs/webapp.log 2>&1 &
  WEBAPP_PID=$!
else
  if [ ! -d webapp/dist ]; then
    echo "==> No Node — building static SPA with Docker (first time)..."
    docker build -t techsource-webapp ./webapp > /dev/null
  fi
  echo "==> Serving built SPA via Docker nginx on :5173"
  docker run --rm -p 5173:80 --network host --name techsource-webapp-dev techsource-webapp \
    >> logs/webapp.log 2>&1 &
  WEBAPP_PID=$!
fi

cat <<EOF

============================================================
  API:      http://localhost:8000   (docs: /docs)
  UI:       http://localhost:5173
  Login:    admin / admin123
  API logs: tail -f logs/api.log
  UI logs:  tail -f logs/webapp.log

  Press Ctrl+C to stop.
============================================================
EOF

wait
