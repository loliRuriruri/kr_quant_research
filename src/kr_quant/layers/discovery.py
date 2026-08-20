from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from kr_quant.orchestration.run import run_demo, run_from_staged
from kr_quant.settings import Settings


def run_discovery_demo(settings: Settings, as_of: date) -> dict[str, Any]:
    return run_demo(settings, as_of)


def run_discovery(settings: Settings, as_of: date, staged_dir: Path) -> dict[str, Any]:
    return run_from_staged(settings, as_of, staged_dir)
