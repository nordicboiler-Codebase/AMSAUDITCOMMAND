from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.detectors import catalog as det_catalog
from backend.detectors.base import add_key_column
from backend.models import AuditAction, Dataset, Finding, TestRun
from backend.services import audit_log, llm
from backend.services.import_service import resolve_parquet_path
from backend.templates import catalog as tpl_catalog

settings = get_settings()

SYSTEM_PROMPT = """You are an audit analytics assistant. Given a dataset schema, sample rows, subledger type, and a natural language question from an auditor, choose the single best test template from the catalog and fill in its parameters.

Return ONLY valid JSON with this schema:
{
  "template_code": "AP08",
  "params": {...detector params...},
  "rationale": "1-2 sentences",
  "confidence": 0.0-1.0
}

Do not invent template codes that are not in the provided catalog."""

EMAIL_NLQ_HINT = """
EMAIL DATASET GUIDANCE (this dataset is an imported mailbox — one row per message):
- Column meanings: custodian = mailbox owner (one per imported PST file);
  sender_email/sender_domain; all_recipients = to+cc+bcc joined with "; ";
  recipient_domains; subject; body_excerpt (first 4000 chars); has_attachments;
  attachment_names; sent_at (UTC); is_after_hours (before 07:00 / after 20:00);
  is_weekend; folder; direction (SENT/RECEIVED).
- Search-style questions ("find mails from/to/about X", "show emails with
  attachments to gmail in March") → choose the email_search template and fill
  its params: keywords (list, matches subject+body+attachment names),
  exclude_keywords, sender_contains, sender_in (list), recipient_contains
  (substring OR a domain like "gmail.com"), recipient_domain_in (list),
  personal_recipients_only (bool — for "personal/private email"),
  subject_contains, custodian, direction (SENT/RECEIVED), date_from/date_to
  (YYYY-MM-DD), has_attachments (true/false/null), attachment_name_contains,
  after_hours_only, weekend_only, external_only, regex. Arabic keywords are
  matched with spelling-variant folding, so pass the user's Arabic terms as-is.
- For a long, multi-condition request, prefer the dedicated deep-search
  endpoint (POST /api/datasets/{id}/email-search) which compiles the whole
  prompt into a multi-clause plan and returns matching messages directly.
- "Leaked to personal ids / private email / gmail" → choose the email_dlp
  template (optionally set require_attachment or require_keyword, or extend
  sensitive_keywords with terms from the question).
- "Patterns/connections between employees", "common contacts", "collusion"
  across multiple mailboxes → choose the email_cross_custodian template.
- Combine narrow user terms into params rather than dropping them: e.g.
  "salary info sent to personal gmail" → email_dlp with
  sensitive_keywords=["salary","payroll","compensation"] or email_search with
  keywords=["salary"] and recipient_contains="gmail.com".
"""


def _get_client(db: Session):
    """Provider-agnostic client. Falls back to legacy env-based Anthropic."""
    return llm.get_active_client(db)


def ai_status(db: Session | None = None) -> dict:
    """Status for the UI badges. Reads DB if available, else legacy env config."""
    if db is not None:
        s = llm.get_status(db)
        return {
            "enabled": s["enabled"],
            "model": s["model"],
            "reason": s["reason"],
            "active": s["active"],
            "providers": s["providers"],
        }
    # Legacy/no-DB path (kept for tests).
    try:
        from anthropic import Anthropic  # noqa: F401
        sdk_installed = True
    except ImportError:
        sdk_installed = False
    key_set = bool(settings.anthropic_api_key)
    enabled = sdk_installed and key_set
    return {
        "enabled": enabled,
        "model": settings.anthropic_model if enabled else None,
        "reason": "ready" if enabled else "AI disabled — configure a provider in Settings",
        "active": "anthropic" if enabled else None,
        "providers": [],
    }


def _stub_reason(db: Session | None = None) -> str:
    return ai_status(db).get("reason", "AI disabled — configure a provider in Settings")


def _build_catalog_block(db: Session, subledger) -> str:
    rows = tpl_catalog.list_templates(db, subledger=subledger)
    return "\n".join(
        f"- {t.code}: {t.name} → detector={t.detector_name} | "
        f"params={json.dumps(t.default_params)} | weight={t.default_weight}"
        for t in rows
    )


def _dataset_context(dataset: Dataset) -> str:
    head = (
        f"Dataset: {dataset.name} (subledger={dataset.subledger_type.value}, "
        f"records={dataset.record_count})\n"
        f"Schema: {json.dumps(dataset.schema_json)}\n"
    )
    # The parquet may have been imported in a different environment with a
    # different absolute path. Fall back gracefully — schema alone is still
    # useful for template selection.
    try:
        df = pl.read_parquet(resolve_parquet_path(dataset.parquet_path)).head(10)
        return head + f"Sample rows:\n{df.write_csv()}"
    except (FileNotFoundError, OSError) as e:
        return head + f"Sample rows: <unavailable — {e}>"


def nl_to_template(
    db: Session, *, dataset_id: uuid.UUID, question: str, user_id: uuid.UUID,
) -> dict[str, Any]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("Dataset not found")
    client = _get_client(db)
    if client is None:
        first = tpl_catalog.list_templates(db, subledger=dataset.subledger_type)
        tpl = first[0] if first else None
        result = {
            "template_code": tpl.code if tpl else None,
            "params": tpl.default_params if tpl else {},
            "rationale": _stub_reason(db),
            "confidence": 0.0,
        }
        audit_log.log_action(
            db, user_id=user_id, action=AuditAction.NLQ, entity_type="dataset",
            entity_id=str(dataset_id),
            details={"question": question, "stub": True, "chosen": result["template_code"]},
        )
        db.commit()
        return result

    catalog_block = _build_catalog_block(db, dataset.subledger_type)
    email_hint = EMAIL_NLQ_HINT if dataset.subledger_type.value == "EMAIL" else ""
    user_prompt = f"""DATASET CONTEXT:
{_dataset_context(dataset)}
{email_hint}
TEMPLATE CATALOG:
{catalog_block}

AUDITOR QUESTION:
{question}

Choose the best template and return JSON only."""
    text = client.complete(
        system=SYSTEM_PROMPT, user=user_prompt,
        max_tokens=1024, temperature=0.2,
    )
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        parsed = {"error": str(e), "raw": text}

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="dataset",
        entity_id=str(dataset_id),
        details={
            "question": question,
            "provider": client.provider,
            "model": client.model,
            "response": parsed,
            "chosen": parsed.get("template_code"),
        },
    )
    db.commit()
    return parsed


def suggest_templates(db: Session, *, dataset_id: uuid.UUID, user_id: uuid.UUID,
                      limit: int = 10) -> list[dict]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("Dataset not found")
    candidates = tpl_catalog.list_templates(db, subledger=dataset.subledger_type)
    client = _get_client(db)
    if client is None or not candidates:
        # Stub fallback — first N by subledger
        reason = _stub_reason(db) if client is None else "No templates match this subledger."
        return [
            {"template_code": t.code, "name": t.name, "detector_name": t.detector_name,
             "params": t.default_params, "confidence": 0.5,
             "rationale": reason}
            for t in candidates[:limit]
        ]

    catalog_block = "\n".join(
        f"- {t.code}: {t.name} → detector={t.detector_name} | "
        f"category={t.category.value} | weight={t.default_weight}"
        for t in candidates
    )
    email_hint = EMAIL_NLQ_HINT if dataset.subledger_type.value == "EMAIL" else ""
    user_prompt = f"""DATASET CONTEXT:
{_dataset_context(dataset)}
{email_hint}
CANDIDATE TEMPLATES (only these are valid):
{catalog_block}

Pick the {limit} highest-value tests an auditor should run on this dataset
based on its subledger ({dataset.subledger_type.value}), schema columns,
and visible patterns in the sample rows. Return ONLY valid JSON:

{{"suggestions": [
  {{"template_code": "...", "rationale": "1-2 sentences why this matters here", "confidence": 0.0-1.0}},
  ...
]}}

Order from highest to lowest priority. Use only template_codes from the catalog above."""

    text = client.complete(
        system="You are an audit analytics assistant. Suggest the most valuable tests for an auditor to run, given a dataset's nature.",
        user=user_prompt, max_tokens=1500, temperature=0.2,
    )
    parsed: dict[str, Any] = {}
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        parsed = {"suggestions": []}

    by_code = {t.code: t for t in candidates}
    out: list[dict] = []
    for s in parsed.get("suggestions", [])[:limit]:
        code = s.get("template_code")
        tpl = by_code.get(code)
        if not tpl:
            continue
        out.append({
            "template_code": tpl.code,
            "name": tpl.name,
            "detector_name": tpl.detector_name,
            "params": tpl.default_params,
            "confidence": float(s.get("confidence", 0.5)),
            "rationale": s.get("rationale", ""),
        })

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="dataset",
        entity_id=str(dataset_id),
        details={
            "provider": client.provider,
            "model": client.model,
            "kind": "suggest_templates",
            "suggested": [s["template_code"] for s in out],
        },
    )
    db.commit()
    return out


def generate_narrative(db: Session, *, test_run_id: uuid.UUID, user_id: uuid.UUID) -> str:
    run = db.get(TestRun, test_run_id)
    if not run:
        raise ValueError("Run not found")
    client = _get_client(db)
    if client is None:
        return (
            f"[{_stub_reason(db)}]\n\n"
            f"Test {run.template_code or run.detector_name} ran on "
            f"{run.started_at} and produced {run.findings_count} findings. "
            "Auditor review recommended."
        )
    prompt = f"""Draft a 2-paragraph audit finding in professional audit report style for:
- Template: {run.template_code or run.detector_name}
- Findings: {run.findings_count}
- Summary: {json.dumps(run.summary)[:2000]}

Keep factual, avoid speculation, suggest follow-up."""
    text = client.complete(system=None, user=prompt, max_tokens=800, temperature=0.3)
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="test_run",
        entity_id=str(run.id),
        details={"narrative_generated": True, "provider": client.provider, "model": client.model},
    )
    db.commit()
    return text


def generate_finding_narrative(
    db: Session, *, finding_id: uuid.UUID, user_id: uuid.UUID,
) -> str:
    f = db.get(Finding, finding_id)
    if not f:
        raise ValueError("Finding not found")

    client = _get_client(db)
    record_sample = (f.record_keys or [])[:20]
    template_codes = list(f.linked_template_codes or [])

    if client is None:
        return (
            f"[{_stub_reason(db)}]\n\n"
            f"Finding {f.code}: {f.title}. Severity {f.severity.value}. "
            f"{len(f.record_keys or [])} record(s) flagged"
            + (f" by templates {', '.join(template_codes)}" if template_codes else "")
            + ". Auditor review recommended."
        )

    template_block = ""
    if template_codes:
        rows = tpl_catalog.list_templates(db)
        by_code = {t.code: t for t in rows}
        descs = []
        for c in template_codes:
            t = by_code.get(c)
            if t:
                descs.append(f"- {t.code}: {t.name} (detector={t.detector_name})")
        if descs:
            template_block = "\nLinked templates:\n" + "\n".join(descs)

    prompt = f"""Draft a 2-3 paragraph audit finding write-up in professional
audit report style.

Finding code: {f.code}
Title: {f.title}
Severity: {f.severity.value}
Status: {f.status.value}
Records flagged: {len(f.record_keys or [])}
Sample record keys: {record_sample}
Existing description: {f.description or "(none)"}
{template_block}

The narrative should:
- State the issue and why it matters
- Reference the type of analytical test that detected it
- Note the potential impact (control weakness, fraud risk, error, compliance gap)
- Suggest specific follow-up procedures for the auditor
- Stay factual; avoid speculation about intent
- Be ready to paste directly into a workpaper."""

    text = client.complete(system=None, user=prompt, max_tokens=900, temperature=0.3)
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="finding",
        entity_id=str(f.id),
        details={"narrative_generated": True, "provider": client.provider,
                 "model": client.model, "kind": "finding_narrative"},
    )
    db.commit()
    return text


TEMPLATE_GEN_SYSTEM = """You are an audit analytics expert. Your job is to translate
an auditor's plain-English description of a test into a *template proposal* —
a parameter preset bound to one of the existing detectors.

Hard rules:
- You MUST pick a detector_name from the catalog provided. Inventing a new
  detector is forbidden. If no detector fits, set "detector_name" to null and
  explain in "rationale".
- default_params keys MUST exist in the chosen detector's params. Do not invent
  parameter keys. Use sensible values that match the auditor's description.
- code: short uppercase alphanumeric, 4-12 chars (e.g. AP_DUP_INV_30D, GL_ROUND).
- name: human-readable, ~6 words.
- category: one of DATA_QUALITY, FRAUD, COMPLIANCE, ANALYTICAL.
- subledger: one of GENERAL_LEDGER, ACCOUNTS_PAYABLE, ACCOUNTS_RECEIVABLE,
  PAYROLL, FIXED_ASSETS, INVENTORY, BANK, PROCUREMENT, TE, SALES, OTHER, or
  null if universal.
- default_weight: 1.0-10.0 — higher = more weight in the ensemble risk score.
- tags: 0-5 short lowercase tokens.

Return ONLY valid JSON with this schema:
{
  "code": "...",
  "name": "...",
  "description": "1-2 sentence description for the auditor",
  "detector_name": "...",
  "default_params": { ... },
  "category": "...",
  "subledger": "..." or null,
  "default_weight": 5.0,
  "tags": ["..."],
  "rationale": "Why this detector + these params answer the auditor's question."
}"""


EMAIL_SEARCH_COMPILER_SYSTEM = """You compile a detailed plain-English (or
Arabic) investigation request into a STRUCTURED SEARCH PLAN over a mailbox
dataset (one row per email message). You do not answer the question — you
translate it into machine-runnable filters.

The dataset rows have these searchable fields: custodian (mailbox owner),
sender_email, sender_domain, all_recipients, recipient_domains, subject,
body_excerpt, attachment_names, has_attachments, sent_at (UTC), is_after_hours,
is_weekend, folder, direction (SENT/RECEIVED).

A plan is a list of CLAUSES. Each clause is one parameter set for the
email_search engine. Clauses are combined with OR (a message matches the plan
if it matches ANY clause) when combine="union", or AND when combine="intersect".
Within a single clause, every non-empty parameter must hold (AND), and list
parameters match ANY of their members.

Use MULTIPLE clauses only when the request needs OR across criteria that can't
live in one clause (e.g. "from Ali OR anyone in finance" → one clause per
group). Prefer the list parameters (sender_in, recipient_domain_in, keywords)
to keep the plan small. Most requests are a single clause.

email_search parameters (all optional; omit what you don't need):
- keywords: list[str] — ANY appears in subject/body/attachment names
- match_all_keywords: bool — require ALL keywords instead of ANY
- exclude_keywords: list[str] — drop the message if ANY appears
- sender_contains: str ; sender_in: list[str] — sender matches ANY substring
- recipient_contains: str — substring or a single domain
- recipient_domain_in: list[str] — recipient on ANY of these domains
- personal_recipients_only: bool — recipient on a personal/free provider
  (gmail/yahoo/hotmail/outlook/icloud/proton/… — use this for "personal email",
  "private account", "non-corporate")
- subject_contains: str ; exclude_subject_contains: str
- custodian: str — restrict to one mailbox owner
- folder_contains: str — e.g. "sent", "deleted"
- direction: "SENT" | "RECEIVED"
- date_from / date_to: "YYYY-MM-DD" (inclusive)
- has_attachments: true | false
- attachment_name_contains: str
- after_hours_only: bool (before 07:00 / after 20:00 local)
- weekend_only: bool
- external_only: bool — recipient domain differs from the sender's
- regex: str — applied to subject+body (use sparingly)

Rules:
- Keep the user's Arabic terms AS-IS in keywords — the engine folds Arabic
  spelling variants automatically. Add obvious English synonyms too when the
  intent is clear (e.g. "أسعار" → also "price","pricing").
- Resolve relative dates against the provided CURRENT DATE.
- Never invent a custodian/sender name the user didn't mention; use substrings
  of the names they gave.
- If the request has no usable filter, return an empty clauses list and explain
  in "interpretation".

Return ONLY valid JSON:
{
  "clauses": [ {"label": "short label", "params": { ...email_search params... }}, ... ],
  "combine": "union" | "intersect",
  "interpretation": "one sentence restating exactly what will be searched",
  "rationale": "why these clauses/params"
}"""


def compile_and_run_email_search(
    db: Session, *, dataset_id: uuid.UUID, prompt: str, user_id: uuid.UUID,
    limit: int = 500,
) -> dict[str, Any]:
    """Compile a detailed NL prompt into an email_search plan via the LLM, run
    every clause against the dataset, union/intersect the results, and return
    the matching messages directly.

    This is the one-shot "natural-language deep search" path: prompt in,
    matching emails out — distinct from nl_to_template which only proposes a
    template for the user to run by hand.
    """
    from datetime import date as _date

    from backend.detectors import catalog as det_catalog
    from backend.services.import_service import resolve_parquet_path

    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("Dataset not found")
    if dataset.subledger_type.value != "EMAIL":
        raise ValueError("Email search only applies to EMAIL datasets (import mailboxes first).")

    client = _get_client(db)
    if client is None:
        return {"error": _stub_reason(db),
                "interpretation": "Configure an AI provider in Settings → AI Providers.",
                "clauses": [], "messages": [], "total": 0}

    user_prompt = f"""CURRENT DATE: {_date.today().isoformat()}

DATASET: {dataset.name} — {dataset.record_count} messages.
Columns present: {json.dumps(list(dataset.schema_json.keys()))}

INVESTIGATION REQUEST:
{prompt}

Compile the search plan. Return JSON only."""

    text = client.complete(
        system=EMAIL_SEARCH_COMPILER_SYSTEM, user=user_prompt,
        max_tokens=1800, temperature=0.1,
    )
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        plan = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        audit_log.log_action(
            db, user_id=user_id, action=AuditAction.NLQ, entity_type="dataset",
            entity_id=str(dataset_id),
            details={"kind": "email_search", "prompt": prompt[:500],
                     "provider": client.provider, "model": client.model,
                     "error": f"unparseable_plan:{e}"},
        )
        db.commit()
        return {"error": f"Could not parse the search plan: {e}", "raw": text,
                "clauses": [], "messages": [], "total": 0}

    clauses = plan.get("clauses") or []
    combine = (plan.get("combine") or "union").lower()
    if not clauses:
        return {
            "interpretation": plan.get("interpretation",
                                       "No usable filters could be derived from the request."),
            "rationale": plan.get("rationale", ""),
            "clauses": [], "messages": [], "total": 0,
            "provider": client.provider, "model": client.model,
        }

    det_catalog.load_all()
    detector = det_catalog.get("email_search")
    df = pl.read_parquet(resolve_parquet_path(dataset.parquet_path))

    # Run each clause; collect matched record keys + the reason from each clause.
    key_reasons: dict[str, list[str]] = {}
    per_clause_counts: list[dict] = []
    matched_sets: list[set[str]] = []
    for clause in clauses:
        params = {**(detector.default_params or {}), **(clause.get("params") or {})}
        result = detector.run(df, params)
        clause_keys = set(result.flagged["_record_key"].to_list()) if result.flagged.height else set()
        matched_sets.append(clause_keys)
        label = clause.get("label") or "clause"
        for s in result.per_record_scores or []:
            key_reasons.setdefault(s.record_key, []).append(f"[{label}] {s.reason}")
        per_clause_counts.append({"label": label, "matched": len(clause_keys),
                                  "params": clause.get("params") or {}})

    if combine == "intersect" and matched_sets:
        final_keys = set.intersection(*matched_sets)
    else:
        final_keys = set().union(*matched_sets) if matched_sets else set()

    df_keyed = add_key_column(df)
    matched = df_keyed.filter(pl.col("_record_key").is_in(list(final_keys)))
    if "sent_at" in matched.columns:
        matched = matched.sort("sent_at", descending=True, nulls_last=True)

    display_cols = [c for c in [
        "sent_at", "custodian", "direction", "sender_email", "all_recipients",
        "subject", "has_attachments", "attachment_names", "folder", "_record_key",
    ] if c in matched.columns]
    head = matched.select(display_cols).head(limit)
    messages = []
    for row in head.to_dicts():
        rk = row.get("_record_key")
        row["match_reason"] = "; ".join(key_reasons.get(rk, [])[:6])
        if isinstance(row.get("sent_at"), (datetime,)):
            row["sent_at"] = row["sent_at"].isoformat()
        messages.append(row)

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="dataset",
        entity_id=str(dataset_id),
        details={
            "kind": "email_search", "prompt": prompt[:500],
            "provider": client.provider, "model": client.model,
            "combine": combine, "clauses": per_clause_counts,
            "total_matched": len(final_keys),
            "interpretation": (plan.get("interpretation") or "")[:300],
        },
    )
    db.commit()
    return {
        "interpretation": plan.get("interpretation", ""),
        "rationale": plan.get("rationale", ""),
        "combine": combine,
        "clauses": per_clause_counts,
        "total": len(final_keys),
        "returned": len(messages),
        "messages": messages,
        "provider": client.provider,
        "model": client.model,
    }


def generate_template_from_description(
    db: Session, *, description: str, dataset_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Translate an auditor's description into a proposed template (DB row).

    Does NOT save the template — returns a proposal the user reviews and
    commits via POST /api/templates. The proposal is validated against the
    detector catalog server-side: invalid detector_name or invalid param keys
    are stripped before returning.
    """
    client = _get_client(db)
    if client is None:
        return {
            "error": _stub_reason(db),
            "rationale": "Configure an AI provider in Settings → AI Providers to "
                         "use plain-English template generation.",
        }

    det_catalog.load_all()
    detectors = det_catalog.list_all()
    detector_block_lines = []
    for d in detectors:
        keys = list((d.default_params or {}).keys())
        cat = d.category.value if hasattr(d.category, "value") else str(d.category)
        detector_block_lines.append(
            f"- {d.name} (category={cat}): {d.description}\n"
            f"  param keys: {keys}\n"
            f"  default params: {json.dumps(d.default_params)[:300]}"
        )
    detector_block = "\n".join(detector_block_lines)

    dataset_block = ""
    if dataset_id:
        ds = db.get(Dataset, dataset_id)
        if ds:
            dataset_block = "\n\nDATASET CONTEXT (use the columns and subledger):\n" + _dataset_context(ds)

    user_prompt = f"""AUDITOR DESCRIPTION OF THE TEST THEY WANT:
{description}

DETECTOR CATALOG (only these are valid):
{detector_block}
{dataset_block}

Pick the best-matching detector_name and design a template around it.
Return JSON only."""

    text = client.complete(
        system=TEMPLATE_GEN_SYSTEM, user=user_prompt,
        max_tokens=1500, temperature=0.2,
    )

    parsed: dict[str, Any] = {}
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        parsed = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        parsed = {"error": f"Could not parse model output as JSON: {e}", "raw": text}

    # Server-side validation against the detector catalog.
    detector_name = parsed.get("detector_name")
    if detector_name:
        try:
            det = det_catalog.get(detector_name)
            valid_keys = set((det.default_params or {}).keys())
            params = parsed.get("default_params") or {}
            # Strip params whose keys aren't real for this detector.
            stripped = {k: v for k, v in params.items() if k in valid_keys}
            removed = sorted(set(params) - valid_keys)
            parsed["default_params"] = stripped
            if removed:
                parsed["validation_warnings"] = [
                    f"Removed params not on detector {detector_name}: {removed}"
                ]
        except KeyError:
            parsed["error"] = f"Model picked unknown detector: {detector_name}"
            parsed["detector_name"] = None

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="template",
        entity_id=None,
        details={
            "kind": "generate_template_from_description",
            "description": description[:500],
            "provider": client.provider,
            "model": client.model,
            "proposed_code": parsed.get("code"),
            "proposed_detector": parsed.get("detector_name"),
            "rationale": (parsed.get("rationale") or "")[:300],
        },
    )
    db.commit()
    return parsed
