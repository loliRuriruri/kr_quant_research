from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from kr_quant.research.season_jev_budget import (
    BudgetLock,
    day_kst,
    read_ledger,
    reserve_daily_slot,
    write_ledger,
)


def _settings(tmp_path):
    data = tmp_path / "data"
    return SimpleNamespace(root=tmp_path, data_dir=data)


def test_concurrent_daily_cap_never_exceeds_limit(tmp_path):
    s = _settings(tmp_path)
    day = day_kst()
    write_ledger(s, {"schema": 1, "day_kst": day, "attempted_calls": 298, "generations": {}})

    def attempt(i):
        return reserve_daily_slot(s, f"gen-{i}", day_cap=300)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(attempt, range(10)))

    assert results.count("ok") == 2
    assert results.count("API_CAP_DAILY") == 8
    assert "ok" in results
    ledger = read_ledger(s, day)
    assert ledger["attempted_calls"] == 300
    assert ledger["attempted_calls"] <= 300


def test_lock_is_released_after_write_failure(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setattr(
        "kr_quant.research.season_jev_budget.write_ledger",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk")),
    )
    assert reserve_daily_slot(s, "g1", day_cap=300) == "API_BUDGET_UNAVAILABLE"
    monkeypatch.undo()
    assert reserve_daily_slot(s, "g1", day_cap=300) == "ok"
    assert read_ledger(s)["attempted_calls"] == 1


def test_lock_acquisition_timeout_is_finite():
    assert BudgetLock.__init__.__defaults__ is not None
    assert BudgetLock.__init__.__defaults__[0] == 2.0
