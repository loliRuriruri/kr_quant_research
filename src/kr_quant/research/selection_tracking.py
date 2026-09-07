"""Background-only materialization of observed Quant cohorts and their outcomes."""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

from kr_quant.hashing import sha256_file, sha256_json
from kr_quant.research.selection_ledger import capture_quant_selection, folder, latest_index, read_verified, write_once, write_verified
from kr_quant.research.selection_outcomes import observe_selection_outcomes

_LOCK = threading.Lock()
_THREADS: dict[str, threading.Thread] = {}
logger = logging.getLogger('kr_quant.selection_tracking')


def price_fingerprint(path):
    stat = path.stat()
    return {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def refresh_tracking(settings) -> dict:
    current = capture_quant_selection(settings)['payload']
    price_path = settings.staged_dir/'live/prices.parquet'
    source_hash = sha256_file(price_path)
    fingerprint = price_fingerprint(price_path)
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    # Conservative local policy: today's daily bar is not evaluated before 19:00.
    through = now.date() if now.hour >= 19 else (now-timedelta(days=1)).date()
    paths = sorted(p for p in folder(settings).glob('*.json') if re.fullmatch(r'[a-f0-9]{64}', p.stem))
    batches = [read_verified(path)['payload'] for path in paths]
    first_day = min(pd.Timestamp(batch['observed_at']).tz_convert('Asia/Seoul').date() for batch in batches)
    columns = pq.ParquetFile(price_path).schema_arrow.names
    day = 'trade_date' if 'trade_date' in columns else 'date'
    needed = [day, 'ticker', 'open', 'close', 'volume'] + (['adj_close'] if 'adj_close' in columns else [])
    frame = pd.read_parquet(price_path, columns=needed,
                            filters=[(day, '>', pd.Timestamp(first_day)), (day, '<=', pd.Timestamp(through))])
    sessions = sorted(pd.to_datetime(frame[day]).dt.date.unique()) if not frame.empty else []
    reports = []
    for batch in batches:
        selected = {row['ticker'] for row in batch['selected']}
        prices = frame[frame['ticker'].astype(str).str.zfill(6).isin(selected)]
        report = observe_selection_outcomes(batch, prices, sessions, observed_through=through)
        report['methodology']['calendar_source'] = 'UNION_OF_OBSERVED_KRX_DAILY_DATES_NOT_OFFICIAL_CALENDAR'
        report['price_source_hash'] = source_hash
        report['price_fingerprint'] = fingerprint
        report['computed_at'] = now.isoformat()
        report['price_data_max_date'] = max(sessions).isoformat() if sessions else None
        report_id = sha256_json([1, batch['batch_id'], source_hash, fingerprint, through.isoformat(),
                                sha256_file(__file_path()), sha256_file(__outcomes_path())])
        report['report_id'] = report_id
        reports.append(report)
    if sha256_file(price_path) != source_hash or price_fingerprint(price_path) != fingerprint:
        raise ValueError('성과 계산 도중 가격 원천이 변경됐습니다.')
    report_dir = folder(settings)/'outcomes'
    newest = None
    for report in reports:
        saved = write_once(report_dir/f"{report['report_id']}.json", report)['payload']
        write_verified(report_dir/f"batch_{report['batch_id']}.json", saved)
        if saved['batch_id'] == current['batch_id']:
            newest = saved
    write_verified(report_dir/'latest.json', newest)
    logger.info('선정 관측 기록 %s개 세대 갱신; 최신 표본 %s개', len(reports), current['selected_count'])
    return newest


def __file_path():
    from pathlib import Path
    return Path(__file__)


def __outcomes_path():
    from pathlib import Path
    from kr_quant.research import selection_outcomes
    return Path(selection_outcomes.__file__)


def request_tracking_refresh(settings):
    key = str(settings.root.resolve())
    with _LOCK:
        running = _THREADS.get(key)
        if running and running.is_alive():
            return
        def work():
            try:
                refresh_tracking(settings)
            except Exception:
                logger.exception('선정 관측 기록 갱신 실패; 기존 관측 자료 보존')
        thread = threading.Thread(target=work, name='quant-observation-refresh', daemon=True)
        _THREADS[key] = thread
        thread.start()


def tracking_response(settings) -> dict:
    index = latest_index(settings)
    if index is None:
        return {'ok': False, 'state': 'NOT_RECORDED', 'detail': '아직 실제 선정 관측 기록이 없습니다. 정상 실데이터 계산 완료 후 생성됩니다.'}
    path = folder(settings)/'outcomes/latest.json'
    report = read_verified(path)['payload'] if path.exists() else None
    if report and report.get('batch_id') != index['batch_id']:
        report = None
    from kr_quant.run_generation import load_manifest, is_updating
    manifest = load_manifest(settings) or {}
    current = (not is_updating(settings) and manifest.get('run_id') == index['run_id']
               and (manifest.get('files', {}).get('latest_all_stocks.parquet') or {}).get('sha256') == index['source_hashes']['stocks'])
    price = settings.staged_dir/'live/prices.parquet'
    fresh = bool(report and price.exists() and report.get('price_fingerprint') == price_fingerprint(price))
    state = 'READY' if report and fresh else ('OUTCOMES_STALE' if report else 'OUTCOMES_PENDING')
    return {'ok': True, 'state': state,
            'current_generation': current, 'selection': index, 'outcomes': report,
            'detail': '실제 기록 시점 이후 가격 관측입니다. 과거 재구성 백테스트나 체결 성과가 아닙니다.'}
