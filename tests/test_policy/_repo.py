"""Helpers to locate and parse repository files for the policy tests."""
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib", reason="policy tests need Python >= 3.11")

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
LOCKFILE = ROOT / "uv.lock"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "main.yaml"

if not PYPROJECT.exists():
    pytest.skip("not running from a PyShEx source checkout", allow_module_level=True)


def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def lockfile() -> dict:
    return tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
