"""pytest 公共夹具。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.profiles import store


@pytest.fixture(autouse=True)
def _clear_profiles():
    """每个用例前后清空工况档，互不影响。"""
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)
