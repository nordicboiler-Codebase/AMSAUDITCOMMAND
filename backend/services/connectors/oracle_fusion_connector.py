from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Any

from backend.services.connectors.base import ConnectorError, ConnectorResult


class OracleFusionConnector:
    """Oracle Fusion ERP REST API read.

    Fetches a paginated resource (e.g. invoices, suppliers, GL journal batches)
    and stages it as CSV. Pattern:
        GET https://{host}/fscmRestApi/resources/{version}/{resource}
            ?onlyData=true&limit=500&offset={offset}&q={filter}
    """

    name = "oracle_fusion"
    description = "Oracle Fusion ERP REST API read"
    config_schema = {
        "base_url": {"type": "string", "required": True,
                     "description": "e.g. https://fa-ab12-saasfaprod1.fa.ocs.oraclecloud.com"},
        "resource_path": {"type": "string", "required": True,
                          "description": "e.g. /fscmRestApi/resources/11.13.18.05/invoices"},
        "query": {"type": "string", "default": "",
                  "description": "Oracle REST q= filter, e.g. InvoiceDate >= '2025-01-01'"},
        "fields": {"type": "string", "default": "",
                   "description": "Comma-separated field names to project"},
        "limit_per_page": {"type": "int", "default": 500},
        "max_rows": {"type": "int", "default": 50000},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "secret": True, "required": True},
    }

    def fetch(self, *, config: dict[str, Any], stage_dir: Path) -> ConnectorResult:
        import httpx

        base_url = (config.get("base_url") or "").rstrip("/")
        resource_path = config.get("resource_path") or ""
        username = config.get("username")
        password = config.get("password")
        if not (base_url and resource_path and username and password):
            raise ConnectorError("oracle_fusion: base_url, resource_path, username, password required")
        limit = int(config.get("limit_per_page", 500))
        max_rows = int(config.get("max_rows", 50000))

        url = f"{base_url}{resource_path}"
        params_base: dict[str, Any] = {"onlyData": "true", "limit": limit}
        if config.get("query"):
            params_base["q"] = config["query"]
        if config.get("fields"):
            params_base["fields"] = config["fields"]

        all_rows: list[dict[str, Any]] = []
        offset = 0
        with httpx.Client(auth=(username, password), timeout=120.0) as client:
            while True:
                r = client.get(url, params={**params_base, "offset": offset})
                r.raise_for_status()
                body = r.json()
                items = body.get("items", [])
                if not items:
                    break
                all_rows.extend(items)
                offset += len(items)
                if len(all_rows) >= max_rows or not body.get("hasMore"):
                    break

        resource_name = resource_path.rstrip("/").split("/")[-1] or "oracle_fusion"
        original_name = f"{resource_name}.csv"
        staged = stage_dir / f"oracle_{uuid.uuid4()}_{original_name}"
        if not all_rows:
            staged.write_text("")
            return ConnectorResult(
                staged_path=staged, original_name=original_name,
                bytes_pulled=0, rows=0,
                source_metadata={"url": url},
            )
        all_keys: list[str] = []
        for row in all_rows:
            for k in row.keys():
                if k not in all_keys and not k.startswith("_"):
                    all_keys.append(k)
        with open(staged, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            for row in all_rows:
                w.writerow({k: row.get(k) for k in all_keys})
        return ConnectorResult(
            staged_path=staged, original_name=original_name,
            bytes_pulled=staged.stat().st_size, rows=len(all_rows),
            source_metadata={"url": url, "query": config.get("query"), "fields": config.get("fields")},
        )
