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

**Phase A — Table stakes complete.** On top of the P1 MVP (35 detectors, 143 templates,
10 packs, ensemble scoring, tamper-evident audit log, Streamlit UI), the following
enterprise controls are now in place:

1. **Single Sign-On (OAuth2)** — configurable in-app under Settings → SSO; Azure AD preset,
   also supports Google / Okta / generic OIDC. Auto-provisions users on first login with
   configurable allowed domains + default role.
2. **MFA (TOTP)** — enrol via Settings → My MFA (QR + provisioning URI). Login flow
   detects mfa-enabled users and requests a 6-digit code via `/api/auth/mfa/verify`.
3. **Email (modern authentication)** — configurable under Settings → Email. Supports
   SMTP (optionally with XOAUTH2 client-credentials) or Microsoft Graph `sendMail`
   (OAuth2 app-only). Includes a "Send test email" admin button.
4. **Project-level access control** — `project_members` table, roles OWNER/EDITOR/
   REVIEWER/VIEWER, permission matrix enforced on projects, datasets, runs, packs,
   ensemble, risk scores, findings. Project owners + ADMIN can manage membership.
5. **Findings Register + maker-checker** — `findings` table with statuses
   DRAFT → UNDER_REVIEW → CONFIRMED/FALSE_POSITIVE → REMEDIATED/ACCEPTED_RISK/
   CARRIED_FORWARD. Reviewer transitions require REVIEW permission and reviewer
   must not be the creator/owner of the finding. Comments with sign-off flag.
6. **Data retention policy** — configurable in Settings → Data Retention. Per-subledger
   days override global default. Dry-run scan + irreversible purge (ADMIN only). Optionally
   preserves datasets referenced by open findings. All purges logged to audit_log.
7. **Charts in PDF reports** — Benford distributions, aging histograms, Pareto charts,
   risk-score distributions, inlined as SVG in template + pack report PDFs via matplotlib
   + WeasyPrint.
8. **UX polish** — spinners + toast notifications on long ops (import, pack run, ensemble);
   parsed `{detail: ...}` error surfacing (no raw tracebacks).
9. **Encrypted uploads at rest** — raw source files are stored Fernet-encrypted in
   `data/uploads/`; plaintext only exists as a short-lived temp file during import.

**Phase B — ACL-parity complete.** Additional deliverables:

10. **Scheduled runs + alerts** — cron-based schedule engine (APScheduler + croniter).
    Per-schedule target (PACK or TEMPLATE), optional auto-ensemble, email alerts when
    max risk score crosses a configurable threshold.
11. **Engagement workspace** — `engagements` table. Scope, period, lead auditor, reviewer.
    Status workflow PLANNING → IN_PROGRESS → REVIEW → FINALISED → ARCHIVED. Maker-checker
    on finalise. Links datasets + pack runs + findings. Executive summary.
12. **KPI dashboard** — real metrics at `/api/metrics/dashboard`: projects, open findings,
    severity breakdown, status breakdown, 12-week finding trend, top risky records.
13. **Auto-rendered param forms** — `/api/templates/detectors/{name}/schema` returns
    typed fields. UI Run page renders proper inputs (text, number, date, list, checkbox)
    instead of a JSON textbox.
14. **ERP connectors** — pluggable framework with SFTP, SAP S/4HANA OData v4, Oracle Fusion
    REST. `POST /api/connectors/pull-and-import` pulls from source, stages, hashes, imports
    as a Dataset in one call.
15. **BI export feeds** — `/api/bi/findings.csv`, `/api/bi/risk_scores.csv`,
    `/api/bi/test_runs.csv` consumable by Power BI Web connector, Tableau WDC, Excel.
    Manifest at `/api/bi/manifest.json`.

**Phase C — Enterprise polish complete.** Additional deliverables:

16. **Bilingual UI** — English + Arabic JSON catalogs, language picker in login and
    sidebar, automatic RTL CSS when Arabic selected. Translation helper `t("key")`.
17. **Workpaper export** — `/api/engagements/{id}/workpaper.zip` produces an evidence
    bundle (manifest.json with hashes, findings.csv, test_runs.csv, audit_chain.json,
    per-run sample flagged rows, README with CaseWare / IDEA / TeamMate import
    instructions).
18. **Per-project branding** — projects table gains logo_data_uri, brand_primary,
    brand_accent, legal_footer, report_language. Template PDF reports honour these.
    `PUT /api/projects/{id}/branding` (ADMIN).
19. **Continuous monitoring** — `monitors` table. An enabled monitor matching a newly
    imported dataset's subledger auto-runs its pack + ensemble and auto-creates DRAFT
    findings for records above a configurable threshold. Alerts routed via the email
    service from Phase A.
20. **Hardening** — in-process token-bucket rate limiter (10 logins/min/IP, 600
    requests/min/IP globally, 30 NLQ/min/IP). Password strength check at registration
    (≥10 chars, ≥3 character classes).

**Phase D — Hardening pass (from tester review) complete.** Additional fixes:

21. **Dataset integrity check** — test_runner aborts if parquet row count differs from
    manifest captured at import time.
22. **Encrypted source re-download** — `GET /api/datasets/{id}/source` (ADMIN-only)
    decrypts the original upload on demand and verifies SHA-256 against the import
    hash before serving.
23. **Ensemble idempotency** — `compute_ensemble` deletes any prior RiskScore rows for
    the dataset before writing new ones. No more duplicate top-N.
24. **Scheduler multi-worker safety** — Postgres advisory lock (`pg_try_advisory_lock`)
    around the tick loop. Only one worker fires schedules at a time.
25. **Fernet keychain rotation** — `SECRET_KEY` encrypts, `SECRET_KEY_PREVIOUS`
    decrypts old ciphertext. `rotate_bytes()` / `rotate_secret()` available for a
    re-encrypt batch.
26. **Pagination + latest-ensemble filter** — findings, risk-scores, runs accept
    `offset` / `limit`; risk-scores accepts `ensemble_run_id` to scope to a run.
27. **NLQ rate limit wired** — `/api/datasets/{id}/nlq`, `/suggest-templates`,
    `/test-runs/{id}/narrative` all enforce 30/min/IP.
28. **Missing routes added** — template `PUT`, project `DELETE`, dataset `DELETE`,
    user `POST/PATCH/deactivate`, auth `/refresh`.
29. **Retention respects open findings only** — closed findings (REMEDIATED /
    ACCEPTED_RISK / FALSE_POSITIVE) no longer block purge.
30. **5 orphan detectors now have templates** — AN08 sequence_order, AN09 stratify,
    AN10 histogram, AN11 cross_tabulate, U16 text_anomaly. Total templates now 148.
31. **Workpaper bundle signature** — SHA-256 + HMAC-SHA256 detached sig file inside
    the exported zip.
32. **FastAPI lifespan migration** — replaced deprecated `@app.on_event("startup")`.
33. **Session expiry warning** — UI banner when < 5 minutes remain on JWT + one-click
    `/api/auth/refresh`.
34. **Connector secrets redacted** in audit log details.
35. **Dataset name uniqueness** enforced per project at import.
36. **Auto-findings prefixed `AUTO-`** so human vs monitor findings are distinguishable.
37. **Audit-log JSON returns chain envelope** — `{chain: {ok, broken_at}, entries: [...]}`.
38. **Email retry** with exponential backoff (1s, 2s, 4s) on transient failures.
39. **Finding attachments** — encrypted-at-rest, hash-verified on download.
40. **Dataset classification tag** — PDPL / NESA-style labelling (PUBLIC / INTERNAL /
    CONFIDENTIAL / RESTRICTED).
41. **SIEM webhook feed** — every audit_log entry fire-and-forwards to a configured
    collector URL (fire-and-forget, 3s timeout, never blocks).

## Deployment notes

- **CSRF**: the API uses bearer tokens in the `Authorization` header with permissive CORS.
  If you put Streamlit (or any browser client) behind a reverse proxy that sets a
  session cookie, add CSRF middleware — bearer-only endpoints are safe, cookie-backed
  ones would need protection.
- **Multi-worker**: scheduler now uses a Postgres advisory lock; safe to run
  `uvicorn --workers N`. Rate limiter is still in-process — for multi-host use Redis.
- **Key rotation**: set new `SECRET_KEY`, keep the old as `SECRET_KEY_PREVIOUS`
  (comma-separated if multiple), restart; ciphertext decrypts transparently.
  Schedule `rotate_secret()` to re-encrypt historical ciphertext.

Phase D candidates (not yet done): AG Grid in Risk Explorer, mobile/tablet responsive,
Redis rate limiter for multi-worker, supervised ML with labelled finding feedback,
SCIM user provisioning, fine-grained per-field data-access policies.

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
