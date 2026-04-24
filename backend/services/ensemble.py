from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

import polars as pl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import AuditAction, EnsembleRun, RiskScore, TestRun
from backend.models.enums import RunStatus
from backend.services import audit_log, test_runner
from backend.templates import catalog as tpl_catalog


def compute_ensemble(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    test_run_ids: list[uuid.UUID],
    user_id: uuid.UUID,
) -> EnsembleRun:
    # Idempotency: remove any prior scores for this dataset before writing new ones.
    # An ensemble is always "full state" — we rank every scored record. Allowing
    # multiple ensemble runs to accumulate makes /risk-scores non-deterministic.
    db.execute(delete(RiskScore).where(RiskScore.dataset_id == dataset_id))
    er = EnsembleRun(
        dataset_id=dataset_id,
        test_run_ids=[str(i) for i in test_run_ids],
        run_by=user_id,
        status=RunStatus.RUNNING,
    )
    db.add(er)
    db.flush()

    per_record: dict[str, list[dict]] = defaultdict(list)
    runs = list(db.execute(select(TestRun).where(TestRun.id.in_(test_run_ids))).scalars())
    total_weight = 0.0
    for run in runs:
        scores_df = test_runner.load_scores(run)
        if scores_df.height == 0:
            continue
        weight = 1.0
        if run.template_code:
            try:
                tpl = tpl_catalog.get_template(db, run.template_code)
                weight = float(tpl.default_weight or 1.0)
            except Exception:
                pass
        total_weight += weight
        raw_scores = scores_df["score"].cast(pl.Float64, strict=False).to_list()
        if not raw_scores:
            continue
        mn = min(raw_scores)
        mx = max(raw_scores)
        rng = mx - mn
        keys = scores_df["record_key"].to_list()
        reasons = scores_df["reason"].to_list()
        for k, s, reason in zip(keys, raw_scores, reasons):
            if rng > 0:
                norm = (s - mn) / rng
            else:
                norm = 1.0 if s > 0 else 0.0
            per_record[str(k)].append({
                "detector_name": run.detector_name,
                "template_code": run.template_code,
                "test_run_id": str(run.id),
                "raw_signal": float(s),
                "normalised_signal": float(norm),
                "weight": weight,
                "reason": reason,
            })

    max_possible_weight = total_weight if total_weight > 0 else 1.0
    risk_rows: list[RiskScore] = []
    for key, contribs in per_record.items():
        weighted = sum(c["normalised_signal"] * c["weight"] for c in contribs)
        score = min(100.0, (weighted / max_possible_weight) * 100.0)
        risk_rows.append(
            RiskScore(
                dataset_id=dataset_id,
                ensemble_run_id=er.id,
                record_key=key,
                score=score,
                contributing_detectors=contribs,
            )
        )
    if risk_rows:
        db.add_all(risk_rows)

    er.status = RunStatus.COMPLETED
    er.finished_at = datetime.now(timezone.utc)
    er.summary = {
        "test_runs_included": len(runs),
        "records_scored": len(risk_rows),
        "max_score": max((r.score for r in risk_rows), default=0),
        "mean_score": sum(r.score for r in risk_rows) / len(risk_rows) if risk_rows else 0,
    }

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.ENSEMBLE_RUN, entity_type="ensemble_run",
        entity_id=str(er.id),
        details={"test_run_count": len(runs), "records_scored": len(risk_rows)},
    )
    db.commit()
    return er
