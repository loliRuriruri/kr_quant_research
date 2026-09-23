# -*- coding: utf-8 -*-
"""Pure planner: health snapshot → ordered action plan (no execution)."""
from __future__ import annotations

from typing import Any, Mapping

VALID_MODES = frozenset({"normal", "recover"})

ACTIONS = frozenset(
    {
        "REFRESH_KRX",
        "REPAIR_DART_ESSENTIAL",
        "REBUILD_QUANT",
        "REFRESH_KIS",
        "REBUILD_SEASON",
        "DART_MAINTENANCE_BATCH",
        "CHECK_PUBLISH",
        "WAIT_SOURCE",
    }
)

# Recover must never schedule these long/forced jobs (H12).
FORBIDDEN_IN_RECOVER = frozenset(
    {
        "krx-history",
        "KRX_HISTORY",
        "DART_FULL_COVERAGE",
        "DART_CONTINUOUS",
        "FULL_UPDATE",
        "LIVE_FULL_UPDATE",
    }
)


class InvalidPipelineMode(ValueError):
    """Fail-closed for unsupported planner modes."""


def _state(components: Mapping[str, Any], name: str) -> str:
    row = components.get(name) or {}
    if isinstance(row, Mapping):
        return str(row.get("state") or "")
    return ""


def _action(kind: str, *, reason: str, **extra: Any) -> dict[str, Any]:
    if kind not in ACTIONS:
        raise ValueError(f"unsupported action: {kind}")
    row = {"action": kind, "reason": reason}
    row.update(extra)
    return row


def plan_pipeline(
    health: Mapping[str, Any],
    *,
    mode: str = "normal",
) -> dict[str, Any]:
    """Build an ordered action plan from a health snapshot.

    Pure: does not call network/jobs/filesystem or mutate ledger.
    """
    if mode not in VALID_MODES:
        raise InvalidPipelineMode(f"invalid pipeline mode: {mode!r}")

    components = health.get("components") or {}
    if not isinstance(components, Mapping):
        components = {}

    actions: list[dict[str, Any]] = []
    busy = bool(health.get("busy"))
    pipeline_state = str(health.get("pipeline_state") or "")

    if busy or pipeline_state == "RUNNING":
        return {
            "mode": mode,
            "actions": [],
            "blocked": True,
            "block_reason": "runner_busy",
            "pipeline_state": pipeline_state,
        }

    krx = _state(components, "krx")
    dart = _state(components, "dart_essential")
    coverage = _state(components, "dart_coverage")
    quant = _state(components, "quant")
    kis = _state(components, "kis")
    season = _state(components, "season")
    master = _state(components, "master")

    # KRX refresh when stale/missing/corrupt (local artifact view).
    if krx in {"STALE", "MISSING", "CORRUPT"}:
        actions.append(_action("REFRESH_KRX", reason=f"krx_{krx.lower()}"))

    # DART essential repair BEFORE Quant (ordering contract).
    if dart in {"MISSING", "CORRUPT"}:
        actions.append(_action("REPAIR_DART_ESSENTIAL", reason=f"dart_essential_{dart.lower()}"))

    # Master missing/corrupt also blocks operable Quant — repair path is via essential data stack;
    # recover/normal both need Quant rebuild after essentials restored. We still schedule Quant
    # rebuild when master is broken so the plan expresses dependency, but DART essential (if any)
    # remains earlier. Master itself has no separate action in the locked action set.
    quant_needs_rebuild = quant in {"STALE", "MISSING", "CORRUPT", "BLOCKED"} or master in {
        "MISSING",
        "CORRUPT",
    }
    if quant_needs_rebuild:
        # If Quant is only blocked by dart_essential and we already scheduled repair, still
        # include REBUILD_QUANT after it so dependents are explicit.
        actions.append(_action("REBUILD_QUANT", reason=f"quant_{quant.lower() or 'blocked'}"))

    # Optional bounded DART maintenance in normal mode only when essential is healthy
    # and coverage is below target. Never a Quant prerequisite.
    if mode == "normal" and dart == "HEALTHY" and coverage == "PARTIAL":
        actions.append(
            _action(
                "DART_MAINTENANCE_BATCH",
                reason="coverage_below_target",
                bounded=True,
            )
        )

    if kis in {"STALE", "MISSING", "CORRUPT", "PARTIAL"}:
        # KIS never forces Quant rebuild (matrix 19).
        actions.append(_action("REFRESH_KIS", reason=f"kis_{kis.lower()}"))

    # Season rebuild only when season itself is not healthy (A1; LKG is A4).
    if season in {"MISSING", "STALE", "UPDATING", "CORRUPT"}:
        actions.append(_action("REBUILD_SEASON", reason=f"season_{season.lower()}"))

    # Publish check when core looks ready-ish after planned work, or already READY.
    if pipeline_state in {"READY", "NEEDS_DAILY_UPDATE", "PARTIAL"} or actions:
        core_ok_after = dart not in {"MISSING", "CORRUPT"} or any(
            a["action"] == "REPAIR_DART_ESSENTIAL" for a in actions
        )
        if pipeline_state == "READY" or (
            core_ok_after and not any(a["action"] == "WAIT_SOURCE" for a in actions)
        ):
            actions.append(_action("CHECK_PUBLISH", reason="evaluate_publish_readiness"))

    # Hard guarantee: no forbidden long-job actions in recover (or ever in this planner).
    for row in actions:
        if row["action"] in FORBIDDEN_IN_RECOVER:
            raise RuntimeError(f"planner emitted forbidden action: {row['action']}")

    if mode == "recover":
        # Strip optional maintenance / publish niceties that are not minimum operable restore.
        actions = [
            row
            for row in actions
            if row["action"]
            in {
                "REFRESH_KRX",
                "REPAIR_DART_ESSENTIAL",
                "REBUILD_QUANT",
                "REFRESH_KIS",
                "REBUILD_SEASON",
                "WAIT_SOURCE",
            }
        ]

    # Enforce DART essential before Quant in the final list.
    kinds = [row["action"] for row in actions]
    if "REPAIR_DART_ESSENTIAL" in kinds and "REBUILD_QUANT" in kinds:
        if kinds.index("REPAIR_DART_ESSENTIAL") > kinds.index("REBUILD_QUANT"):
            raise RuntimeError("planner violated DART-essential-before-Quant ordering")

    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for row in actions:
        key = row["action"]
        if key in seen:
            continue
        seen.add(key)
        ordered.append(row)

    return {
        "mode": mode,
        "actions": ordered,
        "blocked": False,
        "block_reason": None,
        "pipeline_state": pipeline_state,
        "repair_required": bool(health.get("repair_required")),
    }


def action_kinds(plan: Mapping[str, Any]) -> list[str]:
    return [str(row.get("action")) for row in (plan.get("actions") or []) if isinstance(row, Mapping)]
