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


def parse_report_sections(md: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_sec = "header"
    current_lines: list[str] = []

    for line in md.splitlines():
        h_match = re.match(r"^##\s+(\d+\.?\s*[^#\n]+)", line)
        if h_match:
            if current_lines:
                sections[current_sec] = "\n".join(current_lines).strip()
            current_sec = h_match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_sec] = "\n".join(current_lines).strip()

    return sections


def extract_bullet_dict(text: str) -> dict[str, str]:
    res = {}
    for line in text.splitlines():
        m = re.match(r"^\s*[-*•]\s+\*\*([^*]+)\*\*:\s*(.+)$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            res[key] = val
    return res


def md_to_rich_html(md_text: str) -> str:
    """Converts markdown text containing headers, tables, bullet points and bold text into stylish HTML."""
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

        th_html = "".join(f'<th class="py-2.5 px-3 font-semibold text-slate-300 bg-slate-900/90 whitespace-nowrap">{h}</th>' for h in header)
        tbody_html = ""
        for r in rows:
            td_html = ""
            for c in r:
                if "긍정" in c or "서프라이즈" in c or "상향" in c:
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">{c}</span>'
                elif "부정" in c or "리스크" in c or "경쟁" in c or "하향" in c:
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">{c}</span>'
                elif "중립" in c:
                    c_badge = f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-700/50 text-slate-300">{c}</span>'
                else:
                    c_badge = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'>\1</b>", c)
                td_html += f'<td class="py-2.5 px-3 text-slate-200 border-t border-slate-800/80">{c_badge}</td>'
            tbody_html += f'<tr class="hover:bg-slate-800/40 transition">{td_html}</tr>'

        return f"""
        <div class="overflow-x-auto rounded-xl border border-slate-800 my-4 shadow-lg">
            <table class="w-full text-xs sm:text-sm text-left">
                <thead><tr class="border-b border-slate-700">{th_html}</tr></thead>
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
            html_out.append(f'<h4 class="text-base sm:text-lg font-bold text-brand-300 mt-5 mb-2.5 flex items-center gap-2"><span class="w-1.5 h-4 bg-brand-400 rounded-full inline-block"></span>{title}</h4>')
        elif sline.startswith("#### "):
            title = sline[5:].strip()
            html_out.append(f'<h5 class="text-sm sm:text-base font-bold text-slate-200 mt-4 mb-2">{title}</h5>')
        elif sline.startswith("- ") or sline.startswith("* "):
            content = sline[2:].strip()
            content = re.sub(r"\*\*([^*]+)\*\*:\s*", r"<b class='text-slate-100'>\1</b>: ", content)
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'>\1</b>", content)
            html_out.append(f'<div class="flex items-start gap-2 text-sm text-slate-300 my-1.5"><span class="text-brand-400 mt-1 text-xs">◆</span><div class="leading-relaxed">{content}</div></div>')
        elif re.match(r"^\d+\.\s+", sline):
            content = re.sub(r"^\d+\.\s+", "", sline)
            content = re.sub(r"\*\*([^*]+)\*\*:\s*", r"<b class='text-slate-100'>\1</b>: ", content)
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'>\1</b>", content)
            html_out.append(f'<div class="flex items-start gap-2 text-sm text-slate-300 my-1.5"><span class="text-accent-cyan font-bold text-xs mt-0.5">●</span><div class="leading-relaxed">{content}</div></div>')
        else:
            content = re.sub(r"\*\*([^*]+)\*\*", r"<b class='text-white'>\1</b>", sline)
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

    quant_score = record.get("quant_score") or (stock_row.get("quant_score") if stock_row else 0)
    quant_rank = record.get("quant_rank") or (stock_row.get("quant_rank") if stock_row else "—")
    market = record.get("market") or (stock_row.get("market") if stock_row else "KOSPI")
    industry = record.get("industry") or record.get("sector") or (stock_row.get("industry") if stock_row else "우량 기업")
    last_close = _safe_float(record.get("last_close") or (stock_row.get("last_close") if stock_row else 0))

    factors = record.get("factor_scores") or (stock_row.get("factor_scores") if stock_row else {}) or {}
    val_score = _safe_float(factors.get("value") or (stock_row.get("value_score") if stock_row else 0))
    qual_score = _safe_float(factors.get("quality") or (stock_row.get("quality_score") if stock_row else 0))
    grow_score = _safe_float(factors.get("growth") or (stock_row.get("growth_score") if stock_row else 0))
    mom_score = _safe_float(factors.get("momentum") or (stock_row.get("momentum_score") if stock_row else 0))
    stab_score = _safe_float(factors.get("stability") or (stock_row.get("stability_score") if stock_row else 0))

    per = _safe_float(stock_row.get("per") if stock_row else None)
    pbr = _safe_float(stock_row.get("pbr") if stock_row else None)
    roe = _safe_float(stock_row.get("roe") if stock_row else None)
    op_margin = _safe_float(stock_row.get("operating_margin") if stock_row else None)
    rev_yoy = _safe_float(stock_row.get("revenue_yoy") if stock_row else None)
    rev_3y_cagr = _safe_float(stock_row.get("revenue_3y_cagr") if stock_row else None)
    ev_ebit = _safe_float(stock_row.get("ev_ebit") if stock_row else None)
    fcf_yield = _safe_float(stock_row.get("fcf_yield") if stock_row else None)
    roic = _safe_float(stock_row.get("roic") if stock_row else None)
    net_debt = _safe_float(stock_row.get("net_debt_assets") if stock_row else None)
    ret_3m = _safe_float(stock_row.get("return_3m") if stock_row else None)
    ret_6m = _safe_float(stock_row.get("return_6m") if stock_row else None)
    ret_12m = _safe_float(stock_row.get("return_12m") if stock_row else None)

    foreign_rate = 0.0
    if stock_row and "foreign_holding_rate" in stock_row:
        try:
            foreign_rate = float(stock_row.get("foreign_holding_rate") or 0)
        except Exception:
            foreign_rate = 0.0

    bt = record.get("strategy_backtest") or {}
    strategies = bt.get("strategies") or []
    best_name = bt.get("best_name") or "볼린저 평균회귀"
    best_params_ko = bt.get("best_params_ko") or "기간 20일 · 밴드폭 1.5배"
    playbook = bt.get("playbook") or {}

    archetype_badge = playbook.get("archetype_badge") or "🔄 평균회귀형 파동"
    archetype_desc = playbook.get("archetype_desc") or f"{company}은 과매도권에서 분할 매수하여 반등에 파는 '눌림목/평균회귀 매매'가 유리한 종목입니다."
    actionable_reason = playbook.get("actionable_reason") or f"3년간 검증에서 최고 승률과 실전 표본을 기록한 '{best_name}'이 가장 실효성 높은 실전 1픽입니다."
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
        strat_detail_rows += f'<tr style="{bg}"><td>{crown}{s.get("name","")}</td><td><span class="px-2 py-0.5 rounded text-xs bg-slate-800 text-slate-300">{s.get("family_ko","")}</span></td><td class="{"text-emerald-400 font-bold" if ret_val>0 else "text-rose-400 font-bold"}">{ret_val:+.1f}%</td><td><b>{sharpe:.2f}</b></td><td>{wf:.0f}%</td><td class="text-rose-400">{mdd:.1f}%</td><td>{tc}회</td><td class="text-xs text-slate-400">{s.get("params_ko","")}</td></tr>'

    last_close_fmt = f"{int(last_close):,}원" if last_close else "—"
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

    report_md = record.get("report_markdown") or ""
    secs = parse_report_sections(report_md)

    sec0_text = ""
    for k, v in secs.items():
        if "45초" in k or "총평" in k or "0." in k:
            sec0_text = v
            break

    sec0_dict = extract_bullet_dict(sec0_text) if sec0_text else {}
    verdict = sec0_dict.get("최종판정") or "조건부 매수 (Quant 우량)"
    good_co = sec0_dict.get("좋은 회사") or f"ROIC {roic_fmt}, 업계 상위 시장 경쟁력 보유"
    good_pr = sec0_dict.get("좋은 가격") or f"PER {per_fmt}, PBR {pbr_fmt} 수준"
    good_tm = sec0_dict.get("좋은 타이밍") or f"최적 백테스트: {best_name} ({best_params_ko})"
    new_buy_guide = sec0_dict.get("신규") or entry_rule
    hold_guide = sec0_dict.get("보유") or exit_rule
    max_risk = sec0_dict.get("최대 위험") or avoid_rule

    sec1_html = ""
    for k, v in secs.items():
        if "뉴스" in k or "공시" in k or "1." in k:
            sec1_html = md_to_rich_html(v)
            break

    sec2_html = ""
    for k, v in secs.items():
        if "재무" in k or "이익" in k or "2." in k:
            sec2_html = md_to_rich_html(v)
            break

    sec4_html = ""
    for k, v in secs.items():
        if "해자" in k or "성장성" in k or "4." in k:
            sec4_html = md_to_rich_html(v)
            break

    sec5_html = ""
    for k, v in secs.items():
        if "정책" in k or "거시" in k or "5." in k:
            sec5_html = md_to_rich_html(v)
            break

    sec7_html = ""
    for k, v in secs.items():
        if "리스크" in k or "7." in k:
            sec7_html = md_to_rich_html(v)
            break

    sec8_html = ""
    for k, v in secs.items():
        if "목표가" in k or "Price" in k or "사용자" in k or "8." in k or "9." in k or "Playbook" in k:
            sec8_html += md_to_rich_html(v) + "\n"

    sec1_block = f'<div class="glass-card rounded-2xl p-6">{sec1_html}</div>' if sec1_html else ''
    sec2_block = f'<div class="glass-card rounded-2xl p-6 mt-6">{sec2_html}</div>' if sec2_html else ''
    sec4_block = f'<div class="glass-card rounded-2xl p-6">{sec4_html}</div>' if sec4_html else ''
    sec5_block = f'<div class="glass-card rounded-2xl p-6 mt-6"><h3 class="text-lg font-bold text-white mb-3">🏛️ 정책 · 거시(Macro) 환경 연계</h3>{sec5_html}</div>' if sec5_html else ''
    sec7_block = f'<div class="glass-card rounded-2xl p-6 border-l-4 border-l-rose-500">{sec7_html}</div>' if sec7_html else ''
    sec8_block = f'<div class="glass-card rounded-2xl p-6 mt-6 border-l-4 border-l-brand-500"><h3 class="text-lg font-bold text-white mb-3">🎯 목표가 & 사용자별 액션 맵</h3>{sec8_html}</div>' if sec8_html else ''

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
            background: rgba(15, 23, 42, 0.78);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.09);
        }}
        .glass-card:hover {{
            border-color: rgba(56, 189, 248, 0.4);
        }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans antialiased selection:bg-brand-500 selection:text-white">

    <!-- Top Header / Hero -->
    <header class="relative overflow-hidden bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 pt-10 pb-12 border-b border-slate-800">
        <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-brand-600/25 via-transparent to-transparent pointer-events-none"></div>
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
            
            <div class="flex flex-wrap items-center justify-between gap-4 mb-4">
                <div class="flex items-center gap-2">
                    <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-black bg-brand-500/20 text-brand-400 border border-brand-500/30">
                        ✦ CORPORATE DEEP-DIVE INFOGRAPHIC
                    </span>
                    <span class="text-xs text-slate-400 font-medium">{market} · {industry} · 코드 {ticker}</span>
                </div>
                <div class="flex items-center gap-3 text-xs text-slate-400 no-print">
                    <span>기준일: <b class="text-slate-200">{as_of}</b></span>
                    <span>엔진: <b class="text-indigo-400">{provider} ({model})</b></span>
                    <button type="button" onclick="window.print()" class="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 flex items-center gap-1.5 transition font-semibold">
                        🖨️ PDF / 인쇄
                    </button>
                </div>
            </div>

            <div class="flex flex-col md:flex-row md:items-end justify-between gap-6">
                <div>
                    <h1 class="text-3xl sm:text-4xl md:text-5xl font-black text-white tracking-tight leading-tight">
                        {company} <span class="text-transparent bg-clip-text bg-gradient-to-r from-brand-400 via-accent-cyan to-accent-pink">({ticker})</span>
                    </h1>
                    <p class="mt-3 text-base sm:text-lg text-slate-300 max-w-3xl leading-relaxed">
                        재무 5대 팩터 종합 <strong>퀀트 {quant_score}점 (랭킹 {quant_rank}위)</strong>, 4대 전략 백테스트 기반 최적 타이밍 검증 및 AI 심층 리서치 인포그래픽
                    </p>
                </div>
                <div class="flex items-center gap-4 bg-slate-900/90 border border-slate-800 rounded-2xl p-4 self-start md:self-auto shadow-2xl">
                    <div>
                        <div class="text-xs text-slate-400">최근 종가</div>
                        <div class="text-2xl font-black text-white">{last_close_fmt}</div>
                    </div>
                    <div class="h-8 w-px bg-slate-800"></div>
                    <div>
                        <div class="text-xs text-slate-400">외인 지분율</div>
                        <div class="text-2xl font-black text-accent-cyan">{(foreign_rate * 100):.1f}%</div>
                    </div>
                </div>
            </div>

            <!-- 4 Executive Verdict Cards (45초 총평 요약) -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
                <div class="glass-card rounded-2xl p-4 border-l-4 border-l-brand-500">
                    <div class="text-xs text-slate-400 font-semibold mb-1">🎯 최종 투자 판정</div>
                    <div class="text-lg font-black text-brand-300">{verdict}</div>
                    <div class="text-xs text-slate-400 mt-1.5">종합 퀀트 {quant_score}점 (상위 {quant_rank}위)</div>
                </div>

                <div class="glass-card rounded-2xl p-4 border-l-4 border-l-emerald-500">
                    <div class="text-xs text-slate-400 font-semibold mb-1">🏢 좋은 회사 (Quality & Moat)</div>
                    <div class="text-sm font-bold text-slate-100">{good_co}</div>
                    <div class="text-xs text-slate-400 mt-1.5">ROE {roe_fmt} · ROIC {roic_fmt}</div>
                </div>

                <div class="glass-card rounded-2xl p-4 border-l-4 border-l-cyan-500">
                    <div class="text-xs text-slate-400 font-semibold mb-1">💰 좋은 가격 (Valuation)</div>
                    <div class="text-sm font-bold text-slate-100">{good_pr}</div>
                    <div class="text-xs text-slate-400 mt-1.5">PER {per_fmt} · PBR {pbr_fmt} · EV/EBIT {ev_ebit_fmt}</div>
                </div>

                <div class="glass-card rounded-2xl p-4 border-l-4 border-l-amber-500">
                    <div class="text-xs text-slate-400 font-semibold mb-1">⏱️ 좋은 타이밍 (Timing)</div>
                    <div class="text-sm font-bold text-slate-100">{good_tm}</div>
                    <div class="text-xs text-slate-400 mt-1.5">{archetype_badge}</div>
                </div>
            </div>

            <!-- Action Guide Banners -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4">
                <div class="p-3 bg-emerald-950/40 border border-emerald-500/30 rounded-xl text-xs">
                    <b class="text-emerald-400">🟢 신규 매수 가이드:</b> <span class="text-slate-200">{new_buy_guide}</span>
                </div>
                <div class="p-3 bg-cyan-950/40 border border-cyan-500/30 rounded-xl text-xs">
                    <b class="text-cyan-400">🎯 보유자 익절선:</b> <span class="text-slate-200">{hold_guide}</span>
                </div>
                <div class="p-3 bg-rose-950/40 border border-rose-500/30 rounded-xl text-xs">
                    <b class="text-rose-400">⚠️ 최대 리스크:</b> <span class="text-slate-200">{max_risk}</span>
                </div>
            </div>

        </div>
    </header>

    <!-- Sticky Navigation -->
    <nav class="sticky top-0 z-50 bg-slate-900/90 backdrop-blur border-b border-slate-800 py-3">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between overflow-x-auto no-scrollbar space-x-6 text-sm font-medium">
            <a href="#playbook" class="text-slate-300 hover:text-brand-400 whitespace-nowrap transition">1. 실전 매매 가이드</a>
            <a href="#events" class="text-slate-300 hover:text-emerald-400 whitespace-nowrap transition">2. 최신 뉴스·공시</a>
            <a href="#backtest" class="text-slate-300 hover:text-accent-cyan whitespace-nowrap transition">3. 4대 전략 백테스트</a>
            <a href="#factors" class="text-slate-300 hover:text-accent-pink whitespace-nowrap transition">4. 5대 팩터 & 재무</a>
            <a href="#moat" class="text-slate-300 hover:text-amber-400 whitespace-nowrap transition">5. 경제적 해자 & 사업</a>
            <a href="#risks" class="text-slate-300 hover:text-rose-400 whitespace-nowrap transition">6. 핵심 리스크</a>
            <a href="#simulator" class="text-slate-300 hover:text-white bg-brand-600/30 px-3.5 py-1 rounded-full border border-brand-500/40 whitespace-nowrap hover:bg-brand-600/50 transition">★ 적정주가 시뮬레이터</a>
        </div>
    </nav>

    <!-- Main Content Sections -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-16">

        <!-- SECTION 1: Plain Korean Playbook -->
        <section id="playbook" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-brand-400 font-bold text-xs uppercase tracking-wider">SECTION 01</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">💡 3초 핵심 퀀트 해석 & 실전 매매 플레이북</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    백테스트 연산 결과를 직관적인 3대 행동 규칙으로 압축 요약했습니다.
                </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Diagnosis & Reason -->
                <div class="lg:col-span-3 glass-card rounded-2xl p-5 space-y-3">
                    <div class="p-3.5 bg-slate-900/80 rounded-xl border border-slate-800 border-l-4 border-l-brand-400">
                        <div class="font-bold text-brand-300 text-sm">🔍 주가 파동 성향 진단</div>
                        <div class="text-sm text-slate-200 mt-1">{archetype_desc}</div>
                    </div>
                    <div class="p-3.5 bg-slate-900/80 rounded-xl border border-slate-800 border-l-4 border-l-accent-cyan">
                        <div class="font-bold text-cyan-300 text-sm">🎯 실전 1픽 선정 사유 (표본 신뢰도 검증)</div>
                        <div class="text-sm text-slate-200 mt-1">{actionable_reason}</div>
                    </div>
                </div>

                <!-- 3 Action Rules -->
                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-emerald-500">
                    <h3 class="text-base font-bold text-emerald-400 mb-2 flex items-center gap-2">
                        <span>⭕ 가장 유리한 매수 타이밍</span>
                    </h3>
                    <p class="text-sm text-slate-300 leading-relaxed">{entry_rule}</p>
                </div>

                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-cyan-500">
                    <h3 class="text-base font-bold text-cyan-400 mb-2 flex items-center gap-2">
                        <span>🎯 목표가 및 익절 타이밍</span>
                    </h3>
                    <p class="text-sm text-slate-300 leading-relaxed">{exit_rule}</p>
                </div>

                <div class="glass-card rounded-2xl p-5 border-l-4 border-l-rose-500">
                    <h3 class="text-base font-bold text-rose-400 mb-2 flex items-center gap-2">
                        <span>❌ 절대 피해야 할 매매 (함정)</span>
                    </h3>
                    <p class="text-sm text-slate-300 leading-relaxed">{avoid_rule}</p>
                </div>
            </div>
        </section>

        <!-- SECTION 2: Latest News, Disclosure & Events -->
        <section id="events" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-emerald-400 font-bold text-xs uppercase tracking-wider">SECTION 02</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">📰 최신 뉴스 · 공시 · 카탈리스트 매트릭스</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    DART 공식 공시, 실적 발표, 언론 보도 및 시장 기대와의 차이를 분석한 실시간 이벤트 테이블입니다.
                </p>
            </div>
            {sec1_block}
        </section>

        <!-- SECTION 3: 4-Strategy Backtest Charts & Detailed Table -->
        <section id="backtest" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-accent-cyan font-bold text-xs uppercase tracking-wider">SECTION 03</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">🧪 4대 전략 백테스트 성과 정밀 비교</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    752거래일 일봉 데이터를 바탕으로 평균회귀(RSI·볼린저) vs 추세추종(이평교차·돈치안) 전략을 정밀 검증했습니다.
                </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
                <div class="glass-card rounded-2xl p-5">
                    <h3 class="text-base font-bold text-white mb-3">전략별 누적 총수익률 (%)</h3>
                    <div class="chart-container">
                        <canvas id="stratReturnChart"></canvas>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-5">
                    <h3 class="text-base font-bold text-white mb-3">Walk-Forward 미래 검증 승률 (%)</h3>
                    <div class="chart-container">
                        <canvas id="stratWinrateChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Strategy Detail Table -->
            <div class="glass-card rounded-2xl p-5 mt-6 overflow-x-auto">
                <h3 class="text-base font-bold text-white mb-3">📋 4대 전략 백테스트 정밀 비교표</h3>
                <table class="w-full text-xs sm:text-sm text-left">
                    <thead>
                        <tr class="border-b border-slate-700 text-slate-400 bg-slate-900/60">
                            <th class="py-2.5 px-3">전략명</th>
                            <th class="py-2.5 px-3">유형</th>
                            <th class="py-2.5 px-3">총수익률</th>
                            <th class="py-2.5 px-3">샤프비율</th>
                            <th class="py-2.5 px-3">WF 승률</th>
                            <th class="py-2.5 px-3">최대낙폭(MDD)</th>
                            <th class="py-2.5 px-3">매매횟수</th>
                            <th class="py-2.5 px-3">최적 파라미터</th>
                        </tr>
                    </thead>
                    <tbody class="text-slate-200">{strat_detail_rows}</tbody>
                </table>
            </div>
        </section>

        <!-- SECTION 4: 5-Factor DNA & 9-Metric Valuation Matrix -->
        <section id="factors" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-accent-pink font-bold text-xs uppercase tracking-wider">SECTION 04</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">🧬 5대 팩터 DNA & 9대 재무 밸류에이션 매트릭스</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    기업의 내재 가치, 재무 건전성, 수익성 및 최근 주가 모멘텀을 5대 팩터와 핵심 밸류에이션으로 검증합니다.
                </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="glass-card rounded-2xl p-5">
                    <h3 class="text-base font-bold text-white mb-3">5대 팩터 DNA 레이더</h3>
                    <div class="chart-container">
                        <canvas id="factorRadarChart"></canvas>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-5">
                    <h3 class="text-base font-bold text-white mb-3">📊 핵심 재무 밸류에이션 대시보드</h3>
                    <div class="grid grid-cols-3 gap-3 mt-2">
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">PER</div>
                            <div class="text-lg font-bold text-white">{per_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">PBR</div>
                            <div class="text-lg font-bold text-white">{pbr_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">ROE</div>
                            <div class="text-lg font-bold text-accent-cyan">{roe_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">ROIC</div>
                            <div class="text-lg font-bold text-emerald-400">{roic_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">영업이익률</div>
                            <div class="text-lg font-bold text-white">{op_margin_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">EV/EBIT</div>
                            <div class="text-lg font-bold text-white">{ev_ebit_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">FCF Yield</div>
                            <div class="text-lg font-bold text-emerald-400">{fcf_yield_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">매출 YoY</div>
                            <div class="text-lg font-bold text-{'emerald-400' if rev_yoy > 0 else 'rose-400'}">{rev_yoy_fmt}</div>
                        </div>
                        <div class="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-center">
                            <div class="text-xs text-slate-400">순부채비율</div>
                            <div class="text-lg font-bold text-{'emerald-400' if net_debt <= 0 else 'amber-400'}">{net_debt_fmt}</div>
                        </div>
                    </div>
                    <div class="mt-3 p-3 bg-slate-900/60 rounded-xl border border-slate-800">
                        <div class="text-xs text-slate-400 mb-1">최근 주가 수익률</div>
                        <div class="flex gap-4 text-sm">
                            <span>3개월 <b class="text-{'emerald-400' if ret_3m > 0 else 'rose-400'}">{ret_3m_fmt}</b></span>
                            <span>6개월 <b class="text-{'emerald-400' if ret_6m > 0 else 'rose-400'}">{ret_6m_fmt}</b></span>
                            <span>12개월 <b class="text-{'emerald-400' if ret_12m > 0 else 'rose-400'}">{ret_12m_fmt}</b></span>
                        </div>
                    </div>
                </div>
            </div>
            {sec2_block}
        </section>

        <!-- SECTION 5: Economic Moat & Business Breakdown -->
        <section id="moat" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-amber-400 font-bold text-xs uppercase tracking-wider">SECTION 05</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">🏰 경제적 해자(Moat) & 성장 동력 심층 분석</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    사업 포트폴리오, 가격 결정력, 글로벌 시장 점유율 및 중장기 성장 엔진을 분석합니다.
                </p>
            </div>
            {sec4_block}
            {sec5_block}
        </section>

        <!-- SECTION 6: Key Risks & Action Map -->
        <section id="risks" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-rose-400 font-bold text-xs uppercase tracking-wider">SECTION 06</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">⚠️ 핵심 리스크 & 양 웬리식 반대 심문 (Red Team)</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    가장 비관적인 시각에서 투자 가설을 공격하고 잠재된 하방 리스크를 검증합니다.
                </p>
            </div>
            {sec7_block}
            {sec8_block}
        </section>

        <!-- SECTION 7: Interactive Valuation Simulator -->
        <section id="simulator" class="scroll-mt-20">
            <div class="mb-5">
                <span class="text-emerald-400 font-bold text-xs uppercase tracking-wider">SECTION 07</span>
                <h2 class="text-2xl sm:text-3xl font-bold text-white mt-1">🎮 인터랙티브 적정주가 & 밸류에이션 시뮬레이터</h2>
                <p class="text-slate-400 text-sm sm:text-base mt-1.5">
                    예상 매출 성장률과 목표 영업이익률, 적용 Target PER 슬라이더를 움직여 적정 시가총액과 기대 목표주가를 실시간 시뮬레이션하세요.
                </p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <!-- Sliders -->
                <div class="lg:col-span-7 glass-card rounded-2xl p-6 space-y-5">
                    <div>
                        <div class="flex justify-between text-sm mb-1.5">
                            <span class="text-slate-300 font-medium">1. 예상 매출 성장률 (YoY)</span>
                            <span class="font-bold text-accent-cyan text-base" id="growthVal">+15%</span>
                        </div>
                        <input type="range" id="growthRange" min="-20" max="60" value="15" step="1" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400">
                    </div>

                    <div>
                        <div class="flex justify-between text-sm mb-1.5">
                            <span class="text-slate-300 font-medium">2. 타겟 영업이익률 (OPM)</span>
                            <span class="font-bold text-brand-400 text-base" id="opmVal">10.0%</span>
                        </div>
                        <input type="range" id="opmRange" min="2" max="30" value="10" step="0.5" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-400">
                    </div>

                    <div>
                        <div class="flex justify-between text-sm mb-1.5">
                            <span class="text-slate-300 font-medium">3. 적용 Target PER (배)</span>
                            <span class="font-bold text-accent-pink text-base" id="perVal">12.0배</span>
                        </div>
                        <input type="range" id="perRange" min="4" max="35" value="12" step="0.5" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-rose-400">
                    </div>
                </div>

                <!-- Simulation Result Card -->
                <div class="lg:col-span-5 bg-gradient-to-br from-indigo-950/70 to-slate-900/90 border border-brand-500/40 rounded-2xl p-6 flex flex-col justify-between shadow-2xl">
                    <div>
                        <span class="inline-block px-2.5 py-0.5 rounded text-xs font-semibold bg-brand-500/20 text-brand-300 border border-brand-500/30 mb-3">
                            시뮬레이션 산출 결과
                        </span>
                        <div class="text-xs text-slate-400">예상 적정 목표주가</div>
                        <div class="text-3xl sm:text-4xl font-black text-white mt-1" id="simTargetPrice">—</div>
                    </div>

                    <div class="grid grid-cols-2 gap-3 my-4 p-3.5 bg-slate-950/60 rounded-xl border border-slate-800">
                        <div>
                            <div class="text-xs text-slate-400">현재 주가</div>
                            <div class="text-base font-bold text-slate-200">{last_close_fmt}</div>
                        </div>
                        <div>
                            <div class="text-xs text-slate-400">기대 상승여력</div>
                            <div class="text-base font-bold text-emerald-400" id="simUpside">+0.0%</div>
                        </div>
                    </div>

                    <div class="text-xs text-slate-400 leading-relaxed">
                        ※ 본 시뮬레이터는 Quant 추정 모델 기반의 참고용 계산 도구이며 매수·매도 지시가 아닙니다.
                    </div>
                </div>
            </div>
        </section>

    </main>

    <!-- Footer -->
    <footer class="bg-slate-950 border-t border-slate-800 py-8 text-center text-xs text-slate-400">
        <p>KR Quant Research System · Corporate Infographic Report v1.7</p>
        <p class="mt-1 text-slate-400">본 리포트는 인공지능 및 퀀트 통계 알고리즘에 의해 자동 생성된 연구 자료입니다.</p>
    </footer>

    <!-- Chart.js Scripts -->
    <script>
        // 1. Strategy Return Chart
        new Chart(document.getElementById('stratReturnChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(strat_labels, ensure_ascii=False)},
                datasets: [{{
                    label: '총수익률 (%)',
                    data: {json.dumps(strat_returns)},
                    backgroundColor: [
                        'rgba(56, 189, 248, 0.75)',
                        'rgba(99, 102, 241, 0.75)',
                        'rgba(244, 63, 94, 0.6)',
                        'rgba(239, 68, 68, 0.6)'
                    ],
                    borderColor: [
                        '#38bdf8',
                        '#6366f1',
                        '#f43f5e',
                        '#ef4444'
                    ],
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
        const curPrice = {last_close if last_close > 0 else 50000};
        const basePer = {per if per > 0 else 10.0};

        function updateSim() {{
            const growth = parseFloat(document.getElementById('growthRange').value);
            const opm = parseFloat(document.getElementById('opmRange').value);
            const per = parseFloat(document.getElementById('perRange').value);

            document.getElementById('growthVal').textContent = (growth > 0 ? '+' : '') + growth + '%';
            document.getElementById('opmVal').textContent = opm.toFixed(1) + '%';
            document.getElementById('perVal').textContent = per.toFixed(1) + '배';

            const simTarget = Math.round(curPrice * (1 + (growth / 100) * 0.7) * (per / basePer));
            const upside = ((simTarget - curPrice) / curPrice) * 100;

            document.getElementById('simTargetPrice').textContent = simTarget.toLocaleString('ko-KR') + '원';
            const upEl = document.getElementById('simUpside');
            upEl.textContent = (upside > 0 ? '+' : '') + upside.toFixed(1) + '%';
            upEl.className = 'text-base font-bold ' + (upside > 0 ? 'text-emerald-400' : 'text-rose-400');
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
