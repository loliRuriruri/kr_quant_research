from datetime import date
from types import SimpleNamespace

import kr_quant.flow.official as official
import kr_quant.freshness as freshness
import kr_quant.web.jobs as jobs


def _snapshot(*, stale: bool, quant_state: str, coverage: float) -> dict:
    return {
        "stale_price": stale,
        "screen_as_of": "2026-08-31",
        "required_stale": ["krx_prices"] if stale else [],
        "sources": {
            "quant_ranking": {"state": quant_state},
            "financial_facts": {
                "coverage": {
                    "tickers": 414,
                    "universe_tickers": 2544,
                    "coverage_pct": coverage,
                }
            },
        },
    }


def test_smart_sync_runs_only_needed_daily_chain(monkeypatch):
    settings = SimpleNamespace(kis_app_key="key", kis_app_secret="secret")
    seen: list[str] = []
    snapshots = iter(
        [
            _snapshot(stale=True, quant_state="stale", coverage=16.3),
            _snapshot(stale=False, quant_state="fresh", coverage=16.3),
            _snapshot(stale=False, quant_state="fresh", coverage=18.2),
        ]
    )

    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(jobs, "resolve_as_of", lambda value: date(2026, 8, 31))
    monkeypatch.setattr(freshness, "freshness_snapshot", lambda value: next(snapshots))
    monkeypatch.setattr(
        jobs,
        "job_live",
        lambda *args, **kwargs: seen.append("live") or {"pipeline_status": "success", "as_of_date": "2026-08-31"},
    )
    monkeypatch.setattr(
        jobs,
        "job_dart_backfill",
        lambda *args, **kwargs: seen.append("dart")
        or {
            "dart_backfill": {
                "status": "success",
                "processed_this_run": 50,
                "covered_tickers": 464,
                "coverage_pct": 18.2,
            }
        },
    )
    monkeypatch.setattr(
        official,
        "collect_official",
        lambda value: seen.append("kis") or {"attempted": 40, "saved": 400, "errors": []},
    )

    result = jobs.job_smart_sync()

    assert seen == ["live", "dart", "kis"]
    assert result["kind"] == "smart-sync"
    assert result["pipeline_status"] == "success"
    assert result["dart_coverage"]["coverage_pct"] == 18.2
    assert [step["kind"] for step in result["steps"]] == ["live", "dart-backfill", "investor-kis"]


def test_smart_sync_skips_fresh_core_and_sufficient_dart(monkeypatch):
    settings = SimpleNamespace(kis_app_key=None, kis_app_secret=None)
    snapshot = _snapshot(stale=False, quant_state="fresh", coverage=92.0)

    monkeypatch.setattr(jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(jobs, "resolve_as_of", lambda value: date(2026, 8, 31))
    monkeypatch.setattr(freshness, "freshness_snapshot", lambda value: snapshot)
    monkeypatch.setattr(jobs, "job_live", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live should be skipped")))
    monkeypatch.setattr(
        jobs,
        "job_dart_backfill",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DART should be skipped")),
    )

    result = jobs.job_smart_sync()

    assert result["pipeline_status"] == "success"
    assert result["steps"][0]["status"] == "skipped_fresh"
    assert result["steps"][1]["status"] == "skipped_sufficient"
    assert result["steps"][2]["status"] == "skipped_not_configured"


def test_job_runner_exposes_partial_pipeline_status(monkeypatch):
    runner = jobs.JobRunner()
    monkeypatch.setattr(jobs, "_maybe_publish", lambda kind: None)
    monkeypatch.setattr(jobs, "_notify_job", lambda *args, **kwargs: None)

    runner._run("smart-sync", lambda: {"pipeline_status": "partial"})

    assert runner.snapshot()["status"] == "partial"
    assert "일부 완료" in runner.logs[-1]
