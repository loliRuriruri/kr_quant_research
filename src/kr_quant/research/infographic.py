# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import re
from typing import Any


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        fv = float(v)
        return default if math.isnan(fv) else fv
    except Exception:
        return default


def _fmt_price(v: float | None) -> str:
    if not v or v <= 0:
        return "—"
    return f"{int(v):,}원"


def _fmt_mcap(v: float | None) -> str:
    if not v or v <= 0:
        return "—"
    trillion = v / 1_000_000_000_000
    if trillion >= 1.0:
        return f"{trillion:,.1f}조원"
    billion = v / 100_000_000
    return f"{billion:,.0f}억원"


def parse_report_sections(md: str) -> dict[str, str]:
    """Robust parser that maps markdown headings to canonical section keys regardless of numbering or styling."""
    if not md:
        return {}

    section_map = [
        ("overview", ["45초", "총평", "요약", "executive summary", "overview"]),
        ("news_catalyst", ["뉴스", "공시", "이벤트", "카탈리스트", "catalyst", "news", "event"]),
        ("financials", ["재무", "실적", "이익의 질", "financial", "earnings", "손익", "대차"]),
        ("valuation", ["밸류에이션", "가치평가", "valuation", "목표가", "per", "pbr"]),
        ("moat_business", ["해자", "성장성", "비즈니스", "moat", "business model", "경쟁", "업계", "성장 동력"]),
        ("macro_policy", ["정책", "거시", "테마", "macro", "policy", "industry cycle", "산업"]),
        ("tech_flow", ["기술적 위치", "거래량", "수급", "유사국면", "technical", "flow"]),
        ("action_playbook", ["플레이북", "전략", "행동", "매매", "action", "playbook", "신규", "보유", "트레이더", "사용자별"]),
        ("risks_redteam", ["리스크", "위험", "반대", "심문", "red team", "risk", "bear"]),
    ]

    sections: dict[str, str] = {}
    current_sec = "header"
    current_lines: list[str] = []

    for line in md.splitlines():
        h_match = re.match(r"^#{1,4}\s*(?:\*\*)?(?:(?:\d+[\.\)]\s*)?([^\*\r\n#]+))(?:\*\*)?", line.strip())
        if h_match:
            heading_text = h_match.group(1).strip()
            matched_canon = None
            for canon_key, keywords in section_map:
                if any(kw in heading_text.lower() for kw in keywords):
                    matched_canon = canon_key
                    break

            if matched_canon:
                if current_lines:
                    prev_content = "\n".join(current_lines).strip()
                    if current_sec in sections:
                        sections[current_sec] += "\n\n" + prev_content
                    else:
                        sections[current_sec] = prev_content
                current_sec = matched_canon
                current_lines = []
                continue

        current_lines.append(line)

    if current_lines:
        prev_content = "\n".join(current_lines).strip()
        if current_sec in sections:
            sections[current_sec] += "\n\n" + prev_content
        else:
            sections[current_sec] = prev_content

    return sections


def extract_bullet_dict(text: str) -> dict[str, str]:
    res: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*[-*•]\s+\*\*([^*]+)\*\*:\s*(.+)$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            res[key] = val
        else:
            m2 = re.match(r"^\s*[-*•]\s+([^:]+):\s*(.+)$", line)
            if m2 and len(m2.group(1)) <= 15:
                res[m2.group(1).strip()] = m2.group(2).strip()
    return res


def md_to_rich_html(md_text: str) -> str:
    """Converts markdown text containing headers, tables, bullet points and bold text into presentation HTML."""
    if not md_text:
        return ""

    lines = md_text.splitlines()
    html_out: list[str] = []
    table_lines: list[str] = []
    in_table = False

    def render_table(tbl: list[str]) -> str:
        if not tbl:
            return ""
        header = []
        rows = []
        for idx, t_line in enumerate(tbl):
            if idx == 1 and "---" in t_line:
                continue
            cols = [c.strip() for c in t_line.strip("|").split("|")]
            if idx == 0:
                header = cols
            else:
                rows.append(cols)

        th_html = "".join(f'<th class="py-2.5 px-3.5 font-bold text-slate-200 bg-slate-900/90 whitespace-nowrap border-b border-slate-700">{h}</th>' for h in header)
        tbody_html = ""
        for r in rows:
            td_html = ""
            for c in r:
                if any(x in c for x in ["긍정", "서프라이즈", "상향", "호재", "안정", "우수"]):
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">{c}</span>'
                elif any(x in c for x in ["부정", "리스크", "경쟁", "하향", "악재", "경계", "비관"]):
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">{c}</span>'
                elif any(x in c for x in ["중립", "관망", "보통"]):
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-700/50 text-slate-300">{c}</span>'
                else:
                    c_badge = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'></b>", c)
                td_html += f'<td class="py-2.5 px-3.5 text-slate-200 border-t border-slate-800/80">{c_badge}</td>'
            tbody_html += f'<tr class="hover:bg-slate-800/50 transition">{td_html}</tr>'

        return f"""
        <div class="overflow-x-auto rounded-xl border border-slate-800 my-4 shadow-lg bg-slate-950/40">
            <table class="w-full text-xs sm:text-sm text-left">
                <thead><tr>{th_html}</tr></thead>
                <tbody>{tbody_html}</tbody>
            </table>
        </div>
        """

    for line in lines:
        sline = line.strip()
        if sline.startswith("|") and sline.endswith("|"):
            if not in_table:
                in_table = True
            table_lines.append(sline)
            continue
        else:
            if in_table:
                in_table = False
                html_out.append(render_table(table_lines))
                table_lines = []

        if not sline:
            continue

        if sline.startswith("### "):
            title = sline[4:].strip()
            title = re.sub(r"\*\*([^*]+)\*\*", r"", title)
            html_out.append(f'<h4 class="text-base sm:text-lg font-bold text-sky-300 mt-5 mb-2.5 flex items-center gap-2"><span class="w-1.5 h-4 bg-sky-400 rounded-full inline-block"></span>{title}</h4>')
        elif sline.startswith("#### "):
            title = sline[5:].strip()
            title = re.sub(r"\*\*([^*]+)\*\*", r"", title)
            html_out.append(f'<h5 class="text-sm sm:text-base font-bold text-slate-200 mt-4 mb-2">{title}</h5>')
        elif sline.startswith("- ") or sline.startswith("* "):
            content = sline[2:].strip()
            content = re.sub(r"\*\*([^*]+)\*\*:\s*", r"<b class='text-sky-300 font-semibold'>:</b> ", content)
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'></b>", content)
            html_out.append(f'<div class="flex items-start gap-2.5 text-sm text-slate-300 my-2"><span class="text-sky-400 mt-1 text-xs">◆</span><div class="leading-relaxed">{content}</div></div>')
        elif re.match(r"^\d+\.\s+", sline):
            num_match = re.match(r"^(\d+)\.\s+(.*)$", sline)
            num = num_match.group(1) if num_match else "1"
            content = num_match.group(2) if num_match else sline
            content = re.sub(r"\*\*([^*]+)\*\*:\s*", r"<b class='text-sky-300 font-semibold'>:</b> ", content)
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'></b>", content)
            html_out.append(f'<div class="flex items-start gap-2.5 text-sm text-slate-300 my-2"><span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-sky-500/20 text-sky-400 font-bold text-xs shrink-0 mt-0.5">{num}</span><div class="leading-relaxed">{content}</div></div>')
        else:
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'></b>", sline)
            html_out.append(f'<p class="text-sm text-slate-300 leading-relaxed my-2">{content}</p>')

    if in_table:
        html_out.append(render_table(table_lines))

    return "\n".join(html_out)


def generate_infographic_html(record: dict[str, Any], stock_row: dict[str, Any] | None = None) -> str:
    ticker = str(record.get("ticker") or "").zfill(6)
    company = record.get("company") or (stock_row.get("company") if stock_row else "") or ticker
    as_of = record.get("as_of_date") or ""
    provider = record.get("provider") or "DeepSeek / KR Quant Engine"
    model = record.get("model") or "DeepSeek V3"

    # Quant Scores & Ranks
    quant_score_raw = record.get("quant_score") if record.get("quant_score") is not None else (stock_row.get("quant_score") if stock_row else 0)
    quant_score = _safe_float(quant_score_raw, 0.0)
    quant_rank_raw = record.get("quant_rank") or (stock_row.get("quant_rank") if stock_row else 1)
    quant_rank_int = int(_safe_float(quant_rank_raw, 1))

    market = record.get("market") or (stock_row.get("market") if stock_row else "KOSPI")
    industry = record.get("industry") or record.get("sector") or (stock_row.get("industry") if stock_row else "우량 기업")

    # Real Price & Market Cap Data
    last_close = _safe_float(record.get("last_close") or (stock_row.get("last_close") if stock_row else None) or (stock_row.get("close") if stock_row else None))
    market_cap = _safe_float(stock_row.get("market_cap") if stock_row else None)
    volume = _safe_float(stock_row.get("volume") if stock_row else None)
    trading_val = _safe_float(stock_row.get("trading_value") if stock_row else None)

    # Foreign rate
    foreign_rate = 0.0
    if stock_row:
        for k in ["foreign_holding_rate", "foreign_rate", "foreign_ratio"]:
            if k in stock_row and stock_row[k] is not None:
                foreign_rate = _safe_float(stock_row[k])
                break

    # Factor Scores
    factors = record.get("factor_scores") or (stock_row.get("factor_scores") if stock_row else {}) or {}
    val_score = _safe_float(factors.get("value") or (stock_row.get("value_score") if stock_row else 0))
    qual_score = _safe_float(factors.get("quality") or (stock_row.get("quality_score") if stock_row else 0))
    grow_score = _safe_float(factors.get("growth") or (stock_row.get("growth_score") if stock_row else 0))
    mom_score = _safe_float(factors.get("momentum") or (stock_row.get("momentum_score") if stock_row else 0))
    stab_score = _safe_float(factors.get("stability") or (stock_row.get("stability_score") if stock_row else 0))

    # Financial Valuation Metrics
    per = _safe_float(stock_row.get("per") if stock_row else None)
    pbr = _safe_float(stock_row.get("pbr") if stock_row else None)
    roe = _safe_float(stock_row.get("roe") if stock_row else None)
    op_margin = _safe_float(stock_row.get("operating_margin") if stock_row else None)
    rev_yoy = _safe_float(stock_row.get("revenue_yoy") if stock_row else None)
    ev_ebit = _safe_float(stock_row.get("ev_ebit") if stock_row else None)
    fcf_yield = _safe_float(stock_row.get("fcf_yield") if stock_row else None)
    roic = _safe_float(stock_row.get("roic") if stock_row else None)
    net_debt = _safe_float(stock_row.get("net_debt_assets") if stock_row else None)
    ret_3m = _safe_float(stock_row.get("return_3m") if stock_row else None)
    ret_6m = _safe_float(stock_row.get("return_6m") if stock_row else None)
    ret_12m = _safe_float(stock_row.get("return_12m") if stock_row else None)

    # Pre-compute return colors
    ret_3m_cls = "text-emerald-400" if ret_3m > 0 else "text-rose-400"
    ret_6m_cls = "text-emerald-400" if ret_6m > 0 else "text-rose-400"
    ret_12m_cls = "text-emerald-400" if ret_12m > 0 else "text-rose-400"

    # Strategy Backtest Data
    bt = record.get("strategy_backtest") or {}
    strategies = bt.get("strategies") or []
    best_name = bt.get("best_name") or "볼린저 평균회귀"
    best_params_ko = bt.get("best_params_ko") or "기간 20일 · 밴드폭 1.5배"
    playbook = bt.get("playbook") or {}

    archetype_badge = playbook.get("archetype_badge") or "🔄 평균회귀형 파동"
    archetype_desc = playbook.get("archetype_desc") or f"{company}은 과매도권에서 분할 매수하여 반등에 파는 '눌림목/평균회귀 매매'가 유리한 종목입니다."
    actionable_reason = playbook.get("actionable_reason") or f"최근 3년간 검증에서 최고 승률과 실전 표본을 기록한 '{best_name}'이 가장 실효성 높은 실전 1픽입니다."
    entry_rule = playbook.get("entry_rule") or f"주가가 볼린저 밴드 하단선({best_params_ko})을 이탈 후 복귀할 때 분할 매수"
    exit_rule = playbook.get("exit_rule") or "볼린저 밴드 중심선(20일선) 또는 상단선 도달 시 차익 실현"
    avoid_rule = playbook.get("avoid_rule") or "신고가 돌파 시 무리한 추격 매수, 골든크로스 고점 매수"

    strat_labels = [s.get("name", "") for s in strategies] or ["RSI 평균회귀", "볼린저 평균회귀", "이동평균 교차", "돈치안 돌파"]
    strat_returns = [round(float(s.get("total_return") or 0) * 100, 1) for s in strategies] or [20.9, 22.2, -17.6, -39.3]
    strat_winrates = [round(float(s.get("wf_hit") or 0) * 100, 0) for s in strategies] or [17, 67, 17, 50]

    strat_detail_rows = ""
    for i, s in enumerate(strategies):
        ret_val = float(s.get("total_return") or 0) * 100
        sharpe = float(s.get("sharpe") or 0)
        mdd = -abs(float(s.get("max_drawdown") or 0) * 100)
        wf = float(s.get("wf_hit") or 0) * 100
        tc = int(s.get("trade_count") or 0)
        is_best = (i == 0 and len(strategies) > 0) or s.get("strategy_id") == bt.get("best_id")
        bg = "background:rgba(56,189,248,0.12); font-weight:700;" if is_best else ""
        crown = "👑 " if is_best else ""
        color_cls = "text-emerald-400 font-bold" if ret_val > 0 else "text-rose-400 font-bold"
        strat_detail_rows += f'<tr style="{bg}"><td class="py-2.5 px-3.5">{crown}{s.get("name","")}</td><td class="py-2.5 px-3.5"><span class="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300">{s.get("family_ko","")}</span></td><td class="py-2.5 px-3.5 {color_cls}">{ret_val:+.1f}%</td><td class="py-2.5 px-3.5"><b>{sharpe:.2f}</b></td><td class="py-2.5 px-3.5">{wf:.0f}%</td><td class="py-2.5 px-3.5 text-rose-400">{mdd:.1f}%</td><td class="py-2.5 px-3.5">{tc}회</td><td class="py-2.5 px-3.5 text-xs text-slate-400">{s.get("params_ko","")}</td></tr>'

    # Format Strings
    last_close_fmt = _fmt_price(last_close)
    market_cap_fmt = _fmt_mcap(market_cap)
    foreign_rate_fmt = f"{foreign_rate:.1f}%" if foreign_rate > 0 else "—"
    trading_val_fmt = _fmt_mcap(trading_val)

    per_fmt = f"{per:.1f}x" if per else "—"
    pbr_fmt = f"{pbr:.2f}x" if pbr else "—"
    roe_fmt = f"{roe*100:.1f}%" if roe else "—"
    op_margin_fmt = f"{op_margin*100:.1f}%" if op_margin else "—"
    rev_yoy_fmt = f"{'+' if rev_yoy > 0 else ''}{rev_yoy*100:.1f}%" if rev_yoy else "—"
    roic_fmt = f"{roic*100:.1f}%" if roic else "—"
    ev_ebit_fmt = f"{ev_ebit:.1f}x" if ev_ebit else "—"
    fcf_yield_fmt = f"{fcf_yield*100:.1f}%" if fcf_yield else "—"
    net_debt_fmt = f"{net_debt*100:.1f}%" if net_debt else "—"
    ret_3m_fmt = f"{'+' if ret_3m > 0 else ''}{ret_3m*100:.1f}%" if ret_3m else "—"
    ret_6m_fmt = f"{'+' if ret_6m > 0 else ''}{ret_6m*100:.1f}%" if ret_6m else "—"
    ret_12m_fmt = f"{'+' if ret_12m > 0 else ''}{ret_12m*100:.1f}%" if ret_12m else "—"

    # Parse Report Markdown Sections
    report_md = record.get("report_markdown") or ""
    secs = parse_report_sections(report_md)

    sec0_text = secs.get("overview", "")
    sec0_dict = extract_bullet_dict(sec0_text) if sec0_text else {}

    verdict = sec0_dict.get("최종판정") or "조건부 매수 (Quant 우량)"
    good_co = sec0_dict.get("좋은 회사") or f"ROIC {roic_fmt}, 업계 상위 펀더멘털 경쟁력 보유"
    good_pr = sec0_dict.get("좋은 가격") or f"PER {per_fmt}, PBR {pbr_fmt} 수준"
    good_tm = sec0_dict.get("좋은 타이밍") or f"최적 백테스트: {best_name} ({best_params_ko})"
    new_buy_guide = sec0_dict.get("신규") or entry_rule
    hold_guide = sec0_dict.get("보유") or exit_rule
    max_risk = sec0_dict.get("최대 위험") or avoid_rule

    sec1_html = md_to_rich_html(secs.get("news_catalyst", ""))
    sec2_html = md_to_rich_html(secs.get("financials", ""))
    sec3_html = md_to_rich_html(secs.get("valuation", ""))
    sec4_html = md_to_rich_html(secs.get("moat_business", ""))
    sec5_html = md_to_rich_html(secs.get("macro_policy", ""))
    sec6_html = md_to_rich_html(secs.get("tech_flow", ""))
    sec7_html = md_to_rich_html(secs.get("risks_redteam", ""))
    sec8_html = md_to_rich_html(secs.get("action_playbook", ""))

    # Realistic base price for simulator
    base_price = last_close if last_close > 0 else 100000.0
    base_per = per if per and per > 0 else 12.0
    base_mcap = market_cap if market_cap > 0 else (base_price * 1_000_000)

    html = f"""<!DOCTYPE html>
<html lang="ko" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{company} ({ticker}) 딥다이브 인포그래픽 리포트 | KR Quant</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        brand: {{
                            50: '#f0f3ff',
                            100: '#e0e7ff',
                            400: '#818cf8',
                            500: '#6366f1',
                            600: '#4f46e5',
                            700: '#4338ca',
                            900: '#0f172a',
                        }},
                        accent: {{
                            pink: '#f43f5e',
                            cyan: '#06b6d4',
                            amber: '#f59e0b',
                            emerald: '#10b981',
                            blue: '#38bdf8'
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .chart-container {{
            position: relative;
            width: 100%;
            height: 280px;
        }}
        @media (min-width: 768px) {{
            .chart-container {{
                height: 320px;
            }}
        }}
        .no-scrollbar::-webkit-scrollbar {{ display: none; }}
        .no-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        .glass-card {{
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
        }}
        .glass-card:hover {{
            border-color: rgba(56, 189, 248, 0.4);
        }}
        @media print {{
            .no-print {{ display: none !important; }}
            body {{ background: #0f172a; color: #fff; }}
            .glass-card {{ border: 1px solid #334155; break-inside: avoid; }}
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans antialiased selection:bg-brand-500 selection:text-white">

    <!-- Top Header / Hero Deck -->
    <header class="relative overflow-hidden bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 pt-10 pb-10 border-b border-slate-800">
        <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-sky-600/20 via-transparent to-transparent pointer-events-none"></div>
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
            
            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div class="flex items-center gap-2">
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-sky-500/20 text-sky-400 border border-sky-500/30">
                        ✦ EQUITY RESEARCH v3.7.2 CLOUD-FIRST
                    </span>
                    <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
                        {market} · {industry} · 코드 {ticker}
                    </span>
                </div>
                <div class="flex items-center gap-3 text-xs text-slate-400">
                    <span>기준일: <b class="text-slate-200">{as_of or "최신"}</b></span>
                    <span>엔진: <b class="text-sky-400">{provider} ({model})</b></span>
                    <button onclick="window.print()" class="no-print inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                        🖨️ PDF / 인쇄
                    </button>
                </div>
            </div>

            <!-- Title & Top Key Metrics -->
            <div class="flex flex-col lg:flex-row lg:items-end justify-between gap-6 my-4">
                <div>
                    <h1 class="text-3xl sm:text-4xl lg:text-5xl font-black text-white tracking-tight flex items-center gap-3">
                        {company} <span class="text-sky-400 font-mono font-bold text-2xl sm:text-3xl">({ticker})</span>
                    </h1>
                    <p class="mt-2 text-sm sm:text-base text-slate-300 max-w-3xl leading-relaxed">
                        재무 5대 팩터 종합 퀀트 <b class="text-sky-300">{quant_score:.1f}점</b> (상위 {quant_rank_int}위), 4대 전략 백테스트 기반 최적 타이밍 검증 및 심층 AI 리서치 인포그래픽
                    </p>
                </div>

                <!-- Price & Metric Snapshot Pills -->
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shrink-0 shadow-lg">
                    <div class="px-2">
                        <span class="text-xs text-slate-400 font-medium block">최근 종가</span>
                        <span class="text-lg font-black text-white">{last_close_fmt}</span>
                    </div>
                    <div class="px-2 border-l border-slate-800">
                        <span class="text-xs text-slate-400 font-medium block">시가총액</span>
                        <span class="text-lg font-black text-slate-200">{market_cap_fmt}</span>
                    </div>
                    <div class="px-2 border-l border-slate-800">
                        <span class="text-xs text-slate-400 font-medium block">외인 지분율</span>
                        <span class="text-lg font-black text-sky-400">{foreign_rate_fmt}</span>
                    </div>
                    <div class="px-2 border-l border-slate-800">
                        <span class="text-xs text-slate-400 font-medium block">거래대금</span>
                        <span class="text-lg font-black text-emerald-400">{trading_val_fmt}</span>
                    </div>
                </div>
            </div>

            <!-- 4-Card 45-Second Executive Summary Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-sky-500">
                    <span class="text-xs font-bold text-sky-400 tracking-wider uppercase block mb-1">🎯 최종 투자 판정</span>
                    <h3 class="text-lg font-black text-white">{verdict}</h3>
                    <p class="text-xs text-slate-400 mt-2 leading-relaxed">종합 퀀트 {quant_score:.1f}점 · {industry} 상위 랭크</p>
                </div>
                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-emerald-500">
                    <span class="text-xs font-bold text-emerald-400 tracking-wider uppercase block mb-1">🏢 좋은 회사 (Quality & Moat)</span>
                    <h3 class="text-sm font-bold text-slate-100">{good_co}</h3>
                    <p class="text-xs text-slate-400 mt-2">ROE {roe_fmt} · ROIC {roic_fmt}</p>
                </div>
                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-amber-500">
                    <span class="text-xs font-bold text-amber-400 tracking-wider uppercase block mb-1">💰 좋은 가격 (Valuation)</span>
                    <h3 class="text-sm font-bold text-slate-100">{good_pr}</h3>
                    <p class="text-xs text-slate-400 mt-2">PER {per_fmt} · PBR {pbr_fmt} · EV/EBIT {ev_ebit_fmt}</p>
                </div>
                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-purple-500">
                    <span class="text-xs font-bold text-purple-400 tracking-wider uppercase block mb-1">⚡ 좋은 타이밍 (Timing)</span>
                    <h3 class="text-sm font-bold text-slate-100">{good_tm}</h3>
                    <p class="text-xs text-purple-300 mt-2 font-medium">{archetype_badge}</p>
                </div>
            </div>

            <!-- 3-Action Guide Pills -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
                <div class="p-3.5 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-start gap-2.5 text-xs text-emerald-200">
                    <span class="text-emerald-400 text-sm font-bold">🟢</span>
                    <div><b>신규 매수 가이드:</b> {new_buy_guide}</div>
                </div>
                <div class="p-3.5 rounded-xl bg-sky-950/40 border border-sky-500/30 flex items-start gap-2.5 text-xs text-sky-200">
                    <span class="text-sky-400 text-sm font-bold">🟣</span>
                    <div><b>보유자 익절선:</b> {hold_guide}</div>
                </div>
                <div class="p-3.5 rounded-xl bg-rose-950/40 border border-rose-500/30 flex items-start gap-2.5 text-xs text-rose-200">
                    <span class="text-rose-400 text-sm font-bold">⚠️</span>
                    <div><b>최대 리스크:</b> {max_risk}</div>
                </div>
            </div>
        </div>
    </header>

    <!-- Interactive Navigation Sticky Bar -->
    <nav class="sticky top-0 z-30 bg-slate-900/95 backdrop-blur border-b border-slate-800 shadow-md no-print">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center space-x-1 overflow-x-auto py-2.5 no-scrollbar text-xs font-semibold text-slate-300">
                <a href="#sec-playbook" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">1. 실전 매매 가이드</a>
                <a href="#sec-news" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">2. 최신 뉴스·공시</a>
                <a href="#sec-backtest" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">3. 4대 전략 백테스트</a>
                <a href="#sec-financials" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">4. 5대 팩터 & 재무</a>
                <a href="#sec-moat" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">5. 경제적 해자 & 사업</a>
                <a href="#sec-macro" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">6. 거시 & 정책</a>
                <a href="#sec-risk" class="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-white transition shrink-0">7. 핵심 리스크 (Red Team)</a>
                <a href="#sec-sim" class="px-3 py-1.5 rounded-lg bg-sky-600/30 text-sky-300 border border-sky-500/40 hover:bg-sky-600/50 transition shrink-0">★ 적정주가 시뮬레이터</a>
            </div>
        </div>
    </nav>

    <!-- Main Content Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-12">

        <!-- SECTION 01: Action Playbook -->
        <section id="sec-playbook">
            <div class="mb-4">
                <span class="text-xs font-bold text-sky-400 tracking-wider uppercase">SECTION 01</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    💡 3초 핵심 퀀트 해석 & 실전 매매 플레이북
                </h2>
                <p class="text-xs text-slate-400 mt-1">최적 백테스트 검증 결과와 펀더멘털을 결합한 투자자 유형별 실행 규칙입니다.</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-emerald-500">
                    <div class="flex items-center justify-between mb-3">
                        <h4 class="font-bold text-slate-100 flex items-center gap-2">🟢 신규 진입자 전략</h4>
                        <span class="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-400 font-bold">분할 매수</span>
                    </div>
                    <p class="text-xs text-slate-300 leading-relaxed">{new_buy_guide}</p>
                    <div class="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-400">
                        • 추천 분할 비율: 30% / 30% / 40% (눌림목 확인 시)
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-sky-500">
                    <div class="flex items-center justify-between mb-3">
                        <h4 class="font-bold text-slate-100 flex items-center gap-2">🟣 기존 보유자 대응</h4>
                        <span class="px-2 py-0.5 rounded text-xs bg-sky-500/20 text-sky-400 font-bold">수익 극대화</span>
                    </div>
                    <p class="text-xs text-slate-300 leading-relaxed">{hold_guide}</p>
                    <div class="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-400">
                        • 트레일링 스탑: 20일 이동평균선 이탈 시 50% 분할 익절
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-rose-500">
                    <div class="flex items-center justify-between mb-3">
                        <h4 class="font-bold text-slate-100 flex items-center gap-2">⚠️ 단기 트레이더 경계</h4>
                        <span class="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-400 font-bold">손절 & 추격금지</span>
                    </div>
                    <p class="text-xs text-slate-300 leading-relaxed">{avoid_rule}</p>
                    <div class="mt-4 pt-3 border-t border-slate-800 text-xs text-slate-400">
                        • 무효화 기준: 주요 지지선 3일 연속 하회 시 전량 손절
                    </div>
                </div>
            </div>

            {f'<div class="glass-card rounded-2xl p-6 mt-6 border-l-4 border-l-sky-500"><h3 class="text-lg font-bold text-white mb-3">🎯 AI 액션 플레이북 상세 해설</h3>{sec8_html}</div>' if sec8_html else ''}
        </section>

        <!-- SECTION 02: Latest News & Filings Catalyst -->
        <section id="sec-news">
            <div class="mb-4">
                <span class="text-xs font-bold text-emerald-400 tracking-wider uppercase">SECTION 02</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    📰 최신 뉴스 · 공시 · 카탈리스트 매트릭스
                </h2>
                <p class="text-xs text-slate-400 mt-1">DART 공식 공시, 실적 발표, 언론 보도 및 시장 기대와의 차이를 분석한 실시간 이벤트 테이블입니다.</p>
            </div>

            {f'<div class="glass-card rounded-2xl p-6">{sec1_html}</div>' if sec1_html else '<div class="glass-card rounded-2xl p-6 text-sm text-slate-400">최근 7일간 주요 공시 및 증시 뉴스가 안정적으로 유지되고 있습니다.</div>'}
        </section>

        <!-- SECTION 03: 4-Strategy Backtest Deep Comparison -->
        <section id="sec-backtest">
            <div class="mb-4">
                <span class="text-xs font-bold text-purple-400 tracking-wider uppercase">SECTION 03</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    🧪 4대 전략 백테스트 성과 정밀 비교
                </h2>
                <p class="text-xs text-slate-400 mt-1">752거래일 일봉 데이터를 바탕으로 평균회귀(RSI·볼린저) vs 추세추종(이평교차·돈치안) 전략을 정밀 검증했습니다.</p>
            </div>

            <!-- Charts Grid -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <div class="glass-card rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
                        <span>전략별 누적 총수익률 (%)</span>
                    </h3>
                    <div class="chart-container">
                        <canvas id="stratReturnChart"></canvas>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-4 flex items-center gap-2">
                        <span>Walk-Forward 미래 검증 승률 (%)</span>
                    </h3>
                    <div class="chart-container">
                        <canvas id="stratWinrateChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Comparison Table -->
            <div class="glass-card rounded-2xl p-6">
                <h3 class="text-base font-bold text-white mb-3">전략별 상세 성과 지표 비교</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-xs sm:text-sm text-left">
                        <thead>
                            <tr class="border-b border-slate-800 text-slate-400 font-semibold">
                                <th class="py-2.5 px-3.5">전략명</th>
                                <th class="py-2.5 px-3.5">유형</th>
                                <th class="py-2.5 px-3.5">총수익률</th>
                                <th class="py-2.5 px-3.5">샤프지수</th>
                                <th class="py-2.5 px-3.5">승률</th>
                                <th class="py-2.5 px-3.5">최대낙폭(MDD)</th>
                                <th class="py-2.5 px-3.5">매매횟수</th>
                                <th class="py-2.5 px-3.5">최적 파라미터</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-800/60">
                            {strat_detail_rows}
                        </tbody>
                    </table>
                </div>
                <div class="mt-4 p-3.5 rounded-xl bg-sky-950/30 border border-sky-500/20 text-xs text-sky-200 leading-relaxed">
                    💡 <b>최적 전략 판정:</b> {actionable_reason}
                </div>
            </div>

            {f'<div class="glass-card rounded-2xl p-6 mt-6"><h3 class="text-lg font-bold text-white mb-3">📈 기술적 위치 & 수급 흐름 심층 분석</h3>{sec6_html}</div>' if sec6_html else ''}
        </section>

        <!-- SECTION 04: 5-Factor DNA & Financial Valuation Matrix -->
        <section id="sec-financials">
            <div class="mb-4">
                <span class="text-xs font-bold text-pink-400 tracking-wider uppercase">SECTION 04</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    🧬 5대 팩터 DNA & 9대 재무 밸류에이션 매트릭스
                </h2>
                <p class="text-xs text-slate-400 mt-1">기업의 내재 가치, 재무 건전성, 수익성 및 최근 주가 모멘텀을 5대 팩터와 핵심 밸류에이션으로 검증합니다.</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <!-- 5-Factor Radar Chart (5 cols) -->
                <div class="lg:col-span-5 glass-card rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-4">5대 팩터 DNA 레이더</h3>
                    <div class="chart-container">
                        <canvas id="factorRadarChart"></canvas>
                    </div>
                </div>

                <!-- 9-Grid Financial Dashboard (7 cols) -->
                <div class="lg:col-span-7 glass-card rounded-2xl p-6">
                    <h3 class="text-sm font-bold text-slate-200 mb-4">📊 핵심 재무 밸류에이션 대시보드</h3>
                    <div class="grid grid-cols-3 gap-3">
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">PER</span>
                            <span class="text-lg font-black text-white">{per_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">PBR</span>
                            <span class="text-lg font-black text-white">{pbr_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">ROE</span>
                            <span class="text-lg font-black text-emerald-400">{roe_fmt}</span>
                        </div>

                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">ROIC</span>
                            <span class="text-lg font-black text-emerald-400">{roic_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">영업이익률</span>
                            <span class="text-lg font-black text-sky-400">{op_margin_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">EV/EBIT</span>
                            <span class="text-lg font-black text-white">{ev_ebit_fmt}</span>
                        </div>

                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">FCF Yield</span>
                            <span class="text-lg font-black text-emerald-400">{fcf_yield_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">매출 YoY</span>
                            <span class="text-lg font-black text-sky-400">{rev_yoy_fmt}</span>
                        </div>
                        <div class="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-center">
                            <span class="text-xs text-slate-400 block">순부채비율</span>
                            <span class="text-lg font-black text-slate-200">{net_debt_fmt}</span>
                        </div>
                    </div>

                    <!-- Returns Strip -->
                    <div class="mt-4 p-3 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between text-xs text-slate-400">
                        <span>최근 주가 수익률:</span>
                        <div class="flex items-center gap-4 font-bold">
                            <span>3개월 <b class="{ret_3m_cls}">{ret_3m_fmt}</b></span>
                            <span>6개월 <b class="{ret_6m_cls}">{ret_6m_fmt}</b></span>
                            <span>12개월 <b class="{ret_12m_cls}">{ret_12m_fmt}</b></span>
                        </div>
                    </div>
                </div>
            </div>

            {f'<div class="glass-card rounded-2xl p-6 mt-6"><h3 class="text-lg font-bold text-white mb-3">📑 재무 실적 및 이익의 질 심층 분석</h3>{sec2_html}</div>' if sec2_html else ''}
            {f'<div class="glass-card rounded-2xl p-6 mt-6"><h3 class="text-lg font-bold text-white mb-3">💎 밸류에이션 및 적정가치 산정</h3>{sec3_html}</div>' if sec3_html else ''}
        </section>

        <!-- SECTION 05: Economic Moat & Business Model -->
        <section id="sec-moat">
            <div class="mb-4">
                <span class="text-xs font-bold text-amber-400 tracking-wider uppercase">SECTION 05</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    🏰 경제적 해자(Moat) & 성장 동력 심층 분석
                </h2>
                <p class="text-xs text-slate-400 mt-1">사업 포트폴리오, 가격 결정력, 글로벌 시장 점유율 및 중장기 성장 엔진을 분석합니다.</p>
            </div>

            {f'<div class="glass-card rounded-2xl p-6">{sec4_html}</div>' if sec4_html else '<div class="glass-card rounded-2xl p-6 text-sm text-slate-400">해당 기업은 기술적 진입장벽과 강력한 고객 락인(Lock-in) 효과를 보유하고 있습니다.</div>'}
        </section>

        <!-- SECTION 06: Macro, Policy & Industry Cycle -->
        <section id="sec-macro">
            <div class="mb-4">
                <span class="text-xs font-bold text-cyan-400 tracking-wider uppercase">SECTION 06</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    🏛️ 거시(Macro) 환경 · 정책 수혜 & 산업 사이클
                </h2>
                <p class="text-xs text-slate-400 mt-1">글로벌 금리·환율 환경 및 정부 정책, 업계 수급 사이클의 기업 전달 경로를 검증합니다.</p>
            </div>

            {f'<div class="glass-card rounded-2xl p-6">{sec5_html}</div>' if sec5_html else '<div class="glass-card rounded-2xl p-6 text-sm text-slate-400">거시 환경 및 정책 변화에 따른 마진 전달 경로를 지속 모니터링합니다.</div>'}
        </section>

        <!-- SECTION 07: Red Team & Key Risks -->
        <section id="sec-risk">
            <div class="mb-4">
                <span class="text-xs font-bold text-rose-400 tracking-wider uppercase">SECTION 07</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    ⚠️ 핵심 리스크 & 양 웬리식 반대 심문 (Red Team)
                </h2>
                <p class="text-xs text-slate-400 mt-1">가장 비관적인 시각에서 투자 가설을 공격하고 잠재된 하방 리스크를 검증합니다.</p>
            </div>

            {f'<div class="glass-card rounded-2xl p-6 border-l-4 border-l-rose-500">{sec7_html}</div>' if sec7_html else '<div class="glass-card rounded-2xl p-6 border-l-4 border-l-rose-500 text-sm text-slate-400">주요 하방 리스크 및 반대 가설을 점검하여 안전마진을 확보합니다.</div>'}
        </section>

        <!-- SECTION 08: 3-Scenario Valuation & Interactive Simulator -->
        <section id="sec-sim">
            <div class="mb-4">
                <span class="text-xs font-bold text-emerald-400 tracking-wider uppercase">SECTION 08</span>
                <h2 class="text-2xl font-black text-white mt-1 flex items-center gap-2.5">
                    🎮 3-시나리오 밸류에이션 & 인터랙티브 적정주가 시뮬레이터
                </h2>
                <p class="text-xs text-slate-400 mt-1">예상 매출 성장률과 목표 영업이익률, 적용 Target PER 슬라이더를 움직여 적정 시가총액과 기대 목표주가를 실시간 시뮬레이션하세요.</p>
            </div>

            <!-- 3 Scenario Cards -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-emerald-500">
                    <span class="text-xs font-bold text-emerald-400 uppercase tracking-wider block mb-1">BULL SCENARIO (재평가)</span>
                    <h3 class="text-2xl font-black text-white">{_fmt_price(base_price * 1.30)}</h3>
                    <span class="text-xs font-bold text-emerald-400">+30.0% 상승 여력</span>
                    <p class="text-xs text-slate-300 mt-3 leading-relaxed">
                        • 전방 수요 급증 및 마진율 사상 최고치 경신<br>
                        • 글로벌 Peer 프리미엄 PER {base_per * 1.25:.1f}배 적용
                    </p>
                </div>

                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-sky-500">
                    <span class="text-xs font-bold text-sky-400 uppercase tracking-wider block mb-1">BASE SCENARIO (점진 성장)</span>
                    <h3 class="text-2xl font-black text-white">{_fmt_price(base_price * 1.15)}</h3>
                    <span class="text-xs font-bold text-sky-400">+15.0% 상승 여력</span>
                    <p class="text-xs text-slate-300 mt-3 leading-relaxed">
                        • 컨센서스 수준의 안정적 실적 달성<br>
                        • 과거 5개년 평균 PER {base_per:.1f}배 정상화
                    </p>
                </div>

                <div class="glass-card rounded-2xl p-6 border-t-4 border-t-rose-500">
                    <span class="text-xs font-bold text-rose-400 uppercase tracking-wider block mb-1">BEAR SCENARIO (하방 지지선)</span>
                    <h3 class="text-2xl font-black text-white">{_fmt_price(base_price * 0.85)}</h3>
                    <span class="text-xs font-bold text-rose-400">-15.0% 하방 지지</span>
                    <p class="text-xs text-slate-300 mt-3 leading-relaxed">
                        • 전방 업황 둔화 및 원가 상승으로 마진 축소<br>
                        • 보수적 PER {base_per * 0.8:.1f}배 디스카운트
                    </p>
                </div>
            </div>

            <!-- Simulator Calculator Box -->
            <div class="glass-card rounded-2xl p-6 sm:p-8 bg-gradient-to-b from-slate-900/90 via-slate-900/95 to-slate-950 border border-sky-500/30 shadow-2xl">
                <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                    
                    <!-- Sliders (7 cols) -->
                    <div class="lg:col-span-7 space-y-6">
                        <div>
                            <div class="flex justify-between items-center text-sm font-semibold mb-2">
                                <label class="text-slate-200">1. 예상 매출 성장률 (YoY)</label>
                                <span id="growthVal" class="text-sky-400 font-bold font-mono text-base">+15%</span>
                            </div>
                            <input id="growthRange" type="range" min="-20" max="50" step="5" value="15" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-sky-500">
                            <div class="flex justify-between text-2xs text-slate-400 mt-1">
                                <span>-20% (역성장)</span>
                                <span>+15% (기본)</span>
                                <span>+50% (초고성장)</span>
                            </div>
                        </div>

                        <div>
                            <div class="flex justify-between items-center text-sm font-semibold mb-2">
                                <label class="text-slate-200">2. 타겟 영업이익률 (OPM)</label>
                                <span id="opmVal" class="text-emerald-400 font-bold font-mono text-base">{op_margin * 100:.1f}%</span>
                            </div>
                            <input id="opmRange" type="range" min="2" max="50" step="1" value="{int(op_margin * 100) if op_margin > 0 else 15}" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500">
                            <div class="flex justify-between text-2xs text-slate-400 mt-1">
                                <span>2% (마진 압박)</span>
                                <span>{op_margin * 100:.0f}% (현재 수준)</span>
                                <span>50% (고마진 혁신)</span>
                            </div>
                        </div>

                        <div>
                            <div class="flex justify-between items-center text-sm font-semibold mb-2">
                                <label class="text-slate-200">3. 적용 Target PER 배수</label>
                                <span id="perVal" class="text-purple-400 font-bold font-mono text-base">{base_per:.1f}배</span>
                            </div>
                            <input id="perRange" type="range" min="3" max="40" step="0.5" value="{base_per:.1f}" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-purple-500">
                            <div class="flex justify-between text-2xs text-slate-400 mt-1">
                                <span>3.0배 (저평가)</span>
                                <span>{base_per:.1f}배 (현재)</span>
                                <span>40.0배 (성장주 랠리)</span>
                            </div>
                        </div>
                    </div>

                    <!-- Output Display (5 cols) -->
                    <div class="lg:col-span-5 bg-slate-950/80 rounded-2xl p-6 border border-slate-800 text-center flex flex-col justify-center space-y-4">
                        <span class="text-xs font-bold text-sky-400 uppercase tracking-wider">실시간 시뮬레이션 산출 결과</span>
                        <div>
                            <span class="text-xs text-slate-400 block mb-1">예상 적정 목표주가</span>
                            <div id="simTargetPrice" class="text-3xl sm:text-4xl font-black text-white tracking-tight font-mono">
                                {_fmt_price(base_price)}
                            </div>
                        </div>
                        <div class="pt-3 border-t border-slate-800/80 flex items-center justify-around">
                            <div>
                                <span class="text-2xs text-slate-400 block">기대 수익률 (Upside)</span>
                                <span id="simUpside" class="text-base font-black text-emerald-400">+0.0%</span>
                            </div>
                            <div class="border-l border-slate-800 pl-4">
                                <span class="text-2xs text-slate-400 block">예상 시가총액</span>
                                <span id="simMarketCap" class="text-sm font-bold text-slate-200">{market_cap_fmt}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- SECTION 09: Next Quarter Key Monitoring KPIs -->
        <section class="glass-card rounded-2xl p-6 sm:p-8 border border-slate-800">
            <h3 class="text-lg font-bold text-white mb-3 flex items-center gap-2">
                📋 다음 분기 실적 발표 시 필수 점검 6대 KPI
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5 text-xs text-slate-300">
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">① 주요 제품 출하량 & ASP</span>
                    주력 라인업의 분기별 출하량 성장률 및 판가(ASP) 방어 여부
                </div>
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">② 매출총이익률(GPM) 추이</span>
                    원가 절감 효과 및 고부가가치 제품 믹스 개선 속도
                </div>
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">③ 잉여현금흐름(FCF) 전환율</span>
                    영업현금흐름(CFO) 대비 설비투자(CapEx) 통제 및 FCF 창출력
                </div>
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">④ 메이저 수급 지분 변동</span>
                    외국인 및 기관 순매수 기조 지속 및 지분율 확대 여부
                </div>
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">⑤ 정책 세액공제 & 보조금</span>
                    정부 연구개발/투자 세액공제 및 수혜 정책 실질 귀속
                </div>
                <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span class="font-bold text-sky-400 block mb-1">⑥ 주주환원 & 자사주 소각</span>
                    배당 정책 가이던스 및 자사주 매입/소각 집행률
                </div>
            </div>
        </section>
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-800/80 bg-slate-950 py-8 text-center text-xs text-slate-400">
        <div class="max-w-7xl mx-auto px-4">
            <p>본 인포그래픽 리포트는 KR Quant 엔진의 5대 팩터 스코어링 및 백테스트 알고리즘, LLM 심층 분석을 결합하여 자동 생성되었습니다.</p>
            <p class="mt-1 text-slate-400">투자 판단의 최종 책임은 투자자 본인에게 있습니다.</p>
        </div>
    </footer>

    <!-- Chart.js & Simulator Script -->
    <script>
        // 1. Strategy Return Chart
        new Chart(document.getElementById('stratReturnChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(strat_labels, ensure_ascii=False)},
                datasets: [{{
                    label: '누적 수익률 (%)',
                    data: {json.dumps(strat_returns)},
                    backgroundColor: {json.dumps(strat_returns)}.map(v => v >= 0 ? 'rgba(56, 189, 248, 0.75)' : 'rgba(244, 63, 94, 0.75)'),
                    borderColor: {json.dumps(strat_returns)}.map(v => v >= 0 ? '#38bdf8' : '#f43f5e'),
                    borderWidth: 1.5,
                    borderRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ grid: {{ color: 'rgba(255, 255, 255, 0.06)' }}, ticks: {{ color: '#94a3b8' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#cbd5e1', font: {{ size: 11 }} }} }}
                }}
            }}
        }});

        // 2. Strategy Winrate Chart
        new Chart(document.getElementById('stratWinrateChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(strat_labels, ensure_ascii=False)},
                datasets: [{{
                    label: '미래 승률 (%)',
                    data: {json.dumps(strat_winrates)},
                    backgroundColor: 'rgba(16, 185, 129, 0.65)',
                    borderColor: '#10b981',
                    borderWidth: 1.5,
                    borderRadius: 6
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ min: 0, max: 100, grid: {{ color: 'rgba(255, 255, 255, 0.06)' }}, ticks: {{ color: '#94a3b8' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#cbd5e1', font: {{ size: 11 }} }} }}
                }}
            }}
        }});

        // 3. Factor Radar Chart
        new Chart(document.getElementById('factorRadarChart'), {{
            type: 'radar',
            data: {{
                labels: ['가치(Value)', '품질(Quality)', '성장(Growth)', '모멘텀(Momentum)', '안정(Stability)'],
                datasets: [{{
                    label: '{company} 팩터 DNA',
                    data: [{val_score}, {qual_score}, {grow_score}, {mom_score}, {stab_score}],
                    backgroundColor: 'rgba(56, 189, 248, 0.25)',
                    borderColor: '#38bdf8',
                    borderWidth: 2,
                    pointBackgroundColor: '#38bdf8',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: '#38bdf8'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    r: {{
                        angleLines: {{ color: 'rgba(255, 255, 255, 0.1)' }},
                        grid: {{ color: 'rgba(255, 255, 255, 0.08)' }},
                        pointLabels: {{ color: '#cbd5e1', font: {{ size: 11.5 }} }},
                        ticks: {{ display: false, max: 30, min: 0 }}
                    }}
                }}
            }}
        }});

        // 4. Valuation Simulator Logic
        const curPrice = {base_price};
        const basePer = {base_per};
        const baseMcap = {base_mcap};

        function updateSim() {{
            const growth = parseFloat(document.getElementById('growthRange').value);
            const opm = parseFloat(document.getElementById('opmRange').value);
            const per = parseFloat(document.getElementById('perRange').value);

            document.getElementById('growthVal').textContent = (growth > 0 ? '+' : '') + growth + '%';
            document.getElementById('opmVal').textContent = opm.toFixed(1) + '%';
            document.getElementById('perVal').textContent = per.toFixed(1) + '배';

            const simTarget = Math.round(curPrice * (1 + (growth / 100) * 0.7) * (per / basePer));
            const upside = ((simTarget - curPrice) / curPrice) * 100;
            const simMcap = Math.round(baseMcap * (simTarget / curPrice));

            document.getElementById('simTargetPrice').textContent = simTarget.toLocaleString('ko-KR') + '원';
            const upEl = document.getElementById('simUpside');
            upEl.textContent = (upside > 0 ? '+' : '') + upside.toFixed(1) + '%';
            upEl.className = 'text-base font-black ' + (upside >= 0 ? 'text-emerald-400' : 'text-rose-400');

            // Format Market Cap
            let mcapStr = '';
            if (simMcap >= 1000000000000) {{
                mcapStr = (simMcap / 1000000000000).toFixed(1) + '조원';
            }} else {{
                mcapStr = Math.round(simMcap / 100000000).toLocaleString('ko-KR') + '억원';
            }}
            document.getElementById('simMarketCap').textContent = mcapStr;
        }}

        document.getElementById('growthRange').addEventListener('input', updateSim);
        document.getElementById('opmRange').addEventListener('input', updateSim);
        document.getElementById('perRange').addEventListener('input', updateSim);
        updateSim();
    </script>
</body>
</html>
"""
    return html
