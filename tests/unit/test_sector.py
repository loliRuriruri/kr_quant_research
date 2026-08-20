import pandas as pd

from kr_quant.screens import screen_value_growth, screens_payload
from kr_quant.sector.ranking import _pct_rank, _state, rank_sectors


def test_pct_rank_and_state():
    ranks = _pct_rank([0.1, 0.2, 0.3])
    assert ranks[0] < ranks[2]
    assert _state(85, 1) == "LEADING"
    assert _state(30, -8) == "LAGGING"


def test_rank_sectors_overlay(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    rows = []
    for i in range(6):
        rows.append(
            {
                "ticker": f"{i:06d}",
                "company": f"칩{i}",
                "industry": "전자부품반도체",
                "universe_eligible": True,
                "quant_score": 70 + i,
                "quant_rank": i + 1,
                "value_score": 20,
                "return_3m": 0.1,
                "return_6m": 0.05,
                "revenue_yoy": 0.2,
                "op_yoy": 0.1,
            }
        )
    for i in range(6, 12):
        rows.append(
            {
                "ticker": f"{i:06d}",
                "company": f"화학{i}",
                "industry": "화학물질",
                "universe_eligible": True,
                "quant_score": 50,
                "quant_rank": i + 1,
                "value_score": 10,
                "return_3m": -0.1,
                "return_6m": -0.05,
                "revenue_yoy": -0.1,
                "op_yoy": -0.1,
            }
        )
    pd.DataFrame(rows).to_parquet(output / "latest_all_stocks.parquet", index=False)

    class S:
        output_dir = output
        root = tmp_path

    out = rank_sectors(S())
    assert out["used_in_quant"] is False
    names = [r["name"] for r in out["rows"]]
    assert "전자부품반도체" in names
    chip = next(r for r in out["rows"] if r["name"] == "전자부품반도체")
    chem = next(r for r in out["rows"] if r["name"] == "화학물질")
    assert chip["score"] > chem["score"]


def test_value_growth_screen_filters():
    df = pd.DataFrame(
        {
            "ticker": ["000660", "005930", "000880"],
            "company": ["A", "B", "C"],
            "universe_eligible": [True, True, True],
            "value_score": [22, 10, 20],
            "growth_score": [18, 20, 8],
            "quant_score": [80, 70, 60],
        }
    )
    hit = screen_value_growth(df)
    assert set(hit["ticker"]) == {"000660"}
