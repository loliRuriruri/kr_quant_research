"""Read-only old/new peer-score replay; not a full PIT pipeline rerun.

Uses only finite raw values with saved peer_n>0 (known participating metrics).
Eligibility and penalties are held fixed, so this is a diagnostic sensitivity
analysis, not a replacement production ranking.
"""
from __future__ import annotations
import copy
import json
import math
import subprocess
import types
from types import SimpleNamespace
import pandas as pd
from kr_quant.models import MetricResult
from kr_quant.scoring.peers import assign_peer_scores
from kr_quant.settings import load_settings


def main():
    settings = load_settings()
    frame = pd.read_parquet(settings.output_dir / "latest_all_stocks.parquet")
    old = types.ModuleType("audit_baseline_peers")
    source = subprocess.check_output(["git", "show", "bd09ece:src/kr_quant/scoring/peers.py"], cwd=settings.root, text=True, encoding="utf-8")
    exec(compile(source, "bd09ece:peers.py", "exec"), old.__dict__)
    cfg = settings.config
    print("config_keys", list(cfg))
    peer_cfg = cfg.get("peer_scoring") or cfg.get("peer_groups") or cfg.get("peers")
    if not peer_cfg:
        raise ValueError("Peer configuration not located")
    changes = []
    delta = {str(row.ticker): 0. for row in frame.itertuples()}
    for factor, spec in cfg["factors"].items():
        for metric, mspec in spec["metrics"].items():
            names = []
            for row in frame.to_dict("records"):
                raw = (row.get("metric_values") or {}).get(metric)
                context = (row.get("metric_peer_context") or {}).get(metric) or {}
                if raw is None or not math.isfinite(raw) or not context.get("peer_n"):
                    continue
                inp = SimpleNamespace(**{k: row.get(k) for k in ("industry", "industry_code", "sector", "sector_code")})
                names.append(SimpleNamespace(ticker=str(row["ticker"]), inputs=inp, metric_peer_context={}, metrics={metric: MetricResult(metric, raw, "VALID", participates_in_percentile=True, counts_as_observed=True)}))
            before = copy.deepcopy(names)
            direction = mspec.get("direction", "higher")
            old.assign_peer_scores(before, metric, direction, peer_cfg)
            assign_peer_scores(names, metric, direction, peer_cfg)
            count = 0
            for a, b in zip(before, names):
                diff = float(b.metrics[metric].score or 0) - float(a.metrics[metric].score or 0)
                if abs(diff) > 1e-9:
                    count += 1
                    delta[b.ticker] += diff * float(mspec["weight"]) / 100
            changes.append({"metric": metric, "participating_rows": len(names), "changed": count})
    print(json.dumps({"as_of": str(frame["as_of_date"].max()), "rows": len(frame), "metrics": changes,
                      "nonzero_weighted_delta_tickers": sum(abs(v) > 1e-8 for v in delta.values()),
                      "max_absolute_weighted_delta": max(map(abs, delta.values()), default=0),
                      "limitations": "Saved known participants only; eligibility/penalties fixed; not full production rank replay."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
