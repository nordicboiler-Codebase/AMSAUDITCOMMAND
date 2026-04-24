"""ML feedback loop: capture labelled outcomes when findings close.

When a finding transitions to CONFIRMED or FALSE_POSITIVE (a human decision),
we record a FindingLabel row keyed to the record + detectors that fired, so
supervised training has a ground-truth corpus to learn from.

Aggregated metrics:
- per-detector precision (TP / (TP + FP))
- per-template precision
- optional weight suggestions (up-weight high-precision, down-weight noisy)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Finding, FindingLabel, FindingStatus, RiskScore


LABEL_TRUE = "TRUE_POSITIVE"
LABEL_FALSE = "FALSE_POSITIVE"


def record_label_on_status_change(db: Session, *, finding: Finding, user_id: uuid.UUID | None) -> None:
    """Called from finding.transition_status when entering CONFIRMED or FALSE_POSITIVE."""
    if finding.status == FindingStatus.CONFIRMED:
        label = LABEL_TRUE
    elif finding.status == FindingStatus.FALSE_POSITIVE:
        label = LABEL_FALSE
    else:
        return

    detector_names: list[str] = []
    template_codes: list[str] = []
    risk = None
    if finding.dataset_id and finding.record_keys:
        rec = finding.record_keys[0]
        rs = db.execute(
            select(RiskScore).where(
                RiskScore.dataset_id == finding.dataset_id,
                RiskScore.record_key == rec,
            ).order_by(RiskScore.computed_at.desc()).limit(1)
        ).scalar_one_or_none()
        if rs:
            risk = rs.score
            detector_names = sorted({c.get("detector_name", "") for c in rs.contributing_detectors or []})
            template_codes = sorted({c.get("template_code") or "" for c in rs.contributing_detectors or []
                                     if c.get("template_code")})

    label_row = FindingLabel(
        finding_id=finding.id, dataset_id=finding.dataset_id,
        record_key=(finding.record_keys[0] if finding.record_keys else None),
        label=label, severity=finding.severity.value,
        detector_names=detector_names, template_codes=template_codes,
        risk_score=risk, labelled_by=user_id,
    )
    db.add(label_row)


def precision_report(db: Session) -> dict[str, Any]:
    rows = list(db.execute(select(FindingLabel)).scalars())

    per_det_tp: dict[str, int] = defaultdict(int)
    per_det_fp: dict[str, int] = defaultdict(int)
    per_tpl_tp: dict[str, int] = defaultdict(int)
    per_tpl_fp: dict[str, int] = defaultdict(int)
    total_tp = total_fp = 0

    for r in rows:
        is_tp = r.label == LABEL_TRUE
        if is_tp:
            total_tp += 1
        else:
            total_fp += 1
        for d in r.detector_names or []:
            (per_det_tp if is_tp else per_det_fp)[d] += 1
        for c in r.template_codes or []:
            (per_tpl_tp if is_tp else per_tpl_fp)[c] += 1

    def _fmt(tp_map: dict, fp_map: dict) -> list[dict]:
        keys = set(tp_map) | set(fp_map)
        out = []
        for k in keys:
            tp = tp_map.get(k, 0)
            fp = fp_map.get(k, 0)
            if tp + fp == 0:
                continue
            precision = tp / (tp + fp)
            out.append({
                "name": k, "true_positive": tp, "false_positive": fp,
                "precision": round(precision, 3),
                "suggested_weight_scale": round(0.3 + 1.7 * precision, 2),
            })
        out.sort(key=lambda r: (-r["precision"], -r["true_positive"]))
        return out

    return {
        "summary": {
            "total_labels": total_tp + total_fp,
            "true_positive": total_tp,
            "false_positive": total_fp,
            "overall_precision": (round(total_tp / max(total_tp + total_fp, 1), 3)),
        },
        "per_detector": _fmt(per_det_tp, per_det_fp),
        "per_template": _fmt(per_tpl_tp, per_tpl_fp),
    }
