from __future__ import annotations

import json
import uuid
from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AuditAction, Dataset, TestRun
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
            "rationale": "Stub: Anthropic API key not configured",
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
    templates = tpl_catalog.list_templates(db, subledger=dataset.subledger_type)[:limit]
    return [
        {"template_code": t.code, "name": t.name, "detector_name": t.detector_name,
         "params": t.default_params, "confidence": 0.5}
        for t in templates
    ]


def generate_narrative(db: Session, *, test_run_id: uuid.UUID, user_id: uuid.UUID) -> str:
    run = db.get(TestRun, test_run_id)
    if not run:
        raise ValueError("Run not found")
    client = _get_client()
    if client is None:
        return (
            f"Test {run.template_code or run.detector_name} ran on "
            f"{run.started_at} and produced {run.findings_count} findings. "
            "Auditor review recommended. (Stub: configure ANTHROPIC_API_KEY for AI-drafted narratives.)"
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
