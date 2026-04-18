"""Shared pytest setup.

The ``custom_components/flightradar24/api/`` subpackage is self-contained —
it has no Home Assistant imports. We just make it importable as a top-level
``api`` namespace so tests can do ``from api.airport import ...``.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "flightradar24"))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> Any:
        return json.loads((FIXTURES_DIR / name).read_text())
    return _load
