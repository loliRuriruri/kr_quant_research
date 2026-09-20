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
    if endpoint.provider == "tier1_unavailable":
        raise RuntimeError("무료 AI 연결이 없습니다. OpenRouter 무료 경로를 설정하세요. 유료 모델로 자동 전환하지 않습니다.")
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
    is_responses = endpoint.provider in ("opencode_go", "opencode") and (
        "spark" in endpoint.model.lower() or "muse" in endpoint.model.lower()
    )
    if is_responses:
        url = f"{endpoint.base_url}/responses"
        payload = {
            "model": endpoint.model,
            "input": messages,
            "temperature": 0.2,
        }
    else:
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
    elif "output" in body and isinstance(body["output"], list):
        out_parts = []
        for item in body["output"]:
            if isinstance(item, dict) and item.get("type") == "message":
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        out_parts.append(part.get("text", ""))
        text = "".join(out_parts)
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


def get_tier1_insights(
    ticker: str,
    company: str,
    news: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    tech: dict[str, Any] | None = None,
    flow: dict[str, Any] | None = None,
    settings: Any = None,
    force: bool = False,
) -> dict[str, Any]:
    """Stock-click briefing: Nemotron :free first, then OpenRouter Flash if the free hop fails."""
    from kr_quant.research.providers import resolve_tier1_endpoint, resolve_tier1_routine_paid_endpoint

    code = str(ticker).zfill(6)
    today = datetime.now().strftime("%Y-%m-%d")
    root = getattr(settings, "root", Path("."))
    cache_dir = root / "data" / "cache" / "tier1_insights"
    cache_dir.mkdir(parents=True, exist_ok=True)

    endpoint = resolve_tier1_endpoint(settings)
    insight_hops = [endpoint]
    try:
        flash = resolve_tier1_routine_paid_endpoint(settings)
        if (
            getattr(flash, "configured", False)
            and getattr(flash, "provider", "") != "tier1_unavailable"
            and getattr(flash, "model", None) != getattr(endpoint, "model", None)
        ):
            insight_hops.append(flash)
    except Exception:
        pass
    model_id = str(getattr(endpoint, "model", "") or "")
    provider_id = str(getattr(endpoint, "provider", "") or "")
    configured_label = str(getattr(endpoint, "label", "") or "")
    if ":free" in model_id.lower():
        tier_label = f"{configured_label or model_id} · 설정 모델 {model_id}"
    else:
        tier_label = configured_label or f"{provider_id} {model_id}".strip() or "설정된 설명 모델"

    news_list = news.get("news", []) if isinstance(news, dict) else (news if isinstance(news, list) else [])
    events_list = events.get("rows", []) if isinstance(events, dict) else (events if isinstance(events, list) else [])

    news_str = "\n".join(f"- {n.get('title', '')} ({n.get('source', '')}): {n.get('snippet', '') or n.get('description', '')}" for n in news_list[:5]) or "최근 특이 뉴스 없음"
    events_str = "\n".join(f"- [{e.get('date', '') or e.get('report_date', '')}] {e.get('title', '')} ({e.get('market', '') or e.get('event_ko', '')})" for e in events_list[:4]) or "최근 주요 공시 없음"
    tech_str = json.dumps(tech or {}, ensure_ascii=False)
    flow_str = json.dumps(flow or {}, ensure_ascii=False)
    evidence_snapshot = {
        "ticker": code,
        "news": news_list[:5],
        "events": events_list[:4],
        "tech": tech or {},
        "flow": flow or {},
    }
    evidence_hash = sha256_json(evidence_snapshot)
    cache_file = cache_dir / f"{code}_{today}_{evidence_hash[:12]}.json"

    if not force and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    evidence_count = (
        len(news_list[:5])
        + len(events_list[:4])
        + sum(value not in (None, "", {}, []) for value in (tech or {}).values())
        + sum(value not in (None, "", {}, []) for value in (flow or {}).values())
    )
    observations: list[str] = []
    if news_list:
        observations.append(f"뉴스 {len(news_list[:5])}건: {news_list[0].get('title') or '제목 없음'}")
    if events_list:
        observations.append(
            f"공시 {len(events_list[:4])}건: {events_list[0].get('title') or events_list[0].get('event_ko') or '제목 없음'}"
        )
    if any(value not in (None, "", {}, []) for value in (tech or {}).values()):
        observations.append("기술 스냅샷 제공됨")
    if any(value not in (None, "", {}, []) for value in (flow or {}).values()):
        observations.append("수급 스냅샷 제공됨")
    missing_bits = [
        name
        for name, present in (("뉴스", news_list), ("공시", events_list), ("기술", tech), ("수급", flow))
        if not present
    ]

    if evidence_count <= 0:
        gap = "제공된 뉴스·공시·지표가 없어 종목별 촉매를 만들지 않습니다."
        result = {
            "ticker": code,
            "company": company,
            "as_of": today,
            "model": endpoint.model,
            "provider": endpoint.provider,
            "tier": tier_label,
            "status": "INSUFFICIENT_EVIDENCE",
            "ok": True,
            "ai_generated": False,
            "used_in_quant": False,
            "prompt_version": "stock_tier1_insights_v3",
            "evidence_hash": evidence_hash,
            "evidence": {"item_count": 0, "coverage": "NONE", "sources": [], "missing": missing_bits},
            "error_code": "TIER1_EVIDENCE_MISSING",
            "observations": [],
            "calculations": [],
            "interpretation": "근거 부족",
            "falsification": "뉴스·공시·수급·기술 스냅샷이 채워지면 설명을 다시 생성합니다.",
            "data_limits": ["원천이 없으면 가격·확률·목표가를 만들지 않습니다.", "LLM이 퀀트 점수를 바꾸지 않습니다."],
            "news_analysis": {"summary": gap, "sentiment": "근거 부족", "key_driver": "근거 부족"},
            "events_analysis": {"commentary": gap, "risk_level": "판단 불가", "key_point": "근거 부족"},
            "tech_flow_analysis": {"action_guide": gap, "posture": "근거 부족", "timing_tip": "원본 지표 확인"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return result

    combined_prompt = f"""당신은 최고 수준의 퀀트/주식 리서치 전략가입니다.
종목: {company} ({code})

[1. 실시간 뉴스 목록]
{news_str}

[2. DART 최근 공시 목록]
{events_str}

[3. 기술적 지표 & 수급 90일 현황]
기술지표: {tech_str}
수급현황: {flow_str}

위 3가지 영역을 종합 분석하여 반드시 아래 JSON 구조로만 응답하세요:
{{
  "news_analysis": {{
    "summary": "제공된 뉴스가 실적/사업/가격 기대에 미칠 수 있는 영향을 근거 범위 안에서 2줄 요약",
    "sentiment": "긍정/부정/혼재/근거 부족",
    "key_driver": "핵심 드라이버 요약"
  }},
  "events_analysis": {{
    "commentary": "제공된 공시가 지분 희석, 오버행, 실적에 미칠 수 있는 영향과 확인 한계 2줄",
    "risk_level": "낮음/중간/높음/판단 불가",
    "key_point": "핵심 체크 포인트"
  }},
  "tech_flow_analysis": {{
    "action_guide": "외인/기관 수급과 기술 지표가 일치하거나 충돌하는 지점 2줄",
    "posture": "확인/혼재/근거 부족",
    "timing_tip": "추가 확인할 지표"
  }}
}}

제공되지 않은 사실, 가격선, 수익률, 매수·매도·비중·목표가·손절가를 만들지 마세요."""

    news_analysis = {
        "summary": "제공된 뉴스 제목만 확인했습니다. 모델 해석은 없습니다.",
        "sentiment": "근거 확인 필요",
        "key_driver": (news_list[0].get("title") if news_list else "근거 부족"),
    }
    events_analysis = {
        "commentary": "제공된 공시 제목만 확인했습니다. 모델 해석은 없습니다.",
        "risk_level": "판단 불가",
        "key_point": ((events_list[0].get("title") or events_list[0].get("event_ko")) if events_list else "근거 부족"),
    }
    tech_flow_analysis = {
        "action_guide": "제공된 기술·수급 스냅샷만 있습니다. 매수·매도 문구를 만들지 않습니다.",
        "posture": "근거 확인 필요",
        "timing_tip": "원본 지표 확인",
    }
    status = "DETERMINISTIC_FALLBACK"
    ai_generated = False
    error_code: str | None = None
    used_endpoint = endpoint

    for hop in insight_hops:
        if not getattr(hop, "configured", False) or getattr(hop, "provider", "") == "tier1_unavailable":
            continue
        try:
            hop_timeout = 12 if str(getattr(hop, "model", "")).endswith(":free") else 22
            raw_text, _ = call_chat(
                hop,
                [{"role": "system", "content": "You are a professional Korean equity research analyst. Output strictly in valid JSON."},
                 {"role": "user", "content": combined_prompt}],
                timeout=hop_timeout,
                json_mode=True,
            )
            parsed = _extract_json(raw_text)
            if isinstance(parsed, dict):
                if "news_analysis" in parsed and isinstance(parsed["news_analysis"], dict):
                    news_analysis = parsed["news_analysis"]
                if "events_analysis" in parsed and isinstance(parsed["events_analysis"], dict):
                    events_analysis = parsed["events_analysis"]
                if "tech_flow_analysis" in parsed and isinstance(parsed["tech_flow_analysis"], dict):
                    tech_flow_analysis = parsed["tech_flow_analysis"]
                status = "GENERATED"
                ai_generated = True
                used_endpoint = hop
                error_code = None
                break
        except Exception as exc:
            error_code = "TIER1_GENERATION_FAILED"
            print(f"Tier 1 insight unavailable ({getattr(hop, 'model', '')}): {exc}")

    endpoint = used_endpoint
    model_id = str(getattr(endpoint, "model", "") or "")
    provider_id = str(getattr(endpoint, "provider", "") or "")
    configured_label = str(getattr(endpoint, "label", "") or "")
    if ":free" in model_id.lower():
        tier_label = f"{configured_label or model_id} · 설정 모델 {model_id}"
    else:
        tier_label = configured_label or f"{provider_id} {model_id}".strip() or "설정된 설명 모델"

    result = {
        "ticker": code,
        "company": company,
        "as_of": today,
        "model": endpoint.model,
        "provider": endpoint.provider,
        "tier": tier_label,
        "status": status,
        "ok": True,
        "ai_generated": ai_generated,
        "used_in_quant": False,
        "prompt_version": "stock_tier1_insights_v3",
        "evidence_hash": evidence_hash,
        "evidence": {
            "item_count": evidence_count,
            "coverage": "PARTIAL",
            "sources": ["naver_news", "dart_events", "technical_snapshot", "flow_snapshot"],
            "missing": missing_bits,
        },
        "error_code": error_code,
        "observations": observations,
        "calculations": [],
        "interpretation": "모델 해석" if ai_generated else "제공된 항목만 나열한 결정론적 요약입니다.",
        "falsification": "제공된 뉴스·공시가 바뀌면 이 설명을 폐기합니다.",
        "data_limits": ["제공되지 않은 사실·목표가·확률을 만들지 않습니다.", "LLM이 퀀트 점수를 바꾸지 않습니다."],
        "news_analysis": news_analysis,
        "events_analysis": events_analysis,
        "tech_flow_analysis": tech_flow_analysis,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return result

