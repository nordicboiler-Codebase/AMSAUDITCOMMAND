"""Azure Blob Storage sync for the data directory.

Why this exists
---------------
GitHub Codespaces wipes the container filesystem on rebuild — every imported
dataset's parquet file disappears, and the audit database with it (unless you
also persist the Postgres volume). This module mirrors ``data/`` to an Azure
Blob container so that on next start the workspace pulls everything back.

What gets synced
----------------
Anything under ``settings.data_dir`` except ``logs/`` and dotfiles:
  - data/parquet/   — imported datasets and per-run output
  - data/uploads/   — Fernet-encrypted original source files
  - data/reports/   — generated PDFs
  - data/reference/ — reference lookups

Not synced from here: the Postgres database. Use ``pg_dump`` for that (see
``scripts/sync_blob.sh`` for an integrated push/pull that does both).

Configuration
-------------
Two environment variables are enough:
  AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...
  AZURE_BLOB_CONTAINER=techsource-audit-data       (auto-created on first push)

CLI
---
  python3 -m backend.services.blob_storage push    # data/ -> blob
  python3 -m backend.services.blob_storage pull    # blob -> data/
  python3 -m backend.services.blob_storage status  # show what's where

API
---
``is_configured()`` lets the startup script decide whether to auto-pull.
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from backend.core.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

ENV_CONN = "AZURE_BLOB_CONNECTION_STRING"
ENV_CONTAINER = "AZURE_BLOB_CONTAINER"
DEFAULT_CONTAINER = "techsource-audit-data"
EXCLUDE_DIRS = {"logs", ".cache"}


@dataclass
class SyncStats:
    uploaded: int = 0
    downloaded: int = 0
    skipped: int = 0
    bytes: int = 0
    errors: int = 0


def is_configured() -> bool:
    return bool(os.environ.get(ENV_CONN))


def _container_name() -> str:
    return os.environ.get(ENV_CONTAINER, DEFAULT_CONTAINER)


def _client():
    """Return a ContainerClient or raise a clean error if not configured."""
    conn = os.environ.get(ENV_CONN)
    if not conn:
        raise RuntimeError(
            f"{ENV_CONN} is not set. Add it to .env, e.g.\n"
            f"  {ENV_CONN}=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...\n"
            f"  {ENV_CONTAINER}={DEFAULT_CONTAINER}"
        )
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as e:
        raise RuntimeError(
            "azure-storage-blob is not installed. Run: pip install azure-storage-blob"
        ) from e
    service = BlobServiceClient.from_connection_string(conn)
    container = service.get_container_client(_container_name())
    try:
        container.create_container()
    except Exception:  # noqa: BLE001 — already exists or no create permission
        pass
    return container


def _iter_local_files(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # skip logs / dotfiles / temp uploads
        parts = p.relative_to(root).parts
        if any(part in EXCLUDE_DIRS or part.startswith(".") for part in parts):
            continue
        if any(part.startswith("tmp_") for part in parts):
            continue
        yield p


def push(verbose: bool = True) -> SyncStats:
    """Upload everything under data/ to the blob container (delta only)."""
    container = _client()
    root = Path(settings.data_dir)
    root.mkdir(parents=True, exist_ok=True)
    stats = SyncStats()
    # Build a small remote index: name -> size
    remote = {b.name: b.size for b in container.list_blobs()}
    for path in _iter_local_files(root):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        if remote.get(rel) == size:
            stats.skipped += 1
            continue
        try:
            with open(path, "rb") as fh:
                container.upload_blob(name=rel, data=fh, overwrite=True)
            stats.uploaded += 1
            stats.bytes += size
            if verbose:
                print(f"  ↑ {rel} ({_human(size)})")
        except Exception as e:  # noqa: BLE001
            stats.errors += 1
            log.warning("Failed to upload %s: %s", rel, e)
    if verbose:
        print(f"push complete: {stats.uploaded} uploaded, "
              f"{stats.skipped} unchanged, {stats.errors} errors, "
              f"{_human(stats.bytes)} transferred.")
    return stats


def pull(verbose: bool = True, only_if_empty: bool = False) -> SyncStats:
    """Download everything from the blob container into data/.

    ``only_if_empty`` is the safe mode used at startup: if the local parquet
    directory already has files, skip the pull so we never overwrite local
    edits. Set False for an explicit force-pull.
    """
    container = _client()
    root = Path(settings.data_dir)
    root.mkdir(parents=True, exist_ok=True)
    if only_if_empty and any(Path(settings.parquet_dir).glob("*.parquet")):
        if verbose:
            print(f"pull skipped: {settings.parquet_dir} already has parquet files. "
                  "Run `sync_blob.sh pull --force` to overwrite.")
        return SyncStats()
    stats = SyncStats()
    for blob in container.list_blobs():
        dest = root / blob.name
        if dest.exists() and dest.stat().st_size == blob.size:
            stats.skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            downloader = container.download_blob(blob.name)
            with open(dest, "wb") as fh:
                fh.write(downloader.readall())
            stats.downloaded += 1
            stats.bytes += blob.size or 0
            if verbose:
                print(f"  ↓ {blob.name} ({_human(blob.size or 0)})")
        except Exception as e:  # noqa: BLE001
            stats.errors += 1
            log.warning("Failed to download %s: %s", blob.name, e)
    if verbose:
        print(f"pull complete: {stats.downloaded} downloaded, "
              f"{stats.skipped} unchanged, {stats.errors} errors, "
              f"{_human(stats.bytes)} transferred.")
    return stats


def status() -> dict:
    """Quick comparison: what's local vs what's in the container."""
    root = Path(settings.data_dir)
    local_count = sum(1 for _ in _iter_local_files(root)) if root.exists() else 0
    info = {
        "configured": is_configured(),
        "container": _container_name() if is_configured() else None,
        "data_dir": str(root),
        "local_files": local_count,
    }
    if is_configured():
        try:
            container = _client()
            blobs = list(container.list_blobs())
            info["remote_files"] = len(blobs)
            info["remote_bytes"] = sum(b.size or 0 for b in blobs)
        except Exception as e:  # noqa: BLE001
            info["remote_error"] = str(e)
    return info


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    force = "--force" in sys.argv
    if cmd == "push":
        push()
    elif cmd == "pull":
        pull(only_if_empty=not force)
    elif cmd == "status":
        import json
        print(json.dumps(status(), indent=2, default=str))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
