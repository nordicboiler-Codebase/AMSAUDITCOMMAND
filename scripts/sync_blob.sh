#!/usr/bin/env bash
# Push or pull both the data directory AND the Postgres database to/from Azure Blob.
#
#   ./scripts/sync_blob.sh push        # local -> blob (backup)
#   ./scripts/sync_blob.sh pull        # blob -> local (restore; skips parquet if non-empty)
#   ./scripts/sync_blob.sh pull --force  # overwrite local parquet/DB even if present
#   ./scripts/sync_blob.sh status      # what's where
#
# Requires AZURE_BLOB_CONNECTION_STRING (+ optional AZURE_BLOB_CONTAINER) in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env so the Python module sees the variables
if [ -f .env ]; then set -a; . ./.env; set +a; fi

CMD="${1:-status}"
FORCE=""
if [ "${2:-}" = "--force" ]; then FORCE="--force"; fi

if [ -z "${AZURE_BLOB_CONNECTION_STRING:-}" ]; then
  cat <<EOF
Azure Blob storage is not configured. Add to .env:

  AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=<acct>;AccountKey=<key>;EndpointSuffix=core.windows.net
  AZURE_BLOB_CONTAINER=techsource-audit-data

Then re-run:  ./scripts/sync_blob.sh push
EOF
  exit 1
fi

# Ensure SDK is present
python3 -c "import azure.storage.blob" 2>/dev/null || pip install -q azure-storage-blob

DUMP="data/_pg_dump.sql.gz"

case "$CMD" in
  push)
    echo "==> Dumping Postgres → $DUMP"
    mkdir -p data
    if docker compose ps db 2>/dev/null | grep -q "Up"; then
      docker compose exec -T db pg_dump -U audit -d audit | gzip > "$DUMP"
      echo "    wrote $(stat -c%s "$DUMP" 2>/dev/null || stat -f%z "$DUMP") bytes"
    else
      echo "    (Postgres not running; skipping DB dump)"
    fi
    echo "==> Uploading data/ → blob"
    python3 -m backend.services.blob_storage push
    ;;
  pull)
    echo "==> Downloading blob → data/"
    python3 -m backend.services.blob_storage pull $FORCE
    if [ -f "$DUMP" ]; then
      if docker compose ps db 2>/dev/null | grep -q "Up"; then
        if [ "$FORCE" = "--force" ] || ! psql_count=$(docker compose exec -T db psql -U audit -d audit -tAc "SELECT count(*) FROM datasets" 2>/dev/null) || [ "${psql_count:-0}" = "0" ]; then
          echo "==> Restoring Postgres from $DUMP"
          gunzip -c "$DUMP" | docker compose exec -T db psql -U audit -d audit >/dev/null
          echo "    restored"
        else
          echo "    (DB already has $psql_count datasets; pass --force to overwrite)"
        fi
      else
        echo "    (Postgres not running; start it then: ./scripts/sync_blob.sh pull --force)"
      fi
    fi
    ;;
  status)
    python3 -m backend.services.blob_storage status
    ;;
  *)
    echo "usage: $0 {push|pull [--force]|status}"
    exit 2
    ;;
esac
