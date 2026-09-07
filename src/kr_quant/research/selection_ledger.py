"""Observed Quant selections; never backdate records to the price reference day."""
from __future__ import annotations

import json
import math
import os
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from kr_quant.atomic_io import write_json_atomic
from kr_quant.hashing import sha256_file, sha256_json
from kr_quant.run_generation import load_manifest, is_updating

SCHEMA = 1
_LOCK = threading.RLock()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(value) else None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value if isinstance(value, str) else str(value)


def folder(settings) -> Path:
    return settings.data_dir / 'research_snapshots' / 'quant'


def read_verified(path: Path) -> dict:
    result = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(result, dict) or not isinstance(result.get('payload'), dict) or result.get('content_hash') != sha256_json(result.get('payload')):
        raise ValueError('선정 기록 무결성 오류')
    return result


def write_verified(path: Path, payload: dict):
    payload = clean(payload)
    write_json_atomic(path, {'payload': payload, 'content_hash': sha256_json(payload)})


def write_once(path: Path, payload: dict) -> dict:
    """Cross-process atomic create; first observation wins for this identity."""
    document = {'payload': clean(payload)}
    document['content_hash'] = sha256_json(document['payload'])
    temporary = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    try:
        write_json_atomic(temporary, document)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return read_verified(path)
    finally:
        temporary.unlink(missing_ok=True)
    return document


def capture_quant_selection(settings, *, now: datetime | None = None) -> dict:
    """Capture only a current, committed LIVE generation, including rejected names."""
    with _LOCK:
        manifest = load_manifest(settings)
        if not manifest or is_updating(settings):
            raise ValueError('완성된 Quant 세대가 없습니다.')
        run_dir = Path(manifest['generation_dir'])
        stock_path = run_dir/'latest_all_stocks.parquet'
        quality_path = run_dir/'data_quality_report.json'
        stock_hash, quality_hash = sha256_file(stock_path), sha256_file(quality_path)
        for name, actual in [('latest_all_stocks.parquet', stock_hash), ('data_quality_report.json', quality_hash)]:
            expected = (manifest.get('files', {}).get(name) or {}).get('sha256')
            if not expected or actual != expected:
                raise ValueError(f'완성본 원천 해시 불일치: {name}')
        quality = json.loads(quality_path.read_text(encoding='utf-8'))
        if quality.get('status') != 'success' or quality.get('source_mode') != 'live':
            raise ValueError('실데이터 성공 세대만 선정 기록에 저장합니다.')
        if quality.get('run_id') != manifest.get('run_id') or quality.get('as_of_date') != manifest.get('as_of_date'):
            raise ValueError('선정 원천 기준일/실행 ID 불일치')
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError('관측 시각에는 시간대가 필요합니다.')
        as_of = str(manifest['as_of_date'])
        if pd.Timestamp(as_of).date() > now.astimezone(ZoneInfo('Asia/Seoul')).date():
            raise ValueError('미래 기준일은 관측 기록으로 저장할 수 없습니다.')
        if pd.Timestamp(manifest['committed_at']) > pd.Timestamp(now):
            raise ValueError('완성본 게시 시각보다 이른 관측 기록은 허용하지 않습니다.')
        batch_id = sha256_json([SCHEMA, manifest['run_id'], stock_hash, quality_hash])
        destination = folder(settings)/f'{batch_id}.json'
        if destination.exists():
            saved = read_verified(destination)
            _publish_index(settings, saved)
            return saved
        frame = pd.read_parquet(stock_path)
        required = {'ticker', 'run_id', 'as_of_date', 'quant_rank', 'quant_score', 'universe_eligible', 'top100_eligible'}
        if not required.issubset(frame.columns):
            raise ValueError('선정 원천 필수 열 누락')
        rows = clean(frame.to_dict('records'))
        tickers = [r['ticker'] for r in rows]
        if len(set(tickers)) != len(tickers) or any(not isinstance(t, str) or not re.fullmatch(r'[0-9A-Z]{6}', t) for t in tickers):
            raise ValueError('종목 코드 중복/형식 오류')
        if any(r['run_id'] != manifest['run_id'] or str(r['as_of_date'])[:10] != as_of for r in rows):
            raise ValueError('혼합된 종목 기준일/실행 ID')
        candidates = [r for r in rows if r['universe_eligible'] is True and r['top100_eligible'] is True]
        if any(r['quant_rank'] is None or r['quant_score'] is None or not 0 <= r['quant_score'] <= 100
               or r['quant_rank'] < 1 or int(r['quant_rank']) != r['quant_rank'] for r in candidates):
            raise ValueError('적격 후보 점수/순위 누락')
        if len({r['quant_rank'] for r in candidates}) != len(candidates):
            raise ValueError('적격 후보 순위 중복')
        candidates.sort(key=lambda r: (r['quant_rank'], r['ticker']))
        selected = candidates[:100]
        for r in selected:
            r['signal_id'] = sha256_json([batch_id, r['ticker']])
        reasons = Counter()
        decisions = []
        for r in rows:
            excluded = r.get('exclusion_reasons') or []
            if isinstance(excluded, str):
                excluded = [excluded] if excluded else []
            reasons.update(excluded)
            decisions.append({k: r.get(k) for k in ('ticker', 'quant_rank', 'quant_score', 'universe_eligible', 'top100_eligible', 'exclusion_reasons')})
        payload = {'schema': SCHEMA, 'batch_id': batch_id, 'run_id': manifest['run_id'],
                   'source_as_of': as_of, 'observed_at': now.astimezone(timezone.utc).isoformat(),
                   'source_committed_at': manifest['committed_at'], 'record_type': 'observed_quant_selection',
                   'source_hashes': {'stocks': stock_hash, 'quality': quality_hash},
                   'source_bundle_hash': manifest.get('source_bundle_hash'),
                   'selection_rule': 'universe_eligible AND top100_eligible; quant_rank ascending; first 100',
                   'universe_count': len(rows), 'eligible_count': len(candidates),
                   'selected_count': len(selected), 'exclusion_counts': dict(sorted(reasons.items())),
                   'selected': selected, 'universe_decisions': decisions,
                   'outcome_rule': 'NEXT_OBSERVED_MARKET_SESSION_OPEN_TO_HORIZON_CLOSE',
                   'limitations': ['관측 시각은 실제 기록 생성 시각이며 가격 기준일로 소급하지 않습니다.',
                                   '선정 기록은 주문·체결 기록이 아닙니다.']}
        if is_updating(settings) or load_manifest(settings) != manifest or sha256_file(stock_path) != stock_hash or sha256_file(quality_path) != quality_hash:
            raise ValueError('기록 도중 원천 세대 변경')
        saved = write_once(destination, payload)
        _publish_index(settings, saved)
        return saved


def _publish_index(settings, saved):
    p = saved['payload']
    index = {k: p[k] for k in ('batch_id', 'run_id', 'source_hashes', 'source_as_of', 'observed_at', 'record_type', 'universe_count', 'eligible_count', 'selected_count', 'exclusion_counts', 'limitations')}
    index['selected'] = [{k: row.get(k) for k in ('ticker', 'company', 'quant_rank', 'quant_score', 'signal_id')} for row in p['selected']]
    write_verified(folder(settings)/'latest.json', index)


def latest_index(settings):
    path = folder(settings)/'latest.json'
    return read_verified(path)['payload'] if path.exists() else None
