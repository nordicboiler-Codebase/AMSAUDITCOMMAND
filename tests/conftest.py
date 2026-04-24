from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://audit:audit@localhost:5432/audit")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATA_DIR", "/tmp/techsource_test_data")


@pytest.fixture(scope="session")
def detector_catalog():
    from backend.detectors import catalog as c

    c.load_all()
    return c
