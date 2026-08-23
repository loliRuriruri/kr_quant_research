import socket

from fastapi.testclient import TestClient

from kr_quant.web.app import app, dashboard_is_running, pick_listen_port, port_in_use

client = TestClient(app)


def test_port_helpers_detect_busy_and_free():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    busy = sock.getsockname()[1]
    try:
        assert port_in_use("127.0.0.1", busy)
        nxt = pick_listen_port("127.0.0.1", busy, span=8)
        assert nxt != busy
        assert not port_in_use("127.0.0.1", nxt)
        assert dashboard_is_running("127.0.0.1", nxt) is False
    finally:
        sock.close()


def test_index_and_status():
    home = client.get("/")
    assert home.status_code == 200
    assert "KR Quant" in home.text
    assert "Research" in home.text
    assert "styles.css?v=2.17.3" in home.text
    assert "app.js?v=2.17.3" in home.text
    assert "v2.17.3 Engine" in home.text
    assert "sunzi-q" in home.text
    assert "명부 전체" in home.text
    assert 'data-view="sunzi"' in home.text
    assert "양웬리 참모실" in home.text
    assert "손자를 읽는 양웬리" in home.text
    js = client.get("/static/app.js").text
    assert "function loadSunzi" in js
    assert "function postureChip" in js
    assert "criticCard((data.sunzi || {}).critic)" in js
    assert "function loadGlanceTop3" in js
    assert "function openHeatmapPlaybook" in js
    assert "seasonalityRows[idx]" in js
    assert 'id="dash-seasonality-banner"' in home.text
    assert "KOSPI/KOSDAQ 전종목 검색" in home.text
    status = client.get("/api/status")
    assert status.status_code == 200
    body = status.json()
    assert "keys" in body
    assert "opendart" in body["keys"]
    assert "masked" in body["keys"]["opendart"]


def test_guide_explains_selection():
    data = client.get("/api/guide").json()
    assert "universe" in data["criteria"]
    assert "TOP20" in "".join(data["criteria"]["top20"]) or any("양수" in x for x in data["criteria"]["top20"])
    assert "CORE_DATA_INCOMPLETE" in data["exclusion_labels"]


def test_settings_get_does_not_leak_full_secret():
    data = client.get("/api/settings").json()
    raw = str(data)
    assert "sk-proj-" not in raw
    assert data["opendart_api_key"]["configured"] in {True, False}


def test_models_for_xai_do_not_keep_openrouter_id():
    data = client.get("/api/llm/models?provider=xai").json()
    assert data["provider"] == "xai"
    assert data["default_model"].startswith("grok")
    assert data["selected"].startswith("grok")
    assert "grok-4.5" in data["models"] or "grok-4.6" in data["models"]
    assert all("/" not in m or m == data["selected"] for m in data["models"])


def test_research_reports_list_endpoint():
    data = client.get("/api/research/reports").json()
    assert "rows" in data
    assert "total" in data
    html = client.get("/").text
    assert 'data-view="reports"' in html
    assert "보관 리포트" in html
    assert "toss-rankings" in html
    assert 'data-view="toss"' in html
    assert 'data-view="sector"' in html
    assert 'data-view="screens"' in html
    assert "골라보기" in html
    assert "시세 받기" in html
    assert "drawer-back" in html
    css = client.get("/static/styles.css").text
    assert ".drawer.hidden" in css
    assert "class=\"drawer hidden\"" in html or 'class="drawer hidden"' in html
    assert "stock-grid" in client.get("/static/app.js").text
    assert "타이밍 신뢰도" in client.get("/static/app.js").text
    assert "sortable" in html
    assert "reports/delete" in client.get("/static/app.js").text
    assert 'data-sort="last_close"' in html
    assert 'data-sort="foreign_net"' in client.get("/static/app.js").text
    assert 'data-del-report' in client.get("/static/app.js").text
    assert "점수 랭킹" in html
    assert "토스증권" in html
    assert "report-modal" in html
    assert "macro-box" in html
    assert "brief-box" in html
    assert "news-box" in html
    assert "page-asof" in html
    assert "status-modal" in html
    assert "market-box" in html
    assert 'data-view="investor"' in html
    assert "공식 수급" in html
    assert 'data-view="sunzi"' in html
    assert "양웬리 참모실" in html
    assert 'data-view="nps"' in html
    assert "국민연금 5%" in html
    assert "investor-events-box" in html
    js = client.get("/static/app.js").text
    assert "loadSunzi" in js
    assert "fiveStrip" in js
    assert "loadInvestorEvents" in js
    assert "loadNps" in js
    assert "flow90Block" in js
    assert "eventsBlock" in js
    assert "cum20" in js
    assert 'data-view="flow"' in html
    assert 'data-view="empty"' in html
    assert 'data-view="trade"' in html
    assert "수급" in html
    assert "빈집" in html
    assert "트레이딩" in html
    assert 'data-view="us13f"' in html
    assert "13F" in html
    assert 'data-view="strategy"' in html
    assert "전략" in html
    cat = client.get("/api/strategy").json()
    assert cat.get("used_in_quant") is False
    js = client.get("/static/app.js").text
    assert "rowNote" in js
    assert "comment_flow" in js
    assert "factorBars" in js
    assert "가치 ${v.toFixed(1)}" in js or "name} ${v.toFixed(1)}" in js
    assert "faChip" in js
    assert "재무적격" in js or "법 통과" in js or "法 통과" in js
    assert "dual_pe_retail" in js
    assert "data-flow-more" in js
    assert "h-tabs" in js
    assert "FLOW_FIRST" in js
    assert "FLOW_STEP" in js
    assert "기타법인" in js
    assert "comment_short" in js
    assert "스토 데드" in js
    assert "구름 아래" in js
    assert "전환>기준" in js
    assert "data-tip" in js
    assert "float-tip" in js
    assert "데드 크로스" in js
    assert "TERM_TIPS" in js
    assert "Walk-Forward" in js
    assert "Out-Of-Sample" in js
    assert "thTip" in js
    assert "STATUS_KO" in js
    assert "일부 완료" in js
    assert "applyPriceChrome" in js
    assert "PRICE_VIEWS" in js
    assert "openStatusModal" in js
    assert "setPageAsOf" in js
    assert "closeDrawer" in js
    assert "startLiveSync" in js
    html = client.get("/").text
    assert "종목 옆은 선정 코멘트" in html
    top = client.get("/api/results/top?n=20").json()
    if top.get("rows"):
        assert top["rows"][0].get("comment")
        assert "Quant" in top["rows"][0]["comment"] or "적격" in top["rows"][0]["comment"]
    assert top.get("selection")
    js = client.get("/static/app.js").text
    assert "JSON.stringify(best.params" not in js
    assert "best_params_ko" in js
    assert "best_comment" in js
    assert "portfolio-box" in html
    assert "strategy-port-box" in html
    port = client.get("/api/portfolio").json()
    assert port.get("used_in_quant") is False
    spec = client.get("/api/system/spec").json()
    assert spec["overlays"]["strategy"] is False
    assert spec["overlays"]["portfolio"] is False
    assert spec["overlays"]["sector"] is False
    assert spec["overlays"]["macro"] is False
    assert spec["overlays"]["news"] is False
    assert spec["overlays"]["fa_gate"] is False
    assert spec["overlays"]["dao"] is False
    assert spec["overlays"]["jiang"] is False
    assert spec["overlays"]["official_flow"] is False
    assert spec["overlays"]["sunzi"] is False
    assert spec["overlays"]["tian"] is False
    assert spec["overlays"]["di"] is False
    assert spec["overlays"]["nps_holdings"] is False
    assert spec["overlays"]["dart_events"] is False
    sec = client.get("/api/sectors").json()
    assert sec.get("used_in_quant") is False
    scr = client.get("/api/screens").json()
    assert scr.get("used_in_quant") is False
    assert scr.get("catalog")
    assert "스토" in html or "일목" in html
    assert "공포·탐욕" in html or "feargreed" in html.lower()
    assert "watch-box" in html
    assert "FRED" in html
    assert "yfinance" in html
    assert "텔레그램" in html
    assert "주문 없음" in html or "주문은 쓰지" in html
    assert "KRX 시세만 갱신" in html
    assert "krx-history" in html
    assert "시세 이력 확장" in html
    assert "chip-fresh" in html
    spec = client.get("/api/system/spec").json()
    assert spec["orders"] is False
    assert spec["overlays"]["flow"] is False
    assert "freshness" in spec
    status = client.get("/api/status").json()
    assert "freshness" in status
    assert "scheduler" in status
    assert "price_days" in status["freshness"]
    assert "status_explain" in status
    assert "why" in status["status_explain"]
    assert "improve" in status["status_explain"]


def test_index_has_report_hooks():
    html = client.get("/").text
    assert "AI 분석 리포트" in html or "btn-report" in client.get("/static/app.js").text


def test_connections_lists_providers():
    data = client.get("/api/llm/connections").json()
    assert "active" in data
    names = {c["id"] for c in data["connections"]}
    assert names == {"xai", "deepseek", "openrouter"}
    html = client.get("/").text
    assert "llm-active-line" in html


def test_grok_connect_endpoint_exists():
    data = client.get("/api/llm/grok").json()
    assert "status" in data
    assert "session" in data
    assert "verification_url" in data
    html = client.get("/").text
    assert "grok-user-code" in html
    assert "승인" in html


def test_settings_has_no_standalone_openai():
    home = client.get("/")
    assert 'value="openai"' not in home.text
    data = client.get("/api/settings").json()
    assert "openai" not in data["providers"]
    assert set(data["providers"]) == {"xai", "deepseek", "openrouter"}
    assert "openai_api_key" not in data
    assert "fred_api_key" in data
    assert "telegram_bot_token" in data
    status = client.get("/api/status").json()
    assert "openai" not in status["keys"]


def test_macro_endpoint_is_research_only(monkeypatch):
    monkeypatch.setattr(
        "kr_quant.ingest.fred.macro_snapshot",
        lambda _key: {"configured": False, "source": "FRED", "used_in_quant": False, "series": [], "error": "no key"},
    )
    monkeypatch.setattr(
        "kr_quant.ingest.yahoo.index_snapshot",
        lambda: {"configured": True, "used_in_quant": False, "indexes": [], "error": None},
    )
    monkeypatch.setattr(
        "kr_quant.ingest.ecos.ecos_snapshot",
        lambda _key: {"configured": False, "used_in_quant": False, "series": [], "error": "no ecos"},
    )
    data = client.get("/api/macro").json()
    assert data["used_in_quant"] is False
    assert "fred" in data
    assert "yahoo" in data
    assert "brief" in data
    assert "news" in data
    assert data["brief"]["used_in_quant"] is False
    assert data["fred"]["used_in_quant"] is False


def test_settings_raw_endpoint():
    resp = client.get("/api/settings/raw")
    assert resp.status_code == 200
    data = resp.json()
    assert "opendart_api_key" in data
    assert "xai_api_key" in data
    assert "kis_app_key" in data
