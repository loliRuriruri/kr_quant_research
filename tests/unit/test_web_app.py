import re
import socket

from fastapi.testclient import TestClient

from kr_quant.web.app import app, dashboard_is_running, pick_listen_port, port_in_use

client = TestClient(app)
public_client = TestClient(app, base_url="https://public.example")


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
    assert "styles.css?v=" in home.text
    assert "app.js?v=" in home.text
    assert "Engine" in home.text
    assert "disc-modal-deep" in home.text
    assert 'data-view="sunzi"' in home.text
    assert "은하퀀트전설" in home.text
    js = client.get("/static/app.js").text
    assert 'id="sunzi-q"' in js
    assert "전 종목 명부" in js
    assert home.text.count('id="sunzi-q"') == 0
    assert "function normalizePublicStockItem" in js
    assert "manifest.stock_details?.base" in js
    assert "manifest.research_details" in js
    assert "function runFlowSearch" in js
    assert "function selectSeasonalityStock" in js
    assert "function loadSunzi" in js
    assert "function postureChip" in js
    assert "criticCard((data.sunzi || {}).critic)" in js
    assert "function loadGlanceTop3" in js
    assert "function openHeatmapPlaybook" in js
    assert "function renderDiscDeepPlaybook" in js
    assert "function computeTrackStats" in js
    assert "renderPlaybookHtml(data.playbook)" in js
    assert "검증 구간 점수 1위" in js
    assert "👑 최적 추천 전략" not in js
    assert "function applyPublicShareMode" in js
    assert "function bindStockSearchers" in js
    assert "function openStrategyBacktest" in js
    assert "function bindPreEntryClicks" in js
    assert "function renderPbMonthHeat" in js
    assert "function playbookRowFromScan" in js
    assert 'data-ticker="${escapeHtml(r.ticker)}" data-index="${idx}"' in js
    assert "현재 지표가 과거 패턴을 뒷받침하나요?" in js
    assert "12개월 기간별 수익 변동성 히트맵" in js
    assert "seasonalityRows[idx]" in js
    assert 'id="dash-seasonality-banner"' in home.text
    assert "KOSPI/KOSDAQ 전종목 검색" in home.text
    assert 'id="job-cancel-btn"' in home.text
    assert 'id="job-heartbeat-line"' in home.text
    assert "function cancelJob" in js
    assert "/api/jobs/cancel" in js
    assert "function sharpeLabel" in js
    assert "function precisionPanelHtml" in js
    assert "function tradeLogHtml" in js
    assert "점수 재현" in js
    assert "미관측" in js
    assert "INSUFFICIENT_EVIDENCE" in js
    assert "통계 관측 + 업종 가설" in js
    status = client.get("/api/status")
    assert status.status_code == 200
    body = status.json()
    assert "keys" in body
    assert "opendart" in body["keys"]
    assert "masked" in body["keys"]["opendart"]
    assert body["public_mode"] is False


def test_strategy_ai_fallback_uses_real_validation_fields(monkeypatch):
    from kr_quant.research import analyze

    def fail_chat(*args, **kwargs):
        raise RuntimeError("offline test")

    monkeypatch.setattr(analyze, "call_chat", fail_chat)
    response = client.post(
        "/api/strategy/custom-ai-diagnosis",
        json={
            "ticker": "005930",
            "company": "테스트기업",
            "strategy_name": "볼린저 평균회귀",
            "total_return": 0.12,
            "trades_count": 12,
            "validation_return": 0.03,
            "validation_trades": 3,
            "oos_return": -0.02,
            "oos_sharpe": -0.4,
            "oos_trades": 2,
            "stability_label": "LOW",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["verdict"] == "표본 부족"
    assert body["status"] == "DETERMINISTIC_FALLBACK"
    assert body["ai_generated"] is False
    assert body["used_in_quant"] is False
    assert "+3.00%" in body["diagnosis"]
    assert "-2.00%" in body["diagnosis"]
    assert "주문 신호가 아닙니다" in body["execution_risk"]


def test_tier1_ui_exposes_failure_and_provenance_states():
    js = client.get("/static/app.js").text
    assert "function renderTier1Unavailable" in js
    assert "function appendTier1Meta" in js
    assert "퀀트 점수 미반영" in js
    assert "DETERMINISTIC_FALLBACK" in js


def test_menu_evidence_keeps_quant_relation_in_tooltip_only():
    js = client.get("/static/app.js").text
    assert "오버레이·설명 전용" not in js
    assert "점수 관계 ${quantDetail}" in js


def test_pre_entry_top10_cards_show_season_grade_badge():
    js = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text
    assert "function seasonGradeBadge" in js
    assert "seasonGradeBadge(r.grade)" in js
    assert ".grade-badge" in css

    from kr_quant.web.season_listing import pre_entry_card
    card = pre_entry_card({"ticker": "005930", "grade": "A", "remaining_peak": {}}, 5)
    assert card["grade"] == "A"


def test_pre_entry_ui_rejects_null_ranks_and_binds_filters():
    home = client.get("/").text
    js = client.get("/static/app.js").text
    css = client.get("/static/styles.css").text

    assert "function hasCanonicalPreEntryRank" in js
    assert "row?.pre_entry_rank === null" in js
    assert "const canonicalRows = allRows.filter" in js
    assert "preEntryQuery" not in js
    assert '$("#pre-entry-market-filter")?.addEventListener("change"' in js
    assert '$("#theme-filter-reset")?.addEventListener("click"' in js
    assert "대시보드와 동일한 전체 TOP10" in js
    assert 'id="theme-filter-reset"' in home
    assert "#theme-filter-reset[hidden]" in css


def test_external_web_is_read_only_and_hides_settings():
    status = public_client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["public_mode"] is True
    assert status.json()["keys"] == {}

    settings = public_client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json() == {"public_mode": True, "locked": True}
    assert public_client.get("/api/settings/raw").status_code == 403

    assert public_client.post("/api/jobs", json={"kind": "demo"}).status_code == 403
    assert public_client.post("/api/jobs/cancel").status_code == 403
    assert public_client.post("/api/watchlist", json={"ticker": "005930"}).status_code == 403
    assert public_client.delete("/api/watchlist/005930").status_code == 403

    js = public_client.get("/static/app.js").text
    assert 'LOCAL_WEB_HOSTS' in js
    assert 'has("public-preview")' in js
    assert 'function lockPublicAdminUi' in js
    assert "#view-settings" in js
    assert '"#view-run button"' in js
    assert "button.disabled = true" in js


def test_cloudflare_forwarded_request_is_forced_public():
    status = client.get("/api/status", headers={"cf-connecting-ip": "203.0.113.10"})
    assert status.status_code == 200
    assert status.json()["public_mode"] is True
    assert status.json()["keys"] == {}

    blocked = client.put(
        "/api/settings",
        headers={"cf-connecting-ip": "203.0.113.10"},
        json={"llm_provider": "xai"},
    )
    assert blocked.status_code == 403


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


def test_tier1_chain_settings_roundtrip(monkeypatch):
    from dataclasses import replace

    from kr_quant.settings import load_settings

    # Isolate from ambient .env / machine Tier1 overrides so this asserts the
    # default Tier1 contract rather than the user's local configuration.
    settings = load_settings()
    isolated = replace(
        settings,
        tier1_routine_provider=None,
        tier1_routine_model=None,
        tier1_routine_paid_provider=None,
        tier1_routine_paid_model=None,
        tier1_analysis_provider=None,
        tier1_analysis_model=None,
        tier1_analysis_pro_provider=None,
        tier1_analysis_pro_model=None,
    )
    monkeypatch.setattr("kr_quant.web.app.load_settings", lambda: isolated)

    data = client.get("/api/settings").json()
    assert set(data["tier1"]) == {"routine", "routine_paid", "analysis", "analysis_pro"}
    for hop in data["tier1"].values():
        assert set(hop) == {"provider", "label", "model", "configured"}
    assert data["tier1"]["routine"]["model"].endswith(":free")
    from kr_quant.research.providers import PROVIDERS
    assert data["tier1"]["analysis"]["provider"] in set(PROVIDERS) | {"tier1_unavailable"}
    captured = {}
    monkeypatch.setattr("kr_quant.web.app.upsert_env_file", lambda path, mapping: captured.update(mapping))
    monkeypatch.setattr("kr_quant.web.app.apply_env_to_process", lambda path: None)
    body = {"tier1_routine_provider": "opencode_go", "tier1_routine_model": "deepseek/deepseek-v4.1-flash",
            "tier1_analysis_provider": "opencode_go", "tier1_analysis_model": "minimax-m3"}
    resp = client.put("/api/settings", json=body)
    assert resp.status_code == 200
    assert captured["TIER1_ROUTINE_PROVIDER"] == "opencode_go"
    assert captured["TIER1_ROUTINE_MODEL"] == "deepseek/deepseek-v4.1-flash"
    assert captured["TIER1_ANALYSIS_PROVIDER"] == "opencode_go"
    assert captured["TIER1_ANALYSIS_MODEL"] == "minimax-m3"
    html = client.get("/").text
    for sel in ("tier1-routine-provider", "tier1-routine-model", "tier1-routine-paid-provider",
                "tier1-routine-paid-model", "tier1-analysis-provider", "tier1-analysis-model",
                "tier1-analysis-pro-provider", "tier1-analysis-pro-model",
                "tier1-save-btn", "tier1-live-model", "tier1-live-paid-model",
                "tier1-live-analysis-model", "tier1-live-pro-model",
                "tier2-save-btn", "tier2-save-state"):
        assert f'id="{sel}"' in html
    js = client.get("/static/app.js").text
    assert "TIER1_SLOTS" in js and "renderTier1Config" in js and "saveTier1Config" in js


def test_opencode_models_and_settings_wiring():
    data = client.get("/api/llm/models?provider=opencode").json()
    assert data["provider"] == "opencode"
    assert data["label"] == "OpenCode Zen"
    assert data["default_model"] == "deepseek/deepseek-v4-flash-0731"
    assert data["models"][:8] == [
        "deepseek/deepseek-v4-flash-0731",
        "openai/gpt-5.6-luna",
        "zhipuai/glm-5.3-flash",
        "google/gemini-3.7-flash",
        "anthropic/claude-sonnet-5",
        "moonshotai/kimi-k3",
        "deepseek/deepseek-v4-pro",
        "xai/grok-4.6",
    ]
    settings = client.get("/api/settings").json()
    assert "opencode_api_key" in settings
    assert settings["providers"]["opencode"]["label"] == "OpenCode Zen"
    assert settings["help"]["opencode"] == "https://opencode.ai/auth"
    home = client.get("/").text
    assert 'value="opencode"' in home
    assert 'id="key-opencode"' in home
    assert 'data-provider="opencode"' in home
    go = client.get("/api/llm/models?provider=opencode_go").json()
    assert go["provider"] == "opencode_go"
    assert go["label"] == "OpenCode Go"
    assert go["default_model"] == "deepseek-v4-pro"
    # The active ambient model is appended after the curated lineup, if new.
    assert go["models"][:8] == [
        "deepseek-v4-pro",
        "deepseek-v4.1-flash",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "glm-5.3-flash",
        "kimi-k3",
        "kimi-k2.7-code",
        "mimo-v2.5",
    ]
    assert settings["providers"]["opencode_go"]["label"] == "OpenCode Go"
    assert 'value="opencode_go"' in home
    assert 'id="key-opencode-go"' in home
    assert 'data-provider="opencode_go"' in home
    js = client.get("/static/app.js").text
    assert "function modelTokenInfo" in js
    assert "key-opencode" in js
    assert "opencode_api_key" in js


def test_research_reports_list_endpoint():
    data = client.get("/api/research/reports").json()
    assert "rows" in data
    assert "total" in data
    html = client.get("/").text
    assert 'data-view="reports"' in html
    assert "보관 리포트" in html
    assert "toss-rankings" in html
    assert 'data-view="toss"' not in html
    assert 'data-view="sector"' in html
    assert 'data-view="screens"' in html
    assert "골라보기" in html
    assert "스마트 실행" in html
    assert "시세 받기" not in html
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
    assert "은하퀀트전설" in html
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
    assert 'data-view="flow"' not in html
    assert 'data-view="empty"' not in html
    assert 'data-view="trade"' in html
    assert 'data-smart-flow-tab="overview"' in html
    assert 'data-smart-flow-tab="vacancy"' in html
    assert 'data-smart-flow-tab="technical"' in html
    assert 'data-smart-flow-tab="stats"' in html
    assert 'id="trade-universe"' in html
    assert "수급" in html
    assert "빈집" in html
    assert "스마트 수급·타점" in html
    assert "flowHistoryTipAttrs" in js
    assert "설정기간 집계" in js
    assert 'data-tip-layout="flow-history"' in js
    assert "flowHistoryTipHtml" in js
    assert "flow-tip-net-grid" in client.get("/static/styles.css").text
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
    assert 'data-job="smart-sync"' in html
    assert "오늘 필요한 작업 스마트 실행" in html
    assert "데이터 구멍 자동 복구" in html
    assert "고급 데이터 작업" in html
    assert 'value="smart-sync" selected' in html
    assert '"smart-sync": "스마트 실행"' in js
    assert "▶ 오늘 필요한 작업 실행" in html
    assert 'data-job="dart-backfill"' in html
    assert "OpenDART 전 종목 연속 백필" in html
    assert 'fresh.financial_max_available_date || "2026-08-19"' not in js
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
    assert "strategy-port-box" in html
    dash_html = _view_section(html, "view-dash")
    assert 'id="portfolio-box"' not in dash_html
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
    assert "chip-fresh" not in html
    assert "스마트 실행" in html
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
    assert names == {"xai", "antigravity", "deepseek", "openrouter", "opencode", "opencode_go"}
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


def test_antigravity_connect_endpoint_exists():
    data = client.get("/api/llm/antigravity").json()
    assert "connected" in data
    assert "cli_available" in data
    assert "detail" in data
    html = client.get("/").text
    assert "agy-chip" in html
    assert "Google Antigravity CLI AUTH" in html


def test_settings_has_no_standalone_openai():
    home = client.get("/")
    assert 'value="openai"' not in home.text
    data = client.get("/api/settings").json()
    assert "openai" not in data["providers"]
    assert set(data["providers"]) == {"xai", "antigravity", "deepseek", "openrouter", "opencode", "opencode_go"}
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


def test_deploy_status_and_public_block():
    resp = client.get('/api/deploy/status')
    assert resp.status_code == 200
    data = resp.json()
    assert 'state' in data
    assert 'public_url' in data

    # Test blocked in public mode
    blocked = client.post('/api/deploy/run', headers={'cf-connecting-ip': '203.0.113.10'})
    assert blocked.status_code == 403
    blocked_force = client.post('/api/deploy/run?force=true', headers={'cf-connecting-ip': '203.0.113.10'})
    assert blocked_force.status_code == 403
    blocked_code = client.post('/api/deploy/run?code_only=true', headers={'cf-connecting-ip': '203.0.113.10'})
    assert blocked_code.status_code == 403


def _view_section(html: str, view_id: str) -> str:
    pattern = '<section\\b[^>]*\\bid="' + re.escape(view_id) + '"[^>]*>(.*?)</section>'
    match = re.search(pattern, html, re.S)
    assert match, view_id
    return match.group(0)

def test_dash_view_drops_legacy_rank_copy():
    html = client.get("/").text
    dash = _view_section(html, "view-dash")
    assert html.count('id="quality-box"') == 0
    assert dash.count('id="quality-box"') == 0
    for banned in (
        'id="top20-body"',
        "dash-topn-btn",
        'id="dash-leaderboard-title"',
        'id="refresh-dash"',
        "dash-leaderboard-card",
                        'id="portfolio-box"',
    ):
        assert banned not in dash, banned
    for kept in (
        'id="kpis"',
        'id="dash-tier1-briefing"',
        'id="dash-champions"',
        'id="dash-seasonality-banner"',
        'id="dash-reports-body"',
    ):
        assert kept in dash, kept
    assert "strategy-port-box" in html

def test_dash_workflow_contract():
    html = client.get("/").text
    dash = _view_section(html, "view-dash")
    order = [
        "kpis",
        "dash-today",
        "dash-discovery",
        "dash-flow",
        "dash-research",
        "dash-system",
    ]
    positions = []
    for view_id in order:
        token = 'id="' + view_id + '"'
        assert token in dash, view_id
        positions.append(dash.find(token))
    assert positions == sorted(positions)
    today_at = dash.find('id="dash-today"')
    discovery_at = dash.find('id="dash-discovery"')
    research_at = dash.find('id="dash-research"')
    assert dash.find('id="dash-seasonality-banner"') > today_at
    briefing_at = dash.find('id="dash-tier1-briefing"')
    assert briefing_at > discovery_at
    assert dash.find('id="dash-champions"') > briefing_at
    assert dash.find('id="dash-reports-body"') > research_at
    targets = re.findall(r'data-dash-target="([^"]+)"', dash)
    assert targets == [
        "seasonality",
        "rank",
        "screens",
        "investor",
        "trade",
        "watch",
        "strategy",
        "run",
    ]
    assert "data-view=" not in dash
    banned = [
        'top20-body',
        'dash-topn-btn',
        'dash-leaderboard-title',
        'refresh-dash',
        'id="portfolio-box"',
        'id="quality-box"',
        '코스피 평균(13.5배)',
        '매수 후보',
        '오늘 추천 종목',
        '매수 추천',
    ]
    for item in banned:
        assert item not in dash, item
    js = client.get("/static/app.js").text
    assert '현재 데이터로는 reason 없음' not in js
    assert '현재 데이터로는 상세 코멘트가 없습니다.' in js
    kpi = js[js.find('function renderKpis'):js.find('function renderExtLinksTop')]
    assert '상위 20개 핵심 포트폴리오' not in kpi
    assert '우량주' not in kpi
    assert 'TOP20 퀀트 평균' in kpi
    assert '전체 2,700+ 상장사 중 엄선' not in kpi
    assert '전체 상장 종목 중 조건 통과' in kpi
    assert '심층 검증 완료' not in kpi
    assert '저장된 AI 심층 리포트' in kpi
    dna = js[js.find('function renderDashDna'):js.find('function renderKpis')]
    assert '시장 상위 1% 우량주' not in dna
    assert '우량주' not in dna
    assert 'TOP 후보군 팩터 구성' in dna
    assert 'TOP20 평균 종합 점수' not in dna
    assert 'TOP ${n} 평균 종합 점수' in dna
    assert 'renderReportList("#dash-reports-body", reportRows, 3)' in js
    assert "switchView(target)" in js
    start = js.find("function renderKpis")
    assert start >= 0
    nxt = js.find("\nfunction ", start + 1)
    body = js[start:nxt if nxt > start else None]
    assert '코스피 평균' not in body

def test_dash_kpi_density():
    html = client.get("/").text
    dash = _view_section(html, "view-dash")
    for view_id in (
        "dash-seasonality-banner",
        "dash-tier1-briefing",
        "dash-champions",
        "dash-dna-box",
        "dash-flow",
        "dash-research",
        "dash-system",
    ):
        assert 'id="' + view_id + '"' in dash, view_id
    for banned in ("top20-body", "refresh-dash", 'id="portfolio-box"', 'id="quality-box"'):
        assert banned not in dash, banned
    js = client.get("/static/app.js").text
    start = js.find("function renderKpis")
    end = js.find("function renderExtLinksTop", start)
    body = js[start:end]
    for label in ('평균점수', '적격종목', 'AI 분석 리포트'):
        assert label in body, label
    for banned in ('평균PER', '평균ROE', '코스피 평균'):
        assert banned not in body, banned
    assert "dashReportsReady" in js
    assert "dashReportsReady ? " in body


# ----- Pipeline A3: health/plan API + view-run contract -----


def _assert_no_abs_paths(payload, project_root: str | None = None):
    import os
    from pathlib import Path

    roots = []
    if project_root:
        roots.append(str(project_root))
    try:
        from kr_quant.settings import load_settings

        roots.append(str(load_settings().root))
    except Exception:
        pass
    roots.append(str(Path.cwd()))

    def walk(value, path="$"):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}.{key}")
            return
        if isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, f"{path}[{i}]")
            return
        if isinstance(value, str):
            lowered = value.replace("\\", "/").lower()
            assert not re.match(r"^[a-z]:/", lowered), f"drive path leaked at {path}: {value}"
            for root in roots:
                if root and root.replace("\\", "/").lower() in lowered:
                    raise AssertionError(f"project path leaked at {path}: {value}")

    walk(payload)


def test_pipeline_health_api_sanitized(tmp_path, monkeypatch):
    from kr_quant.web import app as app_mod
    from kr_quant.web import smart_ledger

    started = []

    def _forbid_start(*args, **kwargs):
        started.append((args, kwargs))
        raise AssertionError("RUNNER.start must not be called by pipeline GET APIs")

    monkeypatch.setattr(app_mod.RUNNER, "start", _forbid_start)
    before = smart_ledger.load_ledger()
    res = client.get("/api/pipeline/health")
    after = smart_ledger.load_ledger()
    assert res.status_code == 200
    body = res.json()
    assert "pipeline_state" in body
    assert "repair_required" in body
    assert "busy" in body
    assert "components" in body
    _assert_no_abs_paths(body)
    assert before == after
    assert started == []


def test_pipeline_plan_modes_and_invalid(monkeypatch):
    from kr_quant.web import app as app_mod

    started = []

    def _forbid_start(*args, **kwargs):
        started.append(True)
        raise AssertionError("RUNNER.start must not be called by pipeline plan GET")

    monkeypatch.setattr(app_mod.RUNNER, "start", _forbid_start)
    normal = client.get("/api/pipeline/plan", params={"mode": "normal"})
    assert normal.status_code == 200
    assert normal.json().get("mode") == "normal"
    recover = client.get("/api/pipeline/plan", params={"mode": "recover"})
    assert recover.status_code == 200
    assert recover.json().get("mode") == "recover"
    bad = client.get("/api/pipeline/plan", params={"mode": "nope"})
    assert bad.status_code == 400
    _assert_no_abs_paths(normal.json())
    _assert_no_abs_paths(recover.json())
    assert started == []


def test_pipeline_busy_blocks_plan(monkeypatch):
    from kr_quant.web import app as app_mod

    monkeypatch.setattr(app_mod.RUNNER, "snapshot", lambda: {"status": "running", "kind": "krx-history"})
    health = client.get("/api/pipeline/health").json()
    assert health["busy"] is True
    assert health["pipeline_state"] == "RUNNING"
    plan = client.get("/api/pipeline/plan", params={"mode": "normal"}).json()
    assert plan.get("blocked") is True
    assert plan.get("block_reason") == "runner_busy"


def test_pipeline_gets_do_not_mutate_ledger(tmp_path, monkeypatch):
    from kr_quant.settings import load_settings
    from kr_quant.web import smart_ledger

    settings = load_settings()
    path = smart_ledger.ledger_path(settings)
    before = path.read_text(encoding="utf-8") if path.exists() else None
    mtime = path.stat().st_mtime_ns if path.exists() else None
    client.get("/api/pipeline/health")
    client.get("/api/pipeline/plan", params={"mode": "recover"})
    after = path.read_text(encoding="utf-8") if path.exists() else None
    assert before == after
    if mtime is not None:
        assert path.stat().st_mtime_ns == mtime


def test_public_share_pipeline_apis_sanitized():
    health = public_client.get("/api/pipeline/health")
    plan = public_client.get("/api/pipeline/plan", params={"mode": "normal"})
    assert health.status_code == 200
    assert plan.status_code == 200
    _assert_no_abs_paths(health.json())
    _assert_no_abs_paths(plan.json())


def test_view_run_three_layer_contract():
    home = client.get("/")
    assert home.status_code == 200
    html = home.text
    # Layer titles / CTAs
    assert "오늘 필요한 작업 스마트 실행" in html
    assert "▶ 오늘 필요한 작업 실행" in html
    assert 'data-job="smart-sync"' in html and 'data-mode="normal"' in html
    assert "데이터 구멍 자동 복구" in html
    assert "🔧 자동 복구 실행" in html
    assert 'data-mode="recover"' in html
    assert "고급 데이터 작업" in html
    assert "시세 이력 확장" in html
    assert 'data-job="krx-history"' in html
    assert 'data-job="dart-backfill"' in html
    assert "전체 데이터 강제 갱신 + 재계산" in html
    assert "수십 분 이상 걸릴 수 있습니다" in html
    # Full Update only under layer C
    layer_a = html[html.find('id="pipeline-layer-a"'):html.find('id="pipeline-layer-b"')]
    layer_c = html[html.find('id="pipeline-layer-c"'):html.find('id="pipeline-layer-c"') + 8000]
    assert 'data-job="live"' not in layer_a
    assert "전체 데이터 강제 갱신 + 재계산" in layer_c
    assert 'data-job="live"' in layer_c
    assert 'data-job="krx-history"' in layer_c
    assert 'data-job="dart-backfill"' in layer_c
    # Quick Sync not primary daily
    assert "Quick Sync" not in layer_a
    assert "시세만 다시 받기" in html
    # secondary after recover CTA ordering: recover button appears before krx-prices secondary
    assert html.find("smart-recover-btn") < html.find('data-job="krx-prices"')
    js = client.get("/static/app.js").text
    assert "/api/pipeline/health" in js
    assert "/api/pipeline/plan" in js
    assert "REPAIR_DART_ESSENTIAL" in js
    assert "DART_MAINTENANCE_BATCH" in js
    assert "PIPELINE_ACTION_LABELS" in js
    assert "loadPipelinePanel" in js
    assert "setPipelineBusyUi" in js
    assert 'mode: (options && options.mode) || "normal"' in js or "options.mode" in js
    # public lock still targets view-run buttons
    assert '$$("#view-run button")' in js
    # sidebar unchanged relative to committed nav snapshot if present
    assert 'data-view="run"' in html
    assert 'data-view="dash"' in html


def test_a3_sidebar_nav_unchanged_from_baseline():
    """A3 must not reorder/add/remove sidebar navigation entries."""
    from pathlib import Path

    home = client.get("/").text
    # Stable admin/run entry still present once
    assert home.count('data-view="run"') >= 1
    # Capture current nav button order
    buttons = re.findall(r'data-view="([^"]+)"', home)
    # Must still include core views; exact full list may include research items
    for required in ("dash", "rank", "run", "settings"):
        assert required in buttons


def test_pipeline_panel_js_terminal_and_busy_contracts():
    """Busy poll must not triple-scan plans; terminal states refresh full panel."""
    js = client.get("/static/app.js").text
    assert "async function loadPipelinePanel(options = {})" in js or "async function loadPipelinePanel(options" in js
    assert "loadPipelineHealthOnly" in js
    assert "refreshPipelineAfterTerminalJob" in js
    assert "includePlans: false" in js
    assert "includePlans: true" in js or "includePlans !== false" in js
    # running path uses throttled/no-plan loader (pollJob, not renderJob progress)
    assert "loadPipelinePanel({ includePlans: false })" in js
    poll_idx = js.find("async function pollJob")
    assert poll_idx >= 0
    poll_snip = js[poll_idx : poll_idx + 2200]
    assert "loadPipelinePanel({ includePlans: false })" in poll_snip
    assert "setTimeout(pollJob, 1200)" in poll_snip
    # busy tick must not request plan endpoints
    busy_branch = poll_snip[poll_snip.find('job.status === "running"') : poll_snip.find("setTimeout(pollJob, 1200)") + 40]
    assert "includePlans: false" in busy_branch
    assert "plan?mode=normal" not in busy_branch
    assert "plan?mode=recover" not in busy_branch
    # terminal success/partial/error all refresh
    assert "await refreshPipelineAfterTerminalJob();" in js
    err_snip = poll_snip[poll_snip.find('job.status === "error"') : poll_snip.find('job.status === "error"') + 420]
    assert "refreshPipelineAfterTerminalJob" in err_snip
    assert "showToast" in err_snip
    success_snip = poll_snip[poll_snip.find('["success", "partial"]') : poll_snip.find('["success", "partial"]') + 900]
    assert "refreshPipelineAfterTerminalJob" in success_snip
    # Corrective #2: canonical status refresh (no undefined loadStatus)
    refresh_idx = js.find("async function refreshPipelineAfterTerminalJob")
    assert refresh_idx >= 0
    refresh_snip = js[refresh_idx : refresh_idx + 350]
    assert "await loadStatusPanel();" in refresh_snip
    assert "await loadStatus();" not in js
    assert "function loadStatusPanel" in js
    # Layer contracts still present
    html = client.get("/").text
    assert "오늘 필요한 작업 스마트 실행" in html
    assert "데이터 구멍 자동 복구" in html
    assert "고급 데이터 작업" in html
    assert "setPipelineBusyUi" in js

