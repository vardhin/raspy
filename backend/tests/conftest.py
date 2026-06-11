from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raspy.config import Settings
from raspy.core.app import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
