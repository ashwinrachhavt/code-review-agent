from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure imports work both ways:
# - `import backend.xxx` (needs <repo_root> on sys.path)
# - `from main import create_app` (needs <repo_root>/backend on sys.path)
# __file__ = <repo>/backend/tests/conftest.py
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

repo_root_s = str(REPO_ROOT)
backend_dir_s = str(BACKEND_DIR)

if repo_root_s not in sys.path:
    # Put repo root first so `import backend` resolves correctly
    sys.path.insert(0, repo_root_s)

if backend_dir_s not in sys.path:
    # Also allow `import main` from backend/main.py
    sys.path.insert(1, backend_dir_s)


@pytest.fixture(scope="session")
def app():
    from main import create_app  # type: ignore

    return create_app()
