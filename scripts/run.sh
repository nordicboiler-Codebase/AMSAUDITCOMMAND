#!/usr/bin/env bash
# Start API (:8000) and Streamlit UI (:8501) together.
# Press Ctrl+C once to stop both.
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://audit:audit@127.0.0.1:5432/audit}"
export SECRET_KEY="${SECRET_KEY:-dev-secret-change-me}"
export DATA_DIR="${DATA_DIR:-$PWD/data}"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"

mkdir -p logs
: > logs/api.log
: > logs/ui.log

cleanup() {
  echo ""
  echo "==> Stopping API and UI"
  kill "${API_PID:-0}" "${UI_PID:-0}" 2>/dev/null || true
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

echo "==> Starting Streamlit UI on :8501 (logs -> logs/ui.log)"
streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501 \
  --server.headless true --browser.gatherUsageStats false \
  >> logs/ui.log 2>&1 &
UI_PID=$!

echo ""
echo "============================================================"
echo "  API:         http://localhost:8000   (docs: /docs)"
echo "  UI:          http://localhost:8501"
echo "  Login:       admin / admin123"
echo "  API logs:    tail -f logs/api.log"
echo "  UI logs:     tail -f logs/ui.log"
echo ""
echo "  Press Ctrl+C to stop both."
echo "============================================================"

wait
