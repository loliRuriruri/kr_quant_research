"""Versioned, immutable season menu bundles. Reads never run the research engine."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from kr_quant.atomic_io import write_json_atomic

SCHEMA = 1
LOOKBACKS = {0, 2, 3, 5}
_LOCK = threading.RLock()
_BUILD_LOCK = threading.Lock()
_PENDING: set[tuple[str, int]] = set()
_ERRORS: dict[tuple[str, int], tuple[float, str]] = {}
_MEM: dict[tuple[str, int], tuple[str, dict]] = {}
logger = logging.getLogger("kr_quant.season_snapshot")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def source_identity(settings, lookback: int) -> dict:
    if lookback not in LOOKBACKS:
        raise ValueError("지원 기간: 0(전체), 2, 3, 5년")
    from kr_quant.strategy.seasonality import _seasonality_source_signature

    paths = [settings.output_dir / "latest_all_stocks.parquet",
             settings.staged_dir / "live" / "krx_master.parquet",
             settings.data_dir / "cache" / "investor_flow.json"]
    paths += sorted(settings.output_dir.glob("as_of_date=*/all_stocks.parquet"))
    paths += sorted(settings.output_dir.glob("as_of_date=*/scored_all.parquet"))
    code = Path(__file__).resolve().parents[1]
    code_paths = sorted((code / "strategy").glob("*.py")) + sorted((code / "universe").glob("*.py")) + [Path(__file__)]
    sources = _seasonality_source_signature(settings) + [
        [str(p), p.stat().st_mtime_ns, p.stat().st_size] if p.exists() else [str(p), None]
        for p in paths
    ]
    return {"schema": SCHEMA, "root": str(settings.root.resolve()),
            "day": date.today().isoformat(), "lookback": lookback,
            "sources": sources, "config_hash": _digest([settings.config,
                getattr(settings, "universe_rules", None), getattr(settings, "risk_rules", None)]),
            "model_hash": _digest([(str(p), hashlib.sha256(p.read_bytes()).hexdigest()) for p in code_paths])}


def _folder(settings) -> Path:
    return settings.data_dir / "research_snapshots" / "season"


def _key(settings, lookback):
    return (str(settings.root.resolve()), lookback)


def _copy_bundle(bundle, listing_view=None):
    if listing_view is None:
        return copy.deepcopy(bundle)
    if listing_view in ('themes', 'highlights', 'pre-entry', 'pre-entry-summary'):
        payload = bundle['payload']
        selected = {'stats': payload['stats']}
        if listing_view in ('pre-entry', 'pre-entry-summary'):
            selected.update(rows=[r for r in payload['rows'] if r.get('pre_entry_rank') is not None],
                            themes=payload['themes'])
            if listing_view == 'pre-entry-summary':
                from kr_quant.web.season_listing import pre_entry_card
                selected['rows'] = [pre_entry_card(r, bundle['identity']['lookback']) for r in selected['rows']]
        else:
            selected[listing_view] = payload[listing_view]
        return copy.deepcopy({'generation_id': bundle['generation_id'],
                              'generated_at': bundle['generated_at'],
                              'identity': bundle['identity'], 'payload': selected})
    from kr_quant.web.season_listing import LIST_FIELDS, EXPLANATION_FIELDS
    if listing_view not in ('summary', 'explanation'):
        raise ValueError('지원 목록 형식: summary, explanation')
    fields = (LIST_FIELDS if listing_view == 'summary' else EXPLANATION_FIELDS) | {
        'event_explanation_mode', 'event_hypothesis', 'common_event_cluster', 'failed_years'}
    # Cache entries never escape by reference. Do not copy peak samples, themes,
    # highlights or playbooks that are not consumed by the listing endpoint.
    return {'generation_id': bundle['generation_id'], 'generated_at': bundle['generated_at'],
            'identity': copy.deepcopy(bundle['identity']),
            'payload': {'stats': copy.deepcopy(bundle['payload']['stats']),
                        'rows': [{key: copy.deepcopy(value) for key, value in row.items() if key in fields}
                                 for row in bundle['payload']['rows']]}}


def read_bundle(settings, lookback: int = 5, *, listing_view=None) -> dict | None:
    from kr_quant.run_generation import is_updating
    if is_updating(settings):
        return None
    identity = source_identity(settings, lookback)
    generation = _digest(identity)
    key = _key(settings, lookback)
    with _LOCK:
        cached = _MEM.get(key)
        if cached and cached[0] == generation:
            return _copy_bundle(cached[1], listing_view)
    path = _folder(settings) / f"{generation}.json"
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if bundle.get("generation_id") != generation or bundle.get("identity") != identity:
            return None
        if bundle.get("content_hash") != _digest(bundle.get("payload")):
            return None
        if not isinstance(bundle["payload"].get("rows"), list):
            return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    with _LOCK:
        _MEM[key] = (generation, bundle)
    return _copy_bundle(bundle, listing_view)


def select_rows(bundle, *, horizon_days=90, min_grade=None, status=None, query=None, exclude_expired=False):
    if not 0 <= horizon_days <= 365:
        raise ValueError("탐색 범위는 0~365일입니다.")
    today = date.fromisoformat(bundle["identity"]["day"])
    months = {(today + timedelta(days=d)).month for d in range(0, horizon_days + 1, 15)}
    grades = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}
    rows = []
    for row in bundle["payload"]["rows"]:
        month = int(str(row.get("window_name", "")).replace("월", "") or today.month)
        if month not in months:
            continue
        if min_grade and grades.get(row.get("grade"), 0) < grades.get(min_grade, 0):
            continue
        if status and status != "all" and row.get("current_status") != status:
            continue
        if query and query.strip().upper() not in " ".join(str(row.get(k) or "") for k in ("ticker", "company", "common_event_cluster")).upper():
            continue
        if exclude_expired and row.get("entry_stage") == "SEASON_END":
            continue
        rows.append(copy.deepcopy(row))
    # Preserve canonical rank identity across filters; filters do not rewrite history.
    return rows


def public_meta(bundle) -> dict:
    return {"generation_id": bundle["generation_id"], "generated_at": bundle["generated_at"],
            "selection_date": bundle["identity"]["day"], "lookback_years": bundle["identity"]["lookback"],
            "state": "ready", "record_type": "observed_snapshot", "schema": SCHEMA}


def build_bundle(settings, lookback: int = 5) -> dict:
    """Explicit offline/background job; verify inputs before publishing one file."""
    with _BUILD_LOCK:
        from kr_quant.run_generation import is_updating
        if is_updating(settings):
            raise RuntimeError("점수 자료 갱신 중: 완성된 세대를 기다립니다.")
        cached = read_bundle(settings, lookback)
        if cached is not None:
            return cached
        from kr_quant.strategy import seasonality as engine
        from kr_quant.strategy.theme_engine import calculate_theme_seasonality

        identity = source_identity(settings, lookback)
        generation = _digest(identity)
        rows = engine.scan_seasonality_discovery(settings, horizon_days=365, lookback_years=lookback)
        for row in rows:
            row["signal_id"] = _digest([generation, row.get("ticker"), row.get("pattern_id"), row.get("window_name")])
            row["generation_id"] = generation
        if len({row["signal_id"] for row in rows}) != len(rows):
            raise RuntimeError("중복 선정 식별자가 있어 공통 자료를 게시하지 않습니다.")
        bundle = {"generation_id": generation, "identity": identity,
                  "generated_at": datetime.now(timezone.utc).isoformat(), "payload": {"rows": rows}}
        within90 = select_rows(bundle)
        highlights = engine.get_seasonality_highlights(settings, discovery_rows=within90)
        themes = calculate_theme_seasonality([], event_rows_by_preset={
            key: engine.scan_seasonality(settings, preset=key) for key in engine.EVENT_PRESETS
        })
        bundle["payload"].update(highlights=highlights, themes=themes,
                                 stats=engine.seasonality_universe_stats(settings))
        if is_updating(settings) or source_identity(settings, lookback) != identity:
            raise RuntimeError("계산 중 원천 자료 변경: 기존 완성본을 보존하고 다음 갱신에서 다시 준비합니다.")
        bundle["content_hash"] = _digest(bundle["payload"])
        # Each generation is a separate observation, not a retrospectively invented signal.
        destination = _folder(settings) / f"{generation}.json"
        temporary = destination.with_name(f".{generation}.{uuid4().hex}.json")
        try:
            write_json_atomic(temporary, bundle)
            try:
                # Atomic create-if-absent across processes; never overwrite a prior observation.
                os.link(temporary, destination)
            except FileExistsError:
                winner = read_bundle(settings, lookback)
                if winner is None:
                    raise RuntimeError("동일 세대 저장본 무결성 오류: 원본을 덮어쓰지 않습니다.")
                bundle = winner
        finally:
            temporary.unlink(missing_ok=True)
        write_json_atomic(_folder(settings) / f"latest_lb_{lookback}.json",
                          {"generation_id": generation, "generated_at": bundle["generated_at"]})
        with _LOCK:
            _MEM[_key(settings, lookback)] = (generation, bundle)
        return copy.deepcopy(bundle)


def request_build(settings, lookback: int = 5) -> None:
    """Bounded single-flight refresh; never wait in an HTTP handler."""
    if lookback not in LOOKBACKS:
        raise ValueError("지원 기간: 0(전체), 2, 3, 5년")
    key = _key(settings, lookback)
    with _LOCK:
        failed = _ERRORS.get(key)
        if key in _PENDING or (failed and time.monotonic() - failed[0] < 60):
            return
        _PENDING.add(key)

    def work():
        try:
            build_bundle(settings, lookback)
            with _LOCK:
                _ERRORS.pop(key, None)
        except Exception as exc:
            logger.exception("Season snapshot preparation failed")
            with _LOCK:
                _ERRORS[key] = (time.monotonic(), type(exc).__name__)
        finally:
            with _LOCK:
                _PENDING.discard(key)
    threading.Thread(target=work, name=f"season-snapshot-{lookback}", daemon=True).start()


def preparation_failed(settings, lookback: int) -> bool:
    with _LOCK:
        key = _key(settings, lookback)
        failed = _ERRORS.get(key)
        return bool(key not in _PENDING and failed and time.monotonic() - failed[0] < 60)


def refresh_after_data_job(settings) -> None:
    # Always refresh default; also retain periods explicitly used on this installation.
    periods = {5}
    for period in LOOKBACKS:
        if (_folder(settings) / f"latest_lb_{period}.json").exists():
            periods.add(period)
    for period in sorted(periods, key=lambda value: value != 5):
        request_build(settings, period)
