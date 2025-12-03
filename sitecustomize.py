"""Repository-wide Python startup customization.

Prevents Python from writing .pyc files / __pycache__ directories by default.
This file is auto-imported by Python at startup if it is on sys.path
(the repo root is on sys.path when running from here or via Makefile).
"""

import os
import sys

# Tell the interpreter to skip writing bytecode (.pyc) files entirely.
sys.dont_write_bytecode = True

# Also set the environment flag so any subprocesses inherit the behavior.
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

