from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure `backend/` is importable as a top-level package for tests
# __file__ = <repo>/backend/tests/conftest.py
# parents[2] -> <repo> (since parents[0]=tests, [1]=backend, [2]=repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session")
def app():
    from main import create_app  # type: ignore

    return create_app()
