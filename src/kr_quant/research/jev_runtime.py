# -*- coding: utf-8 -*-
"""JEV runtime mode resolution (P1 Task 1.1).

Pure, fail-closed resolution of the runtime lifecycle mode from the raw
``config/season_jev.json`` payload.

Scope lock: this module currently provides only the mode-resolution
foundation. No orchestrator, no provider execution, no gate execution, no
executor, no evidence, no config writes.

Spec: docs/superpowers/specs/2026-09-23-jev-production-routing-design.md §4.3
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

RUNTIME_SCHEMA_VERSION = 1
RUNTIME_ARTIFACT_TYPE = "season_jev_runtime_overlay"

MODE_DISABLED = "disabled"
MODE_SHADOW = "shadow"
MODE_CANARY = "canary"
MODE_PRODUCTION = "production"
MODES = (MODE_DISABLED, MODE_SHADOW, MODE_CANARY, MODE_PRODUCTION)

# Internal marker used by load_raw_runtime_config to carry a load failure into
# resolve_runtime_mode without raising. Never persisted.
_CONFIG_LOAD_ERROR_KEY = "__config_load_error__"


def _disabled(reason: str | None = None, errors: list[str] | None = None) -> dict[str, Any]:
    return {"mode": MODE_DISABLED, "reason": reason, "errors": list(errors or [])}


def load_raw_runtime_config(settings) -> dict[str, Any]:
    """Read ``config/season_jev.json`` without raising.

    Returns the parsed object on success; on any read/parse failure returns a
    marker mapping that ``resolve_runtime_mode`` turns into a fail-closed
    ``disabled`` result with the error recorded. The file is never written.
    """
    path = Path(settings.root) / "config" / "season_jev.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {_CONFIG_LOAD_ERROR_KEY: f"CONFIG_UNREADABLE:{type(exc).__name__}"}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return {_CONFIG_LOAD_ERROR_KEY: f"CONFIG_UNREADABLE:{type(exc).__name__}"}
    if not isinstance(data, dict):
        return {_CONFIG_LOAD_ERROR_KEY: "CONFIG_UNREADABLE:not_an_object"}
    return data


def resolve_runtime_mode(raw_cfg: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the runtime mode exactly per spec §4.3.

    Returns ``{"mode": str, "reason": str | None, "errors": list[str]}``.

    Hard rules:
    - Any conflict or invalid value resolves to ``disabled`` (fail closed).
    - Legacy configuration (no ``mode`` key) can only ever resolve to
      ``shadow`` or ``disabled`` — never ``canary`` / ``production``.
    - Pure: the input mapping is never mutated; nothing is written.
    """
    if not isinstance(raw_cfg, Mapping):
        return _disabled("CONFIG_MODE_INVALID", ["config must be a mapping"])

    load_error = raw_cfg.get(_CONFIG_LOAD_ERROR_KEY)
    if load_error:
        return _disabled(None, [str(load_error)])

    mode_present = "mode" in raw_cfg
    enabled_present = "enabled" in raw_cfg

    if mode_present:
        mode = raw_cfg.get("mode")
        if not isinstance(mode, str) or mode not in MODES:
            return _disabled("CONFIG_MODE_INVALID", [f"invalid mode: {mode!r}"])
        if enabled_present:
            enabled = raw_cfg.get("enabled")
            if not isinstance(enabled, bool):
                return _disabled("CONFIG_MODE_INVALID", ["enabled must be a boolean"])
            if enabled != (mode != MODE_DISABLED):
                return _disabled(
                    "CONFIG_MODE_CONFLICT",
                    [f"mode={mode!r} conflicts with enabled={enabled!r}"],
                )
        return {"mode": mode, "reason": None, "errors": []}

    # Legacy configuration (no mode key): shadow/disabled only.
    if enabled_present and raw_cfg.get("enabled") is True:
        return {"mode": MODE_SHADOW, "reason": "LEGACY_ENABLED_TRUE", "errors": []}
    return _disabled()
