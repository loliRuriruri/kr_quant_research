from kr_quant.context.macro_brief import build_macro_brief
from kr_quant.web.guide import explain_run_status


def test_inverted_curve_is_burden():
    brief = build_macro_brief(
        fred={
            "series": [
                {"id": "T10Y2Y", "label": "스프레드", "value": -0.4, "date": "2026-08-19", "delta": -0.02},
                {"id": "DGS10", "label": "10년", "value": 4.4, "date": "2026-08-19", "delta": 0.15},
                {"id": "FEDFUNDS", "label": "연준", "value": 5.25, "date": "2026-07-01", "delta": 0},
                {"id": "DEXKOUS", "label": "원달러", "value": 1420.0, "date": "2026-08-19", "delta": 12.0},
            ]
        },
        ecos={
            "series": [
                {"alias": "기준금리", "value": 2.5, "time": "20260813", "delta": 0},
                {"alias": "원달러환율", "value": 1425.0, "time": "20260819", "delta": 10.0},
            ]
        },
        yahoo={"indexes": [{"symbol": "^KS11", "label": "KOSPI", "last": 2500, "ret_1d": -0.02, "as_of": "2026-08-19"}]},
    )
    assert brief["used_in_quant"] is False
    spread = next(x for x in brief["international"]["items"] if x["id"] == "T10Y2Y")
    assert spread["tone"] == "부담"
    assert "역전" in spread["comment"]
    fx = next(x for x in brief["domestic"]["items"] if x["id"] == "usdkrw_bok")
    assert fx["tone"] == "부담"
    assert brief["overall"]["tone"] in {"부담", "혼합"}
    assert "Quant" in brief["disclaimer"]


def test_steep_curve_and_strong_won_are_friendly():
    brief = build_macro_brief(
        fred={
            "series": [
                {"id": "T10Y2Y", "value": 0.8, "date": "2026-08-19", "delta": 0.05},
                {"id": "DGS10", "value": 3.2, "date": "2026-08-19", "delta": -0.12},
                {"id": "FEDFUNDS", "value": 1.75, "date": "2026-07-01", "delta": -0.25},
            ]
        },
        ecos={"series": [{"alias": "원달러환율", "value": 1220.0, "time": "20260819", "delta": -8.0}]},
        yahoo={"indexes": [{"symbol": "^GSPC", "label": "S&P 500", "last": 5600, "ret_1d": 0.01, "ret_1y": 0.12, "as_of": "2026-08-19"}]},
    )
    spread = next(x for x in brief["international"]["items"] if x["id"] == "T10Y2Y")
    assert spread["tone"] == "우호"
    fx = next(x for x in brief["domestic"]["items"] if x["id"] == "usdkrw_bok")
    assert fx["tone"] == "우호"


def test_partial_status_explains_missing_feed():
    expl = explain_run_status({"status": "partial", "warnings": ["STATUS_FEED_MISSING"]}, status_csv_exists=False)
    assert expl["label"] == "일부 완료"
    assert expl["used_in_quant"] is False
    assert any("거래정지" in x for x in expl["why"])
    assert any("manual_status.csv" in x or "status" in x.lower() for x in expl["improve"])
    assert any("없습니다" in x for x in expl["improve"])
