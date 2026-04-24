# TechSource Audit Analytics — CLAUDE.md

Internal audit data analytics platform. Alternative to Diligent ACL, CaseWare IDEA, MindBridge.

## Architecture — two layers

1. **Base detectors** (~35): Python modules in `backend/detectors/`, each implementing
   the `Detector` protocol. One detector per analytical *engine* (e.g. `benford`,
   `duplicates`, `weekend_transactions`). Detectors are pure: `(DataFrame, params) -> DetectorResult`.

2. **Named test templates** (~143): database rows in `test_templates` with
   `{code, name, detector_name, default_params, subledger_type, category, tags, weight}`.
   Seeded via Alembic data migrations. Adding a new named test is a DB insert, not
   a code change. Templates are parameter presets bound to a detector.

## Architectural principles

- **Audit integrity is paramount.** Source data is read-only after import. SHA-256 hashes
  on uploads and on every detector input/output. Append-only tamper-evident audit log
  (hash-chained, DB trigger prevents UPDATE/DELETE).
- **Subledger-aware.** Datasets tagged with `SubledgerType`. Templates and packs filtered
  by subledger so auditors see only what applies.
- **Ensemble risk scoring.** Each record gets a 0-100 score from all detectors that
  flagged it. Explainability (which detectors, weights, reasons) stored per-record.
- **Polars first**, pandas only where a library requires it. Pydantic models on every API
  contract. Type hints everywhere.
- **No duplicated test code.** If you reach for a new detector file for the 121st test,
  you're doing it wrong — it's a template row.

## Directory layout

```
backend/
├── core/            # config, db, logging, security
├── models/          # SQLAlchemy ORM
├── schemas/         # Pydantic API contracts
├── detectors/       # 35 base detectors + protocol + catalog
│   ├── base.py
│   ├── catalog.py
│   ├── data_quality/
│   ├── duplicate_sequence/
│   ├── statistical/
│   ├── benford_fraud/
│   ├── temporal/
│   ├── relational/
│   ├── text/
│   ├── ml/
│   └── predictive/
├── templates/       # template catalog + seed modules (U*/AP*/AR*/GL*/...)
├── services/        # import, test_runner, ensemble, audit_log, nlq, reporting, library, packs
└── api/             # FastAPI routers (auth, projects, datasets, templates, packs, runs, ...)

alembic/versions/    # schema + data seed migrations
ui/                  # Streamlit pages
tests/               # pytest suites (one per detector + service)
data/                # uploads, parquet, reports (gitignored)
```

## Enums (single source of truth — backend/models/enums.py)

- `SubledgerType`: GENERAL_LEDGER, ACCOUNTS_PAYABLE, ACCOUNTS_RECEIVABLE, PAYROLL,
  FIXED_ASSETS, INVENTORY, BANK, PROCUREMENT, TE, SALES, OTHER
- `UserRole`: ADMIN, AUDITOR, VIEWER
- `DetectorCategory`: DATA_QUALITY, DUPLICATE_SEQUENCE, STATISTICAL, BENFORD_FRAUD,
  TEMPORAL, RELATIONAL, TEXT, ML, PREDICTIVE
- `TemplateCategory`: DATA_QUALITY, FRAUD, COMPLIANCE, ANALYTICAL
- `TemplateVisibility`: PRIVATE, PROJECT, SHARED
- `AuditAction`: LOGIN, LOGOUT, IMPORT, TEST_RUN, PACK_RUN, ENSEMBLE_RUN, EXPORT, NLQ,
  TEMPLATE_CREATE, TEMPLATE_UPDATE

## Current phase

**P1 MVP (weeks 1-7)** — scaffold, DB models, audit log, import, first 20 detectors,
first 50 templates.

## Commands

```bash
docker-compose up -d db                            # start Postgres
alembic upgrade head                               # apply migrations + seed templates
docker-compose up app                              # run API at :8000
docker-compose up ui                               # run Streamlit at :8501
pytest -q                                          # run tests
pytest --cov=backend --cov-report=term-missing     # coverage
```

## Non-negotiables

1. Never implement a named test as a new Python module. Use the template system.
2. Never UPDATE or DELETE the audit_log table. Append only.
3. Every NL query to Claude is logged with prompt, model, response, and the chosen template.
4. Every detector output is hashed. Every test_run record has input_hash and output_hash.
5. Templates are versioned. Editing a template increments `version`, doesn't overwrite.
