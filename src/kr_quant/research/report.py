from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kr_quant.research.analyze import call_chat, quant_snapshot, snapshot_hash
from kr_quant.research.kit import PROMPT_VERSION, REQUIRED_HEADINGS, compile_system_prompt
from kr_quant.research.providers import LlmEndpoint


def report_path(output_dir: Path, as_of: str, ticker: str) -> Path:
    return output_dir / "research" / f"as_of={as_of}" / f"{ticker}.report.json"


def extract_summary(markdown: str, limit: int = 160) -> str:
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("|"):
            continue
        text = re.sub(r"[*_`>#]", "", line).strip()
        if len(text) < 8:
            continue
        return text[:limit]
    return ""


def _safe_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_saved_reports(output_dir: Path) -> list[dict[str, Any]]:
    root = output_dir / "research"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.glob("as_of=*/*.json"):
        rec = _safe_json(path)
        if not rec:
            continue
        folder_day = path.parent.name.split("=", 1)[-1]
        ticker = str(rec.get("ticker") or path.stem.split(".")[0]).zfill(6)
        is_report = path.name.endswith(".report.json") or rec.get("schema_version") == "research_report_v4"
        if is_report:
            kind = "AI 분석 리포트"
            summary = extract_summary(str(rec.get("report_markdown") or ""))
        else:
            kind = "간단 검증"
            thesis = rec.get("thesis") if isinstance(rec.get("thesis"), dict) else {}
            summary = str(thesis.get("one_line") or rec.get("research_decision") or "")
        rows.append(
            {
                "ticker": ticker,
                "company": rec.get("company") or ticker,
                "as_of_date": rec.get("as_of_date") or folder_day,
                "kind": kind,
                "provider": rec.get("provider"),
                "model": rec.get("model"),
                "researched_at": rec.get("researched_at"),
                "summary": summary,
                "filename": path.name,
            }
        )
    rows.sort(key=lambda r: str(r.get("researched_at") or r.get("as_of_date") or ""), reverse=True)
    return rows


def delete_saved_report(
    output_dir: Path,
    ticker: str,
    as_of: str,
    *,
    kind: str | None = None,
    filename: str | None = None,
) -> dict[str, Any]:
    code = str(ticker).zfill(6)
    folder = output_dir / "research" / f"as_of={as_of}"
    targets: list[Path] = []
    if filename:
        safe = Path(str(filename)).name
        targets.append(folder / safe)
    elif kind == "AI 분석 리포트":
        targets.append(report_path(output_dir, as_of, code))
    elif kind == "간단 검증":
        targets.append(output_dir / "research" / f"as_of={as_of}" / f"{code}.json")
    else:
        targets.extend(
            [
                report_path(output_dir, as_of, code),
                output_dir / "research" / f"as_of={as_of}" / f"{code}.json",
            ]
        )
    deleted: list[str] = []
    for path in targets:
        if path.exists() and path.is_file() and "research" in path.parts:
            path.unlink()
            deleted.append(path.name)
    return {"ok": bool(deleted), "deleted": deleted, "ticker": code, "as_of_date": as_of}


def find_report_file(output_dir: Path, ticker: str, as_of: str | None = None) -> Path | None:
    code = str(ticker).zfill(6)
    if as_of:
        path = report_path(output_dir, as_of, code)
        if path.exists():
            return path
    hits = sorted((output_dir / "research").glob(f"as_of=*/{code}.report.json"), reverse=True)
    return hits[0] if hits else None


def strip_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def missing_headings(markdown: str) -> list[str]:
    return [h for h in REQUIRED_HEADINGS if h not in (markdown or "")]


def build_report_messages(
    row: dict[str, Any],
    as_of: str,
    links: list[dict[str, str]] | None = None,
    root: Path | None = None,
    news: list[dict[str, Any]] | None = None,
    web: list[dict[str, Any]] | None = None,
    macro: dict[str, Any] | None = None,
    yahoo: dict[str, Any] | None = None,
    strategy_backtest: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    snap = quant_snapshot(row, as_of)
    payload = {
        "quant_snapshot": snap,
        "external_links": links or [],
        "naver_news": news or [],
        "naver_web": web or [],
        "macro_context": macro or {},
        "yahoo_research_quote": yahoo or {},
        "strategy_backtest": strategy_backtest or {},
        "required_headings": list(REQUIRED_HEADINGS),
    }
    user = (
        "아래 읽기 전용 스냅샷으로 EquityResearch 3.7.2 Cloud-First Deep 지침 심층 분석리포트를 작성하라.\n"
        "1) 4대 전략 백테스트(RSI 과매도, 볼린저 하단 반등, 골든크로스, 돈치안 채널 돌파) 결과가 포함되어 있습니다. 기술적 위치 및 목표가/타이밍 플레이북 섹션에 해당 종목의 1위 최적 추천 전략, 샤프 지수, 미래검증(OOS) 승률, MDD 및 실전 매매 타이밍 가이드를 명확한 표와 함께 요약·정리하라.\n"
        "2) 네이버 뉴스·공시·웹검색이 있으면 최신 뉴스·공시·이벤트 섹션에 제목·날짜·링크를 인용하라.\n"
        "3) FRED 거시·Yahoo 비교시세는 거시 및 기술적 맥락으로만 쓰고, Quant 점수를 바꾸거나 재계산하지 마라.\n"
        "4) 데이터가 없으면 확인불가로 쓰고 꾸며내지 마라.\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}\n"
    )
    return [
        {"role": "system", "content": compile_system_prompt(root)},
        {"role": "user", "content": user},
    ]


def write_report(
    endpoint: LlmEndpoint,
    row: dict[str, Any],
    as_of: str,
    output_dir: Path,
    *,
    links: list[dict[str, str]] | None = None,
    news: list[dict[str, Any]] | None = None,
    web: list[dict[str, Any]] | None = None,
    macro: dict[str, Any] | None = None,
    yahoo: dict[str, Any] | None = None,
    strategy_backtest: dict[str, Any] | None = None,
    run_id: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").zfill(6)
    messages = build_report_messages(
        row, as_of, links=links, root=root, news=news, web=web, macro=macro, yahoo=yahoo, strategy_backtest=strategy_backtest
    )
    raw_text, raw_body = call_chat(endpoint, messages, timeout=240, json_mode=False)
    markdown = strip_fence(raw_text)
    if any(key in markdown for key in ('"quant_score"', "'quant_score'")):
        raise RuntimeError("리포트가 Quant 필드를 수정하려 해 거부됨")
    record = {
        "schema_version": "research_report_v4",
        "prompt_version": PROMPT_VERSION,
        "run_id": run_id or "",
        "ticker": ticker,
        "company": row.get("company"),
        "as_of_date": as_of,
        "quant_snapshot_hash_ack": snapshot_hash(row),
        "provider": endpoint.provider,
        "model": endpoint.model,
        "researched_at": datetime.now(timezone.utc).isoformat(),
        "usage": (raw_body.get("usage") or {}),
        "missing_headings": missing_headings(markdown),
        "report_markdown": markdown,
        "strategy_backtest": strategy_backtest or {},
        "disclaimer": "리서치 의견이며 매수·매도 지시가 아닙니다.",
    }
    path = report_path(output_dir, as_of, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return record
