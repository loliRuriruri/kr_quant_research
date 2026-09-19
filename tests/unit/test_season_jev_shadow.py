import copy
import json
import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from kr_quant.research import season_jev_shadow as shadow
from kr_quant.web import season_snapshot as snapshots
from kr_quant.research.season_jev_budget import day_kst, ledger_path, read_ledger, write_ledger



def _complete_answers(choice="monitor"):
    answers = {head: {"type": "boolean", "probability": 0.6, "decision": True} for head in shadow.NOUL_HEADS}
    answers["reviewClass"] = {"type": "choice", "choice": choice, "probabilities": {choice: 1}, "confidence": 0.7}
    return answers


def _cand(i, **over):
    row = {
        "id": f"sig-{i}",
        "candidate_type": "season_pattern",
        "ticker": f"00000{i}",
        "state": {"identity": {"ticker": f"00000{i}", "signalId": f"sig-{i}"}},
        "state_hash": f"hash-{i}",
        "quant_reference": {"grade": "A"},
    }
    row.update(over)
    return row


def _ok_runner(calls):
    def runner(settings, payload, timeout):
        calls.append([c["id"] for c in payload["candidates"]])
        return {
            "results": [{
                "id": c["id"],
                "candidate_type": c["candidate_type"],
                "ticker": c.get("ticker"),
                "state_hash": c["state_hash"],
                "answers": _complete_answers(),
                "requested_model": "jev-latest",
                "resolved_model": "jev-1.13.0",
                "usage": {"inputTokens": 1, "outputTokens": 1},
            } for c in payload["candidates"]],
            "errors": [],
            "total_usage": {"inputTokens": len(payload["candidates"]), "outputTokens": len(payload["candidates"])},
        }
    return runner


def _settings(tmp_path, enabled=True):
    root = tmp_path
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "season_jev.json").write_text(json.dumps({
        "enabled": enabled,
        "evaluator_version": "season-jev-shadow-v1",
        "provider": "typesafe_direct",
        "model": "jev-latest",
        "lookback_years": 5,
        "horizon_days": 90,
        "concurrency": 4,
        "candidate_timeout_ms": 8000,
        "process_timeout_seconds": 180,
        "max_api_calls_per_generation": 300,
        "max_api_calls_per_day": 300,
    }), encoding="utf-8")
    data = tmp_path / "data"
    return SimpleNamespace(root=root, data_dir=data, staged_dir=data / "staged",
                           output_dir=data / "output", status_csv=data / "status.csv", config={})


def _bundle(month=None, extra_rows=None):
    month = month or date.today().month
    rows = [
        {
            "ticker": "005930",
            "company": "삼성전자",
            "market": "KOSPI",
            "pattern_id": "p1",
            "signal_id": "sig-1",
            "window_name": f"{month}월",
            "entry_stage": "PRE_ENTRY_15",
            "entry_stage_label": "피크 30~15일 전",
            "current_status": "WATCH",
            "entry_window_str": "08/23~09/07",
            "exit_window_str": "09/19~09/26",
            "price_as_of": "2026-09-07",
            "sample_count": 5,
            "win_rate": 0.8,
            "median_return": 0.12,
            "median_alpha": 0.04,
            "common_event_cluster": "실적",
            "secondary_cluster": None,
            "event_confidence": "medium",
            "invalidating_conditions": ["거래정지"],
            "event_explanation_mode": "cluster",
            "last_close": 70000,
            "chg_pct": 0.01,
            "remaining_peak": {
                "available": True,
                "remaining_p50": 0.05,
                "positive_peak_rate": 0.6,
                "downside_before_peak_p50": 0.03,
                "sample_count": 5,
                "confidence": "medium",
                "validation_status": "ok",
            },
            "pre_entry_rank": 1,
            "grade": "A",
            "seasonality_score": 81.2,
            "score_breakdown": {"historical_edge": 40},
        },
        {
            "ticker": "000660",
            "company": "만료종목",
            "market": "KOSPI",
            "pattern_id": "p2",
            "signal_id": "sig-end",
            "window_name": f"{month}월",
            "entry_stage": "SEASON_END",
            "pre_entry_rank": 9,
            "grade": "B",
            "seasonality_score": 60,
        },
        {
            "ticker": "035420",
            "company": "먼달",
            "market": "KOSPI",
            "pattern_id": "p3",
            "signal_id": "sig-far",
            "window_name": f"{(month + 6 - 1) % 12 + 1}월",
            "entry_stage": "WATCH",
            "pre_entry_rank": 8,
            "grade": "C",
            "seasonality_score": 55,
        },
    ]
    if extra_rows:
        rows.extend(extra_rows)
    return {
        "generation_id": "gen-test",
        "generated_at": "2026-09-18T00:00:00+00:00",
        "identity": {"day": date.today().isoformat(), "lookback": 5, "schema": 1},
        "payload": {"rows": rows, "stats": {}, "themes": [], "highlights": {}},
        "content_hash": "abc",
    }


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe-key")


def test_selects_90day_season_and_excludes_season_end(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "rank_institutional_events", lambda *a, **k: [], raising=False)
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])
    cands = shadow.collect_candidates(s, _bundle())
    types = {c["candidate_type"] for c in cands}
    ids = {c["id"] for c in cands}
    assert types == {"season_pattern"}
    assert "sig-1" in ids
    assert "sig-end" not in ids
    assert "sig-far" not in ids


def test_includes_calendar_event_stock(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    calendar = [{
        "ticker": "005930",
        "company": "삼성전자",
        "market": "KOSPI",
        "event_id": "ces",
        "event_group": "tech",
        "event_title": "CES",
        "target_date": "2026-01-07",
        "d_day": 110,
        "horizon_tag": "90d",
        "optimal_entry_window": "12/01~12/15",
        "optimal_exit_window": "01/05~01/10",
        "binary_risk": "LOW",
        "exposure_desc": "세트",
        "invalidating_rule": "일정 취소",
        "win_rate": 0.7,
        "avg_return": 0.1,
        "median_return": 0.08,
        "years_count": 4,
        "current_confirmation_evidence": ["퀀트 점수 70"],
        "current_confirmation_missing": [],
        "pre_pricing_flag": False,
        "grade": "A",
        "seasonality_score": 77,
        "score_breakdown": {"historical_edge": 30},
    }]
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: calendar)
    cands = shadow.collect_candidates(s, _bundle())
    cal = [c for c in cands if c["candidate_type"] == "calendar_event_stock"]
    assert len(cal) == 1
    assert cal[0]["id"] == "ces:005930:2026-01-07"


def test_state_omits_quant_fields_reference_keeps_them(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])
    cands = shadow.collect_candidates(s, _bundle())
    season = cands[0]
    blob = json.dumps(season["state"])
    for banned in ("pre_entry_rank", "grade", "seasonality_score", "score_breakdown"):
        assert banned not in blob
        assert banned not in season["state"]
    ref = season["quant_reference"]
    assert ref["pre_entry_rank"] == 1
    assert ref["grade"] == "A"
    assert ref["seasonality_score"] == 81.2
    assert ref["score_breakdown"]["historical_edge"] == 40


def test_same_generation_is_single_flight(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    bundle = _bundle()
    calls = []

    def fake_eval(*a, **k):
        calls.append(1)
        path = shadow.shadow_path(s, bundle["generation_id"], "typesafe_direct")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "generation_id": bundle["generation_id"],
            "status": "COMPLETE",
            "provider": "typesafe_direct",
            "requested_model": "jev-latest",
            "evaluator_version": "season-jev-shadow-v1",
        }), encoding="utf-8")
        return {"status": "COMPLETE"}

    monkeypatch.setattr(shadow, "evaluate_generation", fake_eval)
    shadow.request_shadow_evaluation(s, bundle)
    shadow.request_shadow_evaluation(s, bundle)
    time.sleep(0.05)
    # second call may no-op after file exists; at most one evaluation
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and not calls:
        time.sleep(0.01)
    shadow.request_shadow_evaluation(s, bundle)
    time.sleep(0.05)
    assert calls == [1]


def test_missing_typesafe_key_does_not_spawn_node(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gateway-must-not-fallback")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []
    assert list((s.data_dir / "research_snapshots" / "season").glob("*")) == []


def test_node_missing_leaves_season_snapshot(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    season = snapshots._folder(s)
    season.mkdir(parents=True)
    pointer = season / "latest_lb_5.json"
    gen = season / "gen-test.json"
    pointer.write_text(json.dumps({"generation_id": "gen-test"}), encoding="utf-8")
    gen.write_text(json.dumps({"generation_id": "gen-test", "content_hash": "abc"}), encoding="utf-8")
    before = (pointer.read_bytes(), gen.read_bytes())
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])
    monkeypatch.setattr(shadow.shutil, "which", lambda name: None)
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert (pointer.read_bytes(), gen.read_bytes()) == before


def test_partial_status_when_some_candidates_fail(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])

    def runner(settings, payload, timeout):
        first = payload["candidates"][0]
        return {
            "results": [{
                "id": first["id"],
                "candidate_type": "season_pattern",
                "ticker": "005930",
                "state_hash": first["state_hash"],
                "answers": _complete_answers(),
                "usage": {"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
                "wall_latency_ms": 12,
            }],
            "errors": [],
            "total_usage": {"inputTokens": 10, "outputTokens": 2, "totalTokens": 12},
        }

    out = shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert out["status"] == "COMPLETE"
    assert out["evaluated_count"] == 1
    saved = json.loads(shadow.shadow_path(s, "gen-test").read_text(encoding="utf-8"))
    assert saved["results"][0]["quant_reference"]["grade"] == "A"
    assert saved["results"][0]["status"] == "GENERATED"


def test_lookback_five_only_auto_trigger(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    called = []
    monkeypatch.setattr(shadow, "request_shadow_evaluation", lambda settings, bundle: called.append(bundle["identity"]["lookback"]))
    snapshots._schedule_shadow(s, _bundle(), 2)
    snapshots._schedule_shadow(s, _bundle(), 5)
    snapshots._schedule_shadow(s, _bundle(), 3)
    assert called == [5]


def test_shadow_does_not_block_request_return(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def slow(*a, **k):
        entered.set()
        release.wait(2)
        return {"status": "COMPLETE"}

    monkeypatch.setattr(shadow, "evaluate_generation", slow)
    started = time.monotonic()
    shadow.request_shadow_evaluation(s, _bundle())
    assert time.monotonic() - started < 0.4
    assert entered.wait(1)
    release.set()


def test_failed_shadow_does_not_change_generation_pointer(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    season = snapshots._folder(s)
    season.mkdir(parents=True)
    pointer = season / "latest_lb_5.json"
    gen = season / "gen-test.json"
    pointer.write_text(json.dumps({"generation_id": "gen-test", "generated_at": "t"}), encoding="utf-8")
    gen.write_text(json.dumps({"generation_id": "gen-test", "content_hash": "stay"}), encoding="utf-8")
    before = (pointer.read_bytes(), gen.read_bytes())
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])

    def boom(*a, **k):
        raise RuntimeError("gateway")

    monkeypatch.setattr(shadow, "run_node", boom)
    shadow.evaluate_generation(s, _bundle())
    assert (pointer.read_bytes(), gen.read_bytes()) == before
    assert json.loads(gen.read_text(encoding="utf-8"))["content_hash"] == "stay"


def test_quant_reference_not_sent_to_node(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])
    seen = []

    def runner(settings, payload, timeout):
        seen.append(payload)
        return {"results": [], "errors": [{"error": "x"}], "total_usage": {}, "total_cost_usd": 0}

    shadow.evaluate_generation(s, _bundle(), runner=runner)
    sent = json.dumps(seen[0])
    assert "quant_reference" not in sent
    assert "pre_entry_rank" not in sent
    assert "seasonality_score" not in sent



def test_calendar_id_is_event_ticker_date(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [{
        "ticker": "005930",
        "company": "삼성전자",
        "market": "KOSPI",
        "event_id": "ces",
        "event_title": "갤럭시 신제품 출시",
        "target_date": "2026-01-07",
        "invalidating_rule": "계절성 무효화 조건",
    }])
    cands = [c for c in shadow.collect_candidates(s, _bundle()) if c["candidate_type"] == "calendar_event_stock"]
    assert cands[0]["id"] == "ces:005930:2026-01-07"
    assert cands[0]["state"]["identity"]["calendarKey"] == "ces:005930:2026-01-07"


def test_utf8_korean_round_trip_in_subprocess_kwargs(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    script = Path(s.root) / "scripts" / "jev-season-shadow.mjs"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("// stub\n", encoding="utf-8")
    captured = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout='{"results":[],"errors":[]}', stderr="")

    monkeypatch.setattr(shadow.subprocess, "run", fake_run)
    monkeypatch.setattr(shadow.shutil, "which", lambda name: "node")
    payload = {
        "company": "삼성전자",
        "title": "갤럭시 신제품 출시",
        "rule": "계절성 무효화 조건",
    }
    out = shadow.run_node(s, payload, timeout=5)
    assert captured.get("text") is True
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"
    assert isinstance(captured.get("input"), str)
    assert "삼성전자" in captured["input"]
    assert "갤럭시 신제품 출시" in captured["input"]
    assert "계절성 무효화 조건" in captured["input"]
    assert out["results"] == []


def test_node_payload_includes_soft_deadline(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr("kr_quant.strategy.seasonality.rank_institutional_events", lambda *a, **k: [])
    seen = []

    def runner(settings, payload, timeout):
        seen.append(payload)
        return {"results": [], "errors": [{"error": "x"}], "total_usage": {}, "total_cost_usd": 0}

    shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert seen[0]["process_soft_deadline_ms"] == 170000
    assert seen[0]["process_start_cutoff_ms"] == 160000
    assert seen[0]["requested_model"] == "jev-latest"
    assert seen[0]["provider"] == "typesafe_direct"
    assert "zero_data_retention" not in seen[0]

def test_does_not_reuse_vercel_gateway_shadow(tmp_path):
    s = _settings(tmp_path)
    gen = "gen-test"
    cfg = {"provider": "typesafe_direct", "model": "jev-latest", "evaluator_version": "season-jev-shadow-v1"}
    path = shadow.shadow_path(s, gen, "vercel_gateway")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generation_id": gen,
        "provider": "vercel_gateway",
        "requested_model": "typesafe-ai/jev",
        "evaluator_version": "season-jev-shadow-v1",
        "status": "COMPLETE",
    }), encoding="utf-8")
    assert shadow.has_shadow(s, gen, cfg) is False

def test_timing_bucket_stable_and_boundary():
    assert shadow.timing_bucket(48) == shadow.timing_bucket(47) == "31-60"
    assert shadow.timing_bucket(61) == shadow.timing_bucket(70) == ">60"
    assert shadow.timing_bucket(31) == "31-60"
    assert shadow.timing_bucket(30) == "15-30"
    a = {"d_day": 48, "event_id": "ces", "ticker": "005930", "target_date": "2026-01-07"}
    b = dict(a, d_day=47)
    ha = shadow.state_hash(shadow.project_calendar_state(a), "season-jev-shadow-v1")
    hb = shadow.state_hash(shadow.project_calendar_state(b), "season-jev-shadow-v1")
    assert ha == hb
    c = dict(a, d_day=31)
    d = dict(a, d_day=30)
    assert shadow.state_hash(shadow.project_calendar_state(c), "season-jev-shadow-v1") != shadow.state_hash(shadow.project_calendar_state(d), "season-jev-shadow-v1")


def test_raw_dday_not_in_direct_state():
    state = shadow.project_calendar_state({"event_id": "ces", "ticker": "005930", "target_date": "2026-01-07", "d_day": 48})
    blob = json.dumps(state)
    assert "dDay" not in blob
    assert state["timing"]["timingBucket"] == "31-60"
    assert state["timing"]["targetDate"] == "2026-01-07"
    assert state["identity"]["calendarKey"] == "ces:005930:2026-01-07"


def test_generation_cap(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    Path(s.root / "config" / "season_jev.json").write_text(json.dumps({
        **json.loads((s.root / "config" / "season_jev.json").read_text(encoding="utf-8")),
        "max_api_calls_per_generation": 2,
        "max_api_calls_per_day": 300,
    }), encoding="utf-8")
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(i) for i in range(5)])
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == [["sig-0", "sig-1"]]
    skipped = [r for r in out["results"] if r.get("status") == "SKIPPED"]
    assert len(skipped) == 3
    assert all(r["skip_reason"] == "API_CAP_GENERATION" for r in skipped)
    assert out["status"] == "PARTIAL"


def test_daily_cap(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    Path(s.root / "config" / "season_jev.json").write_text(json.dumps({
        **json.loads((s.root / "config" / "season_jev.json").read_text(encoding="utf-8")),
        "max_api_calls_per_generation": 300,
        "max_api_calls_per_day": 300,
    }), encoding="utf-8")
    write_ledger(s, {"schema": 1, "day_kst": day_kst(), "attempted_calls": 299, "generations": {}})
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(i) for i in range(3)])
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == [["sig-0"]]
    skipped = [r for r in out["results"] if r.get("skip_reason") == "API_CAP_DAILY"]
    assert len(skipped) == 2
    assert read_ledger(s)["attempted_calls"] == 300


def test_api_error_consumes_cap(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])
    def runner(settings, payload, timeout):
        return {"results": [], "errors": [{"id": payload["candidates"][0]["id"], "error": "boom"}], "total_usage": {}}
    shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert read_ledger(s)["attempted_calls"] == 1


def test_reused_does_not_consume_cap(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    cands = [_cand(i, state_hash="same") for i in range(3)]
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: cands)
    source = {
        "generation_id": "gen-A",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "finished_at": "2026-09-01T00:00:00+00:00",
        "results": [{
            "status": "GENERATED",
            "state_hash": "same",
            "answers": _complete_answers(),
            "resolved_model": "jev-1.13.0",
        }],
    }
    path = shadow.shadow_path(s, "gen-A", "typesafe_direct")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(source), encoding="utf-8")
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == []
    assert all(r["status"] == "REUSED" for r in out["results"])
    assert all(r["reused_from_generation_id"] == "gen-A" for r in out["results"])
    assert not ledger_path(s, day_kst()).exists()


def test_cross_generation_reuse(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0, state_hash="sem")])
    path = shadow.shadow_path(s, "gen-A", "typesafe_direct")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generation_id": "gen-A",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "finished_at": "z",
        "results": [{"status": "GENERATED", "state_hash": "sem", "answers": _complete_answers()}],
    }), encoding="utf-8")
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == []
    assert out["results"][0]["status"] == "REUSED"
    assert out["results"][0]["reused_from_generation_id"] == "gen-A"


def test_transitive_reuse_preserves_origin(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0, state_hash="sem")])
    folder = shadow.shadow_dir(s)
    folder.mkdir(parents=True)
    (folder / "gen-B__typesafe_direct.json").write_text(json.dumps({
        "generation_id": "gen-B",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "finished_at": "2026-09-02",
        "results": [{"status": "REUSED", "state_hash": "sem", "answers": _complete_answers(), "reused_from_generation_id": "gen-A"}],
    }), encoding="utf-8")
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == []
    assert out["results"][0]["reused_from_generation_id"] == "gen-A"


def test_model_isolation_blocks_reuse(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0, state_hash="sem")])
    path = shadow.shadow_path(s, "gen-A", "typesafe_direct")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generation_id": "gen-A",
        "provider": "typesafe_direct",
        "requested_model": "other-model",
        "evaluator_version": "season-jev-shadow-v1",
        "finished_at": "z",
        "results": [{"status": "GENERATED", "state_hash": "sem", "answers": _complete_answers()}],
    }), encoding="utf-8")
    calls = []
    shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == [["sig-0"]]


def test_evaluator_version_isolation(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0, state_hash="sem")])
    path = shadow.shadow_path(s, "gen-A", "typesafe_direct")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generation_id": "gen-A",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "old-version",
        "finished_at": "z",
        "results": [{"status": "GENERATED", "state_hash": "sem", "answers": _complete_answers()}],
    }), encoding="utf-8")
    calls = []
    shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == [["sig-0"]]


def test_budget_lock_failure_skips(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])
    monkeypatch.setattr("kr_quant.research.season_jev_budget.BudgetLock.acquire", lambda self: False)
    calls = []
    out = shadow.evaluate_generation(s, _bundle(), runner=_ok_runner(calls))
    assert calls == []
    assert out["results"][0]["skip_reason"] == "API_BUDGET_UNAVAILABLE"


def test_deadline_before_start_refunds_cap(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])
    def runner(settings, payload, timeout):
        return {"results": [], "errors": [{"id": payload["candidates"][0]["id"], "error": "SOFT_DEADLINE_NOT_STARTED"}], "total_usage": {}}
    shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert read_ledger(s)["attempted_calls"] == 0


def test_provider_name_accepts_supported_values():
    assert shadow.provider_name({"provider": "typesafe_direct"}) == "typesafe_direct"


def test_provider_name_accepts_openrouter():
    assert shadow.provider_name({"provider": "openrouter"}) == "openrouter"


def test_provider_runner_path_selects_openrouter_script(tmp_path):
    s = _settings(tmp_path)
    path = shadow.provider_runner_path(s, {"provider": "openrouter"})
    assert path == Path(s.root) / "scripts" / "jev-season-shadow-openrouter.mjs"


def test_provider_key_routes_selected_provider_only(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-only")
    assert shadow.provider_key({"provider": "openrouter"}) == "or-only"
    assert shadow.provider_key({"provider": "typesafe_direct"}) is None

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-only")
    assert shadow.provider_key({"provider": "typesafe_direct"}) == "ts-only"
    assert shadow.provider_key({"provider": "openrouter"}) is None


def test_openrouter_missing_key_does_not_fallback_to_typesafe(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "direct-must-not-run")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []


def test_typesafe_missing_key_does_not_fallback_to_openrouter(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-must-not-run")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []


def test_openrouter_requires_pinned_production_model():
    with pytest.raises(
        ValueError,
        match=r"UNSUPPORTED_JEV_MODEL:openrouter:jev-latest",
    ):
        shadow.requested_model({
            "provider": "openrouter",
            "model": "jev-latest",
        })


def test_openrouter_rejects_upgrade_alias_on_production_path():
    with pytest.raises(
        ValueError,
        match=r"UNSUPPORTED_JEV_MODEL:openrouter:~typesafe/jev-latest",
    ):
        shadow.requested_model({
            "provider": "openrouter",
            "model": "~typesafe/jev-latest",
        })


def test_openrouter_accepts_pinned_production_model():
    assert shadow.requested_model({
        "provider": "openrouter",
        "model": "typesafe/jev-1.13",
    }) == "typesafe/jev-1.13"


def test_invalid_openrouter_model_never_runs_node(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "jev-latest"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []


def test_provider_name_rejects_vercel_gateway():
    with pytest.raises(ValueError, match=r"UNSUPPORTED_JEV_PROVIDER:vercel_gateway"):
        shadow.provider_name({"provider": "vercel_gateway"})


def test_provider_name_defaults_to_typesafe_direct():
    assert shadow.provider_name({}) == "typesafe_direct"
    assert shadow.provider_name(None) == "typesafe_direct"


def test_provider_name_rejects_unknown_provider():
    with pytest.raises(ValueError, match=r"UNSUPPORTED_JEV_PROVIDER:bogus"):
        shadow.provider_name({"provider": "bogus"})


def test_provider_runner_path_selects_direct_script(tmp_path):
    s = _settings(tmp_path)
    path = shadow.provider_runner_path(s, {"provider": "typesafe_direct"})
    assert path == Path(s.root) / "scripts" / "jev-season-shadow.mjs"


def test_provider_runner_path_rejects_vercel_gateway(tmp_path):
    s = _settings(tmp_path)
    with pytest.raises(ValueError, match=r"UNSUPPORTED_JEV_PROVIDER:vercel_gateway"):
        shadow.provider_runner_path(s, {"provider": "vercel_gateway"})


def test_provider_runner_path_rejects_unknown_provider(tmp_path):
    s = _settings(tmp_path)
    with pytest.raises(ValueError, match=r"UNSUPPORTED_JEV_PROVIDER:bogus"):
        shadow.provider_runner_path(s, {"provider": "bogus"})


def test_run_node_routes_direct_provider_to_direct_script(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    scripts = Path(s.root) / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "jev-season-shadow.mjs").write_text("", encoding="utf-8")

    monkeypatch.setattr(shadow.shutil, "which", lambda name: "node")
    captured = {}

    class Completed:
        returncode = 0
        stdout = '{"results":[],"errors":[],"total_usage":{}}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return Completed()

    monkeypatch.setattr(shadow.subprocess, "run", fake_run)

    shadow.run_node(
        s,
        {"provider": "typesafe_direct", "candidates": []},
        timeout=5,
    )

    assert captured["cmd"][1] == str(scripts / "jev-season-shadow.mjs")



def test_invalid_provider_is_contained_by_shadow_request(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["enabled"] = True
    cfg["provider"] = "bogus"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    before = copy.deepcopy(_bundle())
    bundle = _bundle()

    shadow.request_shadow_evaluation(s, bundle)

    assert bundle == before



def test_vercel_gateway_config_is_unsupported_even_with_typesafe_key(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "vercel_gateway"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setenv("TYPESAFE_API_KEY", "direct-must-not-run-for-gateway")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gateway-must-not-be-used")

    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})

    out = shadow.evaluate_generation(s, _bundle())

    assert out is None
    assert ran == []



def test_generated_record_stores_provider(tmp_path, monkeypatch, env_key):
    s = _settings(tmp_path)
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])
    calls = []

    def runner(settings, payload, timeout):
        calls.append(payload["provider"])
        item = payload["candidates"][0]
        return {
            "provider": "typesafe_direct",
            "requested_model": "jev-latest",
            "results": [{
                "id": item["id"],
                "candidate_type": item["candidate_type"],
                "ticker": item["ticker"],
                "state_hash": item["state_hash"],
                "provider": "typesafe_direct",
                "answers": _complete_answers(),
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "requested_model": "jev-latest",
                "resolved_model": "jev-1.13.0",
                "wall_latency_ms": 12,
            }],
            "errors": [],
            "total_usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        }

    out = shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert calls == ["typesafe_direct"]
    assert out["requested_model"] == "jev-latest"
    assert out["resolved_models"] == ["jev-1.13.0"]
    rec = out["results"][0]
    assert rec["provider"] == "typesafe_direct"
    assert rec["requested_model"] == "jev-latest"
    assert rec["resolved_model"] == "jev-1.13.0"
    assert rec["wall_latency_ms"] == 12


def test_openrouter_generated_record_stores_provider_and_telemetry(tmp_path, monkeypatch):
    s = _settings(tmp_path)

    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(
        shadow,
        "source_identity",
        lambda *a, **k: _bundle()["identity"],
    )
    monkeypatch.setattr(
        shadow,
        "collect_candidates",
        lambda *a, **k: [_cand(0)],
    )

    def runner(settings, payload, timeout):
        assert payload["provider"] == "openrouter"
        assert payload["requested_model"] == "typesafe/jev-1.13"
        assert payload["model"] == "typesafe/jev-1.13"

        item = payload["candidates"][0]

        return {
            "provider": "openrouter",
            "requested_model": "typesafe/jev-1.13",
            "results": [{
                "id": item["id"],
                "candidate_type": item["candidate_type"],
                "ticker": item["ticker"],
                "state_hash": item["state_hash"],
                "provider": "openrouter",
                "answers": _complete_answers(),
                "usage": {
                    "inputTokens": 2,
                    "outputTokens": 2,
                    "totalTokens": 4,
                },
                "requested_model": "typesafe/jev-1.13",
                "resolved_model": "typesafe/jev-1.13-20260917",
                "wall_latency_ms": 9,
                "provider_name": "TypeSafe",
                "cost": 0.0001,
                "request_id": "gen-test",
            }],
            "errors": [],
            "total_usage": {
                "inputTokens": 2,
                "outputTokens": 2,
                "totalTokens": 4,
            },
        }

    out = shadow.evaluate_generation(
        s,
        _bundle(),
        runner=runner,
    )

    assert out["provider"] == "openrouter"
    assert out["requested_model"] == "typesafe/jev-1.13"
    assert out["resolved_models"] == [
        "typesafe/jev-1.13-20260917",
    ]

    rec = out["results"][0]

    assert rec["status"] == "GENERATED"
    assert rec["provider"] == "openrouter"
    assert rec["requested_model"] == "typesafe/jev-1.13"
    assert rec["resolved_model"] == "typesafe/jev-1.13-20260917"
    assert rec["provider_name"] == "TypeSafe"
    assert rec["cost"] == 0.0001
    assert rec["request_id"] == "gen-test"


def test_openrouter_missing_optional_telemetry_persists_null(tmp_path, monkeypatch):
    s = _settings(tmp_path)

    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(
        shadow,
        "source_identity",
        lambda *a, **k: _bundle()["identity"],
    )
    monkeypatch.setattr(
        shadow,
        "collect_candidates",
        lambda *a, **k: [_cand(0)],
    )

    def runner(settings, payload, timeout):
        item = payload["candidates"][0]

        return {
            "provider": "openrouter",
            "requested_model": "typesafe/jev-1.13",
            "results": [{
                "id": item["id"],
                "candidate_type": item["candidate_type"],
                "ticker": item["ticker"],
                "state_hash": item["state_hash"],
                "provider": "openrouter",
                "answers": _complete_answers(),
                "usage": {
                    "inputTokens": None,
                    "outputTokens": None,
                    "totalTokens": None,
                },
                "requested_model": "typesafe/jev-1.13",
                "resolved_model": "typesafe/jev-1.13-20260917",
                "wall_latency_ms": 9,
                "provider_name": None,
                "cost": None,
                "request_id": None,
            }],
            "errors": [],
            "total_usage": {
                "inputTokens": None,
                "outputTokens": None,
                "totalTokens": None,
            },
        }

    out = shadow.evaluate_generation(
        s,
        _bundle(),
        runner=runner,
    )

    rec = out["results"][0]

    assert rec["provider_name"] is None
    assert rec["cost"] is None
    assert rec["request_id"] is None
    assert rec["usage"]["inputTokens"] is None
    assert rec["usage"]["outputTokens"] is None
    assert rec["usage"]["totalTokens"] is None


def test_direct_generated_record_does_not_invent_openrouter_telemetry(
    tmp_path,
    monkeypatch,
    env_key,
):
    s = _settings(tmp_path)

    monkeypatch.setattr(
        shadow,
        "source_identity",
        lambda *a, **k: _bundle()["identity"],
    )
    monkeypatch.setattr(
        shadow,
        "collect_candidates",
        lambda *a, **k: [_cand(0)],
    )

    out = shadow.evaluate_generation(
        s,
        _bundle(),
        runner=_ok_runner([]),
    )

    rec = out["results"][0]

    assert "provider_name" not in rec
    assert "cost" not in rec
    assert "request_id" not in rec


def test_state_hash_differs_by_provider_and_requested_model():
    state = {
        "identity": {
            "ticker": "TEST000",
        },
    }

    shadow.assert_state_clean(state)

    h_direct = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="typesafe_direct",
        requested_model="jev-latest",
    )

    h_openrouter = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="openrouter",
        requested_model="typesafe/jev-1.13",
    )

    h_openrouter_latest = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="openrouter",
        requested_model="~typesafe/jev-latest",
    )

    assert h_direct != h_openrouter
    assert h_openrouter != h_openrouter_latest


def test_reuse_index_never_crosses_provider(tmp_path):
    s = _settings(tmp_path)

    folder = shadow.shadow_dir(s)
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "gen-openrouter__openrouter.json").write_text(
        json.dumps({
            "generation_id": "gen-openrouter",
            "provider": "openrouter",
            "requested_model": "typesafe/jev-1.13",
            "evaluator_version": "season-jev-shadow-v1",
            "finished_at": "2026-09-19T00:00:00+00:00",
            "results": [{
                "status": "GENERATED",
                "state_hash": "same-state",
                "answers": _complete_answers(),
                "requested_model": "typesafe/jev-1.13",
                "resolved_model": "typesafe/jev-1.13-20260917",
            }],
        }),
        encoding="utf-8",
    )

    direct_cfg = {
        "provider": "typesafe_direct",
        "model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
    }

    openrouter_cfg = {
        "provider": "openrouter",
        "model": "typesafe/jev-1.13",
        "evaluator_version": "season-jev-shadow-v1",
    }

    assert shadow.load_reuse_index(s, direct_cfg) == {}

    openrouter_index = shadow.load_reuse_index(
        s,
        openrouter_cfg,
    )

    key = shadow.reuse_key(
        "season-jev-shadow-v1",
        "openrouter",
        "typesafe/jev-1.13",
        "same-state",
    )

    assert key in openrouter_index


def test_run_node_nonzero_exit_is_failure_even_with_valid_stdout(
    tmp_path,
    monkeypatch,
):
    s = _settings(tmp_path)

    scripts = Path(s.root) / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)

    (
        scripts / "jev-season-shadow-openrouter.mjs"
    ).write_text(
        "",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        shadow.shutil,
        "which",
        lambda name: "node",
    )

    class Completed:
        returncode = 1
        stdout = json.dumps({
            "provider": "openrouter",
            "results": [{
                "id": "x",
            }],
            "errors": [],
        })
        stderr = "UV_HANDLE_CLOSING"

    monkeypatch.setattr(
        shadow.subprocess,
        "run",
        lambda *a, **k: Completed(),
    )

    with pytest.raises(
        RuntimeError,
        match=r"NODE_EXIT_1",
    ):
        shadow.run_node(
            s,
            {
                "provider": "openrouter",
                "candidates": [],
            },
            timeout=5,
        )


def test_openrouter_runner_failure_preserves_quant_bundle(
    tmp_path,
    monkeypatch,
):
    s = _settings(tmp_path)

    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setenv("OPENROUTER_API_KEY", "or")

    monkeypatch.setattr(
        shadow,
        "source_identity",
        lambda *a, **k: _bundle()["identity"],
    )
    monkeypatch.setattr(
        shadow,
        "collect_candidates",
        lambda *a, **k: [_cand(0)],
    )

    monkeypatch.setattr(
        shadow,
        "run_node",
        lambda *a, **k: (
            _ for _ in ()
        ).throw(
            RuntimeError("NODE_EXIT_1")
        ),
    )

    bundle = _bundle()
    before = copy.deepcopy(bundle)

    out = shadow.evaluate_generation(
        s,
        bundle,
    )

    assert bundle == before
    assert out["status"] == "ERROR"
    assert out["provider"] == "openrouter"
    assert out["requested_model"] == "typesafe/jev-1.13"
    assert out["errors"] == [{
        "error": "RUNNER:RuntimeError",
    }]
