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


def test_tier1_hops_honor_user_selection_and_stay_fail_closed():
    settings = SimpleNamespace(
        openrouter_api_key='test-key', xai_api_key='x-test', opencode_go_api_key='go-test',
        deepseek_api_key=None, opencode_api_key=None, xai_base_url=None,
        tier1_routine_provider='opencode_go', tier1_routine_model='deepseek/deepseek-v4.1-flash',
        tier1_analysis_provider='opencode_go', tier1_analysis_model='glm-5.3-flash',
    )
    routine = providers.resolve_tier1_endpoint(settings)
    assert (routine.provider, routine.model) == ('opencode_go', 'deepseek-v4.1-flash')
    assert routine.configured and routine.label == 'OpenCode Go'
    analysis = providers.resolve_tier1_analysis_endpoint(settings)
    assert (analysis.provider, analysis.model) == ('opencode_go', 'glm-5.3-flash')
    assert analysis.configured
    # A selected provider without its own key stays unavailable instead of
    # borrowing another provider's key.
    missing = SimpleNamespace(**{**vars(settings), 'opencode_go_api_key': None})
    ep = providers.resolve_tier1_endpoint(missing)
    assert ep.provider == 'tier1_unavailable' and not ep.configured
    assert ep.base_url == ''
    # Unknown provider/model falls back to the hop default, never another hop.
    weird = SimpleNamespace(**{**vars(settings), 'tier1_routine_provider': 'nope', 'tier1_routine_model': ''})
    ep2 = providers.resolve_tier1_endpoint(weird)
    assert (ep2.provider, ep2.model) == ('openrouter', providers.TIER1_FREE_MODEL)
    # A Go model outside the chat/completions catalog cannot be called and
    # resolves to the provider default instead of failing mid-request.
    odd = SimpleNamespace(**{**vars(settings), 'tier1_routine_model': 'muse-spark-1.3-contributor'})
    ep3 = providers.resolve_tier1_endpoint(odd)
    assert (ep3.provider, ep3.model) == ('opencode_go', 'deepseek-v4-pro')
