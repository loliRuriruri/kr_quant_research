"""Bounded background preparation for optional stock-level year-split diagnostics."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import logging
import re
import threading
import time

import pandas as pd

from kr_quant.hashing import sha256_file, sha256_json
from kr_quant.research import season_holdout
from kr_quant.research.selection_ledger import read_verified, write_once

_LOCK = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='season-holdout')
_PENDING = set()
_ERRORS = {}


def _code_hash():
    return sha256_json([sha256_file(Path(season_holdout.__file__)), sha256_file(Path(__file__))])


_LOADED_CODE_HASH = _code_hash()


def identity(settings, ticker, lookback):
    if not re.fullmatch(r'[0-9A-Z]{6}', ticker) or lookback not in (0, 2, 3, 5):
        raise ValueError('종목 코드 또는 기간 오류')
    if _code_hash() != _LOADED_CODE_HASH:
        raise ValueError('계산 코드가 변경됐습니다. 서버 재시작 후 다시 준비하세요.')
    path = settings.staged_dir/'live/prices.parquet'
    stat = path.stat()
    return {'schema': 2, 'ticker': ticker, 'lookback_years': lookback,
            'as_of': datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),
            'price_size': stat.st_size, 'price_mtime_ns': stat.st_mtime_ns,
            'code_hash': _LOADED_CODE_HASH}


def destination(settings, token):
    return settings.data_dir/'research_snapshots/season_holdout'/f'{sha256_json(token)}.json'


def build_report(settings, ticker, lookback=5):
    token = identity(settings, ticker, lookback)
    path = destination(settings, token)
    if path.exists():
        return read_verified(path)['payload']
    price = settings.staged_dir/'live/prices.parquet'
    digest = sha256_file(price)
    frame = pd.read_parquet(price, columns=['ticker', 'trade_date', 'open', 'close', 'volume'], filters=[('ticker', '==', ticker)])
    dates = pd.read_parquet(price, columns=['trade_date'])['trade_date'].drop_duplicates()
    dates = pd.to_datetime(dates, errors='raise')
    dates = dates[dates.dt.date <= pd.Timestamp(token['as_of']).date()]
    report = season_holdout.evaluate_season_holdout(frame, ticker=ticker,
                as_of=pd.Timestamp(token['as_of']).date(), sessions=dates, lookback_years=lookback)
    report.update(identity=token, report_id=sha256_json(token), price_source_hash=digest,
                  price_as_of=str(pd.to_datetime(dates).max().date()) if len(dates) else None,
                  generated_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
    if identity(settings, ticker, lookback) != token or sha256_file(price) != digest:
        raise ValueError('계산 중 원천 변경: 이전 결과 보존')
    return write_once(path, report)['payload']


def get_or_queue(settings, ticker, lookback=5):
    token = identity(settings, ticker, lookback)
    path = destination(settings, token)
    if path.exists():
        return {'state': 'READY', 'report': read_verified(path)['payload']}
    key = str(path)
    with _LOCK:
        failed = _ERRORS.get(key)
        if failed and time.monotonic()-failed < 60:
            return {'state': 'ERROR', 'detail': '원천 또는 계산 검사 실패. 기존 자료를 보존했습니다. 잠시 후 다시 펼쳐 주세요.'}
        if key in _PENDING:
            return {'state': 'PENDING'}
        if len(_PENDING) >= 8:
            return {'state': 'BUSY'}
        _PENDING.add(key)
    def work():
        try:
            build_report(settings, ticker, lookback)
            with _LOCK:
                _ERRORS.pop(key, None)
        except Exception:
            logging.getLogger('kr_quant.season_holdout').exception('연도 분리 진단 준비 실패')
            with _LOCK:
                _ERRORS[key] = time.monotonic()
        finally:
            with _LOCK:
                _PENDING.discard(key)
    try:
        _POOL.submit(work)
    except Exception:
        with _LOCK:
            _PENDING.discard(key)
        raise
    return {'state': 'PENDING'}
