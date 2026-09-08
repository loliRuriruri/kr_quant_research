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


def test_routine_flash_and_analysis_pro_are_openrouter_named_hops():
    settings = SimpleNamespace(openrouter_api_key='test-key')
    flash = providers.resolve_tier1_routine_paid_endpoint(settings)
    pro = providers.resolve_tier1_analysis_pro_endpoint(settings)
    assert flash.configured and flash.model == providers.TIER1_ROUTINE_PAID_MODEL
    assert pro.configured and pro.model == providers.TIER1_ANALYSIS_PRO_MODEL
    assert flash.provider == 'openrouter' and pro.provider == 'openrouter'
    missing = providers.resolve_tier1_routine_paid_endpoint(SimpleNamespace(openrouter_api_key=None))
    assert not missing.configured
