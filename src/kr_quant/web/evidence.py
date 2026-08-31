from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from kr_quant.settings import Settings

CONTRACT_VERSION = "1.0"
CORE_PUBLIC_MENUS = ("dash", "rank", "screens")


def _json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _count_rows(path: Path, *, eligible_only: bool = False) -> int:
    if not path.exists():
        return 0
    try:
        columns = ["universe_eligible"] if eligible_only else None
        frame = pd.read_parquet(path, columns=columns)
        if eligible_only and "universe_eligible" in frame.columns:
            return int(frame["universe_eligible"].fillna(False).astype(bool).sum())
        return int(len(frame))
    except Exception:  # noqa: BLE001
        return 0


def _cache_count(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _source(name: str, *, as_of: Any, state: str, kind: str = "official") -> dict[str, Any]:
    return {"name": name, "kind": kind, "as_of": as_of, "state": state}


def _entry(
    menu_id: str,
    label: str,
    *,
    sources: list[dict[str, Any]],
    as_of: str | None,
    observed_at: str | None,
    sample_count: int | None,
    sample_unit: str,
    scope: str,
    state: str,
    used_in_quant: bool,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "menu_id": menu_id,
        "label": label,
        "sources": sources,
        "as_of": as_of,
        "observed_at": observed_at,
        "sample": {"count": sample_count, "unit": sample_unit, "scope": scope},
        "calculation_state": state,
        "used_in_quant": used_in_quant,
        "limitations": limitations,
    }


def build_evidence_registry(
    settings: Settings,
    *,
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> dict[str, Any]:
    cache_dir = settings.root / "data" / "cache"
    ranking_path = settings.output_dir / "latest_all_stocks.parquet"
    ranking_count = _count_rows(ranking_path, eligible_only=True)
    quality_as_of = str(quality.get("as_of_date") or freshness.get("screen_as_of") or "") or None
    price_as_of = str(freshness.get("price_max_date") or "") or None
    financial_as_of = str(freshness.get("financial_max_available_date") or "") or None
    ranking_source = (freshness.get("sources") or {}).get("quant_ranking") or {}
    ranking_state = str(ranking_source.get("state") or "missing")
    price_state = str(((freshness.get("sources") or {}).get("krx_prices") or {}).get("state") or "missing")
    financial_state = str(((freshness.get("sources") or {}).get("financial_facts") or {}).get("state") or "missing")
    if not quality_as_of or ranking_count <= 0:
        core_state = "MISSING"
    elif ranking_state == "stale" or price_state == "stale":
        core_state = "STALE"
    elif str(quality.get("status") or "") != "success" or financial_state in {"partial", "missing"}:
        core_state = "READY_WITH_LIMITS"
    else:
        core_state = "READY"
    core_sources = [
        _source("KRX", as_of=price_as_of, state=price_state),
        _source("OpenDART", as_of=financial_as_of, state=financial_state),
    ]
    core_limits = [
        "재무는 available_date가 계산 기준일 이하인 공시만 사용합니다.",
        "재무 공시가 없는 종목은 적격 게이트에서 제외되므로 전체 상장종목과 표본 수가 다릅니다.",
    ]

    strategy_path = cache_dir / "strategy_lab.json"
    strategy = _json(strategy_path)
    strategy_count = _cache_count(strategy, "rows")
    strategy_as_of = str(strategy.get("source_price_as_of") or "") or None
    strategy_state = str(((freshness.get("sources") or {}).get("strategy_cache") or {}).get("state") or "missing")
    strategy_calc = "MISSING" if not strategy_count else ("STALE" if strategy_state == "stale" else "READY_WITH_LIMITS")

    flow_path = cache_dir / "investor_flow.json"
    flow = _json(flow_path)
    flow_count = max(_cache_count(flow, "rows", "dual", "combined"), _cache_count(flow, "pension"))
    flow_as_of = str(flow.get("as_of") or flow.get("to") or flow.get("source_as_of") or "") or None
    flow_state = "READY_WITH_LIMITS" if flow_count else "MISSING"

    sector_path = cache_dir / "sector_rank.json"
    sector = _json(sector_path)
    sector_count = _cache_count(sector, "rows", "sectors")
    sector_as_of = str(sector.get("as_of") or sector.get("source_as_of") or quality_as_of or "") or None
    sector_state = "READY_WITH_LIMITS" if sector_count else "MISSING"

    season_path = cache_dir / "seasonality_cache.json"
    season = _json(season_path)
    season_count = _cache_count(season, "rows", "stocks", "items")
    season_as_of = str(season.get("price_as_of") or season.get("as_of") or price_as_of or "") or None
    season_state = "READY_WITH_LIMITS" if season_count else "MISSING"

    us13f_path = cache_dir / "us13f.json"
    us13f = _json(us13f_path)
    us13f_count = _cache_count(us13f, "rows", "holdings", "managers", "filers", "scanned")
    periods = us13f.get("periods") if isinstance(us13f.get("periods"), list) else []
    us13f_as_of = str(us13f.get("as_of") or us13f.get("report_period") or (max(periods) if periods else "")) or None
    us13f_state = "READY_WITH_LIMITS" if us13f_count else "MISSING"

    menu: dict[str, dict[str, Any]] = {}
    for menu_id, label, scope in (
        ("dash", "대시보드", "현재 적격 종목 요약"),
        ("rank", "점수 랭킹", "현재 적격 전 종목"),
        ("screens", "테마 스크리너", "현재 적격 종목 조건검색"),
    ):
        menu[menu_id] = _entry(
            menu_id,
            label,
            sources=core_sources,
            as_of=quality_as_of,
            observed_at=ranking_source.get("last_updated_at") or _mtime(ranking_path),
            sample_count=ranking_count,
            sample_unit="종목",
            scope=scope,
            state=core_state,
            used_in_quant=True,
            limitations=core_limits,
        )

    menu["strategy"] = _entry(
        "strategy",
        "전략·백테스트",
        sources=[_source("KRX 일봉", as_of=strategy_as_of, state=strategy_state)],
        as_of=strategy_as_of,
        observed_at=_mtime(strategy_path),
        sample_count=strategy_count,
        sample_unit="종목",
        scope="현재 TOP20 종목별 4대 가격 규칙",
        state=strategy_calc,
        used_in_quant=False,
        limitations=[
            "현재 TOP20을 과거에 소급한 종목별 연구로 횡단면 PIT 백테스트가 아닙니다.",
            "일봉 기반 비용·유동성·가격제한폭 프록시이며 실시간 호가 재현은 아닙니다.",
        ],
    )
    menu["market"] = _entry(
        "market",
        "글로벌 매크로",
        sources=[_source("ECOS/FRED/Yahoo/KRX", as_of=price_as_of, state="on_request", kind="mixed")],
        as_of=price_as_of,
        observed_at=None,
        sample_count=None,
        sample_unit="지표",
        scope="거시·환율·원자재·시장 국면 오버레이",
        state="READY_WITH_LIMITS" if price_as_of else "MISSING",
        used_in_quant=False,
        limitations=["지표별 발표 주기와 기준시각이 다르며 퀀트 점수에는 합산하지 않습니다."],
    )
    menu["sector"] = _entry(
        "sector",
        "업종·섹터",
        sources=[_source("KRX + OpenDART", as_of=sector_as_of, state="cached")],
        as_of=sector_as_of,
        observed_at=_mtime(sector_path),
        sample_count=sector_count,
        sample_unit="업종",
        scope="적격 종목의 업종 집계",
        state=sector_state,
        used_in_quant=False,
        limitations=["미분류 종목과 재무 미적격 종목은 업종 집계에서 빠질 수 있습니다."],
    )
    for menu_id, label, scope in (
        ("investor", "메이저 수급", "외국인·기관·기금 수급 후보"),
        ("trade", "스마트 수급·타점", "수급과 KRX 기술지표 결합 후보"),
    ):
        menu[menu_id] = _entry(
            menu_id,
            label,
            sources=[_source("KIS/Toss + KRX", as_of=flow_as_of or price_as_of, state="cached", kind="mixed")],
            as_of=flow_as_of or price_as_of,
            observed_at=_mtime(flow_path),
            sample_count=flow_count,
            sample_unit="종목",
            scope=scope,
            state=flow_state,
            used_in_quant=False,
            limitations=["공급자별 투자자 분류가 다르며 FUND를 국민연금으로 단정하지 않습니다.", "퀀트 점수와 순위에는 합산하지 않습니다."],
        )
    menu["seasonality"] = _entry(
        "seasonality",
        "시즌 모멘텀·캘린더",
        sources=[_source("KRX 일봉", as_of=season_as_of, state="cached")],
        as_of=season_as_of,
        observed_at=_mtime(season_path),
        sample_count=season_count,
        sample_unit="종목",
        scope="현재 거래 가능 종목의 월별 반복 구간",
        state=season_state,
        used_in_quant=False,
        limitations=["연도별 표본 수가 적을 수 있고 이벤트 원인과 가격 패턴의 인과관계를 보장하지 않습니다."],
    )
    menu["watch"] = _entry(
        "watch",
        "관심종목 & AI리포트",
        sources=core_sources + [_source("저장된 AI 리포트", as_of=quality_as_of, state="optional", kind="research")],
        as_of=quality_as_of,
        observed_at=_mtime(ranking_path),
        sample_count=None,
        sample_unit="관심종목",
        scope="사용자 선택 종목",
        state=core_state,
        used_in_quant=False,
        limitations=["AI 설명은 퀀트 점수와 순위를 수정하지 않습니다."],
    )
    menu["us13f"] = _entry(
        "us13f",
        "월가 대가 포트폴리오(13F)",
        sources=[_source("SEC EDGAR 13F", as_of=us13f_as_of, state="cached")],
        as_of=us13f_as_of,
        observed_at=_mtime(us13f_path),
        sample_count=us13f_count,
        sample_unit="보유내역",
        scope="선택 운용사 분기말 보유",
        state=us13f_state,
        used_in_quant=False,
        limitations=["분기말 기준이며 제출까지 최대 45일 시차가 있고 실시간 보유가 아닙니다."],
    )
    menu["sunzi"] = _entry(
        "sunzi",
        "은하퀀트전설",
        sources=core_sources + [_source("시장·수급 오버레이", as_of=price_as_of, state="mixed", kind="derived")],
        as_of=quality_as_of,
        observed_at=_mtime(ranking_path),
        sample_count=ranking_count,
        sample_unit="종목",
        scope="퀀트/전종목 설명 레이어",
        state=core_state,
        used_in_quant=False,
        limitations=["손자 오사와 AI 해석은 설명 레이어이며 결정론적 퀀트 점수에 합산하지 않습니다."],
    )
    for menu_id, label in (("run", "실행 파이프라인"), ("settings", "API 설정")):
        menu[menu_id] = _entry(
            menu_id,
            label,
            sources=[_source("로컬 시스템", as_of=None, state="local", kind="system")],
            as_of=None,
            observed_at=datetime.now(timezone.utc).isoformat(),
            sample_count=None,
            sample_unit="설정",
            scope="이 PC의 실행·환경 관리",
            state="LOCAL_ONLY",
            used_in_quant=False,
            limitations=["시장 데이터 근거가 아니라 로컬 관리 화면이며 공개 웹에서는 변경 기능이 잠깁니다."],
        )

    validation = validate_evidence_registry({"contract_version": CONTRACT_VERSION, "menus": menu})
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "menus": menu,
        "validation": validation,
    }


def validate_evidence_registry(
    registry: dict[str, Any] | None,
    *,
    required_menus: tuple[str, ...] = CORE_PUBLIC_MENUS,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(registry, dict) or registry.get("contract_version") != CONTRACT_VERSION:
        return {"valid": False, "errors": ["EVIDENCE_CONTRACT_VERSION_INVALID"], "required_menus": list(required_menus)}
    menus = registry.get("menus")
    if not isinstance(menus, dict):
        return {"valid": False, "errors": ["EVIDENCE_MENUS_MISSING"], "required_menus": list(required_menus)}
    for menu_id in required_menus:
        entry = menus.get(menu_id)
        if not isinstance(entry, dict):
            errors.append(f"EVIDENCE_MENU_MISSING:{menu_id}")
            continue
        for field in ("sources", "as_of", "sample", "calculation_state", "used_in_quant", "limitations"):
            if field not in entry or entry.get(field) in (None, "", []):
                errors.append(f"EVIDENCE_FIELD_MISSING:{menu_id}:{field}")
        if entry.get("calculation_state") == "MISSING":
            errors.append(f"EVIDENCE_STATE_MISSING:{menu_id}")
    return {"valid": not errors, "errors": errors, "required_menus": list(required_menus)}
