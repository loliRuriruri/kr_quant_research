import pandas as pd

from kr_quant.portfolio.analysis import analyze_top20


def test_analyze_top20_flags_sector_concentration(tmp_path, monkeypatch):
    output = tmp_path / "output"
    staged = tmp_path / "staged" / "live"
    output.mkdir()
    staged.mkdir(parents=True)
    pd.DataFrame(
        {
            "ticker": ["000660", "005930", "000880", "000210"],
            "company": ["SK하이닉스", "삼성전자", "한화", "DL"],
            "sector": ["제조업", "제조업", "제조업", "제조업"],
            "industry": ["전자부품반도체", "전자부품반도체", "화학", "화학"],
            "quant_rank": [1, 2, 3, 4],
            "quant_score": [80, 79, 70, 69],
        }
    ).to_csv(output / "latest_top20.csv", index=False, encoding="utf-8-sig")
    dates = pd.bdate_range("2026-04-01", periods=30)
    rows = []
    for i, day in enumerate(dates):
        for ticker, base in (("000660", 100), ("005930", 100), ("000880", 50), ("000210", 50)):
            close = base * (1.01 ** i)
            rows.append({"ticker": ticker, "trade_date": day.date().isoformat(), "close": close})
    pd.DataFrame(rows).to_parquet(staged / "prices.parquet", index=False)

    class S:
        output_dir = output
        staged_dir = tmp_path / "staged"

    out = analyze_top20(S(), max_sector_weight=0.40)
    assert out["used_in_quant"] is False
    assert out["configured"] is True
    assert out["n"] == 4
    assert out["top_sector"] == "전자부품반도체"
    assert out["sector_concentration"] == 0.5
    assert "SECTOR_CONCENTRATION_HIGH" in out["warnings"]
    assert "한 업종" in out["comment"]
    assert out["avg_pairwise_correlation"] is not None


def test_analyze_top20_missing_file(tmp_path):
    class S:
        output_dir = tmp_path
        staged_dir = tmp_path / "staged"

    out = analyze_top20(S())
    assert out["configured"] is False
    assert out["used_in_quant"] is False
    assert out["error"]
