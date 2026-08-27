# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import numpy as np

from kr_quant.strategy.seasonality import EVENT_PRESETS


THEME_VISUALS: dict[str, dict[str, str]] = {
    "winter_heater": {"emoji": "❄️", "color": "#38BDF8"},
    "summer_heat": {"emoji": "☀️", "color": "#F59E0B"},
    "galaxy_phone": {"emoji": "📱", "color": "#8B5CF6"},
    "dividend_play": {"emoji": "💰", "color": "#10B981"},
    "shopping_frenzy": {"emoji": "🛍️", "color": "#EC4899"},
    "index_rebalance": {"emoji": "📊", "color": "#06B6D4"},
    "earnings_pead": {"emoji": "📈", "color": "#22C55E"},
    "iphone_cycle": {"emoji": "🍎", "color": "#A78BFA"},
    "ces_ai_robot": {"emoji": "🤖", "color": "#34D399"},
    "bio_conference": {"emoji": "🧬", "color": "#F43F5E"},
    "game_show": {"emoji": "🎮", "color": "#FBBF24"},
    "holiday_consumption": {"emoji": "✈️", "color": "#60A5FA"},
    "year_end_calendar": {"emoji": "📅", "color": "#FB7185"},
    "ipo_lockup": {"emoji": "🔓", "color": "#94A3B8"},
}


def _plain_label(label: str) -> str:
    parts = str(label or "").split(maxsplit=1)
    return parts[1] if len(parts) == 2 else str(label or "")


def _theme_definitions_from_presets() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for preset_key, preset in EVENT_PRESETS.items():
        visual = THEME_VISUALS.get(preset_key, {"emoji": "📌", "color": "#64748B"})
        definitions.append(
            {
                "theme_id": preset_key,
                "preset_key": preset_key,
                "theme_name": _plain_label(str(preset.get("label") or preset.get("title") or preset_key)),
                "emoji": visual["emoji"],
                "color": visual["color"],
                "catalyst": str(preset.get("description") or ""),
                "peak_months": [int(month) for month in preset.get("peak_months", [])],
                "analysis_month": int(preset.get("analysis_month") or 1),
                "tickers": [str(ticker).zfill(6) for ticker in preset.get("tickers", [])],
            }
        )
    return definitions


# Single source of truth: the same presets that feed the heatmap event buttons
# also feed the theme contribution map and its stock membership.
THEME_DEFINITIONS: list[dict[str, Any]] = _theme_definitions_from_presets()


def _best_row_by_ticker(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").zfill(6)
        if not ticker or ticker == "000000":
            continue
        current = best.get(ticker)
        if current is None or float(row.get("seasonality_score") or 0) > float(current.get("seasonality_score") or 0):
            best[ticker] = row
    return best


def calculate_theme_seasonality(
    discovery_rows: list[dict[str, Any]],
    event_rows_by_preset: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Build event-theme rankings from the shared preset stock universes.

    Event scan rows own the historical statistics shown on each theme. Discovery
    rows are used only to show how many mapped stocks are also actionable in the
    current pre-entry queue. An empty theme stays empty; unrelated high-scoring
    stocks are never inserted as a fallback.
    """
    discovery_by_ticker = _best_row_by_ticker(discovery_rows)
    supplied_event_rows = event_rows_by_preset or {}
    theme_results: list[dict[str, Any]] = []

    for definition in THEME_DEFINITIONS:
        theme_id = str(definition["theme_id"])
        configured_tickers = list(definition.get("tickers") or [])
        configured_set = set(configured_tickers)

        if theme_id in supplied_event_rows:
            event_by_ticker = _best_row_by_ticker(supplied_event_rows.get(theme_id) or [])
            matched_candidates = [event_by_ticker[ticker] for ticker in configured_tickers if ticker in event_by_ticker]
        else:
            matched_candidates = [discovery_by_ticker[ticker] for ticker in configured_tickers if ticker in discovery_by_ticker]

        candidate_tickers = [str(row.get("ticker") or "").zfill(6) for row in matched_candidates]
        pre_entry_tickers = [
            ticker
            for ticker in candidate_tickers
            if discovery_by_ticker.get(ticker, {}).get("pre_entry_rank") is not None
        ]

        returns = [
            float(row.get("avg_return", row.get("expected_p50", row.get("median_return", 0.0))) or 0.0)
            for row in matched_candidates
        ]
        alphas = [float(row.get("median_alpha") or 0.0) for row in matched_candidates]
        win_rates = [float(row.get("win_rate") or 0.0) for row in matched_candidates]
        seasonality_scores = [float(row.get("seasonality_score") or 0.0) for row in matched_candidates]

        avg_return = float(np.mean(returns)) if returns else 0.0
        avg_alpha = float(np.mean(alphas)) if alphas else 0.0
        avg_win_rate = float(np.mean(win_rates)) if win_rates else 0.0
        avg_seasonality_score = float(np.mean(seasonality_scores)) if seasonality_scores else 0.0

        if matched_candidates:
            top_leader = max(
                matched_candidates,
                key=lambda row: (
                    float(row.get("seasonality_score") or 0),
                    float(row.get("avg_return", row.get("expected_p50", row.get("median_return", 0.0))) or 0.0),
                ),
            )
            leader_name = str(top_leader.get("company") or top_leader.get("ticker") or "해당 없음")
            leader_ticker = str(top_leader.get("ticker") or "").zfill(6)
            leader_return = float(
                top_leader.get("avg_return", top_leader.get("expected_p50", top_leader.get("median_return", 0.0))) or 0.0
            )
        else:
            leader_name = "안전 조건 통과 종목 없음"
            leader_ticker = ""
            leader_return = 0.0

        # Relative contribution is a normalized theme signal, not portfolio
        # attribution. The composite seasonality score keeps weak/negative
        # themes visible in the donut while their return remains explicit.
        raw_score = (max(avg_seasonality_score, 0.0) / 100.0) * max(avg_win_rate, 0.25) * np.sqrt(len(matched_candidates))

        theme_results.append(
            {
                "theme_id": theme_id,
                "preset_key": theme_id,
                "theme_name": definition["theme_name"],
                "emoji": definition["emoji"],
                "color": definition["color"],
                "candidate_count": len(matched_candidates),
                "mapped_count": len(configured_set),
                "excluded_count": max(len(configured_set) - len(matched_candidates), 0),
                "pre_entry_count": len(pre_entry_tickers),
                "avg_return": round(avg_return, 4),
                "avg_alpha": round(avg_alpha, 4),
                "avg_win_rate": round(avg_win_rate, 3),
                "avg_seasonality_score": round(avg_seasonality_score, 1),
                "top_leader_name": leader_name,
                "top_leader_ticker": leader_ticker,
                "top_leader_return": round(leader_return, 4),
                "catalyst": definition["catalyst"],
                "peak_months": definition["peak_months"],
                "analysis_month": definition["analysis_month"],
                "candidate_tickers": candidate_tickers,
                "pre_entry_tickers": pre_entry_tickers,
                "source": "event_preset",
                "raw_score": float(raw_score),
            }
        )

    total_raw = sum(float(theme["raw_score"]) for theme in theme_results)
    nonempty_count = sum(1 for theme in theme_results if theme["candidate_count"] > 0)
    for theme in theme_results:
        if total_raw > 0:
            share = (float(theme["raw_score"]) / total_raw) * 100
        elif nonempty_count and theme["candidate_count"] > 0:
            share = 100.0 / nonempty_count
        else:
            share = 0.0
        theme["weight_share_pct"] = round(share, 1)

    theme_results.sort(
        key=lambda theme: (
            float(theme["weight_share_pct"]),
            int(theme["pre_entry_count"]),
            int(theme["candidate_count"]),
        ),
        reverse=True,
    )
    return theme_results
