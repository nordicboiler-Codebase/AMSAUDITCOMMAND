from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.detectors import catalog as det_catalog
from backend.models import AuditAction, TestTemplate
from backend.models.enums import SubledgerType, TemplateCategory, TemplateVisibility
from backend.services import audit_log


class TemplateError(Exception):
    pass


def list_templates(
    db: Session,
    *,
    subledger: SubledgerType | None = None,
    category: TemplateCategory | None = None,
    tags: list[str] | None = None,
    search: str | None = None,
    include_universal: bool = True,
) -> list[TestTemplate]:
    det_catalog.load_all()
    q = select(TestTemplate)
    if subledger is not None and include_universal:
        q = q.where((TestTemplate.subledger_type == subledger) | (TestTemplate.subledger_type.is_(None)))
    elif subledger is not None:
        q = q.where(TestTemplate.subledger_type == subledger)
    if category is not None:
        q = q.where(TestTemplate.category == category)
    if tags:
        q = q.where(TestTemplate.tags.overlap(tags))
    if search:
        pattern = f"%{search}%"
        q = q.where((TestTemplate.name.ilike(pattern)) | (TestTemplate.description.ilike(pattern)))
    q = q.order_by(TestTemplate.code, TestTemplate.version.desc())
    return list(db.execute(q).scalars())


def get_template(db: Session, code: str, version: int | None = None) -> TestTemplate:
    q = select(TestTemplate).where(TestTemplate.code == code)
    if version is not None:
        q = q.where(TestTemplate.version == version)
    else:
        q = q.order_by(TestTemplate.version.desc())
    tpl = db.execute(q).scalars().first()
    if not tpl:
        raise TemplateError(f"Template not found: {code}")
    return tpl


def _validate_detector(detector_name: str, params: dict[str, Any]) -> None:
    try:
        detector = det_catalog.get(detector_name)
    except KeyError as e:
        raise TemplateError(str(e)) from e
    defaults = detector.default_params or {}
    for k in params.keys():
        if k not in defaults and not k.startswith("_"):
            pass


def create_template(
    db: Session,
    *,
    code: str,
    name: str,
    detector_name: str,
    default_params: dict[str, Any],
    description: str = "",
    subledger: SubledgerType | None = None,
    category: TemplateCategory = TemplateCategory.ANALYTICAL,
    default_weight: float = 1.0,
    tags: list[str] | None = None,
    owner_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    visibility: TemplateVisibility = TemplateVisibility.PRIVATE,
    is_system: bool = False,
    user_id: uuid.UUID | None = None,
) -> TestTemplate:
    det_catalog.load_all()
    _validate_detector(detector_name, default_params)
    existing = db.execute(select(TestTemplate).where(TestTemplate.code == code)).scalars().first()
    if existing:
        raise TemplateError(f"Template code already exists: {code}")
    tpl = TestTemplate(
        code=code,
        name=name,
        description=description,
        detector_name=detector_name,
        default_params=default_params,
        subledger_type=subledger,
        category=category,
        default_weight=default_weight,
        tags=tags or [],
        owner_id=owner_id,
        project_id=project_id,
        visibility=visibility,
        is_system=is_system,
        version=1,
    )
    db.add(tpl)
    db.flush()
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_CREATE, entity_type="test_template",
        entity_id=str(tpl.id), details={"code": code, "detector": detector_name}
    )
    return tpl


def update_template(
    db: Session,
    code: str,
    *,
    name: str | None = None,
    description: str | None = None,
    default_params: dict[str, Any] | None = None,
    default_weight: float | None = None,
    tags: list[str] | None = None,
    user_id: uuid.UUID | None = None,
) -> TestTemplate:
    prev = get_template(db, code)
    new_tpl = TestTemplate(
        code=prev.code,
        name=name or prev.name,
        description=description if description is not None else prev.description,
        detector_name=prev.detector_name,
        default_params=default_params if default_params is not None else prev.default_params,
        subledger_type=prev.subledger_type,
        category=prev.category,
        default_weight=default_weight if default_weight is not None else prev.default_weight,
        tags=tags if tags is not None else list(prev.tags or []),
        owner_id=prev.owner_id,
        project_id=prev.project_id,
        visibility=prev.visibility,
        is_system=prev.is_system,
        version=prev.version + 1,
        parent_template_id=prev.id,
    )
    _validate_detector(new_tpl.detector_name, new_tpl.default_params)
    db.add(new_tpl)
    db.flush()
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_UPDATE, entity_type="test_template",
        entity_id=str(new_tpl.id), details={"code": code, "new_version": new_tpl.version}
    )
    return new_tpl


def clone_template(
    db: Session, code: str, target_project_id: uuid.UUID, user_id: uuid.UUID,
    overrides: dict[str, Any] | None = None, new_code: str | None = None,
) -> TestTemplate:
    source = get_template(db, code)
    overrides = overrides or {}
    cloned_code = new_code or f"{source.code}-FORK-{str(uuid.uuid4())[:8]}"
    cloned = TestTemplate(
        code=cloned_code,
        name=overrides.get("name", source.name + " (fork)"),
        description=overrides.get("description", source.description),
        detector_name=source.detector_name,
        default_params={**source.default_params, **(overrides.get("params") or {})},
        subledger_type=source.subledger_type,
        category=source.category,
        default_weight=overrides.get("weight", source.default_weight),
        tags=list(source.tags or []),
        owner_id=user_id,
        project_id=target_project_id,
        visibility=TemplateVisibility.PRIVATE,
        is_system=False,
        version=1,
        parent_template_id=source.id,
    )
    db.add(cloned)
    db.flush()
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_FORK, entity_type="test_template",
        entity_id=str(cloned.id), details={"source_code": code, "new_code": cloned_code}
    )
    return cloned
