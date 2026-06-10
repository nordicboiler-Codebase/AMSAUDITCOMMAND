#!/usr/bin/env bash
# TechSource Audit Analytics — single-command launcher.
#
# Usage:   ./go               # everything: setup if needed, then run
#          ./go stop          # stop API + UI + Postgres
#          ./go reset         # nuke local data (keeps blob backup)
#          ./go logs          # tail the running logs
#
# Idempotent. Detects state and does the right thing. Designed for GitHub
# Codespaces where the container is ephemeral. If Azure Blob storage is
# configured, your imported datasets and DB survive a Codespace rebuild.
set -euo pipefail
cd "$(dirname "$0")"

# --- colour helpers ---------------------------------------------------------
if [ -t 1 ]; then
  B="\033[1m"; G="\033[32m"; Y="\033[33m"; C="\033[36m"; R="\033[31m"; N="\033[0m"
else
  B=""; G=""; Y=""; C=""; R=""; N=""
fi
say() { printf "${B}${C}==>${N} %s\n" "$*"; }
ok()  { printf "    ${G}✓${N} %s\n" "$*"; }
warn(){ printf "    ${Y}!${N} %s\n" "$*"; }
err() { printf "    ${R}✗${N} %s\n" "$*"; }

CMD="${1:-up}"

# --- core helpers -----------------------------------------------------------
load_env() {
  [ -f .env ] || cp .env.example .env
  set -a; . ./.env; set +a
  export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://audit:audit@127.0.0.1:5432/audit}"
  export SECRET_KEY="${SECRET_KEY:-dev-secret-change-me}"
  export DATA_DIR="${DATA_DIR:-$PWD/data}"
  mkdir -p "$DATA_DIR"/{uploads,parquet,reports,reference} logs
}

is_port_up() { curl -sfL -o /dev/null --max-time 1 "$1"; }

wait_for() {
  local url="$1" name="$2" tries="${3:-40}"
  for _ in $(seq 1 "$tries"); do
    if is_port_up "$url"; then ok "$name ready"; return 0; fi
    sleep 0.5
  done
  err "$name didn't come up — check logs/"; return 1
}

ensure_postgres() {
  say "Starting Postgres"
  docker compose up -d db >/dev/null
  for _ in {1..30}; do
    if docker compose exec -T db pg_isready -U audit >/dev/null 2>&1; then
      ok "Postgres ready"; return 0
    fi
    sleep 1
  done
  err "Postgres didn't come up"; exit 1
}

ensure_python_deps() {
  if ! python3 -c "import backend.main" 2>/dev/null; then
    say "Installing Python dependencies (first run, ~2 min)"
    pip install -q -e ".[dev]"
    pip install -q "bcrypt<4.1"
    pip install -q libpff-python 2>/dev/null || warn "libpff-python skipped (.pst import disabled; .mbox/.eml still work)"
    pip install -q azure-storage-blob || warn "azure-storage-blob skipped (set AZURE_BLOB_CONNECTION_STRING to enable persistence)"
    ok "Python deps installed"
  fi
}

ensure_webapp_deps() {
  if [ ! -d webapp/node_modules ]; then
    say "Installing webapp dependencies"
    (cd webapp && npm install --no-audit --no-fund >/dev/null)
    ok "webapp deps installed"
  fi
}

ensure_migrated() {
  say "Applying database migrations"
  alembic upgrade head >/dev/null
  ok "Schema up to date"
}

ensure_admin() {
  local has_user
  has_user=$(docker compose exec -T db psql -U audit -d audit -tAc \
    "SELECT count(*) FROM users WHERE username='admin'" 2>/dev/null || echo 0)
  if [ "${has_user:-0}" = "0" ]; then
    say "Seeding admin user"
    python3 scripts/seed_admin.py >/dev/null
    ok "Admin created (login below)"
  fi
}

maybe_restore_from_blob() {
  if [ -z "${AZURE_BLOB_CONNECTION_STRING:-}" ]; then
    return 0
  fi
  if ls "$DATA_DIR"/parquet/*.parquet >/dev/null 2>&1; then
    ok "Local data present — skipping blob restore (run './go pull' to force)"
    return 0
  fi
  say "Restoring data from Azure Blob (configured in .env)"
  ./scripts/sync_blob.sh pull --force || warn "Blob restore failed — continuing with empty data"
}

start_api() {
  if is_port_up "http://127.0.0.1:8000/health"; then
    ok "API already running on :8000"
    return 0
  fi
  say "Starting API on :8000 (logs → logs/api.log)"
  : > logs/api.log
  nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
    >> logs/api.log 2>&1 &
  echo $! > logs/api.pid
  wait_for "http://127.0.0.1:8000/health" "API" 60
}

start_webapp() {
  if is_port_up "http://127.0.0.1:5173"; then
    ok "Web UI already running on :5173"
    return 0
  fi
  say "Starting React dev server on :5173 (logs → logs/webapp.log)"
  : > logs/webapp.log
  (cd webapp && nohup npm run dev -- --host 0.0.0.0 >> ../logs/webapp.log 2>&1 &)
  echo $! > logs/webapp.pid
  wait_for "http://127.0.0.1:5173" "Web UI" 60
}

print_urls() {
  local cs_name="${CODESPACE_NAME:-}"
  local forward="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  cat <<EOF

${B}============================================================${N}
  ${B}TechSource Audit Analytics is running${N}

EOF
  if [ -n "$cs_name" ]; then
    printf "  Web UI:  ${G}https://%s-5173.%s${N}\n" "$cs_name" "$forward"
    printf "  API:     ${G}https://%s-8000.%s${N}/docs\n" "$cs_name" "$forward"
    echo "             (open the Ports panel if these don't auto-open)"
  else
    printf "  Web UI:  ${G}http://localhost:5173${N}\n"
    printf "  API:     ${G}http://localhost:8000/docs${N}\n"
  fi
  cat <<EOF

  Login:   admin / admin123  (change the password from Settings)

  ${B}Where to put your AI API key${N}
  Open the Web UI → top-right ${C}Settings${N} → ${C}AI Providers${N} tab.
  Pick one (Groq is free, no card; Anthropic/OpenAI/Gemini also supported),
  paste the key, click ${C}Test${N}, then ${C}Set active${N}. Keys are stored
  Fernet-encrypted in the database, not on disk.

EOF
  if [ -n "${AZURE_BLOB_CONNECTION_STRING:-}" ]; then
    printf "  ${B}Azure Blob persistence:${N} ${G}ENABLED${N}\n"
    echo "  Container: ${AZURE_BLOB_CONTAINER:-techsource-audit-data}"
    echo "  Manual backup:  ./scripts/sync_blob.sh push"
    echo "  Manual restore: ./scripts/sync_blob.sh pull --force"
  else
    printf "  ${B}Azure Blob persistence:${N} ${Y}NOT CONFIGURED${N} — uploads/DB will be lost on Codespace rebuild.\n"
    cat <<EOF
  To enable, add to ${C}.env${N}:
    AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=<acct>;AccountKey=<key>;EndpointSuffix=core.windows.net
    AZURE_BLOB_CONTAINER=techsource-audit-data
  Then:  ./scripts/sync_blob.sh push   (back up the current state once)
  On next ./go in a fresh Codespace, your data will be restored automatically.
EOF
  fi
  cat <<EOF

  Tail logs:    ./go logs
  Stop:         ./go stop
${B}============================================================${N}
EOF
}

# --- commands ---------------------------------------------------------------
case "$CMD" in
  up|"")
    load_env
    ensure_postgres
    ensure_python_deps
    ensure_migrated
    ensure_admin
    maybe_restore_from_blob
    ensure_webapp_deps
    start_api
    start_webapp
    print_urls
    ;;
  stop)
    load_env
    say "Stopping API + webapp"
    [ -f logs/api.pid    ] && kill "$(cat logs/api.pid)"    2>/dev/null || true
    [ -f logs/webapp.pid ] && kill "$(cat logs/webapp.pid)" 2>/dev/null || true
    pkill -f "uvicorn backend.main" 2>/dev/null || true
    pkill -f "vite"                 2>/dev/null || true
    rm -f logs/*.pid
    ok "API + webapp stopped"
    say "Stopping Postgres"
    docker compose down
    ok "Postgres stopped"
    ;;
  logs)
    tail -n 50 -F logs/api.log logs/webapp.log
    ;;
  reset)
    load_env
    warn "This will delete local data/ and reset the database (blob backup, if any, is untouched)."
    read -r -p "Type 'reset' to confirm: " confirm
    if [ "$confirm" = "reset" ]; then
      "$0" stop >/dev/null 2>&1 || true
      docker compose down -v
      rm -rf "$DATA_DIR"
      ok "Local state cleared. Run ./go to start fresh."
    else
      warn "Cancelled."
    fi
    ;;
  push)
    load_env
    exec ./scripts/sync_blob.sh push
    ;;
  pull)
    load_env
    exec ./scripts/sync_blob.sh pull --force
    ;;
  status)
    load_env
    docker compose ps
    ./scripts/sync_blob.sh status 2>/dev/null || true
    ;;
  *)
    cat <<EOF
TechSource Audit Analytics launcher

Usage:
  ./go             Start everything (setup on first run, resume after)
  ./go stop        Stop API + UI + Postgres
  ./go logs        Tail API + UI logs
  ./go push        Back up data/ + DB to Azure Blob
  ./go pull        Restore data/ + DB from Azure Blob (force)
  ./go status      Show what's running and blob state
  ./go reset       Wipe local DB + data/ (blob backup untouched)
EOF
    ;;
esac
