from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from kr_quant.hashing import sha256_json
from kr_quant.research.providers import LlmEndpoint

BANNED = {"quant_score", "quant_rank", "quant_score_raw"}


def snapshot_hash(row: dict[str, Any]) -> str:
    keep = {
        k: row.get(k)
        for k in (
            "ticker",
            "company",
            "quant_rank",
            "quant_score",
            "quant_score_raw",
            "risk_penalty",
            "value_score",
            "quality_score",
            "growth_score",
            "momentum_score",
            "financial_score",
            "data_confidence",
            "risk_flags",
            "per",
            "pbr",
            "ev_ebit",
            "fcf_yield",
            "roic",
            "roe",
            "operating_margin",
            "revenue_yoy",
            "op_yoy",
        )
    }
    return sha256_json(keep)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def quant_snapshot(row: dict[str, Any], as_of: str) -> dict[str, Any]:
    return {
        "read_only": True,
        "as_of": as_of,
        "ticker": row.get("ticker"),
        "company": row.get("company"),
        "market": row.get("market"),
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "quant_rank": row.get("quant_rank"),
        "quant_score": row.get("quant_score"),
        "quant_score_raw": row.get("quant_score_raw"),
        "risk_penalty": row.get("risk_penalty"),
        "value_score": row.get("value_score"),
        "quality_score": row.get("quality_score"),
        "growth_score": row.get("growth_score"),
        "momentum_score": row.get("momentum_score"),
        "financial_score": row.get("financial_score"),
        "data_confidence": row.get("data_confidence"),
        "risk_flags": row.get("risk_flags"),
        "data_flags": row.get("data_flags"),
        "per": row.get("per"),
        "pbr": row.get("pbr"),
        "ev_ebit": row.get("ev_ebit"),
        "fcf_yield": row.get("fcf_yield"),
        "earnings_yield": row.get("earnings_yield"),
        "roic": row.get("roic"),
        "roe": row.get("roe"),
        "operating_margin": row.get("operating_margin"),
        "revenue_yoy": row.get("revenue_yoy"),
        "op_yoy": row.get("op_yoy"),
    }


def build_messages(row: dict[str, Any], as_of: str) -> list[dict[str, str]]:
    quant = quant_snapshot(row, as_of)
    system = (
        "너는 한국 주식 리서치 보조다. 자동매매 신호가 아니라 정성 검증을 한다. "
        "Quant 숫자는 이미 계산되어 있다. PER·ROIC·성장률을 웹에서 다시 찾아 바꾸지 마라. "
        "quant_score, quant_rank, quant_score_raw 필드를 출력에 넣지 마라. "
        "모르면 unknowns에 쓰고 점수를 지어내지 마라. 한국어로 답한다. "
        "반드시 JSON 객체만 출력한다."
    )
    user = (
        "아래 읽기 전용 Quant 스냅샷을 검증하라.\n"
        f"{json.dumps(quant, ensure_ascii=False, default=str)}\n\n"
        "출력 JSON 키:\n"
        "research_decision (PASS|REJECT|RESEARCH_INCOMPLETE),\n"
        "research_score (0-100), research_confidence (0-100),\n"
        "score_components {business_quality 0-25, growth_durability 0-20, catalyst 0-15, "
        "governance_capital_allocation 0-15, risk_resilience 0-25},\n"
        "thesis {one_line, business_model, competitive_position, moat_and_roic_durability},\n"
        "catalysts [ {event, date_or_window, status} ],\n"
        "value_trap_assessment {level HIGH|MEDIUM|LOW, reasons[]},\n"
        "scenarios {bull, base, bear} 각 {conditions[], evidence[]},\n"
        "thesis_breakers[], unknowns[],\n"
        "disclaimer 한 줄.\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _friendly_llm_error(endpoint: LlmEndpoint, resp: Any) -> str:
    raw = (getattr(resp, "text", None) or "")[:400]
    err = raw
    try:
        payload = resp.json()
        msg = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(msg, dict):
            msg = msg.get("message") or msg.get("error")
        if isinstance(msg, str) and msg:
            err = msg
    except Exception:  # noqa: BLE001
        pass
    low = str(err).lower()
    if "model not found" in low or "invalid-argument" in low:
        return (
            f"{endpoint.label}에 '{endpoint.model}' 모델이 없습니다. "
            f"설정에서 {endpoint.label} 모델을 고른 뒤 저장하세요."
        )
    return f"{endpoint.label} HTTP {resp.status_code}: {err[:240]}"


def call_chat(
    endpoint: LlmEndpoint,
    messages: list[dict[str, str]],
    timeout: int = 120,
    *,
    json_mode: bool = True,
) -> tuple[str, dict[str, Any]]:
    if endpoint.provider == "antigravity" or endpoint.base_url.startswith("cli://"):
        from kr_quant.research.antigravity_auth import call_agy_subprocess

        prompt_lines = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                prompt_lines.append(f"[지침 / System Prompt]\n{content}\n")
            else:
                prompt_lines.append(f"[분석 요청 / User Prompt]\n{content}\n")
        combined_prompt = "\n".join(prompt_lines)
        if json_mode:
            combined_prompt += "\n\n반드시 JSON 형식으로만 응답하세요. 다른 설명이나 마크다운 백틱 없이 순수 JSON 객체만 반환하세요."
        return call_agy_subprocess(combined_prompt, model=endpoint.model, timeout=timeout)


    if not endpoint.api_key:
        raise RuntimeError(f"{endpoint.label} 연결이 없습니다. Grok/Antigravity 연결 또는 API 키를 설정하세요.")
    if not endpoint.model:
        raise RuntimeError("모델을 선택하세요.")
    url = f"{endpoint.base_url}/chat/completions"
    payload = {
        "model": endpoint.model,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    from kr_quant.research.providers import extra_headers

    headers = {"Content-Type": "application/json", **extra_headers(endpoint)}
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(_friendly_llm_error(endpoint, resp))
    try:
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(f"{endpoint.label} 응답 JSON 파싱 실패: {resp.text[:300]}") from exc

    if not isinstance(body, dict):
        raise RuntimeError(f"{endpoint.label} 응답 형식 오류: {resp.text[:300]}")

    if body.get("error"):
        err_obj = body["error"]
        msg = err_obj.get("message") if isinstance(err_obj, dict) else str(err_obj)
        code = err_obj.get("code") if isinstance(err_obj, dict) else ""
        code_str = f" [코드: {code}]" if code else ""
        raise RuntimeError(f"{endpoint.label} ({endpoint.model}) API 오류: {msg}{code_str}")

    choices = body.get("choices")
    if choices and isinstance(choices, list) and len(choices) > 0:
        c0 = choices[0]
        if isinstance(c0, dict):
            if "message" in c0 and isinstance(c0["message"], dict):
                text = c0["message"].get("content") or ""
            elif "text" in c0:
                text = c0.get("text") or ""
            else:
                text = str(c0)
        else:
            text = str(c0)
    elif "candidates" in body and isinstance(body["candidates"], list) and len(body["candidates"]) > 0:
        cand = body["candidates"][0]
        content = cand.get("content", {})
        parts = content.get("parts", [])
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    else:
        raise RuntimeError(f"{endpoint.label} ({endpoint.model}) 응답에 유효한 결과가 없습니다: {resp.text[:300]}")

    if not str(text).strip():
        raise RuntimeError(f"{endpoint.label} ({endpoint.model})에서 빈 내용이 반환되었습니다.")

    return text, body


def sanitize_research(parsed: dict[str, Any]) -> dict[str, Any]:
    leaked = BANNED.intersection(parsed)
    if leaked:
        raise RuntimeError(f"LLM 출력이 Quant 필드를 포함해 거부됨: {sorted(leaked)}")
    return parsed


def research_path(output_dir: Path, as_of: str, ticker: str) -> Path:
    return output_dir / "research" / f"as_of={as_of}" / f"{ticker}.json"


def analyze_ticker(
    endpoint: LlmEndpoint,
    row: dict[str, Any],
    as_of: str,
    output_dir: Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").zfill(6)
    qhash = snapshot_hash(row)
    messages = build_messages(row, as_of)
    raw_text, raw_body = call_chat(endpoint, messages)
    parsed = sanitize_research(_extract_json(raw_text))
    record = {
        "schema_version": "gpt_research_output_v1",
        "run_id": run_id or "",
        "security_id": ticker,
        "ticker": ticker,
        "company": row.get("company"),
        "as_of_date": as_of,
        "quant_snapshot_hash_ack": qhash,
        "provider": endpoint.provider,
        "model": endpoint.model,
        "prompt_version": "research_v1.0.0",
        "researched_at": datetime.now(timezone.utc).isoformat(),
        "usage": (raw_body.get("usage") or {}),
        **parsed,
    }
    path = research_path(output_dir, as_of, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return record
