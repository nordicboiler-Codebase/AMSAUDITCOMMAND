"""ERP / source-system connectors.

A connector pulls data from an external system and stages it as a file that
the import service can then ingest as a Dataset. Registered connectors:

- sftp      : pull CSV/Parquet from an SFTP server
- sap_s4    : SAP S/4HANA OData v4 read (generic entity set)
- oracle_fusion : Oracle Fusion ERP REST API read
"""
from __future__ import annotations

from typing import Protocol

from backend.services.connectors.base import ConnectorResult, ConnectorError
from backend.services.connectors.sftp_connector import SftpConnector
from backend.services.connectors.sap_s4_connector import SapS4Connector
from backend.services.connectors.oracle_fusion_connector import OracleFusionConnector


REGISTRY: dict[str, type] = {
    "sftp": SftpConnector,
    "sap_s4": SapS4Connector,
    "oracle_fusion": OracleFusionConnector,
}


def list_connector_names() -> list[str]:
    return sorted(REGISTRY)


def get_connector(name: str):
    if name not in REGISTRY:
        raise ConnectorError(f"Unknown connector: {name}. Registered: {list_connector_names()}")
    return REGISTRY[name]()


__all__ = ["REGISTRY", "list_connector_names", "get_connector", "ConnectorResult", "ConnectorError"]
