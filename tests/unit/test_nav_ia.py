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
