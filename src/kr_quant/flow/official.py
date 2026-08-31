"""Official KIS investor-flow service. P0: collect + status, no all-market ranking."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import yaml

from kr_quant.flow.priority import collect_universe
from kr_quant.flow.store import coverage, load_ticker, open_settings, upsert_flows
from kr_quant.flow.types import display_name, source_note
from kr_quant.ingest.kis import KisInvestorAdapter
from kr_quant.settings import Settings


def _cfg(settings: Settings) -> dict[str, Any]:
    path = settings.root / "config" / "investor_flow.yaml"
    if not path.exists():
        return {"sleep_sec": 0.2, "disclaimer": "", "used_in_quant": False}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def status_payload(settings: Settings) -> dict[str, Any]:
    cfg = _cfg(settings)
    adapter = KisInvestorAdapter(settings.kis_app_key, settings.kis_app_secret, settings.kis_base_url)
    con = open_settings(settings)
    try:
        cov = coverage(con)
    finally:
        con.close()
    universe = collect_universe(settings)
    blockers: list[str] = []
    next_steps: list[str] = []
    if not adapter.configured():
        blockers.append("한국투자증권(KIS) 앱 키와 시크릿이 없습니다.")
        next_steps.append("API 설정에서 KIS 키를 저장한 뒤 연결 테스트를 하세요.")
    if cov["rows"] == 0:
        blockers.append("아직 공식 수급 행이 없습니다.")
        next_steps.append("관심종목을 넣거나, 아래 수집 버튼으로 관심종목·거래대금 상위 종목을 받으세요.")
    if not blockers:
        next_steps.append("연속·동반·방향전환 탭을 보세요. 공식 행이 없으면 토스 캐시(기관+외인)로 채웁니다.")
    return {
        "used_in_quant": False,
        "configured": adapter.configured(),
        "coverage": cov,
        "universe_preview": universe[:12],
        "universe_n": len(universe),
        "blockers": blockers,
        "next_steps": next_steps,
        "types": [
            {"code": "FOREIGN", "ko": display_name("FOREIGN")},
            {"code": "INDIVIDUAL", "ko": display_name("INDIVIDUAL")},
            {"code": "INSTITUTION_TOTAL", "ko": display_name("INSTITUTION_TOTAL")},
            {"code": "FUND", "ko": display_name("FUND"), "note": source_note("FUND")},
        ],
        "disclaimer": cfg.get("disclaimer") or "",
    }


def collect_official(settings: Settings, *, limit: int | None = None) -> dict[str, Any]:
    cfg = _cfg(settings)
    adapter = KisInvestorAdapter(settings.kis_app_key, settings.kis_app_secret, settings.kis_base_url)
    if not adapter.configured():
        raise RuntimeError(adapter.missing_reason())
    names = collect_universe(settings, limit=limit)
    if not names:
        raise RuntimeError("수집 대상이 없습니다. 관심종목을 추가하거나 KRX 시세를 받아 거래대금 상위가 생기게 하세요.")
    sleep = float(cfg.get("sleep_sec") or 0.2)
    run_id = datetime.now(timezone.utc).strftime("kis-%Y%m%dT%H%M%S")
    saved = 0
    errors: list[str] = []
    con = open_settings(settings)
    try:
        for item in names:
            try:
                rows = adapter.collect_stock(item["ticker"])
                for row in rows:
                    row["run_id"] = run_id
                saved += upsert_flows(con, rows)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{item['ticker']}: {str(exc)[:120]}")
            time.sleep(sleep)
        cov = coverage(con)
    finally:
        con.close()
    return {
        "used_in_quant": False,
        "run_id": run_id,
        "attempted": len(names),
        "saved": saved,
        "errors": errors[:8],
        "coverage": cov,
        "note": "관심종목·거래대금 상위 종목의 공식 수급 수집을 완료했습니다.",
    }


def events_payload(settings: Settings, min_turn: int = 5) -> dict[str, Any]:
    from kr_quant.flow.events import from_official_rows, from_toss_cache_rows, sample_rebalance
    from kr_quant.flow.scan import cache_path
    from kr_quant.flow.store import load_all_flows, open_settings

    con = open_settings(settings)
    try:
        official_rows = load_all_flows(con)
        cov = coverage(con)
    finally:
        con.close()
    names: dict[str, str] = {}
    try:
        from kr_quant.flow.universe import resolve_names

        codes = list({str(r.get("ticker") or "") for r in official_rows})
        resolved, _types = resolve_names(settings, codes)
        names = resolved
    except Exception:  # noqa: BLE001
        names = {}
    official = from_official_rows(official_rows, names=names, min_turn=min_turn)
    toss_rows: list[dict[str, Any]] = []
    try:
        import json

        raw = cache_path(settings.root)
        if raw.exists():
            toss_rows = list((json.loads(raw.read_text(encoding="utf-8")) or {}).get("rows") or [])
    except Exception:  # noqa: BLE001
        toss_rows = []
    toss = from_toss_cache_rows(toss_rows, min_turn=min_turn)
    if not official_rows:
        official["empty_reason"] = "공식 KIS 행이 없습니다. 관심·고유동성 수집 뒤에 연속·동반·전환이 채워집니다."
    if toss.get("skipped_no_daily") and not toss.get("consecutive"):
        toss["empty_reason"] = "토스 캐시에 일별 시계열이 없습니다. 수급 메뉴에서 다시 스캔하면 채워집니다."
    return {
        "used_in_quant": False,
        "min_turn": min_turn,
        "coverage": cov,
        "official": official,
        "toss": toss,
        "rebalance": sample_rebalance(official_rows, names=names),
        "active": "official" if official_rows else "toss",
        "disclaimer": "",
    }


def ticker_payload(settings: Settings, ticker: str) -> dict[str, Any]:
    from kr_quant.flow.events import daily_chart, window_sums

    con = open_settings(settings)
    try:
        rows = load_ticker(con, ticker)
    finally:
        con.close()
    code = "".join(ch for ch in str(ticker) if ch.isdigit()).zfill(6)
    chart = daily_chart(rows, max_days=90)
    inst = []
    for point in reversed(chart):
        val = point.get("FUND")
        if val is None:
            val = point.get("INSTITUTION_TOTAL")
        inst.append(float(val or 0))
    inst_newest = list(reversed(inst))
    return {
        "used_in_quant": False,
        "ticker": code,
        "rows": rows,
        "n": len(rows),
        "chart": chart,
        "windows": window_sums(inst_newest),
        "disclaimer": "저장된 KIS 종목별 수급 행의 최근 90일 범위입니다.",
    }
