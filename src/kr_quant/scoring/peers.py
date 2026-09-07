from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from kr_quant.models import MetricResult, ScoredName


def average_ranks(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = ((i + 1) + (j + 1)) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def percentile_high(ranks: list[float]) -> list[float]:
    n = len(ranks)
    if n < 2:
        return [50.0] * n
    return [float(np.clip(100.0 * (r - 1.0) / (n - 1), 0.0, 100.0)) for r in ranks]


def winsor_bounds(values: list[float], n: int, cfg: dict[str, Any]) -> tuple[float, float]:
    large = cfg["winsor"]["large_n"]
    medium = cfg["winsor"]["medium_n"]
    if n >= int(large["min_n"]):
        lo, hi = float(large["lower"]), float(large["upper"])
    else:
        lo, hi = float(medium["lower"]), float(medium["upper"])
    arr = np.asarray(values, dtype=float)
    return float(np.quantile(arr, lo)), float(np.quantile(arr, hi))


def clip(value: float, lo: float, hi: float) -> float:
    return float(min(max(value, lo), hi))


def _group_key(name: ScoredName, level: str) -> str | None:
    inp = name.inputs
    if level == "industry":
        return inp.industry_code or inp.industry
    if level == "sector":
        return inp.sector_code or inp.sector
    if level == "market":
        return "MARKET"
    return None


def assign_peer_scores(
    names: list[ScoredName],
    metric_name: str,
    direction: str,
    peer_cfg: dict[str, Any],
) -> None:
    hierarchy = peer_cfg["hierarchy"]
    last_resort = int(peer_cfg.get("last_resort_min_n", 2))

    candidates: list[tuple[int, MetricResult]] = []
    for i, nm in enumerate(names):
        m = nm.metrics.get(metric_name)
        if m and m.participates_in_percentile and (m.raw is None or not np.isfinite(m.raw)):
            m.score = 50.0
            m.state = "DATA_MISSING"
            m.participates_in_percentile = False
            m.counts_as_observed = False
            m.flags = [*m.flags, "NONFINITE_METRIC"]
        if m and m.participates_in_percentile and m.raw is not None:
            candidates.append((i, m))

    if not candidates:
        return

    assigned: set[int] = set()
    for spec in hierarchy:
        level = spec["level"]
        min_n = int(spec["min_valid_n"])
        buckets: dict[str, list[tuple[int, MetricResult]]] = defaultdict(list)
        for i, m in candidates:
            key = _group_key(names[i], level)
            if key:
                buckets[key].append((i, m))
        for key, items in buckets.items():
            if len(items) < min_n:
                continue
            if all(i in assigned for i, _ in items):
                continue
            _score_bucket(items, names, metric_name, direction, peer_cfg, level, key, skip=assigned)
            assigned.update(i for i, _ in items)

    leftover = [(i, m) for i, m in candidates if i not in assigned]
    if leftover and len(candidates) >= last_resort:
        _score_bucket(candidates, names, metric_name, direction, peer_cfg, "market", "MARKET", skip=assigned)
        assigned.update(i for i, _ in leftover)

    for i, m in candidates:
        if i not in assigned:
            m.score = 50.0
            m.state = "DATA_MISSING"
            m.participates_in_percentile = False
            m.counts_as_observed = False
            m.flags = [*m.flags, "PEER_SAMPLE_TOO_SMALL"]
            m.peer_level = None
            m.peer_n = 0


def _score_bucket(
    items: list[tuple[int, MetricResult]],
    names: list[ScoredName],
    metric_name: str,
    direction: str,
    peer_cfg: dict[str, Any],
    level: str,
    code: str,
    *,
    skip: set[int] | None = None,
) -> None:
    raws = [m.raw for _, m in items if m.raw is not None]
    n = len(raws)
    lo, hi = winsor_bounds(raws, n, peer_cfg)
    clipped = [clip(m.raw, lo, hi) for _, m in items]
    ranks = average_ranks(clipped)
    highs = percentile_high(ranks)
    for (i, m), cval, ph in zip(items, clipped, highs):
        if skip and i in skip:
            continue
        score = ph if direction == "higher" else 100.0 - ph
        m.clipped = cval
        m.score = float(np.clip(score, 0.0, 100.0))
        m.peer_level = level
        m.peer_code = code
        m.peer_n = n
        names[i].metric_peer_context[metric_name] = {
            "peer_level": level,
            "peer_code": code,
            "peer_n": n,
            "clipped": cval,
        }
