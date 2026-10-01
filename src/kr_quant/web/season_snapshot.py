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
_MEM_FILE_STAT: dict = {}
_MODEL_CACHE: dict = {}
logger = logging.getLogger("kr_quant.season_snapshot")


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _source_file_provenance(paths):
    result = []
    for path in sorted({Path(p) for p in paths}, key=str):
        if not path.is_file():
            result.append({"path": str(path), "sha256": None})
            continue
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        result.append({"path": str(path), "sha256": sha.hexdigest()})
    return result


def _stat(path):
    p = Path(path)
    try:
        stat = p.stat()
        return [str(p.resolve()), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size]
    except OSError:
        return [str(p.resolve()), None]


def _actual_sources(settings):
    """Only selected inputs, including the alias actually read by safety gates."""
    from kr_quant.strategy.seasonality import _committed_scored_source
    def choose(paths):
        return next((p for p in paths if p.is_file()), paths[0])
    live, demo = settings.staged_dir / 'live', settings.staged_dir / 'demo'
    committed = _committed_scored_source(settings)
    alias = settings.output_dir / 'latest_all_stocks.parquet'
    fallback = []
    if not committed or not alias.exists():
        for dated in sorted(settings.output_dir.glob('as_of_date=*'), reverse=True):
            fallback.extend([dated / 'all_stocks.parquet', dated / 'scored_all.parquet'])
    classification = committed['path'] if committed else choose([alias, *fallback])
    gate_scored = choose([alias, *[p for p in fallback if p.name == 'scored_all.parquet']])
    paths = [choose([live / 'prices.parquet', demo / 'prices.parquet']), classification,
             gate_scored, choose([live / 'krx_master.parquet', live / 'master.parquet']),
             choose([live / 'corporate_actions.parquet', demo / 'corporate_actions.parquet']),
             settings.status_csv, settings.data_dir / 'cache/investor_flow.json',
             settings.output_dir / 'current_manifest.json']
    return sorted(set(paths), key=str), committed


def _model_identity(strong=False):
    code = Path(__file__).resolve().parents[1]
    paths = sorted((code / 'strategy').glob('*.py')) + sorted((code / 'universe').glob('*.py')) + [
        Path(__file__), code / 'flow/reliability.py', code / 'research/statistical_reliability.py']
    signature = _digest([_stat(p) for p in paths])
    with _LOCK:
        if strong or signature not in _MODEL_CACHE:
            _MODEL_CACHE.clear()
            _MODEL_CACHE[signature] = _digest([(str(p), hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
        return _MODEL_CACHE[signature]


def source_revision(settings, lookback=5):
    """Cheap currentness, not a claim of content integrity. Trusted local writer
    publishes immutable generations; changed revision requires a strong rebuild.
    """
    if lookback not in LOOKBACKS:
        raise ValueError("지원 기간: 0(전체), 2, 3, 5년")
    paths, committed = _actual_sources(settings)
    manifest = settings.output_dir / 'current_manifest.json'
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None
    return {"revision_schema": 1, "schema": SCHEMA, "root": str(settings.root.resolve()),
            "day": date.today().isoformat(), "lookback": lookback,
            "sources": [_stat(p) for p in paths], "manifest_sha256": manifest_sha,
            "config_hash": _digest([settings.config,
                getattr(settings, "universe_rules", None), getattr(settings, "risk_rules", None)]),
            "model_hash": _model_identity()}


def source_identity(settings, lookback: int) -> dict:
    """Strong build/publication identity. Never used for normal dashboard reads."""
    paths, committed = _actual_sources(settings)
    _model_identity(strong=True)
    revision = source_revision(settings, lookback)
    provenance = _source_file_provenance(paths)
    if committed:
        actual = next(r['sha256'] for r in provenance if Path(r['path']).resolve() == committed['path'].resolve())
        if actual != committed['expected_sha256']:
            raise RuntimeError('Committed classification SHA256 mismatch')
    return {**revision, 'revision': revision, 'source_file_provenance': provenance}


def _folder(settings) -> Path:
    return settings.data_dir / "research_snapshots" / "season"


def _key(settings, lookback):
    return (str(settings.root.resolve()), lookback)


def _copy_bundle(bundle, listing_view=None):
    if listing_view is None:
        out = copy.deepcopy(bundle)
        out.pop("_serve_meta", None)
        return out
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
    if lookback not in LOOKBACKS:
        raise ValueError("지원 기간: 0(전체), 2, 3, 5년")
    if is_updating(settings):
        return None
    try:
        revision = source_revision(settings, lookback)
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    key = _key(settings, lookback)
    try:
        tip = json.loads((_folder(settings) / f'latest_lb_{lookback}.json').read_text(encoding='utf-8'))
        if tip.get('revision_hash') != _digest(revision):
            return None  # Avoid parsing a huge stale/legacy artifact just to reject it.
        generation = _safe_generation_id(tip.get('generation_id'))
        if generation is None:
            return None
        path = _folder(settings) / f"{generation}.json"
        artifact_stat = _stat(path)
        with _LOCK:
            cached = _MEM.get(key)
            if cached and cached[0] == generation and _MEM_FILE_STAT.get(key) == artifact_stat:
                if cached[1]['identity'].get('revision') == revision:
                    return _copy_bundle(cached[1], listing_view)
                return None
        bundle = json.loads(path.read_text(encoding="utf-8"))
        identity = bundle.get('identity')
        if not isinstance(identity, dict) or bundle.get("generation_id") != generation or _digest(identity) != generation:
            return None
        if identity.get('schema') != SCHEMA or identity.get('root') != str(settings.root.resolve()) or identity.get('lookback') != lookback:
            return None
        if identity.get('revision') != revision:
            return None
        if bundle.get("content_hash") != _digest(bundle.get("payload")):
            return None
        if not isinstance(bundle["payload"].get("rows"), list):
            return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    with _LOCK:
        _MEM[key] = (generation, bundle)
        _MEM_FILE_STAT[key] = artifact_stat
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


def _safe_generation_id(value) -> str | None:
    """Accept only opaque hex digests; reject path-like or traversable names."""
    if not isinstance(value, str) or not value:
        return None
    lowered = value.lower()
    if any(token in value for token in ("/", "\\", "..", ":", "\0")):
        return None
    if len(lowered) != 64 or any(ch not in "0123456789abcdef" for ch in lowered):
        return None
    return lowered


def read_last_known_good(settings, lookback: int = 5, *, listing_view=None) -> dict | None:
    """Display-only prior snapshot. Never weakens read_bundle() current identity checks."""
    if lookback not in LOOKBACKS:
        raise ValueError("지원 기간: 0(전체), 2, 3, 5년")
    pointer = _folder(settings) / f"latest_lb_{lookback}.json"
    try:
        tip = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(tip, dict):
        return None
    generation = _safe_generation_id(tip.get("generation_id"))
    if generation is None:
        return None
    path = _folder(settings) / f"{generation}.json"
    try:
        # Resolve strictly under the season folder; reject escapes even if hex-like.
        if path.resolve().parent != _folder(settings).resolve():
            return None
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(bundle, dict):
            return None
        if _safe_generation_id(bundle.get("generation_id")) != generation:
            return None
        identity = bundle.get("identity")
        if not isinstance(identity, dict) or identity.get("lookback") != lookback:
            return None
        if identity.get("schema") != SCHEMA:
            return None
        # Fail-closed: LKG generation must still bind to the stored identity digest.
        if _digest(identity) != generation:
            return None
        # Installation root must match; never silently rewrite a foreign snapshot root.
        if identity.get("root") != str(settings.root.resolve()):
            return None
        payload = bundle.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            return None
        if bundle.get("content_hash") != _digest(payload):
            return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return _copy_bundle(bundle, listing_view)


def refresh_in_flight(settings, lookback: int) -> bool:
    with _LOCK:
        return _key(settings, lookback) in _PENDING


def attach_serve_meta(
    bundle,
    *,
    is_current: bool,
    refresh_pending: bool = False,
    expected_as_of: str | None = None,
    refresh_error: bool = False,
    refresh_error_code: str | None = None,
):
    """Ephemeral HTTP/serve marker only. Must never be written into generation JSON."""
    if bundle is None:
        return None
    meta = {
        "is_current": bool(is_current),
        "refresh_pending": bool(refresh_pending),
    }
    if is_current:
        meta["state"] = "ready"
    else:
        meta["state"] = "stale_while_revalidate"
        meta["snapshot_as_of"] = bundle["identity"]["day"]
        meta["expected_as_of"] = expected_as_of or date.today().isoformat()
        if refresh_error:
            meta["refresh_error"] = True
            meta["refresh_error_code"] = refresh_error_code or "SEASON_BUILD_FAILED"
    bundle["_serve_meta"] = meta
    return bundle


def public_meta(bundle) -> dict:
    serve = bundle.get("_serve_meta") if isinstance(bundle.get("_serve_meta"), dict) else {}
    meta = {
        "generation_id": bundle["generation_id"],
        "generated_at": bundle["generated_at"],
        "selection_date": bundle["identity"]["day"],
        "lookback_years": bundle["identity"]["lookback"],
        "state": serve.get("state", "ready"),
        "record_type": "observed_snapshot",
        "schema": SCHEMA,
        "is_current": serve.get("is_current", True),
        "refresh_pending": bool(serve.get("refresh_pending", False)),
    }
    if serve.get("state") == "stale_while_revalidate":
        meta["snapshot_as_of"] = serve.get("snapshot_as_of") or meta["selection_date"]
        meta["expected_as_of"] = serve.get("expected_as_of")
        if serve.get("refresh_error"):
            meta["refresh_error"] = True
            meta["refresh_error_code"] = serve.get("refresh_error_code") or "SEASON_BUILD_FAILED"
    return meta


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
                          {"generation_id": generation, "generated_at": bundle["generated_at"],
                           "revision_hash": _digest(identity['revision'])})
        with _LOCK:
            _MEM[_key(settings, lookback)] = (generation, bundle)
        return copy.deepcopy(bundle)


def _schedule_shadow(settings, bundle, lookback: int) -> None:
    """Never block snapshot completion. Jev is optional and isolated."""
    if lookback != 5 or not isinstance(bundle, dict):
        return
    try:
        from kr_quant.research.jev_runtime import request_runtime_evaluation

        request_runtime_evaluation(settings, bundle)
    except Exception:
        logger.exception("Jev shadow schedule failed; season snapshot unchanged")


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
            bundle = build_bundle(settings, lookback)
            with _LOCK:
                _ERRORS.pop(key, None)
            _schedule_shadow(settings, bundle, lookback)
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
