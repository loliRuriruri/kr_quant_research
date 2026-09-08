"""Bounded season prompt evaluation; paid Grok requires --allow-paid. No production cache writes."""
import json
import time
import queue
import threading
import argparse
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kr_quant.web import app as web
from kr_quant.settings import load_settings
from kr_quant.research.providers import resolve_tier1_endpoint, resolve_provider
from kr_quant.research.analyze import call_chat, _extract_json
from kr_quant.research.tier1_contract import ANALYSIS_GUIDANCE
from kr_quant.research.season_ai_quality import validate_season_card


def cases():
    for name, sample, median, wins, current, missing, date in [
        ('normal', 8, .08, 6, ['3개월 수익률 +4%'], [], '2026-09-08'),
        ('weak', 8, -.12, 2, ['3개월 수익률 -18%'], [], '2026-09-08'),
        ('small_sample', 2, .30, 2, [], ['수급', '뉴스'], '2026-09-08'),
        ('missing', 5, .06, 3, [], ['수급', '뉴스', '현재 가격'], '2026-09-08'),
        ('stale', 5, .06, 3, [], ['최신 시세 미수집'], '2026-08-01'),
    ]:
        yield name, {'snapshot': {'selection_date': date, 'generation_id': 'synthetic-'+name},
            'data': {'current_month': 9, 'next_month': 10, 'glance_top3': [{
                'ticker': '000000', 'company': '검증용 가상기업', 'signal_id': name,
                'current_status': 'WATCH', 'current_confirmation_evidence': current,
                'current_confirmation_missing': missing, 'remaining_peak': {
                    'price_as_of': date, 'sample_count': sample, 'window_end_p50': median,
                    'window_end_positive_count': wins, 'window_adverse_excursion_p50': -.05,
                    'validation_status': 'HISTORICAL_ONLY', 'costs_included': False}}]}}


def safe_error_category(exc):
    """Classify errors without retaining arbitrary provider text or credentials."""
    text = str(exc).lower()
    if 'overloaded' in text or '502' in text or '503' in text:
        return 'PROVIDER_UNAVAILABLE'
    if '429' in text or 'rate limit' in text:
        return 'RATE_LIMIT'
    if '401' in text or '403' in text:
        return 'AUTHORIZATION'
    if 'timeout' in type(exc).__name__.lower() or 'timed out' in text:
        return 'TIMEOUT'
    return 'OTHER_ERROR'


def bounded_call(endpoint, messages, deadline=60, request_timeout=20):
    """CLI-only wall-clock bound; daemon ends when this evaluator exits."""
    result = queue.Queue(maxsize=1)
    def worker():
        try:
            result.put((True, call_chat(endpoint, messages, timeout=request_timeout)))
        except Exception as exc:
            result.put((False, exc))
    threading.Thread(target=worker, daemon=True).start()
    try:
        ok, value = result.get(timeout=deadline)
    except queue.Empty:
        raise TimeoutError('Evaluation wall-clock deadline exceeded') from None
    if not ok:
        raise value
    return value


def run(provider='free', allow_paid=False, selected_cases=None):
    if provider != 'free' and (provider != 'xai' or not allow_paid):
        raise RuntimeError('Grok evaluation requires explicit --allow-paid approval')
    endpoint = resolve_provider(load_settings(), 'xai') if provider == 'xai' else resolve_tier1_endpoint(load_settings())
    if provider == 'free' and (endpoint.provider != 'openrouter' or not endpoint.model.endswith(':free')):
        raise RuntimeError('Only configured OpenRouter :free route is allowed')
    records = []
    planned = [(name, fixture) for name, fixture in cases() if not selected_cases or name in selected_cases]
    for name, fixture in planned:
        with patch.object(web, 'api_seasonality_highlights_get', return_value=fixture), patch.object(
            web, 'tier1_cached_chat_json', side_effect=lambda *a, **k: k):
            request = web.api_seasonality_tier1_briefing_get()
        record = {'case': name, 'input': fixture, 'prompt_version': request['prompt_version'],
                  'messages': request['messages'], 'factual_review': 'NOT_REVIEWED'}
        start = time.perf_counter()
        try:
            raw, _ = bounded_call(endpoint, [{'role': 'system', 'content': ANALYSIS_GUIDANCE},
                *request['messages']], deadline=90 if allow_paid else 60,
                request_timeout=75 if allow_paid else 20)
            record['raw_output'] = raw
            record['output'] = _extract_json(raw)
            validate_season_card(record['output'])
            record['status'] = 'SCHEMA_PASS'
        except Exception as exc:
            record['status'] = 'FAILED'
            # Never persist credentials, request headers or arbitrary provider error bodies.
            record['error_type'] = type(exc).__name__
            record['error_category'] = safe_error_category(exc)
        record['seconds'] = round(time.perf_counter()-start, 2)
        records.append(record)
        print(name, record['status'], record['seconds'], flush=True)
        if record['status'] == 'FAILED':
            break  # No retries or paid fallback; do not hammer an unavailable provider.
    destination = Path('docs/audits/ai-stage3')
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = destination / f'{provider}-evaluation-{stamp}.json'
    path.write_text(json.dumps({'provider': endpoint.provider, 'paid_authorized': allow_paid,
        'model': endpoint.model, 'synthetic': True, 'records': records,
        'planned_cases': len(planned), 'unattempted': len(planned)-len(records)}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(path, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['free', 'xai'], default='free')
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--cases', nargs='+', choices=[name for name, _ in cases()])
    args = parser.parse_args()
    run(args.provider, args.allow_paid, args.cases)
