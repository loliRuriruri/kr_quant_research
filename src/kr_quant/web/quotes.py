"""Small read-only price overlay. Never writes engine inputs or changes ranks."""
import json
import math
import re
from datetime import datetime
from urllib.request import Request, urlopen

from kr_quant.freshness import KST, expected_price_date
from kr_quant.web.cache import ttl_cache


def parse_codes(raw):
    codes = sorted(set(raw.split(',')))
    if not 1 <= len(codes) <= 50 or any(not re.fullmatch(r'[0-9A-Z]{6}', c) for c in codes):
        raise ValueError('6자리 종목 코드 1~50개를 쉼표로 구분해 주세요.')
    return tuple(codes)


@ttl_cache(seconds=15)
def fetch_quotes(codes):
    # Single-flight per canonical batch; no credentials, KIS token or collector.
    request = Request('https://polling.finance.naver.com/api/realtime/domestic/stock/' + ','.join(codes),
                      headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read(512_000).decode('utf-8'))
        return {'ok': True, 'items': data.get('datas', []), 'fetched_at': datetime.now(KST).isoformat()}
    except Exception:
        # Briefly cache outages too, so repeated clicks cannot hammer the source.
        return {'items': [], 'error': '가격 제공처 응답 없음', 'fetched_at': datetime.now(KST).isoformat()}


def normalize_quote(item, now):
    try:
        price = float(item.get('closePriceRaw'))
        traded = datetime.fromisoformat(str(item.get('localTradedAt')))
        if traded.tzinfo is None or not math.isfinite(price) or price <= 0:
            return None
        traded = traded.astimezone(KST)
        age = (now - traded).total_seconds()
        if age < -60:
            return None
    except (ValueError, TypeError):
        return None
    if traded.date() < expected_price_date(now):
        kind, label = 'stale', '지연·과거 시세'
    elif item.get('marketStatus') == 'OPEN' and traded.date() == now.date():
        kind, label = ('intraday', '장중 조회·지연 가능') if age <= 120 else ('stale', '장중 시세 지연')
    elif item.get('marketStatus') == 'CLOSE':
        kind, label = 'close', '종가' if traded.date() == now.date() else '직전 거래 종가'
    else:
        kind, label = 'snapshot', '조회 시세·상태 미확인'
    return {'ticker': str(item.get('itemCode')), 'price': price, 'traded_at': traded.isoformat(),
            'kind': kind, 'label': label, 'source': 'NAVER', 'realtime_verified': False}


def quote_payload(raw, now=None):
    codes = parse_codes(raw)
    current = now or datetime.now(KST)
    source = fetch_quotes(codes)
    rows = []
    for item in source.get('items', []):
        if isinstance(item, dict) and item.get('itemCode') in codes:
            quote = normalize_quote(item, current)
            if quote:
                rows.append(quote)
    found = {r['ticker'] for r in rows}
    return {'ok': bool(rows), 'rows': rows, 'missing': [c for c in codes if c not in found],
            'fetched_at': source['fetched_at'], 'checked_at': current.isoformat(),
            'error': source.get('error'), 'used_in_quant': False,
            'notice': '가격 표시만 갱신합니다. 저장 종가·점수·시즌 선정·목표 환산값은 재계산하지 않습니다.'}
