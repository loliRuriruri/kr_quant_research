"""Phase 1 Jev Shadow Decision Layer. Never mutates Quant ranks or season snapshots."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_quant.atomic_io import write_json_atomic
from kr_quant.web.season_snapshot import select_rows, source_identity

logger = logging.getLogger("kr_quant.season_jev_shadow")

FORBIDDEN_STATE_KEYS = frozenset({"pre_entry_rank", "grade", "seasonality_score", "score_breakdown"})
REMAINING_PEAK_FIELDS = (
    "available",
    "remaining_p50",
    "positive_peak_rate",
    "downside_before_peak_p50",
    "sample_count",
    "confidence",
    "validation_status",
)
DEFAULTS = {
    "enabled": False,
    "evaluator_version": "season-jev-shadow-v1",
    "provider": "typesafe_direct",
    "model": "jev-latest",
    "lookback_years": 5,
    "horizon_days": 90,
    "concurrency": 4,
    "candidate_timeout_ms": 8000,
    "process_timeout_seconds": 180,
    "process_soft_deadline_seconds": 170,
    "process_start_cutoff_seconds": 160,
    "max_api_calls_per_generation": 300,
    "max_api_calls_per_day": 300,
}

_PENDING: set[str] = set()
_LOCK = threading.Lock()

SUPPORTED_PROVIDERS = frozenset({"typesafe_direct", "vercel_gateway"})
PROVIDER_RUNNERS = {
    "typesafe_direct": "scripts/jev-season-shadow.mjs",
    "vercel_gateway": "scripts/jev-season-shadow-gateway.mjs",
}


def load_config(settings) -> dict[str, Any]:
    path = Path(settings.root) / "config" / "season_jev.json"
    data: dict[str, Any] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, ValueError, TypeError):
        data = {}
    out = dict(DEFAULTS)
    out.update({key: data[key] for key in DEFAULTS if key in data})
    return out


def shadow_dir(settings) -> Path:
    return Path(settings.data_dir) / "research_snapshots" / "season_jev_shadow"


def shadow_path(settings, generation_id: str, provider: str = "typesafe_direct") -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in provider)
    return shadow_dir(settings) / f"{generation_id}__{safe}.json"


def has_shadow(settings, generation_id: str, cfg: dict[str, Any] | None = None) -> bool:
    path = shadow_path(settings, generation_id, provider_name(cfg))
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    cfg = cfg or {}
    return (
        payload.get("provider") == provider_name(cfg)
        and payload.get("requested_model") == (cfg.get("model") or "jev-latest")
        and payload.get("evaluator_version") == (cfg.get("evaluator_version") or DEFAULTS["evaluator_version"])
    )


def _camel(key: str) -> str:
    parts = str(key).split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:] if part)


def compact_remaining_peak(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    out = {}
    for key in REMAINING_PEAK_FIELDS:
        if key in raw:
            out[_camel(key)] = raw.get(key)
    return out


def assert_state_clean(state: Any) -> None:
    stack = [state]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_STATE_KEYS or key in {"quantReference", "quant_reference"}:
                    raise ValueError(f"Jev state must not include {key}")
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)



NOUL_HEADS = (
    "materialNow",
    "needsCurrentYearCheck",
    "needsNews",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
    "needsDeepAI",
)


def timing_bucket(d_day) -> str | None:
    if d_day is None or d_day == "":
        return None
    try:
        value = int(d_day)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return "overdue"
    if value <= 7:
        return "0-7"
    if value <= 14:
        return "8-14"
    if value <= 30:
        return "15-30"
    if value <= 60:
        return "31-60"
    return ">60"


def answers_complete(answers: Any) -> bool:
    if not isinstance(answers, dict):
        return False
    for head in NOUL_HEADS:
        node = answers.get(head) or {}
        if not isinstance(node, dict) or not isinstance(node.get("probability"), (int, float)):
            return False
    review = answers.get("reviewClass") or {}
    return bool(isinstance(review, dict) and review.get("choice"))


def reuse_key(evaluator_version: str, provider: str, requested_model: str, state_hash_value: str) -> tuple[str, str, str, str]:
    return (str(evaluator_version), str(provider), str(requested_model), str(state_hash_value))


def load_reuse_index(settings, cfg: dict[str, Any]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    folder = shadow_dir(settings)
    if not folder.exists():
        return {}
    provider = provider_name(cfg)
    requested_model = str(cfg.get("model") or "jev-latest")
    evaluator_version = str(cfg.get("evaluator_version") or DEFAULTS["evaluator_version"])
    index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for path in folder.glob("*.json"):
        if path.name.startswith("_") or path.name.startswith("."):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("provider") != provider:
            continue
        if payload.get("requested_model") != requested_model:
            continue
        if payload.get("evaluator_version") != evaluator_version:
            continue
        finished = str(payload.get("finished_at") or "")
        origin_generation = str(payload.get("generation_id") or "")
        for rec in payload.get("results") or []:
            if not isinstance(rec, dict):
                continue
            status = rec.get("status") or ("GENERATED" if answers_complete(rec.get("answers")) else "")
            if status not in {"GENERATED", "REUSED"}:
                continue
            if not answers_complete(rec.get("answers")):
                continue
            digest = rec.get("state_hash")
            if not digest:
                continue
            key = reuse_key(evaluator_version, provider, requested_model, digest)
            original = rec.get("reused_from_generation_id") or origin_generation
            current = index.get(key)
            if current is None or finished >= str(current.get("finished_at") or ""):
                index[key] = {
                    "record": rec,
                    "original_generation": original,
                    "finished_at": finished,
                }
    return index


def _skipped(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "candidate_type": candidate.get("candidate_type"),
        "candidate_id": candidate.get("id"),
        "signal_id": candidate.get("id") if candidate.get("candidate_type") == "season_pattern" else None,
        "ticker": candidate.get("ticker"),
        "state_hash": candidate.get("state_hash"),
        "quant_reference": candidate.get("quant_reference") or {},
        "status": "SKIPPED",
        "skip_reason": reason,
        "answers": {},
    }


def _reused(candidate: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    rec = source["record"]
    return {
        "candidate_type": candidate.get("candidate_type"),
        "candidate_id": candidate.get("id"),
        "signal_id": candidate.get("id") if candidate.get("candidate_type") == "season_pattern" else None,
        "ticker": candidate.get("ticker"),
        "state_hash": candidate.get("state_hash"),
        "quant_reference": candidate.get("quant_reference") or {},
        "status": "REUSED",
        "reused_from_generation_id": source["original_generation"],
        "answers": rec.get("answers") or {},
        "requested_model": rec.get("requested_model"),
        "resolved_model": rec.get("resolved_model"),
    }

def project_season_state(row: dict[str, Any]) -> dict[str, Any]:
    peak = compact_remaining_peak(row.get("remaining_peak"))
    state = {
        "identity": {
            "signalId": row.get("signal_id"),
            "ticker": row.get("ticker"),
            "company": row.get("company"),
            "market": row.get("market"),
            "patternId": row.get("pattern_id"),
        },
        "timing": {
            "windowName": row.get("window_name"),
            "entryStage": row.get("entry_stage"),
            "entryStageLabel": row.get("entry_stage_label"),
            "currentStatus": row.get("current_status"),
            "entryWindow": row.get("entry_window_str"),
            "exitWindow": row.get("exit_window_str"),
            "priceAsOf": row.get("price_as_of"),
        },
        "historical": {
            "sampleCount": row.get("sample_count"),
            "winRate": row.get("win_rate"),
            "medianReturn": row.get("median_return"),
            "medianAlpha": row.get("median_alpha"),
        },
        "event": {
            "commonEventCluster": row.get("common_event_cluster"),
            "secondaryCluster": row.get("secondary_cluster"),
            "eventConfidence": row.get("event_confidence"),
            "invalidatingConditions": row.get("invalidating_conditions"),
            "eventExplanationMode": row.get("event_explanation_mode"),
        },
        "current": {
            "lastClose": row.get("last_close"),
            "chgPct": row.get("chg_pct"),
            "remainingPeak": peak,
        },
    }
    assert_state_clean(state)
    return state


def project_calendar_state(row: dict[str, Any]) -> dict[str, Any]:
    calendar_key = row.get("calendar_key") or f"{row.get('event_id')}:{row.get('ticker')}:{row.get('target_date')}"
    state = {
        "identity": {
            "calendarKey": calendar_key,
            "ticker": row.get("ticker"),
            "company": row.get("company"),
            "market": row.get("market"),
        },
        "timing": {
            "eventId": row.get("event_id"),
            "eventGroup": row.get("event_group"),
            "eventTitle": row.get("event_title"),
            "targetDate": row.get("target_date"),
            "timingBucket": timing_bucket(row.get("d_day")),
            "horizonTag": row.get("horizon_tag"),
            "optimalEntryWindow": row.get("optimal_entry_window"),
            "optimalExitWindow": row.get("optimal_exit_window"),
        },
        "event": {
            "binaryRisk": row.get("binary_risk"),
            "exposureDesc": row.get("exposure_desc"),
            "invalidatingRule": row.get("invalidating_rule"),
        },
        "historical": {
            "winRate": row.get("win_rate"),
            "avgReturn": row.get("avg_return"),
            "medianReturn": row.get("median_return"),
            "yearsCount": row.get("years_count"),
        },
        "current": {
            "currentConfirmationEvidence": row.get("current_confirmation_evidence"),
            "currentConfirmationMissing": row.get("current_confirmation_missing"),
            "prePricingFlag": row.get("pre_pricing_flag"),
        },
    }
    assert_state_clean(state)
    return state


def quant_reference_season(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pre_entry_rank": row.get("pre_entry_rank"),
        "grade": row.get("grade"),
        "seasonality_score": row.get("seasonality_score"),
        "score_breakdown": row.get("score_breakdown"),
    }


def quant_reference_calendar(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "grade": row.get("grade"),
        "seasonality_score": row.get("seasonality_score"),
        "score_breakdown": row.get("score_breakdown"),
        "pre_entry_rank": row.get("pre_entry_rank"),
    }


def state_hash(state: dict[str, Any], evaluator_version: str, *, provider: str = "typesafe_direct", requested_model: str = "jev-latest") -> str:
    """Reuse identity uses requested_model (jev-latest), not resolved_model.

    If the jev-latest alias later resolves to a different version, bump
    evaluator_version to invalidate cache. Do not pin or auto-invalidate here.
    """

    blob = json.dumps(
        {"evaluator_version": evaluator_version, "provider": provider, "requested_model": requested_model, "state": state},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def collect_candidates(settings, bundle: dict[str, Any], *, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = config or load_config(settings)
    horizon = int(cfg.get("horizon_days") or 90)
    evaluator_version = str(cfg.get("evaluator_version") or DEFAULTS["evaluator_version"])
    provider = str(cfg.get("provider") or "typesafe_direct")
    requested_model = str(cfg.get("model") or "jev-latest")
    season_rows = select_rows(bundle, horizon_days=horizon, exclude_expired=True)
    out: list[dict[str, Any]] = []
    for row in season_rows:
        if not isinstance(row, dict):
            continue
        state = project_season_state(row)
        out.append({
            "id": row.get("signal_id"),
            "candidate_type": "season_pattern",
            "ticker": row.get("ticker"),
            "state": state,
            "state_hash": state_hash(state, evaluator_version, provider=provider, requested_model=requested_model),
            "quant_reference": quant_reference_season(row),
        })
    from kr_quant.strategy.seasonality import rank_institutional_events

    for row in rank_institutional_events(settings, horizon_days=horizon):
        if not isinstance(row, dict):
            continue
        state = project_calendar_state(row)
        calendar_key = state["identity"]["calendarKey"]
        out.append({
            "id": calendar_key,
            "candidate_type": "calendar_event_stock",
            "ticker": row.get("ticker"),
            "state": state,
            "state_hash": state_hash(state, evaluator_version, provider=provider, requested_model=requested_model),
            "quant_reference": quant_reference_calendar(row),
        })
    return out


def provider_name(cfg: dict[str, Any] | None = None) -> str:
    name = str((cfg or {}).get("provider") or "typesafe_direct")
    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"UNSUPPORTED_JEV_PROVIDER:{name}")
    return name


def provider_runner_path(settings, cfg: dict[str, Any] | None = None) -> Path:
    provider = provider_name(cfg)
    return Path(settings.root) / PROVIDER_RUNNERS[provider]


def provider_key(cfg: dict[str, Any] | None = None) -> str | None:
    name = provider_name(cfg)
    env_name = "AI_GATEWAY_API_KEY" if name == "vercel_gateway" else "TYPESAFE_API_KEY"
    value = (os.environ.get(env_name) or "").strip()
    return value or None


def gateway_key() -> str | None:
    """Deprecated alias. Direct provider does not fall back to the Gateway key."""
    return provider_key({"provider": "typesafe_direct"})


def _skip(reason: str) -> None:
    logger.info("Jev shadow skipped: %s", reason)


def request_shadow_evaluation(settings, bundle: dict[str, Any] | None) -> None:
    """Fire-and-forget. Never delays the season snapshot worker."""
    if not isinstance(bundle, dict) or not bundle.get("generation_id"):
        return
    lookback = (bundle.get("identity") or {}).get("lookback")
    if lookback != 5:
        return
    cfg = load_config(settings)
    if not cfg.get("enabled"):
        _skip("disabled")
        return
    try:
        provider = provider_name(cfg)
    except ValueError as exc:
        _skip(str(exc))
        return
    if provider != "vercel_gateway" and not provider_key(cfg):
        _skip("TYPESAFE_API_KEY missing")
        return
    if provider == "vercel_gateway" and not provider_key(cfg):
        _skip("AI_GATEWAY_API_KEY missing")
        return
    generation = str(bundle["generation_id"])
    if has_shadow(settings, generation, cfg):
        return
    with _LOCK:
        if generation in _PENDING:
            return
        _PENDING.add(generation)

    def work():
        try:
            evaluate_generation(settings, bundle, config=cfg)
        except Exception:
            logger.exception("Jev shadow evaluation failed; season snapshot unchanged")
        finally:
            with _LOCK:
                _PENDING.discard(generation)

    threading.Thread(target=work, name=f"jev-shadow-{generation[:8]}", daemon=True).start()


def evaluate_generation(settings, bundle: dict[str, Any], *, config: dict[str, Any] | None = None, runner=None) -> dict[str, Any] | None:
    cfg = config or load_config(settings)
    generation = str(bundle.get("generation_id") or "")
    if not generation:
        return None
    try:
        provider = provider_name(cfg)
    except ValueError as exc:
        _skip(str(exc))
        return None
    if has_shadow(settings, generation, cfg):
        return json.loads(shadow_path(settings, generation, provider).read_text(encoding="utf-8"))
    if not cfg.get("enabled"):
        _skip("disabled")
        return None
    if provider != "vercel_gateway" and not provider_key(cfg):
        _skip("TYPESAFE_API_KEY missing")
        return None
    if provider == "vercel_gateway" and not provider_key(cfg):
        _skip("AI_GATEWAY_API_KEY missing")
        return None
    identity = bundle.get("identity") or {}
    lookback = identity.get("lookback")
    try:
        current = source_identity(settings, int(lookback))
    except Exception as exc:
        return _store_error(settings, bundle, cfg, f"SOURCE_IDENTITY:{type(exc).__name__}")
    if current != identity:
        logger.info("Jev shadow skipped: SOURCE_CHANGED")
        return None

    started = datetime.now(timezone.utc)
    from kr_quant.research.season_jev_budget import refund_daily_slot, reserve_daily_slot

    candidates = collect_candidates(settings, bundle, config=cfg)
    reuse_index = load_reuse_index(settings, cfg)
    provider = provider_name(cfg)
    requested_model = str(cfg.get("model") or "jev-latest")
    evaluator_version = str(cfg.get("evaluator_version") or DEFAULTS["evaluator_version"])
    gen_cap = int(cfg.get("max_api_calls_per_generation") or 300)
    day_cap = int(cfg.get("max_api_calls_per_day") or 300)

    outcome_by_id: dict[str, dict[str, Any]] = {}
    need_api: list[dict[str, Any]] = []
    for item in candidates:
        key = reuse_key(evaluator_version, provider, requested_model, item["state_hash"])
        source = reuse_index.get(key)
        if source:
            outcome_by_id[str(item["id"])] = _reused(item, source)
            continue
        need_api.append(item)

    api_records: list[dict[str, Any]] = []
    reserved_ids: list[str] = []
    generation_attempts = 0
    for item in need_api:
        if generation_attempts >= gen_cap:
            api_records.append(_skipped(item, "API_CAP_GENERATION"))
            continue
        slot = reserve_daily_slot(settings, generation, day_cap=day_cap)
        if slot == "API_CAP_DAILY":
            api_records.append(_skipped(item, "API_CAP_DAILY"))
            continue
        if slot != "ok":
            api_records.append(_skipped(item, "API_BUDGET_UNAVAILABLE"))
            continue
        reserved_ids.append(str(item["id"]))
        generation_attempts += 1
        api_records.append({"_pending": item})

    pending_items = [row["_pending"] for row in api_records if "_pending" in row]
    raw: dict[str, Any] = {"results": [], "errors": [], "total_usage": {}}
    if pending_items:
        node_payload = {
            "provider": provider,
            "requested_model": requested_model,
            "model": requested_model,
            "concurrency": int(cfg["concurrency"]),
            "candidate_timeout_ms": int(cfg["candidate_timeout_ms"]),
            "process_soft_deadline_ms": int(cfg.get("process_soft_deadline_seconds") or 170) * 1000,
            "process_start_cutoff_ms": int(cfg.get("process_start_cutoff_seconds") or 160) * 1000,
            "max_api_calls_per_generation": gen_cap,
            "candidates": [
                {
                    "id": item["id"],
                    "candidate_type": item["candidate_type"],
                    "ticker": item["ticker"],
                    "state": item["state"],
                    "state_hash": item["state_hash"],
                }
                for item in pending_items
            ],
        }
        try:
            raw = (runner or run_node)(settings, node_payload, timeout=int(cfg["process_timeout_seconds"]))
        except FileNotFoundError:
            for item in pending_items:
                refund_daily_slot(settings, generation)
            _skip("NODE_MISSING")
            return None
        except subprocess.TimeoutExpired:
            for item in pending_items:
                refund_daily_slot(settings, generation)
            return _store_error(settings, bundle, cfg, "PROCESS_TIMEOUT", started=started, candidate_count=len(candidates))
        except Exception as exc:
            for item in pending_items:
                refund_daily_slot(settings, generation)
            return _store_error(settings, bundle, cfg, f"RUNNER:{type(exc).__name__}", started=started, candidate_count=len(candidates))

    by_id = {item["id"]: item for item in pending_items}
    started_ids = set()
    generated_by_id: dict[str, dict[str, Any]] = {}
    for item in raw.get("results") or []:
        cid = str(item.get("id") or "")
        started_ids.add(cid)
        source = by_id.get(item.get("id")) or {}
        generated_by_id[cid] = {
            "candidate_type": item.get("candidate_type") or source.get("candidate_type"),
            "candidate_id": item.get("id") or source.get("id"),
            "signal_id": source.get("id") if source.get("candidate_type") == "season_pattern" else None,
            "ticker": item.get("ticker") or source.get("ticker"),
            "state_hash": item.get("state_hash") or source.get("state_hash"),
            "quant_reference": source.get("quant_reference") or {},
            "status": "GENERATED" if answers_complete(item.get("answers")) else "ERROR",
            "answers": item.get("answers") or {},
            "provider": item.get("provider") or provider,
            "usage": item.get("usage") or {},
            "requested_model": item.get("requested_model") or requested_model,
            "resolved_model": item.get("resolved_model"),
            "wall_latency_ms": item.get("wall_latency_ms"),
        }
    error_by_id: dict[str, dict[str, Any]] = {}
    for err in raw.get("errors") or []:
        if not isinstance(err, dict):
            continue
        cid = str(err.get("id") or "")
        reason = str(err.get("error") or "ERROR")
        api_started = reason not in {"SOFT_DEADLINE_NOT_STARTED", "API_CAP_GENERATION"}
        if api_started:
            started_ids.add(cid)
        else:
            if cid in reserved_ids:
                refund_daily_slot(settings, generation)
        source = by_id.get(err.get("id")) or {}
        skip_reason = "API_CAP_GENERATION" if reason == "API_CAP_GENERATION" else None
        if reason == "SOFT_DEADLINE_NOT_STARTED":
            skip_reason = None
            error_by_id[cid] = {
                "candidate_type": source.get("candidate_type"),
                "candidate_id": source.get("id"),
                "signal_id": source.get("id") if source.get("candidate_type") == "season_pattern" else None,
                "ticker": source.get("ticker"),
                "state_hash": source.get("state_hash"),
                "quant_reference": source.get("quant_reference") or {},
                "status": "ERROR",
                "skip_reason": None,
                "answers": {},
                "error": reason,
            }
        elif skip_reason:
            error_by_id[cid] = _skipped(source, skip_reason)
        else:
            error_by_id[cid] = {
                "candidate_type": source.get("candidate_type"),
                "candidate_id": source.get("id"),
                "signal_id": source.get("id") if source.get("candidate_type") == "season_pattern" else None,
                "ticker": source.get("ticker"),
                "state_hash": source.get("state_hash"),
                "quant_reference": source.get("quant_reference") or {},
                "status": "ERROR",
                "answers": {},
                "error": reason,
            }

    for rec in api_records:
        if "_pending" not in rec:
            outcome_by_id[str(rec.get("candidate_id"))] = rec
            continue
        item = rec["_pending"]
        cid = str(item["id"])
        if cid in generated_by_id:
            outcome_by_id[cid] = generated_by_id[cid]
        elif cid in error_by_id:
            outcome_by_id[cid] = error_by_id[cid]
        else:
            refund_daily_slot(settings, generation)
            outcome_by_id[cid] = {**_skipped(item, "ERROR"), "status": "ERROR", "error": "MISSING_NODE_RESULT"}
    merged = [outcome_by_id[str(item["id"])] for item in candidates if str(item["id"]) in outcome_by_id]

    generated = [r for r in merged if r.get("status") == "GENERATED"]
    reused = [r for r in merged if r.get("status") == "REUSED"]
    skipped = [r for r in merged if r.get("status") == "SKIPPED"]
    failed = [r for r in merged if r.get("status") == "ERROR"]
    if failed and not generated and not reused and not skipped:
        bundle_status = "ERROR"
    elif failed or skipped:
        bundle_status = "PARTIAL"
    else:
        bundle_status = "COMPLETE"
    finished = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1,
        "evaluator_version": cfg["evaluator_version"],
        "generation_id": generation,
        "selection_date": identity.get("day"),
        "lookback_years": lookback,
        "horizon_days": cfg["horizon_days"],
        "provider": provider,
        "model": cfg["model"],
        "requested_model": requested_model,
        "resolved_models": sorted(
            {
                str(r.get("resolved_model"))
                for r in (generated + reused)
                if r.get("resolved_model") not in (None, "")
            }
        ),
        "status": bundle_status,
        "candidate_count": len(candidates),
        "evaluated_count": len(generated),
        "reused_count": len(reused),
        "skipped_count": len(skipped),
        "failed_count": len(failed),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "total_usage": raw.get("total_usage") or {},
        "results": merged,
        "errors": [r for r in merged if r.get("status") == "ERROR"],
    }
    write_json_atomic(shadow_path(settings, generation, provider), payload)
    return payload


def _store_error(settings, bundle, cfg, reason: str, *, started=None, candidate_count=0, status="ERROR") -> dict[str, Any]:
    started = started or datetime.now(timezone.utc)
    finished = datetime.now(timezone.utc)
    identity = bundle.get("identity") or {}
    requested_model = str(cfg.get("model") or "jev-latest")
    payload = {
        "schema_version": 1,
        "evaluator_version": cfg["evaluator_version"],
        "generation_id": bundle.get("generation_id"),
        "selection_date": identity.get("day"),
        "lookback_years": identity.get("lookback"),
        "horizon_days": cfg["horizon_days"],
        "provider": provider_name(cfg),
        "model": cfg["model"],
        "requested_model": requested_model,
        "resolved_models": [],
        "status": status,
        "candidate_count": candidate_count,
        "evaluated_count": 0,
        "failed_count": candidate_count,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "total_usage": {},
        "total_cost_usd": None,
        "results": [],
        "errors": [{"error": reason}],
    }
    write_json_atomic(shadow_path(settings, bundle["generation_id"], provider_name(cfg)), payload)
    return payload


def run_node(settings, payload: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("node")
    provider = provider_name({"provider": payload.get("provider") or "typesafe_direct"})
    script = provider_runner_path(settings, {"provider": provider})
    if not script.exists():
        raise FileNotFoundError(str(script))
    completed = subprocess.run(
        [node, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1, int(timeout)),
        shell=False,
        cwd=str(settings.root),
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.stderr:
        logger.debug("Jev node stderr chars=%s", len(completed.stderr))
    if completed.returncode != 0:
        raise RuntimeError(f"NODE_EXIT_{completed.returncode}")
    try:
        parsed = json.loads(completed.stdout)
    except ValueError as exc:
        raise RuntimeError("NODE_STDOUT_NOT_JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("NODE_STDOUT_NOT_OBJECT")
    return parsed
