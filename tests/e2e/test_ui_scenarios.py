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
        page.wait_for_selector("#top20-body tr.clickable", timeout=15000)
        page.wait_for_selector(".glance-pick-name", timeout=15000)
        yield page
        browser.close()


def _open_view(page, name: str) -> None:
    page.locator(f'button.nav-btn[data-view="{name}"]').click()


def test_dashboard_top30_has_real_rows(browser_page):
    rows = browser_page.locator("#top20-body tr.clickable")
    assert rows.count() == 30
    assert "현대차" in rows.nth(0).inner_text()
    assert "Quant TOP 30" in browser_page.locator("#dash-leaderboard-title").inner_text()


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
    _open_view(browser_page, "dash")
    browser_page.locator("#top20-body tr.clickable").first.click()
    browser_page.wait_for_selector("#drawer:not(.hidden)", timeout=8000)
    browser_page.wait_for_selector("#drawer a[href*='naver.com']", timeout=8000)
    body = browser_page.locator("#drawer-body").inner_html()
    assert "finance.naver.com/item/main.naver?code=005380" in body or "finance.naver.com" in body
    hrefs = browser_page.locator("#drawer a[href*='naver.com'], #drawer a[href*='tossinvest']").all()
    joined = " ".join(link.get_attribute("href") or "" for link in hrefs)
    assert "005380" in joined
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
    browser_page.wait_for_selector("#top20-body tr.clickable", timeout=15000)
    assert browser_page.locator('button.nav-btn[data-view="settings"]').count() == 0
    run_btn = browser_page.locator("#view-run button").first
    if run_btn.count():
        assert run_btn.is_disabled()
    assert browser_page.locator("#top20-body tr.clickable").count() >= 1


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
    browser_page.wait_for_selector("#top20-body tr.clickable", timeout=15000)
    cards = browser_page.locator("#view-dash .card, #view-dash .glance-pick-card").all()
    boxes = [el.bounding_box() for el in cards if el.bounding_box() and el.bounding_box()["width"] > 0]
    for i, left in enumerate(boxes[:8]):
        for right in boxes[i + 1 : 8]:
            if _overlap_collision(left, right):
                pytest.fail("mobile cards overlap")
    table = browser_page.locator("#top20-body").bounding_box()
    assert table is not None
    assert table["width"] > 0
