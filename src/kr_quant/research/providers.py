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
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "help": "https://platform.deepseek.com/",
        "fallback_models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "env_key": "OPENROUTER_API_KEY",
        "help": "https://openrouter.ai/keys",
        "fallback_models": [
            "openai/gpt-4o-mini",
            "x-ai/grok-4-fast",
            "google/gemini-2.5-flash",
            "anthropic/claude-sonnet-4",
            "deepseek/deepseek-chat",
        ],
    },
}

DEFAULT_PROVIDER = "xai"
REMOVED_PROVIDERS = frozenset({"openai", "opencode", "custom"})


def normalize_provider(name: str | None) -> str:
    n = (name or DEFAULT_PROVIDER).lower().strip()
    if n == "grok":
        return "xai"
    if n in REMOVED_PROVIDERS:
        return DEFAULT_PROVIDER
    return n or DEFAULT_PROVIDER


def model_fits_provider(provider: str, model: str | None) -> bool:
    m = (model or "").strip()
    if not m:
        return False
    if provider == "openrouter":
        return "/" in m
    if "/" in m:
        return False
    if provider == "xai":
        return m.lower().startswith("grok")
    if provider == "deepseek":
        return m.lower().startswith("deepseek")
    return True


def coerce_model(provider: str, model: str | None) -> str:
    spec = PROVIDERS.get(provider) or PROVIDERS[DEFAULT_PROVIDER]
    if model_fits_provider(provider, model):
        return str(model).strip()
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
        return bool(self.api_key)


def resolve_provider(settings: Any, provider: str | None = None) -> LlmEndpoint:
    name = normalize_provider(provider or getattr(settings, "llm_provider", None))
    if name not in PROVIDERS:
        raise ValueError(f"지원하지 않는 LLM 제공자: {name}")
    spec = PROVIDERS[name]
    session_key = None
    try:
        from kr_quant.research.grok_auth import load_session_token

        session_key = load_session_token()
    except Exception:
        session_key = None
    xai_key = session_key or getattr(settings, "xai_api_key", None)
    key_map = {
        "xai": xai_key,
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
        api_key=key_map[name],
    )


def fallback_models(provider: str) -> list[str]:
    spec = PROVIDERS.get(provider) or {}
    return list(spec.get("fallback_models") or [])


def is_chat_model(provider: str, model: str | None) -> bool:
    m = (model or "").strip()
    if not m or not model_fits_provider(provider, m):
        return False
    low = m.lower()
    if provider == "xai" and any(tok in low for tok in ("imagine", "image", "video", "tts", "voice", "embedding")):
        return False
    return True


def sort_models(provider: str, models: list[str]) -> list[str]:
    uniq = list(dict.fromkeys(m for m in models if m))
    if provider != "xai":
        return uniq
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
    ]
    head = [m for m in pinned if m in uniq]
    tail = [m for m in uniq if m not in head]
    return head + tail


def list_chat_models(endpoint: LlmEndpoint) -> list[str]:
    remote = fetch_remote_models(endpoint)
    keep = [m for m in remote if is_chat_model(endpoint.provider, m)]
    keep.extend(m for m in fallback_models(endpoint.provider) if is_chat_model(endpoint.provider, m))
    if endpoint.model:
        keep.append(endpoint.model)
    return sort_models(endpoint.provider, keep)


def extra_headers(endpoint: LlmEndpoint) -> dict[str, str]:
    if endpoint.provider == "openrouter":
        return {
            "HTTP-Referer": "http://127.0.0.1:8787",
            "X-Title": "KR Quant Screener",
        }
    return {}


def fetch_remote_models(endpoint: LlmEndpoint, timeout: int = 20) -> list[str]:
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
