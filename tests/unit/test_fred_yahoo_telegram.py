from kr_quant.ingest.fred import normalize_api_key, parse_observations, summarize_series
from kr_quant.ingest.telegram import format_job_error, format_report_notice, format_screen_done, notify_safe
from kr_quant.ingest.yahoo import kr_yahoo_symbol, parse_chart, summarize_bars


def test_fred_key_is_lowercased():
    assert normalize_api_key("  ABCDEF0123456789ABCDEF0123456789  ") == "abcdef0123456789abcdef0123456789"


def test_kr_yahoo_symbol():
    assert kr_yahoo_symbol("5930", "KOSPI") == "005930.KS"
    assert kr_yahoo_symbol("247540", "KOSDAQ") == "247540.KQ"


def test_parse_chart_and_summarize():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "005930.KS", "regularMarketPrice": 80.0, "currency": "KRW"},
                    "timestamp": [1700000000, 1700086400, 1735689600],
                    "indicators": {"quote": [{"close": [100.0, 110.0, 80.0]}]},
                }
            ]
        }
    }
    parsed = parse_chart(payload)
    assert parsed["symbol"] == "005930.KS"
    assert len(parsed["bars"]) == 3
    stats = summarize_bars(parsed["bars"], last_override=80.0)
    assert stats["last"] == 80.0
    assert stats["used_in_quant"] is False
    assert stats["high_52w"] == 110.0


def test_fred_parse_skips_missing():
    obs = parse_observations(
        {
            "observations": [
                {"date": "2026-08-18", "value": "4.25"},
                {"date": "2026-08-17", "value": "."},
                {"date": "2026-08-16", "value": "4.20"},
            ]
        }
    )
    assert [x["value"] for x in obs] == [4.25, 4.20]
    row = summarize_series(obs, {"id": "DGS10", "label": "미국 10년 금리", "unit": "%"})
    assert row["used_in_quant"] is False
    assert abs(row["delta"] - 0.05) < 1e-9


def test_telegram_format_and_silent(monkeypatch):
    text = format_screen_done(
        {
            "as_of_date": "2026-08-18",
            "status": "success",
            "top20_count": 2,
            "top": [{"ticker": "071970", "company": "HD현대마린엔진", "quant_score": 82.1}],
            "warnings": ["STATUS_FEED_MISSING"],
        }
    )
    assert "071970" in text
    assert "매수·매도" in text
    assert "주문" in format_job_error("live", "boom")
    assert "AI 분석 리포트" in format_report_notice({"schema_version": "research_report_v4", "ticker": "005930"})
    monkeypatch.setenv("STOCK_SCREENER_SILENT", "1")
    out = notify_safe("token", "123", "hello")
    assert out["skipped"] == "silent"
