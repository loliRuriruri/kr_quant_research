"""KR_QUANT_NO_BROWSER env gate used by serve() — no server start."""
from __future__ import annotations

import os

import pytest


def _no_browser_disables(open_browser: bool = True) -> bool:
    if str(os.environ.get("KR_QUANT_NO_BROWSER", "")).strip().lower() in {"1", "true", "yes"}:
        open_browser = False
    return open_browser


@pytest.mark.parametrize("raw,expected", [("1", False), ("true", False), ("YES", False), ("", True), ("0", True)])
def test_kr_quant_no_browser_gate(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    if raw == "":
        monkeypatch.delenv("KR_QUANT_NO_BROWSER", raising=False)
    else:
        monkeypatch.setenv("KR_QUANT_NO_BROWSER", raw)
    assert _no_browser_disables(True) is expected


def test_serve_source_honors_no_browser_env() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src" / "kr_quant" / "web" / "app.py"
    text = src.read_text(encoding="utf-8")
    assert "KR_QUANT_NO_BROWSER" in text
    assert "open_browser = False" in text
