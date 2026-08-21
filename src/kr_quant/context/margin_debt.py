# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import re
import time
from typing import Any
import requests

logger = logging.getLogger("kr_quant.context.margin_debt")

_CACHE: tuple[float, dict[str, Any]] | None = None
_CACHE_TTL = 3600  # 1 hour cache


def fetch_margin_debt_history(pages: int = 3, timeout: int = 10) -> list[dict[str, Any]]:
    history = []
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/sise/sise_deposit.naver?page={page}"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=timeout)
            text = resp.content.decode("euc-kr", errors="ignore")
        except Exception as e:
            logger.warning("Failed to fetch deposit page %d: %s", page, e)
            continue

        tables = re.findall(r"<table[^>]*>(.*?)</table>", text, flags=re.DOTALL)
        if not tables:
            continue
        tbl0 = tables[0]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tbl0, flags=re.DOTALL)

        for r in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", r, flags=re.DOTALL)
            if not tds:
                continue
            clean = [re.sub(r"<[^>]+>", " ", td).strip().replace(",", "") for td in tds]
            if len(clean) >= 5 and re.match(r"^\d{2}\.\d{2}\.\d{2}$", clean[0]):
                date_str = "20" + clean[0]
                try:
                    deposit = float(clean[1])  # 억원
                    margin_debt = float(clean[3])  # 억원
                    history.append(
                        {
                            "date": date_str,
                            "deposit_krw_100m": deposit,
                            "margin_debt_krw_100m": margin_debt,
                            "deposit_trillion": round(deposit / 10000, 2),
                            "margin_debt_trillion": round(margin_debt / 10000, 2),
                            "margin_deposit_ratio": round((margin_debt / deposit) * 100, 2) if deposit else 0,
                        }
                    )
                except (ValueError, IndexError):
                    continue
    return history


def get_margin_debt_snapshot(*, refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    now = time.time()
    if not refresh and _CACHE is not None and (now - _CACHE[0] < _CACHE_TTL):
        return _CACHE[1]

    history = fetch_margin_debt_history(pages=3)
    if not history:
        res = {
            "ok": False,
            "error": "신용잔고 데이터를 불러올 수 없습니다.",
            "latest_date": "—",
            "margin_debt_trillion": 0,
            "deposit_trillion": 0,
            "margin_deposit_ratio": 0,
            "delta_1d_trillion": 0,
            "delta_5d_trillion": 0,
            "kospi_est_trillion": 0,
            "kosdaq_est_trillion": 0,
            "sparkline": [],
            "status": "NEUTRAL",
            "status_label": "중립",
            "status_cls": "neutral",
            "warning": "데이터 로딩 중",
        }
        return res

    latest = history[0]
    prev = history[1] if len(history) > 1 else latest
    prev_5d = history[5] if len(history) > 5 else latest

    margin_now = latest["margin_debt_trillion"]
    margin_prev = prev["margin_debt_trillion"]
    margin_5d = prev_5d["margin_debt_trillion"]
    delta_1d = round(margin_now - margin_prev, 2)
    delta_5d = round(margin_now - margin_5d, 2)
    ratio_now = latest["margin_deposit_ratio"]

    # Historical sparkline (reversed to chronological)
    sparkline = [h["margin_debt_trillion"] for h in reversed(history[:30])]

    # Market breakdown estimation (코스피 ~58%, 코스닥 ~42% 통상 비중)
    kospi_est = round(margin_now * 0.58, 2)
    kosdaq_est = round(margin_now * 0.42, 2)

    # Risk Warning & Status Diagnosis
    if ratio_now >= 35.0 or margin_now >= 32.0 or (delta_5d >= 1.0 and margin_now >= 28.0):
        status = "DANGER"
        status_label = "🚨 극단적 레버리지 과열 (반대매매 위험)"
        status_cls = "down"
        warning = (
            "🚨 <b>【신용잔고 위험 경보】</b> 시장 신용융자 잔고가 매우 높거나 예탁금 대비 신용비율이 과열권입니다. "
            "작은 지수 하락에도 <b>반대매매(Forced Liquidation) 연쇄 출회</b> 및 투매 폭탄 위험이 급증합니다. "
            "신용 레버리지가 높은 중소형 개별주 매수를 극도로 자제하고, 현금 비중을 30% 이상 확보하세요."
        )
    elif ratio_now >= 30.0 or margin_now >= 28.0:
        status = "CAUTION"
        status_label = "⚠️ 신용 과열 주의 (리스크 관리)"
        status_cls = "warn"
        warning = (
            "⚠️ <b>【신용잔고 과열 주의】</b> 개인 투자자의 빚투 레버리지가 증가 추세에 있습니다. "
            "단기 조정 시 신용 물량이 출회되며 변동성이 커질 수 있으므로, 분할 익절 및 보수적 포트폴리오 비중 유지를 권장합니다."
        )
    elif ratio_now <= 22.0 or margin_now <= 20.0 or delta_5d <= -1.5:
        status = "OPPORTUNITY"
        status_label = "🟢 신용 매물 청산 클린존 (반등 탄력성 극대화)"
        status_cls = "up"
        warning = (
            "🟢 <b>【악성 신용 청산 완료 / 기회 구간】</b> 반대매매 및 신용 털림이 대거 소화되어 시장의 잠재 매도 압력이 현저히 낮아졌습니다. "
            "악성 빚투 매물이 청산된 후에는 가벼워진 수급으로 인해 <b>강력한 V자 턴어라운드 및 반등 탄력성</b>이 나타나는 황금 매수 구간입니다."
        )
    else:
        status = "NEUTRAL"
        status_label = "🟡 신용잔고 적정 안정 구간"
        status_cls = "neutral"
        warning = (
            "🟡 <b>【신용잔고 균형】</b> 예탁금 대비 신용융자 비율이 안정적인 밴드 내에 유지되고 있습니다. "
            "단기 수급 쏠림보다는 기업 펀더멘털과 5대 팩터 점수를 중심으로 종목을 선별하세요."
        )

    res = {
        "ok": True,
        "latest_date": latest["date"],
        "margin_debt_trillion": margin_now,
        "deposit_trillion": latest["deposit_trillion"],
        "margin_deposit_ratio": ratio_now,
        "delta_1d_trillion": delta_1d,
        "delta_5d_trillion": delta_5d,
        "kospi_est_trillion": kospi_est,
        "kosdaq_est_trillion": kosdaq_est,
        "status": status,
        "status_label": status_label,
        "status_cls": status_cls,
        "warning": warning,
        "history": history[:20],
        "sparkline": sparkline,
    }

    _CACHE = (now, res)
    return res
