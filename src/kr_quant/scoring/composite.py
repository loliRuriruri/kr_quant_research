from __future__ import annotations

from datetime import date
from typing import Any

from kr_quant.models import MetricResult, ScoredName


FACTOR_KEYS = {
    "value": "value_score",
    "quality": "quality_score",
    "growth": "growth_score",
    "momentum": "momentum_score",
    "financial_stability": "financial_score",
}


def factor_specs(cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    out = []
    for factor_name, spec in cfg["factors"].items():
        for metric_name, mspec in spec["metrics"].items():
            out.append((factor_name, metric_name, mspec))
    return out


def metric_weight_total(cfg: dict[str, Any]) -> float:
    return float(sum(mspec["weight"] for _, _, mspec in factor_specs(cfg)))


def contribution(weight: float, score: float | None) -> float:
    if score is None:
        return 0.0
    return weight * score / 100.0


def factor_score(names_metrics: dict[str, MetricResult], spec: dict[str, Any]) -> tuple[float, float, bool]:
    """Return (points, observed_weight, unreliable)."""
    total_w = 0.0
    observed_w = 0.0
    points = 0.0
    for metric_name, mspec in spec["metrics"].items():
        w = float(mspec["weight"])
        total_w += w
        m = names_metrics.get(metric_name)
        if m is None:
            continue
        points += contribution(w, m.score if m.score is not None else 50.0)
        if m.counts_as_observed:
            observed_w += w
    unreliable = total_w > 0 and (observed_w / total_w) < 0.60
    return points, observed_w, unreliable


def _momentum_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("factors", {}).get("momentum", {}).get("enabled", False))


def enabled_weight_total(cfg: dict[str, Any]) -> float:
    total = 0.0
    for factor, _name, mspec in factor_specs(cfg):
        if factor == "momentum" and not _momentum_enabled(cfg):
            continue
        total += float(mspec["weight"])
    return total or 100.0


def weighted_coverage(metrics: dict[str, MetricResult], cfg: dict[str, Any]) -> float:
    observed = 0.0
    denom = 0.0
    for factor, metric_name, mspec in factor_specs(cfg):
        if factor == "momentum" and not _momentum_enabled(cfg):
            continue
        w = float(mspec["weight"])
        denom += w
        m = metrics.get(metric_name)
        if m and m.counts_as_observed:
            observed += w
    return observed / denom if denom else 0.0


def freshness_component(period_end: date | None, as_of: date, cfg: dict[str, Any]) -> float:
    if period_end is None:
        return 0.0
    days = (as_of - period_end).days
    if days < 0:
        return 0.0
    bands = cfg["data_confidence"]["freshness_days"]
    if days <= int(bands["full"]):
        return 1.0
    if days <= int(bands["high"]):
        return 0.8
    if days <= int(bands["mid"]):
        return 0.5
    return 0.0


def data_confidence(
    coverage: float,
    pit: float,
    freshness: float,
    recon: float,
    history: float,
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    comps = {
        "coverage": coverage,
        "pit_integrity": pit,
        "freshness": freshness,
        "reconciliation": recon,
        "history": history,
    }
    score = 100.0 * (
        weights["coverage"] * coverage
        + weights["pit_integrity"] * pit
        + weights["freshness"] * freshness
        + weights["reconciliation"] * recon
        + weights["history"] * history
    )
    return score, comps


def apply_composite(name: ScoredName, cfg: dict[str, Any], as_of: date) -> None:
    factors = cfg["factors"]
    v, v_obs, v_bad = factor_score(name.metrics, factors["value"])
    q, q_obs, q_bad = factor_score(name.metrics, factors["quality"])
    g, g_obs, g_bad = factor_score(name.metrics, factors["growth"])
    m, m_obs, m_bad = factor_score(name.metrics, factors["momentum"])
    f, f_obs, f_bad = factor_score(name.metrics, factors["financial_stability"])
    name.value_score = v
    name.quality_score = q
    name.growth_score = g
    name.momentum_score = m
    name.financial_score = f
    name.quant_score_raw = v + q + g + m + f
    name.quant_score = max(0.0, name.quant_score_raw - name.risk_penalty)
    name.coverage = weighted_coverage(name.metrics, cfg)
    if v_bad:
        name.data_flags.append("VALUE_UNRELIABLE")
    if q_bad:
        name.data_flags.append("QUALITY_UNRELIABLE")
    if g_bad:
        name.data_flags.append("GROWTH_UNRELIABLE")
    if m_bad:
        name.data_flags.append("MOMENTUM_UNRELIABLE")
    if f_bad:
        name.data_flags.append("STABILITY_UNRELIABLE")

    fresh = freshness_component(name.inputs.latest_period_end, as_of, cfg)
    conf, comps = data_confidence(
        coverage=name.coverage,
        pit=name.inputs.pit_integrity,
        freshness=fresh,
        recon=name.inputs.recon_score,
        history=name.inputs.history_score,
        weights=cfg["data_confidence"]["weights"],
    )
    name.data_confidence = conf
    name.confidence_components = comps
    name.metric_peer_scores = {k: (m.score if m.score is not None else 50.0) for k, m in name.metrics.items()}
    name.metric_values = {k: m.raw for k, m in name.metrics.items()}
