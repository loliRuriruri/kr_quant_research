from __future__ import annotations

import os
from typing import Any

API = "https://api.telegram.org/bot{token}/{method}"


def silent() -> bool:
    return os.environ.get("STOCK_SCREENER_SILENT", "").strip() in {"1", "true", "TRUE", "yes"}


def configured(token: str | None, chat_id: str | None) -> bool:
    return bool(token and chat_id)


def _post(token: str, method: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    import requests

    if not token:
        raise RuntimeError("텔레그램 봇 토큰이 없습니다.")
    resp = requests.post(API.format(token=token, method=method), json=payload or {}, timeout=timeout)
    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"텔레그램 {method} HTTP {resp.status_code}: {resp.text[:160]}") from exc
    if resp.status_code >= 400 or not body.get("ok"):
        desc = body.get("description") or resp.text[:160]
        raise RuntimeError(f"텔레그램 {method}: {desc}")
    return body


def get_me(token: str) -> dict[str, Any]:
    data = _post(token, "getMe")
    result = data.get("result") or {}
    return {
        "id": result.get("id"),
        "username": result.get("username"),
        "name": result.get("first_name"),
    }


def list_chats(token: str) -> list[dict[str, Any]]:
    data = _post(token, "getUpdates", {"limit": 30, "timeout": 0})
    seen: dict[str, dict[str, Any]] = {}
    for upd in data.get("result") or []:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        key = str(cid)
        seen[key] = {
            "id": key,
            "type": chat.get("type"),
            "title": chat.get("title") or chat.get("username") or chat.get("first_name") or key,
        }
    return list(seen.values())


def send_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID가 없습니다. 봇에게 메시지를 보낸 뒤 채팅 ID를 찾으세요.")
    data = _post(token, "sendMessage", {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True})
    return {"ok": True, "message_id": (data.get("result") or {}).get("message_id")}


def format_screen_done(result: dict[str, Any]) -> str:
    as_of = result.get("as_of_date") or ""
    status = result.get("status") or ""
    n20 = result.get("top20_count")
    lines = [
        "KR Quant Screener · 스크리닝 완료",
        f"기준일 {as_of}",
        f"상태 {status} · TOP20 {n20}종목",
        "",
    ]
    for i, row in enumerate(result.get("top") or [], 1):
        score = row.get("quant_score")
        try:
            score_s = f"{float(score):.1f}"
        except (TypeError, ValueError):
            score_s = "-"
        name = row.get("company") or ""
        ticker = row.get("ticker") or ""
        lines.append(f"{i}. {name} {ticker} {score_s}")
    warnings = result.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("경고: " + ", ".join(str(w) for w in warnings[:4]))
    lines.append("")
    lines.append("후보 발굴용이며 매수·매도 지시가 아닙니다.")
    return "\n".join(lines)


def format_job_error(kind: str, error: str) -> str:
    return "\n".join(
        [
            "KR Quant Screener · 작업 실패",
            f"작업 {kind}",
            str(error)[:500],
            "",
            "주문은 실행하지 않습니다.",
        ]
    )


def format_report_notice(record: dict[str, Any]) -> str:
    kind = "AI 분석 리포트" if record.get("schema_version") == "research_report_v4" else "간단 검증"
    return "\n".join(
        [
            f"KR Quant Screener · {kind} 발간",
            f"{record.get('company') or ''} {record.get('ticker') or ''}",
            f"기준일 {record.get('as_of_date') or ''}",
            f"모델 {record.get('provider') or ''} {record.get('model') or ''}",
            "",
            "리서치 의견이며 매수·매도 지시가 아닙니다.",
        ]
    )


def notify_safe(token: str | None, chat_id: str | None, text: str) -> dict[str, Any]:
    if silent():
        return {"ok": False, "skipped": "silent"}
    if not configured(token, chat_id):
        return {"ok": False, "skipped": "not_configured"}
    try:
        return send_message(str(token), str(chat_id), text)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}
