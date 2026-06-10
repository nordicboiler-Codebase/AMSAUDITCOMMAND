# TechSource Audit Analytics — Quickstart

## One command. Really.

In a fresh GitHub Codespace (or any Linux box with Docker + Python 3.11):

```bash
./go
```

That's it. The launcher detects what's missing and only does the work that's needed:

- First run on a fresh box → bootstraps Postgres + Python deps + DB migrations + admin user + sample data, **then** starts API and Web UI.
- Codespace was rebuilt → restores your `data/` and Postgres dump from Azure Blob (if configured), then starts.
- Already set up → just starts API + Web UI.
- Already running → tells you the URLs and exits.

When it finishes, the terminal prints clickable URLs and login credentials.

```text
============================================================
  TechSource Audit Analytics is running

  Web UI:  https://<codespace>-5173.app.github.dev
  API:     https://<codespace>-8000.app.github.dev/docs

  Login:   admin / admin123
============================================================
```

In a Codespace, ports 5173 (UI) and 8000 (API) auto-forward — check the **Ports** panel.

## Where to put your AI API key

**In the Web UI:** click the gear icon (top-right) → **Settings** → **AI Providers** tab.

Pick one provider, paste the key, click **Test**, then **Set active**. The key is stored Fernet-encrypted in the database (not on disk, not in `.env`).

| Provider | Free option? | Get a key |
|---|---|---|
| **Groq** | Yes, no card | <https://console.groq.com> |
| **Google Gemini** | Free tier with limits | <https://aistudio.google.com/apikey> |
| **Anthropic Claude** | Paid | <https://console.anthropic.com> |
| **OpenAI** | Paid | <https://platform.openai.com> |

For UAE / regulated client data, prefer paid providers (data residency + no-train guarantees). Free tiers may train on prompts.

## Where to put your storage (Azure Blob)

Codespaces wipes the container filesystem on rebuild — every imported PST, every parquet, the Postgres DB. To survive rebuilds, point the app at an Azure Blob container in your subscription.

**1.** In Azure Portal → Storage account → **Access keys** → copy the connection string.

**2.** Add two lines to `.env` at the repo root (the file is created from `.env.example` on first run):

```dotenv
AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=<acct>;AccountKey=<key>;EndpointSuffix=core.windows.net
AZURE_BLOB_CONTAINER=techsource-audit-data
```

**3.** Back up the current state once:

```bash
./go push
```

That uploads `data/` (parquet, encrypted uploads, reports) **and** a gzipped `pg_dump` of the database to the container. The container is auto-created on first push.

From then on, every fresh `./go` automatically restores everything before starting the API. Manual operations:

```bash
./go push           # back up local → blob
./go pull           # restore blob → local (overwrites)
./go status         # what's where
./scripts/sync_blob.sh status    # same, more detail
```

## Importing large mailboxes (multi-GB PST/OST)

The **Import mailboxes (PST)** button in the Datasets page uploads through HTTP — fine for <2 GB per file. For larger mailboxes (e.g. six 50 GB OSTs), HTTP upload isn't viable. Use the direct-from-blob path:

**1.** Upload your `.ost` / `.pst` files straight into the blob container (Azure Storage Explorer, or `azcopy copy "*.ost" "https://<acct>.blob.core.windows.net/techsource-audit-data?<sas>"`).

**2.** Call the streaming-import endpoint:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=admin123" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/datasets/import-email-from-blob \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "project_id": "<your-project-uuid>",
    "name": "Q1 2026 mailbox review",
    "blob_paths": ["mailboxes/j.smith.ost", "mailboxes/a.khan.ost"],
    "custodians": ["j.smith", "a.khan"]
  }'
```

The API streams each blob to a local temp file, runs `libpff` over it, writes the messages to Parquet in 25 000-row batches (memory stays bounded — never holds the whole mailbox in RAM), and deletes the temp. Once `./go push` runs, the resulting parquet is also persisted to blob.

### Honest scale notes for 6 × 50 GB OSTs

- Codespaces default disk is ~32 GB. **You cannot stage 300 GB of source data on a Codespace.** Run on a self-hosted VM or local workstation with enough disk to hold one OST at a time (so ~60 GB free is enough — files are processed sequentially, then the temp is deleted).
- `libpff` requires random-access to the OST, so each file is downloaded fully before parsing — it can't be parsed straight from blob bytes. Plan for a download burst per file proportional to file size.
- Memory stays under ~2 GB per worker regardless of mailbox size thanks to the batched parquet writer.
- The resulting Parquet (messages-only, no attachments) is typically 1–3% of the OST size — six 50 GB OSTs → a 6–10 GB Parquet — which fits comfortably and can be analysed in-place.
- AI search over a multi-GB Parquet runs locally on Polars (deterministic, no provider call); only the prompt-compile step calls your AI provider, so cost stays in the cents.

## Useful commands

```bash
./go              # start (or resume) — the only command you usually need
./go stop         # shut everything down
./go logs         # tail API + UI logs
./go push         # back up data + DB to blob
./go pull         # restore data + DB from blob
./go status       # what's running, blob status
./go reset        # nuke local data (asks for confirmation; blob untouched)

make test         # pytest
make smoke        # end-to-end smoke against the running API
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `./go` says `command not found` | `chmod +x go && ./go` — git sometimes drops the bit. |
| Postgres won't start | `docker compose down -v && ./go` — nukes the DB volume and rebootstraps. |
| `bcrypt` error on login | Bootstrap pins `bcrypt<4.1`; `pip install "bcrypt<4.1"`. |
| Web UI is blank | Check `./go logs` — usually a Vite proxy error. |
| "Dataset parquet file is missing" | Codespace was rebuilt without blob backup. Configure `AZURE_BLOB_CONNECTION_STRING` (above) and re-import. |
| Import-from-blob says PST library missing | `pip install libpff-python` (native, may need build tools). |
| Port already in use | `./go stop && ./go`. |
