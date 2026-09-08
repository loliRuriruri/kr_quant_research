from types import SimpleNamespace
import pytest
from kr_quant.research import providers
from kr_quant.research.analyze import call_chat


def test_missing_free_key_never_resolves_paid_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('paid provider must not be resolved')
    monkeypatch.setattr(providers, 'resolve_provider', forbidden)
    endpoint = providers.resolve_tier1_endpoint(SimpleNamespace(openrouter_api_key=None))
    assert not endpoint.configured
    assert endpoint.base_url == ''
    with pytest.raises(RuntimeError, match='자동 전환하지 않습니다'):
        call_chat(endpoint, [])


def test_free_route_and_explicit_paid_route_are_separate(monkeypatch):
    endpoint = providers.resolve_tier1_endpoint(SimpleNamespace(openrouter_api_key='test-key'))
    assert endpoint.provider == 'openrouter'
    assert endpoint.model.endswith(':free')
    selected = object()
    monkeypatch.setattr(providers, 'resolve_provider', lambda settings: selected)
    assert providers.resolve_tier2_endpoint(SimpleNamespace()) is selected
