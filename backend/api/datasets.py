from __future__ import annotations

import uuid
from pathlib import Path

import hashlib
from pathlib import Path

import polars as pl
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_db
from backend.core.security import get_current_user, require_role
from backend.models import AuditAction, Dataset, SubledgerType, User
from backend.services import acl, audit_log, import_service, settings_store

router = APIRouter()
settings = get_settings()


@router.get("")
def list_datasets(project_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[dict]:
    q = select(Dataset)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Dataset.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return []
        q = q.where(Dataset.project_id.in_(visible))
    q = q.order_by(Dataset.imported_at.desc())
    return [_ds_out(d) for d in db.execute(q).scalars()]


@router.post("/import")
async def import_dataset(
    file: UploadFile = File(...),
    project_id: uuid.UUID = Form(...),
    name: str = Form(...),
    subledger_type: SubledgerType = Form(...),
    description: str | None = Form(None),
    classification: str = Form("INTERNAL"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.EDIT)
    settings.ensure_dirs()
    raw = await file.read()
    # Store the raw upload encrypted-at-rest with Fernet (SECRET_KEY-derived).
    encrypted = settings.upload_dir / f"{uuid.uuid4()}_{file.filename}.enc"
    with open(encrypted, "wb") as f:
        f.write(settings_store.encrypt_bytes(raw))
    # Stage a decrypted temp copy for Polars import, then delete.
    dest = settings.upload_dir / f"tmp_{uuid.uuid4()}_{file.filename}"
    with open(dest, "wb") as f:
        f.write(raw)
    try:
        result = import_service.import_dataset(
            db,
            file_path=dest,
            source_filename=file.filename,
            project_id=project_id,
            name=name,
            subledger_type=subledger_type,
            user_id=user.id,
            description=description,
            classification=classification,
        )
    finally:
        try:
            dest.unlink()
        except OSError:
            pass
    return {
        "dataset_id": str(result.dataset_id),
        "record_count": result.record_count,
        "source_hash": result.source_hash,
        "control_totals": result.control_totals,
        "schema": result.schema,
        "encrypted_source_path": str(encrypted),
    }


@router.post("/import-email")
async def import_email_dataset(
    files: list[UploadFile] = File(...),
    project_id: uuid.UUID = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    classification: str = Form("CONFIDENTIAL"),
    custodians: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Import one or more mailbox files (.pst/.ost/.mbox/.eml/.zip of .eml)
    as a single EMAIL dataset — one row per message, with a `custodian`
    column per source file so cross-employee detectors can correlate.

    `custodians` is an optional comma-separated list overriding the
    per-file custodian names (defaults to each filename's stem).
    """
    from backend.services import email_ingest

    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.EDIT)
    settings.ensure_dirs()
    cust_overrides = [c.strip() for c in (custodians or "").split(",") if c.strip()]

    staged: list[tuple[Path, str, str | None]] = []
    encrypted_paths: list[str] = []
    tmp_files: list[Path] = []
    try:
        for idx, up in enumerate(files):
            raw = await up.read()
            enc = settings.upload_dir / f"{uuid.uuid4()}_{up.filename}.enc"
            enc.write_bytes(settings_store.encrypt_bytes(raw))
            encrypted_paths.append(str(enc))
            tmp = settings.upload_dir / f"tmp_{uuid.uuid4()}_{up.filename}"
            tmp.write_bytes(raw)
            tmp_files.append(tmp)
            cust = cust_overrides[idx] if idx < len(cust_overrides) else None
            staged.append((tmp, up.filename or tmp.name, cust))

        try:
            df = email_ingest.parse_mail_files(staged)
        except email_ingest.PstSupportMissing as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        if df.height == 0:
            raise HTTPException(status_code=422,
                                detail="No messages could be parsed from the uploaded file(s).")

        merged = email_ingest.write_merged_parquet(df, settings.upload_dir)
        tmp_files.append(merged)
        result = import_service.import_dataset(
            db,
            file_path=merged,
            source_filename="; ".join(up.filename or "?" for up in files),
            project_id=project_id,
            name=name,
            subledger_type=SubledgerType.EMAIL,
            user_id=user.id,
            description=description,
            classification=classification,
        )
    finally:
        for t in tmp_files:
            try:
                t.unlink()
            except OSError:
                pass

    custodian_counts = (
        df.group_by("custodian").len().sort("len", descending=True)
    )
    return {
        "dataset_id": str(result.dataset_id),
        "record_count": result.record_count,
        "source_hash": result.source_hash,
        "custodians": {
            c: int(n) for c, n in
            zip(custodian_counts["custodian"].to_list(), custodian_counts["len"].to_list())
        },
        "encrypted_source_paths": encrypted_paths,
        "schema": result.schema,
    }


@router.get("/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)
    return _ds_out(ds)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.ADMIN)
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.EXPORT, entity_type="dataset",
        entity_id=str(ds.id), project_id=ds.project_id,
        details={"action": "delete", "name": ds.name, "source_hash": ds.source_hash_sha256},
    )
    db.delete(ds)
    db.commit()
    return {"deleted": True}


@router.get("/{dataset_id}/source")
def download_source(
    dataset_id: uuid.UUID, db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
) -> Response:
    """Return the original uploaded file, decrypted on demand, with hash verification."""
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    upload_dir = get_settings().upload_dir
    encrypted_candidates = list(upload_dir.glob(f"*_{ds.source_filename}.enc"))
    if not encrypted_candidates:
        raise HTTPException(status_code=410, detail="Encrypted source file no longer available")
    enc_path = encrypted_candidates[0]
    try:
        ciphertext = enc_path.read_bytes()
        plaintext = settings_store.decrypt_bytes(ciphertext)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decryption failed: {e}") from e
    h = hashlib.sha256(plaintext).hexdigest()
    if h != ds.source_hash_sha256:
        raise HTTPException(
            status_code=500,
            detail=f"INTEGRITY VIOLATION: decrypted hash {h} != import hash {ds.source_hash_sha256}",
        )
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.EXPORT, entity_type="dataset_source",
        entity_id=str(ds.id), project_id=ds.project_id,
        details={"filename": ds.source_filename, "bytes": len(plaintext), "hash_ok": True},
    )
    db.commit()
    return Response(
        content=plaintext, media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{ds.source_filename}"',
            "X-Source-SHA256": ds.source_hash_sha256,
        },
    )


@router.get("/{dataset_id}/preview")
def preview(dataset_id: uuid.UUID, rows: int = 100, db: Session = Depends(get_db),
            _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = import_service.resolve_parquet_path(ds.parquet_path)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=410,
            detail=(
                "Dataset parquet file is missing on the backend. "
                "Re-import the dataset from the original source file. "
                f"Details: {e}"
            ),
        ) from e
    df = pl.read_parquet(path).head(rows)
    return {"columns": df.columns, "rows": df.to_dicts()}


@router.get("/{dataset_id}/schema")
def schema(dataset_id: uuid.UUID, db: Session = Depends(get_db),
           _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    return ds.schema_json


@router.get("/{dataset_id}/control-totals")
def control_totals(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)
    return ds.control_totals


def _ds_out(ds: Dataset) -> dict:
    return {
        "id": str(ds.id),
        "project_id": str(ds.project_id),
        "name": ds.name,
        "source_filename": ds.source_filename,
        "source_hash": ds.source_hash_sha256,
        "subledger_type": ds.subledger_type.value,
        "record_count": ds.record_count,
        "schema": ds.schema_json,
        "control_totals": ds.control_totals,
        "parquet_available": import_service.parquet_available(ds.parquet_path),
    }
