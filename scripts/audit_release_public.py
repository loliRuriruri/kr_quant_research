"""Read-only static release browser smoke; no collection, publishing or orders."""
import argparse
import json
import threading
import socket
import time
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(folder, output):
    app = FastAPI()
    app.mount('/', StaticFiles(directory=str(folder), html=True), name='public')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(.05)
    result = {'views': [], 'page_errors': [], 'failed_local_requests': [], 'requests': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('request', lambda r: result['requests'].append(r.url.split('/',3)[-1]))
            page.on('pageerror', lambda err: result['page_errors'].append(str(err)))
            page.on('response', lambda r: result['failed_local_requests'].append({'url':r.url.split('/',3)[-1], 'status':r.status})
                    if '127.0.0.1' in r.url and r.status >= 400 else None)
            page.goto(f'http://127.0.0.1:{port}/', wait_until='domcontentloaded')
            page.locator('#top20-body tr.clickable').first.wait_for(timeout=15000)
            views = page.locator('button.nav-btn[data-view]').evaluate_all(
                "els=>els.filter(e=>e.offsetParent!==null).map(e=>e.dataset.view)")
            for view in views:
                page.locator(f'button.nav-btn[data-view="{view}"]').click()
                page.wait_for_timeout(500)
                result['views'].append({'view':view, 'visible':page.locator(f'#view-{view}').is_visible()})
            page.locator('button.nav-btn[data-view="dash"]').click()
            page.screenshot(path=str(output.with_suffix('.png')), full_page=False)
            browser.close()
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    finally:
        server.should_exit = True
        worker.join(timeout=3)
    result['ok'] = bool(result['views']) and all(v['visible'] for v in result['views']) and not result['page_errors'] and not result['failed_local_requests'] and not result.get('error_type')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True))
    return result['ok']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new evidence path')
    raise SystemExit(0 if run(args.folder.resolve(), args.output.resolve()) else 1)
