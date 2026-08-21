import pandas as pd

from kr_quant.research.report import delete_saved_report, list_saved_reports, report_path
from kr_quant.timing.research import apply_strategy_confidence, strategy_confidence, timing_from_history


def _up_frame(n=260):
    close = [100.0 + i * 0.4 for i in range(n)]
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-02", periods=n, freq="B"),
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [1_000_000] * n,
        }
    )


def test_uptrend_multi_tf_not_quant():
    out = timing_from_history(_up_frame())
    assert out["ok"] is True
    assert out["used_in_quant"] is False
    assert out["timeframes"]["short"]["trend"] == "UP"
    assert out["timeframes"]["mid"]["trend"] == "UP"
    assert out["confidence"] > 40
    assert out["comment"]
    assert out["state"] in {"TREND", "OVERHEATED", "NEUTRAL", "RECOVERY"}


def test_short_sample_caps_confidence():
    out = timing_from_history(_up_frame(40))
    assert out["ok"] is True
    assert out["confidence"] <= 45
    assert out["timeframes"]["long"]["ok"] is False


def test_strategy_blend_stays_overlay():
    timing = timing_from_history(_up_frame())
    row = {
        "stability_label": "MEDIUM",
        "strategies": [
            {
                "oos_sharpe": 0.9,
                "max_drawdown": -0.12,
                "wf_hit": 0.6,
                "trade_count": 14,
                "stability_label": "MEDIUM",
            }
        ],
    }
    assert strategy_confidence(row)["used_in_quant"] is False
    blended = apply_strategy_confidence(timing, row)
    assert blended["used_in_quant"] is False
    assert blended["confidence_source"] == "price+strategy"
    assert blended["strategy_confidence"]["score"] > 0


def test_delete_saved_report(tmp_path):
    as_of = "2026-08-19"
    path = report_path(tmp_path, as_of, "005930")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"ticker":"005930","company":"삼성전자","as_of_date":"2026-08-19","schema_version":"research_report_v4","report_markdown":"요약 본문입니다."}',
        encoding="utf-8",
    )
    rows = list_saved_reports(tmp_path)
    assert rows
    out = delete_saved_report(tmp_path, "005930", as_of, kind="AI 분석 리포트")
    assert out["ok"] is True
    assert not path.exists()
    assert list_saved_reports(tmp_path) == []
