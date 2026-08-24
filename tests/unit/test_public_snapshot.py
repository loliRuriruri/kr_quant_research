# -*- coding: utf-8 -*-
import sys
from pathlib import Path

from kr_quant.settings import load_settings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from export_public_snapshot import FORMULAS, export, fact  # noqa: E402


def test_missing_is_not_zero():
    f = fact(None, as_of="2026-08-21", source="OpenDART", kind="official", formula="x")
    assert f["missing"] is True
    assert f["display"] == "미수집"
    assert f["value"] is None


def test_export_snapshot_has_no_settings_and_recomputes(tmp_path):
    s = load_settings()
    if not (s.output_dir / "latest_all_stocks.parquet").exists():
        return
    meta = export(tmp_path)
    snap = (tmp_path / "snapshot.json").read_text(encoding="utf-8")
    assert "sk-" not in snap
    assert "OPENDART_API_KEY=" not in snap
    assert "API 설정" not in snap
    assert meta["orders"] is False
    assert meta["ai_mutates_quant"] is False
    assert meta["public_ui"]["settings"] is False
    data = (tmp_path / "ranking.json").read_text(encoding="utf-8")
    assert "quant_score" in data
    assert "연기금" not in (tmp_path / "flow.json").read_text(encoding="utf-8") or "기금" in (tmp_path / "flow.json").read_text(encoding="utf-8")
    assert "quant_score" in FORMULAS
