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
            "openai/gpt-5.6-luna",
            "google/gemini-3.7-flash",
            "z-ai/glm-5.2",
            "upstage/solar-pro4",
        ],
    },
}

DEFAULT_PROVIDER = "xai"

OPENROUTER_MODEL_ALIASES: dict[str, str] = {
    "deepseek/deepseek-chat-0731": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-chat-0324": "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-vl": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-vl2": "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-vision": "deepseek/deepseek-v4-flash-0731",
    "qwen/qwen-2.5-vl-72b-instruct": "qwen/qwen2.5-vl-72b-instruct",
}

REMOVED_PROVIDERS = frozenset({"openai", "opencode", "custom"})


def normalize_provider(name: str | None) -> str:
    n = (name or DEFAULT_PROVIDER).lower().strip()
    if n in ("grok", "x_ai"):
        return "xai"
    if n in ("agy", "google", "gemini", "antigravity_cli", "google_antigravity", "antigravity"):
        return "antigravity"
    if n in REMOVED_PROVIDERS:
        return DEFAULT_PROVIDER
    return n or DEFAULT_PROVIDER


def model_fits_provider(provider: str, model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    if provider == "openrouter":
        return "/" in m
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

    return uniq


def list_chat_models(endpoint: LlmEndpoint) -> list[str]:
    if endpoint.provider in ("antigravity", "openrouter"):
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
TIER1_ANALYSIS_PRO_MODEL = "deepseek/deepseek-v4-pro-0813"


def _openrouter_named(settings: Any, model: str, label: str) -> LlmEndpoint:
    or_key = getattr(settings, "openrouter_api_key", None)
    if or_key:
        return LlmEndpoint(
            provider="openrouter",
            label=label,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            api_key=or_key,
        )
    return LlmEndpoint(
        provider="tier1_unavailable",
        label=f"{label} 연결 없음",
        base_url="",
        model=model,
        api_key=None,
    )


def resolve_tier1_endpoint(settings: Any) -> LlmEndpoint:
    """Routine first hop: OpenRouter NVIDIA Nemotron :free.

    Missing access returns an unconfigured endpoint. Paid hops are resolved
    separately so a blank free key cannot silently become the user switcher.
    """
    return _openrouter_named(
        settings,
        TIER1_FREE_MODEL,
        "NVIDIA Nemotron 550B (OpenRouter :free)",
    )


def resolve_tier1_routine_paid_endpoint(settings: Any) -> LlmEndpoint:
    """Routine paid hop when :free hangs or fails. Not counted against Grok/Pro budget."""
    return _openrouter_named(
        settings,
        TIER1_ROUTINE_PAID_MODEL,
        "DeepSeek V4 Flash (OpenRouter)",
    )


def resolve_tier1_analysis_pro_endpoint(settings: Any) -> LlmEndpoint:
    """Analysis hop after Grok: OpenRouter DeepSeek V4 Pro."""
    return _openrouter_named(
        settings,
        TIER1_ANALYSIS_PRO_MODEL,
        "DeepSeek V4 Pro (OpenRouter)",
    )


def resolve_tier2_endpoint(settings: Any) -> LlmEndpoint:
    """Tier 2: User-selected high-performance model for deep research reports & infographics."""
    return resolve_provider(settings)

