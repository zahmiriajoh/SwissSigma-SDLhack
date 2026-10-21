"""Shared paths and fixtures. Run from the repo root:  uv run pytest tests/"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BO_BRIDGE = REPO / "OT protocols" / "bo_bridge.py"
PROTOCOLS = [REPO / "OT protocols" / "sdl_solubility_ot2.py", REPO / "production" / "sdl_solubility_ot2.py"]  # the lab uploads the second
OT_EXAMPLES = REPO / "OT protocols" / "examples"
DEBUG_DIR = REPO / "analysis" / "examples"
SDL_BO_EXAMPLES = REPO / "SDL_BO" / "examples"
for path in (REPO, DEBUG_DIR, SDL_BO_EXAMPLES):
    sys.path.insert(0, str(path))


def load_bo_bridge():
    """Import bo_bridge.py as a module (its folder name has a space, so it is not importable by name)."""
    spec = importlib.util.spec_from_file_location("bo_bridge", BO_BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_bridge(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BO_BRIDGE), *map(str, args)], capture_output=True, text=True)


@pytest.fixture
def coarse_grid(monkeypatch):
    """50 uL steps (201 mixtures instead of 23,016) so GP-based picks run in seconds."""
    from SDL_BO import space
    monkeypatch.setattr(space, "STEP_UL", 50)
    return 50
