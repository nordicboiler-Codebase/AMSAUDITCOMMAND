from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditAction, AuditLog

GENESIS_HASH = "0" * 64


@dataclass
class ChainStatus:
    ok: bool
    total_entries: int
    broken_at: str | None = None
    reason: str | None = None


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(previous_hash: str, payload: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(previous_hash.encode("utf-8"))
    h.update(_canonical(payload).encode("utf-8"))
    return h.hexdigest()


def _last_hash(db: Session, project_id: uuid.UUID | None) -> str:
    q = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).limit(1)
    if project_id is not None:
        q = select(AuditLog).where(AuditLog.project_id == project_id).order_by(
            AuditLog.timestamp.desc(), AuditLog.id.desc()
        ).limit(1)
    row = db.execute(q).scalar_one_or_none()
    return row.current_hash if row else GENESIS_HASH


def log_action(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: AuditAction,
    entity_type: str,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    project_id: uuid.UUID | None = None,
) -> AuditLog:
    entry_id = uuid.uuid4()
    timestamp = datetime.now(timezone.utc)
    details = details or {}
    previous = _last_hash(db, project_id=None)  # chain is global; project_id scopes verify only
    payload = {
        "id": str(entry_id),
        "timestamp": timestamp.isoformat(),
        "user_id": str(user_id) if user_id else None,
        "action": action.value if isinstance(action, AuditAction) else str(action),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
    }
    current = _compute_hash(previous, payload)
    entry = AuditLog(
        id=entry_id,
        timestamp=timestamp,
        user_id=user_id,
        project_id=project_id,
        action=action if isinstance(action, AuditAction) else AuditAction(action),
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        previous_hash=previous,
        current_hash=current,
    )
    db.add(entry)
    db.flush()

    try:
        from backend.services import siem

        siem.forward_event(db, {
            "id": str(entry.id),
            "timestamp": entry.timestamp.isoformat(),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "project_id": str(entry.project_id) if entry.project_id else None,
            "action": entry.action.value if hasattr(entry.action, "value") else str(entry.action),
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "details": entry.details,
            "current_hash": entry.current_hash,
        })
    except Exception:
        pass

    return entry


def verify_chain(db: Session, project_id: uuid.UUID | None = None) -> ChainStatus:
    q = select(AuditLog).order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
    if project_id is not None:
        q = q.where(AuditLog.project_id == project_id)
    rows = list(db.execute(q).scalars())
    previous = GENESIS_HASH
    for row in rows:
        payload = {
            "id": str(row.id),
            "timestamp": row.timestamp.isoformat(),
            "user_id": str(row.user_id) if row.user_id else None,
            "action": row.action.value if hasattr(row.action, "value") else str(row.action),
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "details": row.details or {},
        }
        expected = _compute_hash(previous, payload)
        if row.previous_hash != previous:
            return ChainStatus(ok=False, total_entries=len(rows), broken_at=str(row.id),
                               reason="previous_hash mismatch")
        if row.current_hash != expected:
            return ChainStatus(ok=False, total_entries=len(rows), broken_at=str(row.id),
                               reason="current_hash mismatch (tamper detected)")
        previous = row.current_hash
    return ChainStatus(ok=True, total_entries=len(rows))


def export_log(db: Session, project_id: uuid.UUID | None = None) -> list[dict]:
    q = select(AuditLog).order_by(AuditLog.timestamp.asc())
    if project_id is not None:
        q = q.where(AuditLog.project_id == project_id)
    rows = db.execute(q).scalars().all()
    return [
        {
            "id": str(r.id),
            "timestamp": r.timestamp.isoformat(),
            "user_id": str(r.user_id) if r.user_id else None,
            "action": r.action.value if hasattr(r.action, "value") else str(r.action),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "details": r.details,
            "previous_hash": r.previous_hash,
            "current_hash": r.current_hash,
        }
        for r in rows
    ]


def export_log_pdf(db: Session, project_id: uuid.UUID | None = None) -> bytes:
    from weasyprint import HTML

    entries = export_log(db, project_id=project_id)
    status = verify_chain(db, project_id=project_id)
    rows_html = "".join(
        f"<tr><td>{e['timestamp']}</td><td>{e['action']}</td><td>{e['entity_type']}</td>"
        f"<td>{e.get('entity_id') or ''}</td><td class='mono'>{e['current_hash'][:16]}…</td></tr>"
        for e in entries
    )
    status_color = "green" if status.ok else "red"
    status_text = "VERIFIED" if status.ok else f"BROKEN at {status.broken_at}: {status.reason}"
    html = f"""
    <html><head><style>
      body {{ font-family: DejaVu Sans, sans-serif; font-size: 10pt; }}
      h1 {{ color: #0b2a4a; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: left; }}
      th {{ background: #0b2a4a; color: white; }}
      .mono {{ font-family: DejaVu Sans Mono, monospace; font-size: 8pt; }}
      .status {{ font-weight: bold; color: {status_color}; }}
    </style></head><body>
      <h1>TechSource Audit Log</h1>
      <p>Total entries: {status.total_entries} — <span class="status">{status_text}</span></p>
      <table><thead><tr><th>Timestamp</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Hash</th></tr></thead>
      <tbody>{rows_html}</tbody></table>
    </body></html>
    """
    return HTML(string=html).write_pdf()
