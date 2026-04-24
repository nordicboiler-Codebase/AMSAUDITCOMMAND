from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditAction, TestTemplate
from backend.models.enums import SubledgerType, TemplateVisibility
from backend.services import audit_log
from backend.templates import catalog as tpl_catalog


def publish_template(
    db: Session, *, template_id: uuid.UUID, visibility: TemplateVisibility, user_id: uuid.UUID,
) -> TestTemplate:
    tpl = db.get(TestTemplate, template_id)
    if not tpl:
        raise tpl_catalog.TemplateError("Template not found")
    previous = tpl.visibility
    tpl.visibility = visibility
    db.flush()
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_PUBLISH, entity_type="test_template",
        entity_id=str(tpl.id),
        details={"code": tpl.code, "from": previous.value if previous else None, "to": visibility.value},
    )
    db.commit()
    return tpl


def fork_template(
    db: Session, *, code: str, target_project_id: uuid.UUID, user_id: uuid.UUID,
    overrides: dict[str, Any] | None = None, new_code: str | None = None,
) -> TestTemplate:
    cloned = tpl_catalog.clone_template(db, code, target_project_id, user_id,
                                        overrides=overrides, new_code=new_code)
    db.commit()
    return cloned


def list_shared_templates(
    db: Session, *, subledger: SubledgerType | None = None,
    tags: list[str] | None = None, search: str | None = None,
) -> list[TestTemplate]:
    q = select(TestTemplate).where(TestTemplate.visibility == TemplateVisibility.SHARED)
    if subledger is not None:
        q = q.where(
            (TestTemplate.subledger_type == subledger) | (TestTemplate.subledger_type.is_(None))
        )
    if tags:
        q = q.where(TestTemplate.tags.overlap(tags))
    if search:
        pattern = f"%{search}%"
        q = q.where(TestTemplate.name.ilike(pattern) | TestTemplate.description.ilike(pattern))
    q = q.order_by(TestTemplate.code, TestTemplate.version.desc())
    return list(db.execute(q).scalars())


def get_template_versions(db: Session, code: str) -> list[TestTemplate]:
    q = select(TestTemplate).where(TestTemplate.code == code).order_by(TestTemplate.version.desc())
    return list(db.execute(q).scalars())


def diff_template_versions(db: Session, code: str, v1: int, v2: int) -> dict[str, Any]:
    q = select(TestTemplate).where(TestTemplate.code == code, TestTemplate.version.in_([v1, v2]))
    versions = {t.version: t for t in db.execute(q).scalars()}
    if v1 not in versions or v2 not in versions:
        raise tpl_catalog.TemplateError(f"Versions {v1}/{v2} not both present for {code}")
    a, b = versions[v1], versions[v2]
    return {
        "code": code,
        "v1": v1,
        "v2": v2,
        "name": {"from": a.name, "to": b.name} if a.name != b.name else None,
        "weight": {"from": a.default_weight, "to": b.default_weight}
        if a.default_weight != b.default_weight else None,
        "tags": {"from": list(a.tags or []), "to": list(b.tags or [])}
        if list(a.tags or []) != list(b.tags or []) else None,
        "params_diff": _param_diff(a.default_params or {}, b.default_params or {}),
    }


def _param_diff(a: dict, b: dict) -> dict[str, Any]:
    diff: dict[str, Any] = {"added": {}, "removed": {}, "changed": {}}
    for k, v in b.items():
        if k not in a:
            diff["added"][k] = v
        elif a[k] != v:
            diff["changed"][k] = {"from": a[k], "to": v}
    for k, v in a.items():
        if k not in b:
            diff["removed"][k] = v
    return diff
