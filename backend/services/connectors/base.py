from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ConnectorError(Exception):
    pass


@dataclass
class ConnectorResult:
    staged_path: Path
    original_name: str
    bytes_pulled: int
    rows: int | None = None
    source_metadata: dict[str, Any] | None = None


class Connector(Protocol):
    name: str
    description: str
    config_schema: dict[str, Any]

    def fetch(self, *, config: dict[str, Any], stage_dir: Path) -> ConnectorResult: ...
