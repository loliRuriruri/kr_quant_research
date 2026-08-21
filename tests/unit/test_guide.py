from kr_quant.web.guide import WARNING_FIX, explain_run_status, external_links, format_krw, pad_ticker, selection_guide, stock_brief


def test_pad_and_naver_link():
    assert pad_ticker(71970) == "071970"
    links = external_links("5930", "삼성전자")
    urls = {x["label"]: x["url"] for x in links}
    assert "finance.naver.com/item/main.naver?code=005930" in urls["네이버 시세"]
    assert urls["다음 금융"].endswith("A005930")
    assert "wcomp.fnguide.com/CompanyInfo/Snapshot" in urls["FnGuide"]
    assert "gicode=A005930" in urls["FnGuide"]
    assert "dsab001/main.do" in urls["DART 검색"]
    assert "disclosureSimpleSearch.do" in urls["KIND"]
    assert "repIsuSrtCd=005930" in urls["KIND"]
    assert urls["토스증권"].endswith("A005930")


def test_stock_brief_intro_without_llm():
    brief = stock_brief(
        {
            "ticker": "071970",
            "company": "HD현대마린엔진",
            "market": "KOSPI",
            "sector": "제조업",
            "industry": "기타기계",
            "as_of_date": "2026-08-13",
            "quant_score": 81.2,
            "quant_rank": 1,
            "top20_eligible": True,
            "per": 11.0,
            "pbr": 3.9,
            "roic": 0.28,
            "revenue_yoy": 0.34,
            "net_debt_assets": -0.13,
        },
        {"kind": "보통주", "list_date": "20090515", "market_cap": 1.96e12, "acc_mt": 12},
    )
    assert "HD현대마린엔진(071970)" in brief["headline"]
    assert "KOSPI" in brief["headline"]
    assert "1.96조원" in brief["headline"]
    assert any("1위" in p for p in brief["paragraphs"])
    assert any(f["label"] == "시가총액" and "조원" in f["value"] for f in brief["facts"])
    assert format_krw(3.0e11) == "3,000억원" or format_krw(3.0e11).endswith("억원")


def test_warning_fix_tells_how_to_leave_partial():
    assert "STATUS_FEED_MISSING" in WARNING_FIX
    expl = explain_run_status({"status": "partial", "warnings": ["STATUS_FEED_MISSING"]})
    assert expl["label"] == "일부 완료"
    assert expl["improve"]


def test_selection_guide_has_thresholds(settings):
    g = selection_guide(settings.config)
    assert any("300" in x for x in g["universe"])
    assert any("80%" in x for x in g["top100"])
    assert any("양수" in x for x in g["top20"])
