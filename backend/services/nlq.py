from __future__ import annotations

import json
import uuid
from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AuditAction, Dataset, Finding, TestRun
from backend.services import audit_log
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


def _get_client():
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    if not settings.anthropic_api_key:
        return None
    return Anthropic(api_key=settings.anthropic_api_key)


def ai_status() -> dict:
    """Returns whether Claude is wired up, and why not if not."""
    try:
        from anthropic import Anthropic  # noqa: F401
        sdk_installed = True
    except ImportError:
        sdk_installed = False
    key_set = bool(settings.anthropic_api_key)
    enabled = sdk_installed and key_set
    if enabled:
        reason = "ready"
    elif not sdk_installed:
        reason = "anthropic SDK not installed in this environment"
    else:
        reason = "ANTHROPIC_API_KEY not set in .env"
    return {
        "enabled": enabled,
        "model": settings.anthropic_model if enabled else None,
        "reason": reason,
        "sdk_installed": sdk_installed,
        "key_set": key_set,
    }


def _stub_reason() -> str:
    s = ai_status()
    if not s["sdk_installed"]:
        return "AI disabled — anthropic SDK not installed (run: pip install anthropic)"
    return "AI disabled — ANTHROPIC_API_KEY not set in .env"


def _build_catalog_block(db: Session, subledger) -> str:
    rows = tpl_catalog.list_templates(db, subledger=subledger)
    return "\n".join(
        f"- {t.code}: {t.name} → detector={t.detector_name} | "
        f"params={json.dumps(t.default_params)} | weight={t.default_weight}"
        for t in rows
    )


def _dataset_context(dataset: Dataset) -> str:
    df = pl.read_parquet(dataset.parquet_path).head(10)
    return (
        f"Dataset: {dataset.name} (subledger={dataset.subledger_type.value}, "
        f"records={dataset.record_count})\n"
        f"Schema: {json.dumps(dataset.schema_json)}\n"
        f"Sample rows:\n{df.write_csv()}"
    )


def nl_to_template(
    db: Session, *, dataset_id: uuid.UUID, question: str, user_id: uuid.UUID,
) -> dict[str, Any]:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError("Dataset not found")
    client = _get_client()
    if client is None:
        first = tpl_catalog.list_templates(db, subledger=dataset.subledger_type)
        tpl = first[0] if first else None
        result = {
            "template_code": tpl.code if tpl else None,
            "params": tpl.default_params if tpl else {},
            "rationale": _stub_reason(),
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
    user_prompt = f"""DATASET CONTEXT:
{_dataset_context(dataset)}

TEMPLATE CATALOG:
{catalog_block}

AUDITOR QUESTION:
{question}

Choose the best template and return JSON only."""
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        temperature=0.2,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
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
            "model": settings.anthropic_model,
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
    client = _get_client()
    if client is None or not candidates:
        # Stub fallback — first N by subledger
        reason = _stub_reason() if client is None else "No templates match this subledger."
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
    user_prompt = f"""DATASET CONTEXT:
{_dataset_context(dataset)}

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

    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        temperature=0.2,
        system="You are an audit analytics assistant. Suggest the most valuable tests for an auditor to run, given a dataset's nature.",
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
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
            "model": settings.anthropic_model,
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
    client = _get_client()
    if client is None:
        return (
            f"[{_stub_reason()}]\n\n"
            f"Test {run.template_code or run.detector_name} ran on "
            f"{run.started_at} and produced {run.findings_count} findings. "
            "Auditor review recommended."
        )
    prompt = f"""Draft a 2-paragraph audit finding in professional audit report style for:
- Template: {run.template_code or run.detector_name}
- Findings: {run.findings_count}
- Summary: {json.dumps(run.summary)[:2000]}

Keep factual, avoid speculation, suggest follow-up."""
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=800,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="test_run",
        entity_id=str(run.id),
        details={"narrative_generated": True, "model": settings.anthropic_model},
    )
    db.commit()
    return text


def generate_finding_narrative(
    db: Session, *, finding_id: uuid.UUID, user_id: uuid.UUID,
) -> str:
    f = db.get(Finding, finding_id)
    if not f:
        raise ValueError("Finding not found")

    client = _get_client()
    record_sample = (f.record_keys or [])[:20]
    template_codes = list(f.linked_template_codes or [])

    if client is None:
        return (
            f"[{_stub_reason()}]\n\n"
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

    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=900,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.NLQ, entity_type="finding",
        entity_id=str(f.id),
        details={"narrative_generated": True, "model": settings.anthropic_model,
                 "kind": "finding_narrative"},
    )
    db.commit()
    return text
