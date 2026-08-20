from kr_quant.research.analyze import sanitize_research
from kr_quant.research.providers import DEFAULT_PROVIDER, PROVIDERS, resolve_provider


class _S:
    llm_provider = "xai"
    llm_model = None
    xai_api_key = "xai-test"
    deepseek_api_key = None
    openrouter_api_key = "or-test"
    xai_base_url = "https://api.x.ai/v1"
    custom_llm_base_url = "http://127.0.0.1:11434/v1"
    custom_llm_api_key = None


def test_default_is_grok():
    assert DEFAULT_PROVIDER == "xai"
    ep = resolve_provider(_S())
    assert ep.provider == "xai"
    assert ep.model == "grok-4.6"
    assert ep.configured


def test_alias_grok():
    assert resolve_provider(_S(), "grok").provider == "xai"


def test_openrouter():
    ep = resolve_provider(_S(), "openrouter")
    assert ep.provider == "openrouter"
    assert "openrouter.ai" in ep.base_url
    assert ep.model.startswith("openai/") or "/" in ep.model


def test_xai_drops_openrouter_model():
    class S(_S):
        llm_provider = "xai"
        llm_model = "deepseek/deepseek-v4-flash-0731"

    ep = resolve_provider(S())
    assert ep.provider == "xai"
    assert ep.model == "grok-4.6"
    assert "/" not in ep.model


def test_removed_providers_fall_back_to_grok():
    assert "openai" not in PROVIDERS
    assert set(PROVIDERS) == {"xai", "deepseek", "openrouter"}
    assert resolve_provider(_S(), "openai").provider == "xai"
    assert resolve_provider(_S(), "opencode").provider == "xai"


def test_rejects_quant_fields():
    try:
        sanitize_research({"research_score": 10, "quant_score": 80})
    except RuntimeError as exc:
        assert "quant_score" in str(exc)
        return
    raise AssertionError("expected reject")
