from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROVIDERS = {
    "xai": {
        "label": "Grok (xAI)",
        "base_url": "https://api.x.ai/v1",
        "model": "grok-4.6",
        "env_key": "XAI_API_KEY",
        "help": "https://console.x.ai/",
        "fallback_models": [
            "grok-4.6",
            "grok-4.5",
            "grok-4.3",
            "grok-4-1-fast",
            "grok-4",
            "grok-3",
            "grok-3-mini",
            "grok-2-vision-1212",
        ],
    },
    "antigravity": {
        "label": "Antigravity CLI (Google)",
        "base_url": "cli://agy",
        "model": "gemini-2.5-pro",
        "env_key": "ANTIGRAVITY_AUTH",
        "help": "Windows 터미널에서 agy를 실행하여 Google 계정으로 로그인",
        "fallback_models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-pro",
            "gemini-2.0-flash",
            "auto",
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "help": "https://platform.deepseek.com/",
        "fallback_models": [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v3",
            "deepseek-r1",
            "deepseek-coder",
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-v4-flash-0731",
        "env_key": "OPENROUTER_API_KEY",
        "help": "https://openrouter.ai/keys",
        "fallback_models": [
            "deepseek/deepseek-v4-flash-0731",
            "deepseek/deepseek-v4-pro-0813",
            "deepseek/deepseek-v4-flash-vision-exp",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "anthropic/claude-sonnet-5",
            "openai/gpt-5.6-luna",
            "google/gemini-3.7-flash",
            "z-ai/glm-5.2",
            "upstage/solar-pro4",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
        ],
    },
    "opencode": {
        "label": "OpenCode Zen",
        "base_url": "https://opencode.ai/zen/v1",
        "model": "deepseek/deepseek-v4-flash-0731",
        "env_key": "OPENCODE_API_KEY",
        "help": "https://opencode.ai/auth",
        "fallback_models": [
            "deepseek/deepseek-v4-flash-0731",
            "openai/gpt-5.6-luna",
            "zhipuai/glm-5.3-flash",
            "google/gemini-3.7-flash",
            "anthropic/claude-sonnet-5",
            "moonshotai/kimi-k3",
            "deepseek/deepseek-v4-pro",
            "xai/grok-4.6",
        ],
    },
    "opencode_go": {
        "label": "OpenCode Go",
        "base_url": "https://opencode.ai/zen/go/v1",
        "model": "deepseek-v4-pro",
        "env_key": "OPENCODE_GO_API_KEY",
        "help": "https://opencode.ai/auth",
        # Go short model ids. Muse/Spark uses /responses via call_chat;
        # other /responses (grok-4.6, gpt-5.6-luna) and /messages (minimax, qwen)
        # models remain excluded from this chat-oriented catalog.
        "fallback_models": [
            "deepseek-v4-pro",
            "deepseek-v4.1-flash",
            "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp",
            "glm-5.3-flash",
            "kimi-k3",
            "kimi-k2.7-code",
            "mimo-v2.5",
            "muse-spark-1.3-contributor",
        ],
    },
}

DEFAULT_PROVIDER = "xai"

OPENCODE_GO_MODEL_ALIASES: dict[str, str] = {
    "deepseek/deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "deepseek/deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-vision-exp": "deepseek-v4-flash-vision-exp",
    "deepseek/deepseek-v4-pro": "deepseek-v4-pro",
    "zhipuai/glm-5.3-flash": "glm-5.3-flash",
    "zhipuai/glm-5.3": "glm-5.3",
    "zhipuai/glm-5.2": "glm-5.2",
    "moonshotai/kimi-k3": "kimi-k3",
    "moonshotai/kimi-k2.7-code": "kimi-k2.7-code",
    "muse-spark-1.3": "muse-spark-1.3-contributor",
    "muse-spark": "muse-spark-1.3-contributor",
    "muse-spark-1.3-contributor": "muse-spark-1.3-contributor",
    "muse-spark-1.2": "muse-spark-1.2-contributor",
    "muse-spark-1.2-contributor": "muse-spark-1.2-contributor",
}

OPENROUTER_MODEL_ALIASES: dict[str, str] = {
    "deepseek/deepseek-chat-0731": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-chat-0324": "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-vl": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-vl2": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-vision": "deepseek/deepseek-v4-flash-0731",
    "qwen/qwen-2.5-vl-72b-instruct": "qwen/qwen2.5-vl-72b-instruct",
}

REMOVED_PROVIDERS = frozenset({"openai", "custom"})


def normalize_provider(name: str | None) -> str:
    n = (name or DEFAULT_PROVIDER).lower().strip()
    if n in ("grok", "x_ai"):
        return "xai"
    if n in ("agy", "google", "gemini", "antigravity_cli", "google_antigravity", "antigravity"):
        return "antigravity"
    if n in ("zen", "opencode_zen", "opencodezen"):
        return "opencode"
    if n in ("opencode-go", "opencodego", "opencode_go"):
        return "opencode_go"
    if n in REMOVED_PROVIDERS:
        return DEFAULT_PROVIDER
    return n or DEFAULT_PROVIDER


def model_fits_provider(provider: str, model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    if provider == "openrouter":
        return "/" in m
    if provider in ("opencode", "opencode_go"):
        # Zen/Go serve both prefixed (author/model) and short model ids.
        return True
    if provider == "antigravity":
        return "/" not in m
    if "/" in m:
        return False
    if provider == "xai":
        return m.lower().startswith("grok")
    if provider == "deepseek":
        return m.lower().startswith("deepseek")
    return True


def coerce_model(provider: str, model: str | None) -> str:
    spec = PROVIDERS.get(provider) or PROVIDERS[DEFAULT_PROVIDER]
    m = str(model or "").strip()
    if provider == "openrouter" and m in OPENROUTER_MODEL_ALIASES:
        return OPENROUTER_MODEL_ALIASES[m]
    if provider == "opencode_go":
        if m in OPENCODE_GO_MODEL_ALIASES:
            return OPENCODE_GO_MODEL_ALIASES[m]
        short = m.split("/")[-1] if "/" in m else m
        # Only the chat/completions catalog is callable through call_chat.
        if short in set(spec["fallback_models"]):
            return short
        return str(spec["model"])
    if model_fits_provider(provider, m):
        return m
    return str(spec["model"])


@dataclass(frozen=True)
class LlmEndpoint:
    provider: str
    label: str
    base_url: str
    model: str
    api_key: str | None

    @property
    def configured(self) -> bool:
        if self.provider == "antigravity":
            return bool(self.api_key or self.base_url.startswith("cli://"))
        return bool(self.api_key)


def resolve_provider(settings: Any, provider: str | None = None) -> LlmEndpoint:
    name = normalize_provider(provider or getattr(settings, "llm_provider", None))
    if name not in PROVIDERS:
        raise ValueError(f"지원하지 않는 LLM 제공자: {name}")
    spec = PROVIDERS[name]
    session_key = None
    if name == "xai":
        try:
            from kr_quant.research.grok_auth import load_session_token

            session_key = load_session_token()
        except Exception:
            session_key = None
    elif name == "antigravity":
        try:
            from kr_quant.research.antigravity_auth import check_agy_auth

            auth_info = check_agy_auth()
            if auth_info.get("connected"):
                session_key = "antigravity-cli-cached-session"
        except Exception:
            session_key = None

    xai_key = (session_key or getattr(settings, "xai_api_key", None)) if name == "xai" else getattr(settings, "xai_api_key", None)
    key_map = {
        "xai": xai_key,
        "antigravity": session_key,
        "deepseek": getattr(settings, "deepseek_api_key", None),
        "openrouter": getattr(settings, "openrouter_api_key", None),
        "opencode": getattr(settings, "opencode_api_key", None),
        "opencode_go": getattr(settings, "opencode_go_api_key", None),
    }
    model = coerce_model(name, getattr(settings, "llm_model", None))
    base = spec["base_url"]
    if name == "xai" and getattr(settings, "xai_base_url", None):
        base = settings.xai_base_url
    return LlmEndpoint(
        provider=name,
        label=spec["label"],
        base_url=str(base).rstrip("/"),
        model=str(model or ""),
        api_key=key_map.get(name),
    )


def fallback_models(provider: str) -> list[str]:
    spec = PROVIDERS.get(provider) or {}
    return list(spec.get("fallback_models") or [])


def is_chat_model(provider: str, model: str | None) -> bool:
    m = (model or "").strip()
    if not m or not model_fits_provider(provider, m):
        return False
    low = m.lower()
    if any(tok in low for tok in ("tts", "voice", "embedding", "whisper", "moderation")):
        return False
    if provider == "xai" and any(tok in low for tok in ("imagine", "image", "video")):
        return False
    return True


def sort_models(provider: str, models: list[str]) -> list[str]:
    uniq = list(dict.fromkeys(m for m in models if m))
    if provider == "xai":
        pinned = [
            "grok-4.6",
            "grok-4.5",
            "grok-4.3",
            "grok-4.20-0309-reasoning",
            "grok-4.20-0309-non-reasoning",
            "grok-4.20-multi-agent-0309",
            "grok-build-0.1",
            "grok-4-1-fast",
            "grok-4-fast",
            "grok-4",
            "grok-3-mini",
            "grok-3",
            "grok-2-vision-1212",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    if provider == "openrouter":
        pinned = [
            "deepseek/deepseek-v4-flash-0731",
            "deepseek/deepseek-v4-pro-0813",
            "deepseek/deepseek-v4-flash-vision-exp",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "openai/gpt-5.6-luna",
            "google/gemini-3.7-flash",
            "z-ai/glm-5.2",
            "upstage/solar-pro4",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    if provider == "deepseek":
        pinned = [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-v3",
            "deepseek-r1",
            "deepseek-coder",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    if provider == "antigravity":
        pinned = [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-pro",
            "gemini-2.0-flash",
            "auto",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    if provider == "opencode":
        pinned = [
            "deepseek/deepseek-v4-flash-0731",
            "openai/gpt-5.6-luna",
            "zhipuai/glm-5.3-flash",
            "google/gemini-3.7-flash",
            "anthropic/claude-sonnet-5",
            "moonshotai/kimi-k3",
            "deepseek/deepseek-v4-pro",
            "xai/grok-4.6",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    if provider == "opencode_go":
        pinned = [
            "deepseek-v4-pro",
            "deepseek-v4.1-flash",
            "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp",
            "glm-5.3-flash",
            "kimi-k3",
            "kimi-k2.7-code",
            "mimo-v2.5",
            "muse-spark-1.3-contributor",
        ]
        head = [m for m in pinned if m in uniq]
        tail = [m for m in uniq if m not in head]
        return head + tail

    return uniq


def list_chat_models(endpoint: LlmEndpoint) -> list[str]:
    if endpoint.provider in ("antigravity", "openrouter", "opencode", "opencode_go"):
        curated = fallback_models(endpoint.provider)
        if endpoint.model and endpoint.model not in curated:
            curated.append(endpoint.model)
        return sort_models(endpoint.provider, curated)
    try:
        remote = fetch_remote_models(endpoint)
        keep = [m for m in remote if is_chat_model(endpoint.provider, m)]
        keep.extend(m for m in fallback_models(endpoint.provider) if is_chat_model(endpoint.provider, m))
        if endpoint.model:
            keep.append(endpoint.model)
        return sort_models(endpoint.provider, keep)
    except Exception:
        curated = fallback_models(endpoint.provider)
        if endpoint.model and endpoint.model not in curated:
            curated.append(endpoint.model)
        return sort_models(endpoint.provider, curated)


def extra_headers(endpoint: LlmEndpoint) -> dict[str, str]:
    if endpoint.provider == "openrouter":
        return {
            "HTTP-Referer": "http://127.0.0.1:8787",
            "X-Title": "KR Quant Screener",
        }
    if endpoint.provider == "opencode_go":
        # Go requires a client-identifying agent and a stable session header;
        # otherwise requests are rejected as unroutable.
        from uuid import uuid4

        return {
            "User-Agent": "kr-quant-research/1.0",
            "x-opencode-session": f"krq-{uuid4().hex}",
        }
    return {}


def fetch_remote_models(endpoint: LlmEndpoint, timeout: int = 20) -> list[str]:
    if endpoint.provider == "antigravity" or endpoint.base_url.startswith("cli://"):
        return fallback_models(endpoint.provider)
    import requests

    headers = extra_headers(endpoint)
    if endpoint.api_key:
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    resp = requests.get(f"{endpoint.base_url}/models", headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    ids: list[str] = []
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
            elif isinstance(item, str):
                ids.append(item)
    return sorted(set(ids))


TIER1_FREE_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
TIER1_ROUTINE_PAID_MODEL = "deepseek/deepseek-v4-flash-0731"
TIER1_ANALYSIS_MODEL = "grok-4.6"
TIER1_ANALYSIS_PRO_MODEL = "deepseek/deepseek-v4-pro-0813"


def _tier1_endpoint(settings: Any, *, hop: str, provider_attr: str, model_attr: str,
                    default_provider: str, default_model: str) -> LlmEndpoint:
    """User-configurable Tier1 hop that reuses the provider registry.

    Missing access returns an unconfigured endpoint. It never borrows another
    provider's key, so an unset key cannot silently become a paid call.
    The label always names the effective provider so cards never show a
    stale model name.
    """
    from types import SimpleNamespace

    name = normalize_provider(getattr(settings, provider_attr, None) or default_provider)
    if name not in PROVIDERS:
        name = default_provider
    model = coerce_model(name, str(getattr(settings, model_attr, None) or "").strip() or default_model)
    if name in ("xai", "antigravity"):
        # Session/CLI providers keep their dedicated resolution path.
        shim = SimpleNamespace(
            llm_provider=name,
            llm_model=model,
            xai_api_key=getattr(settings, "xai_api_key", None),
            xai_base_url=getattr(settings, "xai_base_url", None),
        )
        ep = resolve_provider(shim, name)
    else:
        key = getattr(settings, f"{name}_api_key", None)
        ep = LlmEndpoint(
            provider=name,
            label=str(PROVIDERS[name]["label"]),
            base_url=str(PROVIDERS[name]["base_url"]).rstrip("/"),
            model=model,
            api_key=key,
        )
    if not ep.configured:
        return LlmEndpoint(
            provider="tier1_unavailable",
            label=f"Tier1 {hop} 연결 없음",
            base_url="",
            model=ep.model,
            api_key=None,
        )
    return ep


def resolve_tier1_endpoint(settings: Any) -> LlmEndpoint:
    """Routine first hop (default OpenRouter NVIDIA Nemotron :free).

    Missing access returns an unconfigured endpoint. Paid hops are resolved
    separately so a blank free key cannot silently become the user switcher.
    """
    return _tier1_endpoint(
        settings,
        hop="일상 1순위",
        provider_attr="tier1_routine_provider",
        model_attr="tier1_routine_model",
        default_provider="openrouter",
        default_model=TIER1_FREE_MODEL,
    )


def resolve_tier1_routine_paid_endpoint(settings: Any) -> LlmEndpoint:
    """Routine paid hop when :free hangs or fails. Not counted against Grok/Pro budget."""
    return _tier1_endpoint(
        settings,
        hop="일상 대체",
        provider_attr="tier1_routine_paid_provider",
        model_attr="tier1_routine_paid_model",
        default_provider="openrouter",
        default_model=TIER1_ROUTINE_PAID_MODEL,
    )


def resolve_tier1_analysis_endpoint(settings: Any) -> LlmEndpoint:
    """Analysis first hop (default xAI Grok). Shares the daily analysis budget."""
    return _tier1_endpoint(
        settings,
        hop="분석 1순위",
        provider_attr="tier1_analysis_provider",
        model_attr="tier1_analysis_model",
        default_provider="xai",
        default_model=TIER1_ANALYSIS_MODEL,
    )


def resolve_tier1_analysis_pro_endpoint(settings: Any) -> LlmEndpoint:
    """Analysis hop after the first analysis hop fails (default OpenRouter DeepSeek V4 Pro)."""
    return _tier1_endpoint(
        settings,
        hop="분석 대체",
        provider_attr="tier1_analysis_pro_provider",
        model_attr="tier1_analysis_pro_model",
        default_provider="openrouter",
        default_model=TIER1_ANALYSIS_PRO_MODEL,
    )


def resolve_tier2_endpoint(settings: Any) -> LlmEndpoint:
    """Tier 2: User-selected high-performance model for deep research reports & infographics."""
    return resolve_provider(settings)

