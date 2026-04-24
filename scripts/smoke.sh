#!/usr/bin/env bash
# End-to-end smoke test. Assumes ./scripts/bootstrap.sh has run and API is up.
set -euo pipefail

API="${API_BASE_URL:-http://127.0.0.1:8000}"

echo "==> [1] /health"
curl -sf "$API/health" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'"
echo "    OK"

echo "==> [2] Login as admin"
TOKEN=$(curl -sf -X POST "$API/api/auth/token" \
  -d "username=admin&password=admin123" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "    token OK"

echo "==> [3] Template count == 143"
TCOUNT=$(curl -sf -H "$AUTH" "$API/api/templates" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "    $TCOUNT templates"
[ "$TCOUNT" = "143" ] || { echo "FAIL: expected 143"; exit 1; }

echo "==> [4] Pack count == 10"
PCOUNT=$(curl -sf -H "$AUTH" "$API/api/packs" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "    $PCOUNT packs"
[ "$PCOUNT" = "10" ] || { echo "FAIL: expected 10"; exit 1; }

echo "==> [5] Resolve Pilot dataset"
DSID=$(docker compose exec -T db psql -U audit -d audit -tA -c \
  "SELECT id FROM datasets WHERE name='AP Sample (seeded)' ORDER BY imported_at DESC LIMIT 1" \
  | tr -d '[:space:]')
[ -n "$DSID" ] || { echo "FAIL: seeded dataset not found; run: python3 scripts/sample_data.py"; exit 1; }
echo "    dataset $DSID"

echo "==> [6] Run AP_STANDARD pack"
PACK=$(curl -sf -X POST "$API/api/packs/run" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"$DSID\",\"pack_code\":\"AP_STANDARD\",\"template_overrides\":{}}")
RAN=$(echo "$PACK" | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['templates_run'])")
echo "    $RAN templates ran"
[ "$RAN" = "29" ] || { echo "WARN: expected 29, got $RAN"; }

echo "==> [7] Run ensemble"
RIDS=$(echo "$PACK" | python3 -c "import sys,json;print(','.join('\"'+i+'\"' for i in json.load(sys.stdin)['summary']['test_run_ids']))")
ENS=$(curl -sf -X POST "$API/api/ensemble" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"$DSID\",\"test_run_ids\":[$RIDS]}")
echo "$ENS" | python3 -c "
import sys, json
s = json.load(sys.stdin)['summary']
print(f\"    records_scored={s['records_scored']} max={s['max_score']:.1f} mean={s['mean_score']:.1f}\")
assert s['records_scored'] > 0, 'ensemble produced no scores'
assert s['max_score'] > 0, 'max score should be > 0'
"

echo "==> [8] Top risky records"
curl -sf -H "$AUTH" "$API/api/datasets/$DSID/risk-scores?min_score=0&limit=5&sort=desc" \
  | python3 -c "
import sys, json
for r in json.load(sys.stdin):
    detectors = sorted({c['detector_name'] for c in r['contributing_detectors']})
    print(f\"    {r['record_key']}: score={r['score']:.1f} detectors={detectors}\")
"

echo "==> [9] Audit log chain"
curl -sf -H "$AUTH" "$API/api/audit-log/verify" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['ok'], f'chain broken at {d.get(\"broken_at\")}: {d.get(\"reason\")}'
print(f\"    ok (total_entries={d['total_entries']})\")
"

echo ""
echo "============================================================"
echo "  SMOKE TEST PASSED"
echo "============================================================"
