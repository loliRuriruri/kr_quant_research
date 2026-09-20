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
    assert set(PROVIDERS) == {"xai", "antigravity", "deepseek", "openrouter", "opencode", "opencode_go"}
    assert resolve_provider(_S(), "openai").provider == "xai"


def test_opencode_zen_provider():
    from kr_quant.research.providers import coerce_model, fallback_models, list_chat_models, model_fits_provider, normalize_provider, sort_models

    assert normalize_provider("opencode") == "opencode"
    assert normalize_provider("zen") == "opencode"

    class S(_S):
        llm_provider = "opencode"
        llm_model = None
        opencode_api_key = "zen-test"

    ep = resolve_provider(S())
    assert ep.provider == "opencode"
    assert ep.base_url == "https://opencode.ai/zen/v1"
    assert ep.model == "deepseek/deepseek-v4-flash-0731"
    assert ep.configured
    assert model_fits_provider("opencode", "openai/gpt-5.6-luna")
    assert model_fits_provider("opencode", "kimi-k2.5")
    assert coerce_model("opencode", "openai/gpt-5.6-luna") == "openai/gpt-5.6-luna"
    curated = list_chat_models(ep)
    assert curated == fallback_models("opencode") == sort_models("opencode", curated)
    assert len(curated) == 8

    class NoKey(_S):
        llm_provider = "opencode"
        llm_model = None
        opencode_api_key = None

    assert resolve_provider(NoKey()).configured is False


def test_opencode_go_provider():
    from kr_quant.research.providers import (
        coerce_model,
        extra_headers,
        fallback_models,
        list_chat_models,
        model_fits_provider,
        normalize_provider,
        sort_models,
    )

    assert normalize_provider("opencode-go") == "opencode_go"

    class S(_S):
        llm_provider = "opencode_go"
        llm_model = None
        opencode_go_api_key = "go-test"

    ep = resolve_provider(S())
    assert ep.provider == "opencode_go"
    assert ep.base_url == "https://opencode.ai/zen/go/v1"
    assert ep.model == "deepseek-v4-pro"
    assert ep.configured
    assert model_fits_provider("opencode_go", "deepseek/deepseek-v4.1-flash")
    assert model_fits_provider("opencode_go", "minimax-m3")
    # Go serves short ids on the chat surface; prefixed ids are coerced.
    assert coerce_model("opencode_go", "deepseek/deepseek-v4.1-flash") == "deepseek-v4.1-flash"
    assert coerce_model("opencode_go", "zhipuai/glm-5.3-flash") == "glm-5.3-flash"
    assert coerce_model("opencode_go", "deepseek-v4.1-flash") == "deepseek-v4.1-flash"
    assert coerce_model("opencode_go", "unknown/thing") == "deepseek-v4-pro"
    assert coerce_model("opencode_go", "muse-spark") == "muse-spark-1.3-contributor"
    assert coerce_model("opencode_go", "muse-spark-1.3") == "muse-spark-1.3-contributor"
    headers = extra_headers(ep)
    assert "x-opencode-session" in headers
    assert headers["User-Agent"] == "kr-quant-research/1.0"
    curated = list_chat_models(ep)
    assert curated == fallback_models("opencode_go") == sort_models("opencode_go", curated)
    assert len(curated) == 9
    assert "muse-spark-1.3-contributor" in curated
    assert all("/" not in m for m in curated)


def test_antigravity_provider():
    ep = resolve_provider(_S(), "antigravity")
    assert ep.provider == "antigravity"
    assert ep.base_url == "cli://agy"
    assert "gemini" in ep.model



def test_rejects_quant_fields():
    try:
        sanitize_research({"research_score": 10, "quant_score": 80})
    except RuntimeError as exc:
        assert "quant_score" in str(exc)
        return
    raise AssertionError("expected reject")
