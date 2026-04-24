from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import SubledgerType, User
from backend.services import acl, connectors as conn_registry, import_service

router = APIRouter()
settings = get_settings()


@router.get("")
def list_connectors(_u: User = Depends(get_current_user)) -> list[dict]:
    out = []
    for name in conn_registry.list_connector_names():
        cls = conn_registry.REGISTRY[name]
        c = cls()
        out.append({
            "name": c.name,
            "description": c.description,
            "config_schema": c.config_schema,
        })
    return out


class PullIn(BaseModel):
    connector: str
    project_id: uuid.UUID
    dataset_name: str
    subledger_type: SubledgerType
    config: dict
    description: str | None = None


@router.post("/pull-and-import")
def pull_and_import(body: PullIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    acl.assert_permission(db, project_id=body.project_id, user=user, permission=acl.Permission.EDIT)
    settings.ensure_dirs()
    try:
        connector = conn_registry.get_connector(body.connector)
    except conn_registry.ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        result = connector.fetch(config=body.config, stage_dir=settings.upload_dir)
    except conn_registry.ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Connector pull failed: {e}") from e

    imported = import_service.import_dataset(
        db,
        file_path=result.staged_path,
        source_filename=result.original_name,
        project_id=body.project_id,
        name=body.dataset_name,
        subledger_type=body.subledger_type,
        user_id=user.id,
        description=body.description or f"Pulled via {body.connector}",
    )
    try:
        result.staged_path.unlink()
    except OSError:
        pass
    return {
        "dataset_id": str(imported.dataset_id),
        "record_count": imported.record_count,
        "source_hash": imported.source_hash,
        "connector": body.connector,
        "rows_pulled": result.rows,
        "bytes_pulled": result.bytes_pulled,
        "source_metadata": result.source_metadata,
    }
