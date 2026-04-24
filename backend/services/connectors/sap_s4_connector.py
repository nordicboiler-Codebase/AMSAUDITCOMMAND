from __future__ import annotations

import csv
import uuid
from pathlib import Path
from typing import Any

from backend.services.connectors.base import ConnectorError, ConnectorResult


class SapS4Connector:
    """SAP S/4HANA OData v4 read.

    Uses standard OData v4 query pattern:
        GET https://{host}/sap/opu/odata4/sap/{service}/srvd_a2x/sap/{entity}/{version}
            ?$select=...&$filter=...&$top=...

    Auth options:
      - basic        : HTTP Basic (username + password)
      - bearer       : static bearer token
      - oauth2_client: client_credentials (token_url + client_id + client_secret)
    """

    name = "sap_s4"
    description = "SAP S/4HANA OData v4 read"
    config_schema = {
        "base_url": {"type": "string", "required": True,
                     "description": "e.g. https://my400000.s4hana.ondemand.com"},
        "service_path": {"type": "string", "required": True,
                         "description": "e.g. /sap/opu/odata4/sap/api_journal_entryitembasic/srvd_a2x/sap/journalentryitem/0001"},
        "entity_set": {"type": "string", "required": True,
                       "description": "e.g. JournalEntryItemBasic"},
        "select": {"type": "string", "default": ""},
        "filter": {"type": "string", "default": ""},
        "top": {"type": "int", "default": 10000},
        "auth_mode": {"type": "string", "default": "basic",
                      "choices": ["basic", "bearer", "oauth2_client"]},
        "username": {"type": "string"},
        "password": {"type": "string", "secret": True},
        "bearer_token": {"type": "string", "secret": True},
        "oauth_token_url": {"type": "string"},
        "oauth_client_id": {"type": "string"},
        "oauth_client_secret": {"type": "string", "secret": True},
        "oauth_scope": {"type": "string", "default": ""},
    }

    def _authorize(self, config: dict[str, Any]) -> dict[str, str]:
        mode = config.get("auth_mode", "basic")
        if mode == "basic":
            import base64

            u = config.get("username") or ""
            p = config.get("password") or ""
            tok = base64.b64encode(f"{u}:{p}".encode()).decode()
            return {"Authorization": f"Basic {tok}"}
        if mode == "bearer":
            return {"Authorization": f"Bearer {config.get('bearer_token', '')}"}
        if mode == "oauth2_client":
            import httpx

            token_url = config.get("oauth_token_url")
            cid = config.get("oauth_client_id")
            cs = config.get("oauth_client_secret")
            if not (token_url and cid and cs):
                raise ConnectorError("oauth2_client: token_url + client_id + client_secret required")
            data = {"grant_type": "client_credentials", "client_id": cid, "client_secret": cs}
            if config.get("oauth_scope"):
                data["scope"] = config["oauth_scope"]
            r = httpx.post(token_url, data=data, timeout=30.0)
            r.raise_for_status()
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        raise ConnectorError(f"Unknown auth_mode: {mode}")

    def fetch(self, *, config: dict[str, Any], stage_dir: Path) -> ConnectorResult:
        import httpx

        base_url = (config.get("base_url") or "").rstrip("/")
        service_path = config.get("service_path") or ""
        entity = config.get("entity_set")
        if not (base_url and service_path and entity):
            raise ConnectorError("sap_s4: base_url, service_path, entity_set required")

        headers = {"Accept": "application/json", **self._authorize(config)}
        params = {}
        if config.get("select"):
            params["$select"] = config["select"]
        if config.get("filter"):
            params["$filter"] = config["filter"]
        params["$top"] = str(int(config.get("top", 10000)))
        params["$format"] = "json"

        url = f"{base_url}{service_path}/{entity}"
        with httpx.Client(timeout=120.0) as client:
            r = client.get(url, headers=headers, params=params)
            r.raise_for_status()
            payload = r.json()

        rows = payload.get("value", [])
        if not isinstance(rows, list):
            raise ConnectorError("sap_s4: response has no 'value' array")

        original_name = f"sap_{entity}.csv"
        staged = stage_dir / f"sap_{uuid.uuid4()}_{original_name}"
        if not rows:
            staged.write_text("")
            return ConnectorResult(
                staged_path=staged, original_name=original_name,
                bytes_pulled=0, rows=0,
                source_metadata={"url": url, "entity": entity},
            )
        all_keys: list[str] = []
        for row in rows:
            for k in row.keys():
                if k not in all_keys:
                    all_keys.append(k)
        with open(staged, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_keys)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k) for k in all_keys})
        return ConnectorResult(
            staged_path=staged, original_name=original_name,
            bytes_pulled=staged.stat().st_size, rows=len(rows),
            source_metadata={"url": url, "entity": entity, "params": params},
        )
