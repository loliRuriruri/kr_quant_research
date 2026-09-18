# -*- coding: utf-8 -*-
"""Fixture-backed browser E2E. Skips when Chromium is unavailable."""
from __future__ import annotations

import pytest

from tests.e2e.harness import start_server

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def base_url():
    url, server = start_server()
    yield url
    server.should_exit = True


@pytest.fixture(scope="module")
def browser_page(base_url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright is not installed")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base_url, wait_until="domcontentloaded")
        page.wait_for_selector("#dash-champions .champ-card", timeout=15000)
        page.wait_for_selector(".glance-pick-name", timeout=15000)
        yield page
        browser.close()


def _open_view(page, name: str) -> None:
    page.locator(f'button.nav-btn[data-view="{name}"]').click()


def test_dashboard_table_does_not_wait_for_status_or_hidden_menus(browser_page, base_url):
    page = browser_page.context.browser.new_page()
    requests = []
    held = []
    page.on('request', lambda req: requests.append(req.url))
    page.route('**/api/status', lambda route: held.append(route))
    try:
        page.goto(base_url, wait_until='domcontentloaded')
        page.locator('#dash-champions .champ-card').first.wait_for(timeout=8000)
        assert held, 'Status deliberately remains pending while rows are already visible'
        assert not any(path in url for url in requests for path in ['/api/results/all', '/api/settings', '/api/watchlist', '/api/portfolio', '/api/llm/connections', '/api/seasonality/momentum-portfolio'])
    finally:
        page.close()


def test_failed_view_can_retry_and_refresh_does_not_reload_dashboard(browser_page, base_url):
    page = browser_page.context.browser.new_page()
    calls = []
    page.on('request', lambda req: calls.append(req.url))
    try:
        page.goto(base_url, wait_until='domcontentloaded')
        page.locator('#dash-champions .champ-card').first.wait_for()
        page.route('**/api/results/all?*', lambda route: route.fulfill(status=503, json={'detail': 'test temporary failure'}))
        _open_view(page, 'rank')
        retry = page.locator('#view-rank > .view-load-state button')
        retry.wait_for()
        page.unroute('**/api/results/all?*')
        before = sum('/api/results/top?' in url for url in calls)
        retry.click()
        page.wait_for_function("document.querySelector('#view-rank').getAttribute('aria-busy') === 'false' && document.querySelector('#view-rank > .view-load-state').hidden")
        assert sum('/api/results/top?' in url for url in calls) == before
        all_count = sum('/api/results/all?' in url for url in calls)
        _open_view(page, 'dash')
        _open_view(page, 'rank')
        assert sum('/api/results/all?' in url for url in calls) == all_count
    finally:
        page.close()


def test_strategy_navigation_never_starts_a_backtest(browser_page, base_url):
    page = browser_page.context.browser.new_page()
    mutations = []
    page.on('request', lambda req: mutations.append(req.url) if req.method == 'POST' else None)
    page.route('**/api/strategy', lambda route: route.fulfill(json={'need_run': True, 'rows': []}))
    try:
        page.goto(base_url, wait_until='domcontentloaded')
        page.locator('#dash-champions .champ-card').first.wait_for()
        _open_view(page, 'strategy')
        page.wait_for_function("document.querySelector('#strategy-box').textContent.includes('자동 백테스트하지 않습니다')")
        assert not any('/api/strategy' in url for url in mutations)
    finally:
        page.close()


def test_momentum_unknown_data_has_no_fabricated_confidence(browser_page):
    page = browser_page
    route_pattern = "**/api/seasonality/momentum-portfolio"
    page.route(route_pattern, lambda route: route.fulfill(json={"ok": True, "items": [{
        "id": "audit-stock", "code": "005380", "name": "현대차", "entry_date": "2026-08-27", "peak_date": "2026-09-15",
        "entry_price": 100, "target_price": 95, "current_price": None, "current_return": None,
        "trajectory_match": None, "trajectory_samples": 0, "history_curve": [], "actual_curve": [], "price_source": "UNAVAILABLE",
    }]}))
    try:
        _open_view(page, "seasonality")
        page.locator("#btn-open-momentum-manager").click()
        page.locator("#momentum-cards-grid .card-mom-item").wait_for()
        text = page.locator("#momentum-cards-grid").inner_text()
        assert "자료 없음" in text and "계산 불가" in text
        assert "비교 불가" in text
        assert "-5.0%" in text and "+-5.0%" not in text
        assert "87.8%" not in page.locator("#momentum-kpis").inner_text()
        assert "정상 궤도" not in text
    finally:
        page.unroute(route_pattern)
        _open_view(page, "dash")


def test_rank_view_has_real_rows(browser_page):
    _open_view(browser_page, "rank")
    browser_page.wait_for_selector("#rank-body tr.clickable", timeout=15000)
    rows = browser_page.locator("#rank-body tr.clickable")
    assert rows.count() >= 1
    assert '퀀트 랭킹' in browser_page.locator("#view-rank h2").first.inner_text()
    _open_view(browser_page, "dash")


def test_glance_top3_matches_seasonality_order(browser_page):
    browser_page.wait_for_selector(".glance-pick-name")
    glance = browser_page.locator(".glance-pick-name").all_inner_texts()
    assert glance[:3] == ["현대차", "삼성전자", "SK하이닉스"]
    _open_view(browser_page, "seasonality")
    browser_page.wait_for_selector("#tab-v11-pre-entry")
    browser_page.locator("#tab-v11-pre-entry").click()
    browser_page.wait_for_selector("#pre-entry-cards-list .pre-entry-card", timeout=8000)
    cards = [
        card.locator("b").first.inner_text().strip()
        for card in browser_page.locator("#pre-entry-cards-list .pre-entry-card").all()
    ]
    assert cards[:3] == glance[:3]


def test_season_metric_detail_and_pc_layout(browser_page, base_url):
    page = browser_page.context.browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda exc: errors.append(str(exc)))
    try:
        page.goto(base_url, wait_until='domcontentloaded')
        card = page.locator('.glance-pick-card').first
        card.wait_for()
        assert '-3.2%' in card.inner_text() and '2/5회 상승' in card.inner_text()
        _open_view(page, 'seasonality')
        page.locator('#tab-v11-pre-entry').click()
        first = page.locator('#pre-entry-cards-list .pre-entry-card').first
        first.wait_for()
        assert '-3.2%' in first.inner_text() and '+12.0%' in first.inner_text()
        first.get_by_role('button', name='상세 플레이북 ➔').click()
        detail = page.locator('#disc-modal-deep')
        detail.wait_for(state='visible')
        assert '-3.2%' in detail.inner_text() and '+12.0%' in detail.inner_text()
        assert '아직 산출 전' in detail.inner_text()
        detail.get_by_text('계산 방법·표본 차이·주의사항 자세히', exact=True).click()
        assert '-6.0% ~ +2.0%' in detail.inner_text()
        assert page.locator('.expected-kpi-item').evaluate_all(
            '(items) => items.every(e => e.scrollWidth <= e.clientWidth + 1 && e.scrollHeight <= e.clientHeight + 1)')
        assert not errors
    finally:
        page.close()


def test_search_hyundai_name_and_ticker_autocomplete(browser_page):
    _open_view(browser_page, "strategy")
    inp = browser_page.locator("#custom-strategy-q")
    inp.wait_for()
    inp.fill("현대차")
    browser_page.wait_for_selector(".stock-autocomplete-item", timeout=5000)
    menu = browser_page.locator("#custom-strategy-menu").inner_text()
    assert "현대차" in menu
    assert "005380" in menu
    inp.fill("005380")
    browser_page.wait_for_timeout(250)
    browser_page.wait_for_selector(".stock-autocomplete-item", timeout=5000)
    menu = browser_page.locator("#custom-strategy-menu").inner_text()
    assert "005380" in menu
    assert "현대차" in menu


def test_table_click_opens_stock_drawer_with_links(browser_page):
    _open_view(browser_page, "rank")
    row = browser_page.locator("#rank-body tr.clickable").first
    row.wait_for(timeout=15000)
    ticker = row.get_attribute("data-ticker")
    assert ticker
    row.click()
    browser_page.wait_for_selector("#drawer:not(.hidden)", timeout=8000)
    browser_page.wait_for_selector("#drawer a[href*='naver.com']", timeout=8000)
    hrefs = browser_page.locator("#drawer a[href*='naver.com'], #drawer a[href*='tossinvest']").all()
    joined = " ".join(link.get_attribute("href") or "" for link in hrefs)
    assert ticker in joined
    assert "naver.com" in joined
    assert "tossinvest.com" in joined or "toss" in joined.lower()
    close_btn = browser_page.locator("#drawer-close")
    if close_btn.count():
        close_btn.click()


def test_event_preset_ignores_month_filter(browser_page):
    _open_view(browser_page, "seasonality")
    browser_page.locator("#tab-v11-heatmap").click()
    browser_page.wait_for_selector('button[data-preset="winter_heater"]')
    browser_page.locator('button[data-preset="winter_heater"]').click()
    browser_page.wait_for_timeout(600)
    note = browser_page.locator("#seasonality-filter-mode-note").inner_text()
    badge = browser_page.locator("#seasonality-count-badge").inner_text()
    assert "특수 이벤트" in note or "월/최소조건" in badge
    table = browser_page.locator("#seasonality-body").inner_text()
    assert "경동나비엔" in table or "009450" in table
    assert "삼성전자" not in table or "월/최소조건 미적용" in badge


def test_smart_flow_vacancy_dual_and_technical_filters(browser_page):
    _open_view(browser_page, "trade")
    browser_page.wait_for_timeout(800)
    browser_page.locator('[data-smart-flow-tab="vacancy"]').click()
    browser_page.wait_for_selector("#empty-box", timeout=8000)
    browser_page.wait_for_timeout(400)
    vacancy = browser_page.locator("#empty-box").inner_text()
    assert "현대차" in vacancy
    browser_page.locator('[data-smart-flow-tab="technical"]').click()
    browser_page.wait_for_timeout(400)
    browser_page.select_option("#trade-mode", "dual")
    browser_page.select_option("#trade-ta", "stoch_os")
    browser_page.wait_for_timeout(200)
    technical = browser_page.locator("#trade-box").inner_text()
    assert "현대차" in technical


def test_flow_hover_shows_daily_lines_and_period_total(browser_page):
    _open_view(browser_page, "trade")
    browser_page.locator('[data-smart-flow-tab="overview"]').click()
    browser_page.wait_for_selector('[data-tip-layout="flow-history"]', timeout=8000)
    target = browser_page.locator('[data-tip-layout="flow-history"]').first
    target.hover()
    browser_page.wait_for_selector("#float-tip:not(.hidden)", timeout=4000)
    tip = browser_page.locator("#float-tip").inner_text()
    assert "08-28" in tip or "종가" in tip
    assert "설정기간 집계" in tip or "5거래일" in tip
    assert "외인" in tip
    browser_page.evaluate("document.dispatchEvent(new Event('scroll'))")
    browser_page.wait_for_timeout(100)
    assert browser_page.locator("#float-tip").is_visible()
    browser_page.mouse.move(0, 0)
    browser_page.wait_for_selector("#float-tip.hidden", state="attached")


def test_long_strategy_and_company_names_are_not_clipped(browser_page):
    _open_view(browser_page, "strategy")
    browser_page.wait_for_selector(".strat-pill-name", timeout=8000)
    name = browser_page.locator(".strat-pill-name").first
    company = browser_page.locator("#view-strategy b").first
    for loc in (name, company):
        box = loc.bounding_box()
        assert box is not None
        clipped = loc.evaluate(
            "el => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).textOverflow === 'ellipsis'"
        )
        assert clipped is False
    warning = browser_page.locator("#view-strategy").inner_text()
    assert "잘리면 안 되는 회귀 문구" in warning


def test_public_preview_locks_settings_and_run(browser_page, base_url):
    browser_page.goto(base_url + "/?public-preview", wait_until="domcontentloaded")
    browser_page.wait_for_selector("#dash-champions .champ-card", timeout=15000)
    assert browser_page.locator('button.nav-btn[data-view="settings"]').count() == 0
    run_btn = browser_page.locator("#view-run button").first
    if run_btn.count():
        assert run_btn.is_disabled()
    assert browser_page.locator("#dash-champions .champ-card").count() >= 1


def _overlap_collision(left, right, pad=8) -> bool:
    overlap_x = min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"])
    overlap_y = min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"])
    if overlap_x <= pad or overlap_y <= pad:
        return False
    a_in_b = (
        left["x"] >= right["x"] - 1
        and left["y"] >= right["y"] - 1
        and left["x"] + left["width"] <= right["x"] + right["width"] + 1
        and left["y"] + left["height"] <= right["y"] + right["height"] + 1
    )
    b_in_a = (
        right["x"] >= left["x"] - 1
        and right["y"] >= left["y"] - 1
        and right["x"] + right["width"] <= left["x"] + left["width"] + 1
        and right["y"] + right["height"] <= left["y"] + left["height"] + 1
    )
    return not (a_in_b or b_in_a)


def test_mobile_cards_and_tables_do_not_overlap(browser_page, base_url):
    browser_page.set_viewport_size({"width": 390, "height": 844})
    browser_page.goto(base_url, wait_until="domcontentloaded")
    browser_page.wait_for_selector("#dash-champions .champ-card", timeout=15000)
    cards = browser_page.locator("#view-dash .card, #view-dash .glance-pick-card").all()
    boxes = [el.bounding_box() for el in cards if el.bounding_box() and el.bounding_box()["width"] > 0]
    for i, left in enumerate(boxes[:8]):
        for right in boxes[i + 1 : 8]:
            if _overlap_collision(left, right):
                pytest.fail("mobile cards overlap")

def test_dashboard_workflow_quick_actions(browser_page, base_url):
    page = browser_page.context.browser.new_page()
    try:
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator("#dash-champions .champ-card").first.wait_for(timeout=15000)
        targets = ["seasonality", "rank", "screens", "investor", "trade", "watch", "strategy", "run"]
        for target in targets:
            page.locator(f'#view-dash [data-dash-target="{target}"]').click()
            page.wait_for_function(
                "(name) => { const el = document.querySelector('#view-' + name); return !!el && !el.classList.contains('hidden'); }",
                arg=target,
            )
            active = page.locator(f'button.nav-btn.active[data-view="{target}"] span:not(.nav-icon)')
            assert active.count() >= 1, target
            label = " ".join((active.first.text_content() or "").split())
            title = " ".join((page.locator("#page-title").text_content() or "").split())
            assert title == label, (target, title, label)
            page.locator('button.nav-btn[data-view="dash"]').first.click()
            page.wait_for_function(
                "() => { const el = document.querySelector('#view-dash'); return !!el && !el.classList.contains('hidden'); }"
            )
    finally:
        page.close()


def test_dashboard_kpi_count_waits_for_reports(browser_page, base_url):
    page = browser_page.context.browser.new_page()
    held = []

    def hold_reports(route):
        held.append(route)

    try:
        page.set_viewport_size({"width": 1440, "height": 900})
        page.route("**/api/research/reports", hold_reports)
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator(".glance-pick-card").first.wait_for(timeout=20000)
        page.locator("#dash-champions .champ-card").first.wait_for(timeout=20000)
        page.locator("#kpis .kpi").nth(2).wait_for(timeout=20000)
        loading = (page.locator("#kpis .card-rose .kpi-num").inner_text() or "").strip()
        assert loading == "\u2014", loading
        assert held, "reports request was not intercepted"
        for route in list(held):
            route.continue_()
        held.clear()
        page.locator("#dash-reports-body .dash-report-card, #dash-reports-body .hint").first.wait_for(timeout=20000)
        page.wait_for_function(
            "() => { const num = document.querySelector('#kpis .card-rose .kpi-num');"
            " const unit = document.querySelector('#kpis .card-rose .kpi-unit');"
            " return !!num && !!unit && num.textContent.trim() !== '\\u2014' && /^\\d+$/.test(num.textContent.trim()) && unit.textContent.trim() === '\\uac74'; }"
        )
        loaded = (page.locator("#kpis .card-rose .kpi-num").inner_text() or "").strip()
        assert loaded.isdigit(), loaded
        assert page.locator("#kpis .kpi").count() == 3
        assert page.locator("#dash-flow .dash-nav-card").count() == 2
        assert page.locator("#dash-reports-body tr").count() == 0
        assert page.locator("#dash-reports-body .dash-report-card").count() <= 3
        assert page.locator("#dash-dna-box").count() == 1
        wide = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert wide <= 1, wide
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#kpis .kpi").nth(2).wait_for(timeout=5000)
        narrow = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert narrow <= 1, narrow
        assert page.locator("#kpis .kpi").count() == 3
    finally:
        for route in held:
            try:
                route.continue_()
            except Exception:
                pass
        page.close()
