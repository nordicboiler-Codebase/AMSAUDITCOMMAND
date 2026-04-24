from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from backend.services.connectors.base import ConnectorError, ConnectorResult


class SftpConnector:
    name = "sftp"
    description = "Pull a file from an SFTP server"
    config_schema = {
        "host": {"type": "string", "required": True},
        "port": {"type": "int", "default": 22},
        "username": {"type": "string", "required": True},
        "password": {"type": "string", "secret": True},
        "private_key": {"type": "string", "secret": True,
                        "description": "PEM private key text (alternative to password)"},
        "remote_path": {"type": "string", "required": True,
                        "description": "Absolute path to the remote file"},
    }

    def fetch(self, *, config: dict[str, Any], stage_dir: Path) -> ConnectorResult:
        host = config.get("host")
        username = config.get("username")
        remote_path = config.get("remote_path")
        if not (host and username and remote_path):
            raise ConnectorError("sftp: host, username, remote_path required")
        port = int(config.get("port", 22))
        password = config.get("password")
        private_key_pem = config.get("private_key")
        try:
            import paramiko
        except ImportError as e:
            raise ConnectorError("paramiko not installed; pip install paramiko") from e

        transport = paramiko.Transport((host, port))
        try:
            if private_key_pem:
                from io import StringIO

                pkey = paramiko.RSAKey.from_private_key(StringIO(private_key_pem))
                transport.connect(username=username, pkey=pkey)
            elif password:
                transport.connect(username=username, password=password)
            else:
                raise ConnectorError("sftp: password or private_key required")
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                original_name = Path(remote_path).name
                staged = stage_dir / f"sftp_{uuid.uuid4()}_{original_name}"
                sftp.get(remote_path, str(staged))
                size = staged.stat().st_size
                return ConnectorResult(
                    staged_path=staged, original_name=original_name,
                    bytes_pulled=size,
                    source_metadata={"host": host, "remote_path": remote_path},
                )
            finally:
                sftp.close()
        finally:
            transport.close()
