"""Verify the approved production season route and same-snapshot cache reuse."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from kr_quant.web import app as web

snapshot = web.api_seasonality_highlights_get()
with patch.object(web, 'api_seasonality_highlights_get', return_value=snapshot):
    started = time.perf_counter()
    result = web.api_seasonality_tier1_briefing_get()
    seconds = round(time.perf_counter()-started, 2)
    started = time.perf_counter()
    repeated = web.api_seasonality_tier1_briefing_get() if result.get('ok') else {}
    repeat_seconds = round(time.perf_counter()-started, 2)
path = Path('docs/audits/ai-stage3') / ('live-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({'input': snapshot, 'result': result, 'seconds': seconds,
    'repeat_cache_hit': repeated.get('cache', {}).get('hit'), 'repeat_seconds': repeat_seconds,
    'same_headline': result.get('headline') == repeated.get('headline')}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
print(json.dumps({'path':str(path), 'ok':result.get('ok'), 'provider':result.get('provider'),
    'seconds':seconds,'cache_hit':repeated.get('cache',{}).get('hit'),'repeat_seconds':repeat_seconds}))
