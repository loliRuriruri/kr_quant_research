from datetime import datetime, timezone
from kr_quant.context.seasonality import compute_seasonality_brief, get_election_cycle_overlay


def test_election_cycle_midterm_2026():
    overlay = get_election_cycle_overlay(2026, 8)
    assert overlay["year"] == 2026
    assert overlay["cycle_rem"] == 2
    assert "중간선거" in overlay["title"]
    assert "안도 랠리" in overlay["pattern"]
    assert "밸류업" in overlay["kr_policy"]


def test_seasonality_brief_structure():
    dt = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)
    brief = compute_seasonality_brief(dt)
    assert brief["used_in_quant"] is False
    assert brief["current_month"] == 8
    assert brief["current_month_name"] == "8월"
    assert "election_overlay" in brief
    assert brief["election_overlay"]["cycle_rem"] == 2
    assert len(brief["months"]) == 12
    assert brief["current_stat"]["month"] == 8
    assert brief["strategy"]["stock_ratio"] > 0
    assert len(brief["strategy"]["leading_sectors"]) > 0
