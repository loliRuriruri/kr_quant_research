# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
import pytest

from kr_quant.ingest import kis
from kr_quant.ingest.kis import KisInvestorAdapter, KisTokenError, KisTokenRateLimited, clear_token_cache, token_meta


class FakeResp:
    def __init__(self, status: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_token(tmp_path, monkeypatch):
    clear_token_cache()
    monkeypatch.setattr(kis, "protect_bytes", lambda data: None)
    monkeypatch.setattr(kis, "unprotect_bytes", lambda blob: None)
    yield
    clear_token_cache()


def _adapter(tmp_path) -> KisInvestorAdapter:
    return KisInvestorAdapter("k" * 16, "s" * 30, "https://example.invalid", cache_path=tmp_path / "kis_token.dpapi")


def test_concurrent_collect_issues_one_token(tmp_path, monkeypatch):
    posts = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(200, {"access_token": "tok-once", "expires_in": 86400})

    monkeypatch.setattr("requests.post", fake_post)
    adapter = _adapter(tmp_path)
    with ThreadPoolExecutor(max_workers=20) as pool:
        tokens = list(pool.map(lambda _: adapter.token(reason="collect"), range(20)))
    assert posts["n"] == 1
    assert set(tokens) == {"tok-once"}


def test_cached_token_skips_second_issue(tmp_path, monkeypatch):
    posts = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(200, {"access_token": "tok-a", "expires_in": 86400})

    monkeypatch.setattr("requests.post", fake_post)
    adapter = _adapter(tmp_path)
    assert adapter.token(reason="collect") == "tok-a"
    assert adapter.token(reason="connection_test") == "tok-a"
    assert posts["n"] == 1
    status = adapter.token_status()
    assert status["cached"] is True
    assert "access_token" not in status
    assert "tok-a" not in json.dumps(status)


def test_rate_limit_does_not_retry_immediately(tmp_path, monkeypatch):
    posts = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(403, {}, text="EGW00133 1분당 1회 접근토큰 발급")

    monkeypatch.setattr("requests.post", fake_post)
    adapter = _adapter(tmp_path)
    with pytest.raises(KisTokenRateLimited) as first:
        adapter.token(reason="collect")
    with pytest.raises(KisTokenRateLimited):
        adapter.token(reason="collect")
    assert posts["n"] == 1
    assert first.value.retry_at > 0
    meta = token_meta()
    assert meta["can_issue"] is False
    assert meta["retry_at"]


def test_401_refreshes_once_then_stops(tmp_path, monkeypatch):
    posts = {"n": 0}
    gets = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(200, {"access_token": f"tok-{posts['n']}", "expires_in": 86400})

    def fake_get(*_a, **_k):
        gets["n"] += 1
        return FakeResp(401, {}, text="expired")

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.get", fake_get)
    adapter = _adapter(tmp_path)
    with pytest.raises(KisTokenError, match="401"):
        adapter.fetch_stock_investor("005930")
    assert posts["n"] == 2
    assert gets["n"] == 2


def test_token_logs_have_no_secrets(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="kr_quant.ingest.kis")

    def fake_post(*_a, **_k):
        return FakeResp(200, {"access_token": "super-secret-token", "expires_in": 86400})

    monkeypatch.setattr("requests.post", fake_post)
    adapter = _adapter(tmp_path)
    adapter.token(reason="collect")
    text = caplog.text
    assert "super-secret-token" not in text
    assert "appsecret" not in text.lower()
    assert "s" * 30 not in text
    assert "reason=collect" in text


def test_persistent_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(kis, "protect_bytes", lambda data: data)
    monkeypatch.setattr(kis, "unprotect_bytes", lambda blob: blob)
    posts = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(200, {"access_token": "tok-disk", "expires_in": 86400})

    monkeypatch.setattr("requests.post", fake_post)
    path = tmp_path / "kis_token.dpapi"
    first = KisInvestorAdapter("k" * 16, "s" * 30, "https://example.invalid", cache_path=path)
    first.token(reason="collect")
    clear_token_cache()
    assert token_meta()["cached"] is False
    second = KisInvestorAdapter("k" * 16, "s" * 30, "https://example.invalid", cache_path=path)
    assert second.token(reason="collect") == "tok-disk"
    assert posts["n"] == 1


def test_stock_detail_does_not_auto_collect_kis():
    import inspect

    from kr_quant.web.app import api_stock

    source = inspect.getsource(api_stock)
    assert "collect_stock" not in source
    assert "adapter.token" not in source


def test_new_adapter_reuses_memory_cache_without_issue(tmp_path, monkeypatch):
    posts = {"n": 0}

    def fake_post(*_a, **_k):
        posts["n"] += 1
        return FakeResp(200, {"access_token": "tok-cached", "expires_in": 86400})

    monkeypatch.setattr("requests.post", fake_post)
    first = _adapter(tmp_path)
    first.token(reason="collect")
    second = KisInvestorAdapter("k" * 16, "s" * 30, "https://example.invalid", cache_path=tmp_path / "other.dpapi")
    status = second.token_status()
    assert status["cached"] is True
    assert second.token(reason="connection_test") == "tok-cached"
    assert posts["n"] == 1
    assert "access_token" not in status
    assert "tok-cached" not in json.dumps(status)
