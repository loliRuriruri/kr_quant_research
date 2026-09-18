from pathlib import Path
import re

HTML = Path(__file__).resolve().parents[2] / "src/kr_quant/web/static/index.html"

VISIBLE = [
    "dash", "rank", "screens", "seasonality", "market", "sector",
    "investor", "trade", "strategy", "watch", "us13f", "sunzi", "run", "settings",
]
HIDDEN = ["reports", "nps"]


def _nav_buttons(html: str):
    return re.findall(
        r'<button([^>]*class="[^"]*nav-btn[^"]*"[^>]*)>',
        html,
    )


def test_visible_nav_order_and_views():
    html = HTML.read_text(encoding="utf-8")
    views = re.findall(r'<button class="nav-btn(?: nav-admin)?(?: active)?" data-view="([^"]+)"', html)
    hidden = re.findall(r'<button class="nav-btn hidden" data-view="([^"]+)"', html)
    assert views == VISIBLE
    assert hidden == HIDDEN
    assert len(views) == len(set(views))
    for name in VISIBLE + HIDDEN:
        assert f'id="view-{name}"' in html
    assert 'data-view="toss"' not in html
    assert 'id="view-toss"' in html
    assert "퀀트 랭킹" in html
    assert "시즌·캘린더" in html
    assert "nav-compat hidden" in html
    assert 'data-view="reports"' in html
    assert 'data-view="nps"' in html
    assert "Jev" not in html.split('<main>')[0]
    assert "TypeSafe" not in html.split('<main>')[0]


def test_sidebar_labels_match_contract():
    html = HTML.read_text(encoding="utf-8")
    rank = re.search(
        r'<button class="nav-btn" data-view="rank"[^>]*>.*?<span>([^<]+)</span>',
        html,
        re.S,
    )
    season = re.search(
        r'<button class="nav-btn" data-view="seasonality"[^>]*>.*?<span>([^<]+)</span>',
        html,
        re.S,
    )
    assert rank and rank.group(1) == "퀀트 랭킹"
    assert season and season.group(1) == "시즌·캘린더"


def test_hidden_nav_skips_tab_order():
    html = HTML.read_text(encoding="utf-8")
    for name in HIDDEN:
        match = re.search(
            rf'<button class="nav-btn hidden" data-view="{name}"([^>]*)>',
            html,
        )
        assert match, name
        assert 'tabindex="-1"' in match.group(0)
        assert "nav-compat hidden" in html


def test_compat_routes_remain():
    html = HTML.read_text(encoding="utf-8")
    js = (HTML.parent / "app.js").read_text(encoding="utf-8")
    assert 'id="view-reports"' in html
    assert 'id="view-nps"' in html
    assert 'data-view="reports"' in html
    assert 'data-view="nps"' in html
    assert 'switchView("reports")' in js
    assert "nps: [" in js
    assert 'id="view-toss"' in html
    assert 'data-view="toss"' not in html


def test_page_titles_match_sidebar():
    html = HTML.read_text(encoding="utf-8")
    js = (HTML.parent / "app.js").read_text(encoding="utf-8")
    rank = re.search(r'rank: \["([^"]+)"', js)
    season = re.search(r'seasonality: \["([^"]+)"', js)
    heading = re.search(r'id="view-rank"[\s\S]{0,800}<h2>([^<]+)</h2>', html)
    assert rank and rank.group(1) == "퀀트 랭킹"
    assert season and season.group(1) == "시즌·캘린더"
    assert heading and heading.group(1).strip() == "퀀트 랭킹"
