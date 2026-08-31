import pandas as pd

from kr_quant.strategy.engine import run_backtest
from kr_quant.strategy.registry import strategy_registry


def test_next_bar_execution_buys_next_open():
    data = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "open": [100.0, 110.0, 120.0, 130.0],
            "high": [101, 111, 121, 131],
            "low": [99, 109, 119, 129],
            "close": [100.0, 110.0, 120.0, 130.0],
            "volume": [1, 1, 1, 1],
        }
    )
    signals = pd.DataFrame(
        {"entry": [True, False, False, False], "exit": [False, False, True, False]}
    )
    result = run_backtest(data, signals, commission_bps=0, slippage_bps=0)
    assert result.metrics["trade_count"] == 1
    # buy next open 110, sell next open after exit signal: exit signal day2 close -> sell day3 open 130
    assert result.trades.iloc[0]["return"] == 130 / 110 - 1


def test_registry_has_research_strategies():
    reg = strategy_registry()
    assert "rsi_reversion" in reg
    assert "ma_cross" in reg
    data = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=60, freq="B"),
            "open": range(100, 160),
            "high": range(101, 161),
            "low": range(99, 159),
            "close": range(100, 160),
            "volume": [1000] * 60,
        }
    )
    sig = reg["ma_cross"].generate_signals(data)
    assert "entry" in sig.columns
    assert len(sig) == 60


def test_parameter_search_and_walk_forward_do_not_peek_future():
    from kr_quant.strategy.search import chronological_splits, parameter_combinations, search_strategy, walk_forward

    spec = strategy_registry()["ma_cross"]
    combos = parameter_combinations(spec)
    assert combos
    assert all(int(c["fast"]) < int(c["slow"]) for c in combos)
    data = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=80, freq="B"),
            "open": [100 + i * 0.2 for i in range(80)],
            "high": [101 + i * 0.2 for i in range(80)],
            "low": [99 + i * 0.2 for i in range(80)],
            "close": [100 + i * 0.2 for i in range(80)],
            "volume": [1000] * 80,
        }
    )
    splits = chronological_splits(data)
    assert splits["TRAIN"]["date"].max() < splits["VALIDATION"]["date"].min()
    assert splits["VALIDATION"]["date"].max() < splits["OOS"]["date"].min()
    searched = search_strategy(data, spec, commission_bps=1, slippage_bps=2)
    assert searched.validation
    assert searched.oos
    windows = walk_forward(data, spec, train_days=40, test_days=15, step_days=15, slippage_bps=0)
    assert len(windows) >= 1


def test_displayed_metrics_match_selected_parameters():
    from kr_quant.strategy.run import evaluate_ticker, generate_plain_strategy_playbook

    data = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=180, freq="B"),
            "open": [100 + (i % 30) * 0.7 + i * 0.03 for i in range(180)],
            "high": [102 + (i % 30) * 0.7 + i * 0.03 for i in range(180)],
            "low": [98 + (i % 30) * 0.7 + i * 0.03 for i in range(180)],
            "close": [100 + (i % 30) * 0.7 + i * 0.03 for i in range(180)],
            "volume": [1000 + i for i in range(180)],
        }
    )
    result = evaluate_ticker(data, commission_bps=3, slippage_bps=4, oos_ratio=0.2, min_days=40)
    registry = strategy_registry()
    for row in result["strategies"]:
        spec = registry[row["strategy_id"]]
        expected = run_backtest(
            data,
            spec.generate_signals(data, row["params"]),
            commission_bps=3,
            slippage_bps=4,
        )
        assert row["total_return"] == expected.metrics["total_return"]
        assert row["trade_count"] == expected.metrics["trade_count"]
        assert row["selection_basis"] == "validation"
        assert "oos_trade_count" in row
    scores = [row["selection_score"] for row in result["strategies"]]
    assert scores == sorted(scores, reverse=True)
    playbook = generate_plain_strategy_playbook(result["strategies"], "테스트기업")
    assert "가운데 검증 구간" in playbook["actionable_reason"]
    assert "최종검증 수익률" in playbook["actionable_reason"]
    assert "분할 매수" not in playbook["entry_rule"]
    assert "추천" not in playbook["actionable_reason"]


def test_strategy_evaluation_uses_only_latest_clean_price_segment():
    from kr_quant.strategy.run import evaluate_ticker

    first = [100.0 + index * 0.1 for index in range(50)]
    second = [200.0 + index * 0.1 for index in range(50)]
    close = first + second
    data = pd.DataFrame(
        {
            "date": pd.date_range("2025-01-02", periods=100, freq="B"),
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1_000] * 100,
            "listed_shares": [1_000] * 100,
            "market_cap": [value * 1_000 for value in close],
        }
    )

    result = evaluate_ticker(data, slippage_bps=0, oos_ratio=0.2, min_days=40)

    assert result["ok"] is True
    assert result["raw_bars"] == 100
    assert result["bars"] == 50
    assert result["from"] == str(data.iloc[50]["date"].date())
    assert result["price_integrity"]["issue_counts"] == {"UNEXPLAINED_PRICE_DISCONTINUITY": 1}


def test_params_and_comments_are_korean():
    from kr_quant.strategy.registry import SELECTION_KO, format_params_ko, strategy_comment
    from kr_quant.strategy.run import annotate_strategy_payload

    text = format_params_ko({"overbought": 70, "oversold": 25, "period": 10})
    assert "과매수 70" in text
    assert "과매도 25" in text
    assert "기간 10일" in text
    assert "overbought" not in text
    comment = strategy_comment(
        {
            "name": "RSI 평균회귀",
            "strategy_id": "rsi_reversion",
            "family": "MEAN_REVERSION",
            "params": {"overbought": 70, "oversold": 25, "period": 10},
            "stability_label": "LOW",
            "wf_hit": 0,
            "wf_windows": 2,
            "trade_count": 0,
            "oos_sharpe": 1.77,
            "max_drawdown": -0.12,
        }
    )
    assert "과매도" in comment
    assert "학습" in comment
    assert "LOW" in comment
    assert "overbought" not in comment
    payload = annotate_strategy_payload(
        {
            "rows": [
                {
                    "best_name": "RSI 평균회귀",
                    "strategies": [
                        {
                            "name": "RSI 평균회귀",
                            "family": "MEAN_REVERSION",
                            "params": {"period": 10, "oversold": 25, "overbought": 70},
                            "stability_label": "LOW",
                        }
                    ],
                }
            ]
        }
    )
    rec = payload["rows"][0]
    assert "기간 10일" in rec["best_params_ko"]
    assert rec["best_comment"]
    assert payload["selection"] == SELECTION_KO
