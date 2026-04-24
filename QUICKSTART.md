# TechSource Audit Analytics — Quickstart

> **The UI is now a React SPA under `webapp/`.** The old Streamlit `ui/` was removed.
> Backend (FastAPI) is unchanged.

## In a fresh GitHub Codespace

```bash
make setup            # ~2 min: Postgres + Python deps + migrations + admin + sample data
make webapp-install   # installs React deps (first time only)
make run              # starts API (:8000) + React dev server (:5173)
```

That's it. Login: `admin` / `admin123`.

Codespaces auto-forwards the ports. Look in the **Ports** tab for the public URLs. Streamlit opens in a new tab automatically.

On a freshly created Codespace on this branch, `make setup` happens **automatically** via `.devcontainer/devcontainer.json → postCreateCommand`, so the first command you typically need is just:

```bash
make run
```

## Verify it works

In a second terminal:

```bash
make smoke
```

Expected last line: `SMOKE TEST PASSED`.

## What just happened

`make setup` ran `scripts/bootstrap.sh`:

1. `docker compose up -d db` — starts Postgres 15
2. Installs Python dependencies from `pyproject.toml`
3. `alembic upgrade head` — applies three migrations:
   - `0001` schema (11 tables + append-only audit log trigger)
   - `0002` seeds **143 test templates**
   - `0003` seeds **10 domain packs**
4. `scripts/seed_admin.py` — creates `admin / admin123` + Pilot project
5. `scripts/sample_data.py` — imports a 200-row AP CSV with planted fraud signals

`make run` starts the API and UI together, streaming logs to `logs/api.log` and `logs/ui.log`.

## Useful commands

```bash
make test        # pytest (should say: 44 passed)
make migrate     # re-apply migrations only
make reset       # drop + recreate DB + re-seed everything
make stop        # kill API + UI processes
make api-logs    # tail -f logs/api.log
make ui-logs     # tail -f logs/ui.log
make db-logs     # tail -f Postgres logs
make clean       # remove logs/ and data/
make help        # show all targets
```

## Exploring the UI

Sidebar navigation:

- **Dashboard** — project and template counts
- **Datasets** — preview the seeded `AP Sample (seeded)` dataset (paste its ID from the Projects page into the sidebar "Active dataset ID" field)
- **Templates** — browse all 143 templates, filter by subledger
- **Packs** — browse 10 domain packs
- **Run** — execute a single template, a pack, or a custom detector against the active dataset
- **Risk Explorer** — see records scored 0–100 with per-detector explainability
- **Audit Log** — hash-chain integrity status (green = verified)

## Recommended demo flow in the UI

1. **Sidebar** → select `Pilot` project, paste the dataset ID you see in Datasets page
2. **Packs** page → type `AP_STANDARD` → click "Run ... on active dataset"
3. **Risk Explorer** → set min_score to 30 → see top-risk records with which detectors fired
4. **Audit Log** → confirm chain is verified and count of entries matches your activity

## API instead of UI

Full Swagger UI at `http://localhost:8000/docs`.

Auth:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
  -d "username=admin&password=admin123" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/templates | head -c 400
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker: command not found` | Codespaces has it; locally install Docker Desktop. |
| Postgres `no response` | `make stop && make setup` — re-bootstraps cleanly. |
| `bcrypt` error on login | Bootstrap pins `bcrypt<4.1`; run `pip install "bcrypt<4.1"`. |
| API won't start | `make api-logs` — full traceback is there. |
| Tests fail with `DuplicateObject` | `make reset` — wipes schema and re-seeds. |
| Port already in use | `make stop` then `make run`. |

## Non-Codespaces (local) setup

Same two commands work if you have Docker + Python 3.11:

```bash
git clone <repo-url>
cd amsauditcommand
make setup
make run
```
