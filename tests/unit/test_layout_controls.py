from pathlib import Path


STATIC = Path(__file__).resolve().parents[2] / 'src/kr_quant/web/static'


def test_layout_controls_preserve_desktop_and_zoom():
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    js = (STATIC / 'app.js').read_text(encoding='utf-8')
    css = (STATIC / 'styles.css').read_text(encoding='utf-8')
    assert 'width=device-width, initial-scale=1, user-scalable=yes' in html
    assert 'id="layout-mode"' in html
    assert 'aria-controls="main-navigation"' in html
    assert 'function applyLayoutMode(mode)' in js
    assert 'localStorage.getItem("kr-quant-layout")' in js
    assert 'width=1200, user-scalable=yes' in js
    assert 'setCompactMenu(false);\n  switchView(btn.dataset.view);' in js
    assert 'overflow-x: auto' in css
    assert 'html:not([data-layout="desktop"])' in css
