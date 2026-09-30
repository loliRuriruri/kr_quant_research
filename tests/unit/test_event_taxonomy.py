"""Forward-only synthetic fixtures; never use or rewrite V3.1 review records."""
import copy
from types import SimpleNamespace

import pandas as pd
import pytest

from kr_quant.strategy import event_explainer as events
from kr_quant.strategy.discovery_engine import pattern_from_month_stat
from kr_quant.strategy.seasonality import _load_scored_map
from kr_quant.research.season_jev_shadow import project_season_state, state_hash
from kr_quant.web.season_snapshot import source_identity


def pattern(ticker="192820", company="코스맥스"):
    return pattern_from_month_stat(ticker, company, "KOSPI", {
        "month": 12, "history": [.12, .08, -.03, .15, .07],
        "win_rate": .8, "median_return": .08, "years_count": 5,
    }, lookback_years=5)


def test_cosmax_synthetic_specific_cosmetics_never_battery():
    row = events.explain_and_score_pattern(pattern(), {
        "company": "코스맥스", "sector": "화학", "industry": "화장품 제조업"})
    assert "배터리" not in (row["event_hypothesis"] or "")
    assert row["event_mapping_rule_id"] == "consumer"
    assert row["event_mapping_source_fields"]["sector"] == "화학"


@pytest.mark.parametrize("fields, mode", [
    ({"sector": "화학", "industry": "화학물질 및 화학제품 제조업"}, "DOMAIN_UNMAPPED"),
    ({"sector": "배터리", "industry": "화장품 제조업"}, "DOMAIN_AMBIGUOUS"),
    ({"company": "가상배터리화장품"}, "DOMAIN_UNMAPPED"),
    ({"sector": None, "industry": float("nan")}, "DOMAIN_UNMAPPED"),
    ({"industry": "금속"}, "DOMAIN_UNMAPPED"),
])
def test_unmapped_or_multi_domain_fails_closed(fields, mode):
    row = events.explain_and_score_pattern(pattern("123456", "가상회사"), fields)
    assert row["event_hypothesis"] is None
    assert row["event_explanation_mode"] == mode
    assert row["event_confidence"] == "UNKNOWN"


def test_rules_have_stable_ids_and_order_does_not_change_result(monkeypatch):
    p = pattern()
    fields = {"industry": " 화장품   제조업 ", "sector": "화학"}
    expected = events.explain_and_score_pattern(p, fields)
    monkeypatch.setattr(events, "_DOMAIN_CATALYST_RULES", tuple(reversed(events._DOMAIN_CATALYST_RULES)))
    assert events.explain_and_score_pattern(p, fields) == expected


def test_provenance_projects_and_changes_state_hash():
    row = events.explain_and_score_pattern(pattern(), {"industry": "화장품"})
    row.update(signal_id="synthetic", generation_id="forward-generation")
    state = project_season_state(row)
    assert state["event"]["mappingProvenance"]["ruleId"] == "consumer"
    altered = copy.deepcopy(state)
    altered["event"]["mappingProvenance"]["version"] = "different"
    assert state_hash(state, "test") != state_hash(altered, "test")


def test_consumed_scored_file_sha_and_generation_are_attached(tmp_path):
    s = SimpleNamespace(output_dir=tmp_path)
    p = tmp_path / "latest_all_stocks.parquet"
    pd.DataFrame([{"ticker": "192820", "company": "코스맥스", "industry": "화장품"}]).to_parquet(p)
    import hashlib
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    row = _load_scored_map(s)["192820"]
    assert row["event_source_provenance"]["file_sha256"] == sha
    assert row["event_source_provenance"]["generation_id"] == "sha256:" + sha
    assert row["event_source_provenance"]["file_path"] == str(p.resolve())


def test_bundle_identity_uses_content_sha_even_same_stat(tmp_path):
    import os
    s = SimpleNamespace(root=tmp_path, data_dir=tmp_path / "data", staged_dir=tmp_path / "data/staged",
                        output_dir=tmp_path / "data/output", status_csv=tmp_path / "status.csv", config={})
    p = s.output_dir / "latest_all_stocks.parquet"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"aaaa")
    first = source_identity(s, 5)
    stat = p.stat()
    p.write_bytes(b"bbbb")
    os.utime(p, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    second = source_identity(s, 5)
    assert first != second
    assert first["source_file_provenance"] != second["source_file_provenance"]


def test_forward_bundle_to_state_provenance_in_temporary_workspace(tmp_path, monkeypatch):
    from kr_quant.web import season_snapshot as snapshots
    from kr_quant.strategy import seasonality as engine
    import hashlib
    s = SimpleNamespace(root=tmp_path, data_dir=tmp_path / "data", staged_dir=tmp_path / "data/staged",
                        output_dir=tmp_path / "data/output", status_csv=tmp_path / "status.csv", config={})
    s.output_dir.mkdir(parents=True)
    p = s.output_dir / "latest_all_stocks.parquet"
    pd.DataFrame([{"ticker": "192820", "company": "코스맥스", "sector": "화학", "industry": "화장품"}]).to_parquet(p)
    def scan(*args, **kwargs):
        row = events.explain_and_score_pattern(pattern(), _load_scored_map(s)["192820"])
        return [row]
    monkeypatch.setattr(engine, "scan_seasonality_discovery", scan)
    monkeypatch.setattr(engine, "scan_seasonality", lambda *a, **k: [])
    monkeypatch.setattr(engine, "seasonality_universe_stats", lambda *a: {})
    monkeypatch.setattr(engine, "get_seasonality_highlights", lambda *a, **k: {})
    monkeypatch.setattr(snapshots, "_MEM", {})
    bundle = snapshots.build_bundle(s)
    row = bundle["payload"]["rows"][0]
    state = project_season_state(row)
    provenance = state["event"]["mappingProvenance"]
    assert provenance["sourceProvenance"]["file_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert provenance["seasonGenerationId"] == bundle["generation_id"]
    assert provenance["sourceFields"]["industry"] == "화장품"
    assert provenance["ruleId"] == "consumer"
    assert state["event"]["eventHypothesis"] == row["event_hypothesis"]
    provenance["sourceFields"]["industry"] = "altered"
    assert row["event_mapping_source_fields"]["industry"] == "화장품"


def test_curated_and_historical_paths_are_separately_identified():
    ticker = next(iter(events.EVENT_KNOWLEDGE_BASE))
    curated = events.explain_and_score_pattern(pattern(ticker, "검토종목"), {"industry": "화장품"})
    assert curated["event_explanation_mode"] == "CURATED_TICKER"
    assert curated["event_mapping_rule_id"] == "CURATED:" + ticker + ":v1"
    historical = events.explain_and_score_pattern(pattern(), event_context={
        "common_event": "명시된 과거 가설", "secondary_event": "과거 확인 항목",
        "invalidating_rules": "과거 무효화 조건", "source": "합성 과거 입력", "confidence": "LOW"})
    assert historical["event_explanation_mode"] == "HISTORICAL_INPUT_UNVERIFIED"
    assert historical["event_mapping_rule_id"] == "historical_input"


def test_missing_provenance_keeps_legacy_projection_unchanged():
    state = project_season_state({"ticker": "192820", "event_explanation_mode": "RULE_BASED"})
    assert "mappingProvenance" not in state["event"]
    assert "eventHypothesis" not in state["event"]


def test_taxonomy_alias_order_and_mixed_domain_separators(monkeypatch):
    from kr_quant.strategy import event_taxonomy as taxonomy
    row = {"industry": "배터리/화장품"}
    first = taxonomy.classify_domain(row)
    monkeypatch.setattr(taxonomy, "DOMAIN_ALIASES", dict(reversed(list(taxonomy.DOMAIN_ALIASES.items()))))
    assert taxonomy.classify_domain(row) == first
    assert first["ambiguity"] is True
    assert first["rule_id"] is None


def test_domain_field_and_projection_are_explicit():
    row = events.explain_and_score_pattern(pattern(), {"industry": "화장품"})
    assert row["event_mapping_domain"] == "consumer"
    state = project_season_state(row)
    assert state["event"]["mappingProvenance"]["domain"] == "consumer"
    assert not any(k in str(state) for k in ("seasonality_score", "pre_entry_rank", "quant_score"))


@pytest.mark.parametrize("industry,domain", [("전자부품반도체", "semiconductor"),
    ("식료품", "consumer"), ("종합건설", "construction"), ("수상운송", "transport")])
def test_current_source_exact_labels(industry, domain):
    from kr_quant.strategy.event_taxonomy import classify_domain
    assert classify_domain({"sector": "제조업", "industry": industry})["domain"] == domain


def committed_fixture(tmp_path):
    import hashlib, json
    folder = tmp_path / "generations" / "synthetic-run"
    folder.mkdir(parents=True)
    p = folder / "latest_all_stocks.parquet"
    pd.DataFrame([{"ticker": "192820", "industry": "화장품"}]).to_parquet(p)
    manifest = {"run_id": "synthetic-run", "generation_dir": str(folder), "files": {
        p.name: {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}}}
    (tmp_path / "current_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pd.DataFrame([{"ticker": "192820", "industry": "배터리"}]).to_parquet(tmp_path / p.name)
    return p, manifest


def test_committed_generation_is_consumed_instead_of_legacy_alias(tmp_path):
    p, _ = committed_fixture(tmp_path)
    row = _load_scored_map(SimpleNamespace(output_dir=tmp_path))["192820"]
    assert row["industry"] == "화장품"
    assert row["event_source_provenance"]["generation_id"] == "synthetic-run"
    assert row["event_source_provenance"]["file_path"] == str(p.resolve())
    assert row["event_source_provenance"]["manifest_sha256"]


def test_corrupt_committed_source_never_falls_back_to_alias(tmp_path):
    p, _ = committed_fixture(tmp_path)
    pd.DataFrame([{"ticker": "192820", "industry": "배터리"}]).to_parquet(p)
    assert _load_scored_map(SimpleNamespace(output_dir=tmp_path)) == {}


def test_foreign_manifest_never_follows_another_checkout(tmp_path):
    import json
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    p, manifest = committed_fixture(foreign)
    local = tmp_path / "local"
    local.mkdir()
    (local / "current_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pd.DataFrame([{"ticker": "192820", "industry": "전기장비"}]).to_parquet(local / p.name)
    row = _load_scored_map(SimpleNamespace(output_dir=local))["192820"]
    assert row["industry"] == "전기장비"
    assert row["event_source_provenance"]["generation_kind"] == "consumed_scored_file_content"


@pytest.mark.parametrize("fields", [{"industry": "화장품"}, {"industry": "배터리/화장품"}, {"industry": "새업종"}])
def test_catalog_permutations_preserve_entire_semantic_output(fields, monkeypatch):
    catalog = events._DOMAIN_CATALYST_RULES
    expected = events.explain_and_score_pattern(pattern(), fields)
    for index in range(len(catalog)):
        monkeypatch.setattr(events, "_DOMAIN_CATALYST_RULES", catalog[index:] + catalog[:index])
        assert events.explain_and_score_pattern(pattern(), fields) == expected


def test_committed_source_content_is_part_of_bundle_identity(tmp_path):
    import os
    s = SimpleNamespace(root=tmp_path, data_dir=tmp_path / "data", staged_dir=tmp_path / "data/staged",
                        output_dir=tmp_path / "data/output", status_csv=tmp_path / "status.csv", config={})
    s.output_dir.mkdir(parents=True)
    p, _ = committed_fixture(s.output_dir)
    before = source_identity(s, 5)
    raw, stat = p.read_bytes(), p.stat()
    p.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    os.utime(p, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert source_identity(s, 5) != before
    assert _load_scored_map(s) == {}


def test_curated_content_is_unchanged_by_conflicting_classification():
    for ticker, kb in events.EVENT_KNOWLEDGE_BASE.items():
        row = events.explain_and_score_pattern(pattern(ticker), {"industry": "배터리/화장품"})
        assert row["event_hypothesis"] == kb["common_event"]
        assert row["event_confidence"] == kb["confidence"]
        assert row["event_mapping_rule_id"] == f"CURATED:{ticker}:v1"
        assert row["event_mapping_domain"] is None
