# Execution Pipeline Self-Healing Design v1

**Status:** Design Lock (A0)  
**Date:** 2026-09-23 (Asia/Seoul)  
**Scope:** `view-run` execution pipeline only (no sidebar IA)  
**Base:** `origin/main` @ `aaeb557a92ceaaad36af0712942fd80e6b21afa3`  
**Branch:** `pipeline-a-v1-design`

## 0. One-line principle

> KR Quant's execution pipeline must diagnose real artifact state, plan the minimum work, execute it, and re-verify artifacts — not ask the operator which job button to press.

Ledger convenience and legacy step order never outrank this principle.

## 1. Problem statement

Current `view-run` already has a primary **스마트 실행** (`smart-sync`) and a details drawer of recovery/advanced tools:

1. Quick Sync (`krx-prices`)
2. Full Update (`live`)
3. Price history expansion (`krx-history`)
4. OpenDART full-universe backfill (`dart-backfill`)

### P1 — Daily / repair / long jobs share one drawer

Operators must decide which button fits the situation.

### P2 — Full Update overlaps Smart Sync

Full Update looks like a daily action but is a forced full refresh.

### P3 — Ledger can outrank missing artifacts

Observed failure mode:

```text
DART ledger = success
coverage = 99.9% (from dart_backfill_state ticker_outcomes)
financial_facts.parquet = MISSING
→ smart-sync skips DART as sufficient
→ Quant runs and fails
→ later DART still skipped as same-day success
→ no self-heal
```

Root cause: `_financial_coverage` can report high coverage from backfill state even when the live parquet is absent; `needs_more_dart_backfill` then returns false.

### P4 — Season looks broken during long data jobs

`season_snapshot.build_bundle` correctly aborts when `is_updating` or `source_identity` changes mid-build (preserve prior complete snapshot). UI currently surfaces this like a hard failure / empty season rather than refresh-pending with last-known-good.

## 2. UX — three layers inside `view-run` only

Sidebar IA is out of scope (H1).

### Layer A — Daily ops (always expanded)

- Name: **오늘 필요한 작업 스마트 실행**
- Primary CTA: **▶ 오늘 필요한 작업 실행**
- Job: existing `smart-sync` with `mode=normal`
- Shows: component status, **pre-run plan preview**, busy reason, next schedule time
- Full Update is **not** a daily primary CTA

### Layer B — Repair / auto-recover (collapsed by default)

- Name: **데이터 구멍 자동 복구**
- Primary CTA: **🔧 자동 복구 실행**
- Call: `smart-sync` with `trigger=manual`, `mode=recover`
- Auto-expand / warn when health says `REPAIR_REQUIRED`
- Minimum path only; never auto-starts `krx-history`, continuous DART, or Full Update
- Optional small links only: 시세만 다시 받기 / 점수만 다시 계산

### Layer C — Advanced (collapsed by default)

1. Price history expansion (`krx-history`)
2. OpenDART full-universe continuous backfill (`dart-backfill`)
3. Forced full refresh + recompute (`live` / Full Update) with demotion copy
4. Expert: demo / live-skip / screen / as_of / lookback

Mandatory long-job warning: tens of minutes possible; daily smart and new season snapshot generation may defer; existing verified data is not deleted.

Remove the numbered 1/2/3/4 daily-looking hierarchy in favor of layer semantics.

### Status cards (keep four)

KRX / OpenDART / Quant / Scheduler — CTA wiring only changes (stale → daily/repair plan actions; essential DART missing → repair; coverage partial ≠ missing; scheduler skip → RUNNER busy copy).

## 3. Hard constraints (H1–H20) — immutable for v1

| ID | Invariant |
|----|-----------|
| H1 | Do not change sidebar IA. |
| H2 | **Real artifact state outranks the ledger.** Ledger success is not evidence of artifact presence/integrity. |
| H3 | Before Quant, validate required inputs (`prices`, `master`, `financial_facts`). |
| H4 | If `financial_facts.parquet` is missing/corrupt, do **not** treat DART as `skipped_sufficient` or `skipped_already_success`. |
| H5 | Required DART artifact repair runs **before** Quant. |
| H6 | DART full-universe ~90% coverage is **not** an absolute Quant precondition. If essential artifact is healthy, Quant may run with partial coverage. |
| H7 | Separate `trigger` and `mode`. Add `mode=recover` as a distinct policy. Never overload `trigger=recover`. |
| H8 | Action return success is not enough; **artifact re-verification** is required for VERIFIED. |
| H9 | On verify failure, do not proceed to dependent actions. |
| H10 | Keep a single `RUNNER`. No job queue in v1. |
| H11 | When RUNNER is busy, disable smart/recover CTAs and show current job kind + reason. |
| H12 | Recover mode must not auto-start `krx-history`, continuous DART, or Full Update. |
| H13 | Keep season source-change / `is_updating` guards. |
| H14 | Season Last-Known-Good is **display-only read fallback**; never disguise as today's current candidate. |
| H15 | Do not loosen public Pages publish safety. |
| H16 | Do not change J3/JEV config, thresholds, or Research Gate behavior. |
| H17 | Do not change Quant factor / ranking / strategy algorithms. |
| H18 | Do not package failures as success. Distinguish `VERIFY_FAILED`, `REPAIR_INCOMPLETE`, `WAITING_SOURCE`. |
| H19 | Health scan is read-only: no file/ledger/config mutation during diagnosis. |
| H20 | Health must not full-scan large parquets every time; use existence/size/metadata/schema/minimal bounded reads. |

## 4. Truth model — Artifact > Ledger

Ledger records: run history, attempts, timestamps, in-progress status.

**Authority for "what work is needed"** is the health snapshot.

Examples:

- ledger.dart=success + financial_facts MISSING → `REPAIR_REQUIRED`
- ledger.quant=success + latest all_stocks MISSING → `REPAIR_REQUIRED`
- ledger.krx=success + prices.max_date < expected → `STALE` / `WAITING_SOURCE`

Coverage 99.9% must never mask essential artifact MISSING.

## 5. Health layer

Recommended module: `src/kr_quant/web/pipeline_health.py`

- Pure / read-only; no network; no ingest; no ledger/config mutation (H19)
- Bounded checks only (H20)

### Component states

`HEALTHY` | `STALE` | `PARTIAL` | `MISSING` | `CORRUPT` | `UPDATING` | `BLOCKED`

### Pipeline states

`READY` | `NEEDS_DAILY_UPDATE` | `REPAIR_REQUIRED` | `WAITING_SOURCE` | `RUNNING` | `PARTIAL` | `FAILED`

### Minimum inspection targets

- **KRX:** `data/staged/live/prices.parquet`, max trade_date vs expected (source-ready probe is planner/runtime, not health mutation)
- **Master:** `master.parquet` exists, readable, minimal columns
- **DART essential:** `financial_facts.parquet` exists, size>0, readable, minimal columns, rows>0; coverage is a separate `PARTIAL` signal
- **Quant outputs:** committed generation/manifest, latest all-stocks equivalent, as-of vs price as-of
- **KIS:** reuse official collection freshness
- **Season:** current readiness, LKG presence, updating flag

## 6. Planner layer

Recommended module: `src/kr_quant/web/pipeline_plan.py`

- Input: health snapshot → output: ordered actions
- Planner does **not** execute

### Example actions

`REFRESH_KRX` | `REPAIR_DART_ESSENTIAL` | `REBUILD_QUANT` | `REFRESH_KIS` | `REBUILD_SEASON` | `DART_MAINTENANCE_BATCH` | `CHECK_PUBLISH` | `WAIT_SOURCE`

### Normal mode order (representative)

Health → KRX if needed → **DART essential verify/repair** → recent filings check → Quant if stale/dirty → optional bounded DART maintenance batch → re-verify Quant if needed → KIS → derived/season → quality/publish readiness.

### Recover mode

Restore **minimum operable** state only. Same essential gates; never schedule long/full jobs (H12).

## 7. DART meanings (three)

1. **Essential** — Quant-required `financial_facts` artifact; repair target; bounded
2. **Maintenance** — optional one bounded batch in normal mode; must not block Quant availability when essential is healthy (H6)
3. **Full coverage** — long continuous universe backfill; Layer C only; never auto in recover

### Essential repair policy

When facts missing/corrupt: confirm prices/master prerequisites → reuse existing DART backfill internals → bounded batches → verify after each batch → stop when healthy artifact appears → else `REPAIR_INCOMPLETE` → no auto-escalation to Full Update / continuous.

## 8. Post-action verification gate

Every important action: execute → health rescan → verify expected artifact/state (H8). Verify fail → stop dependents (H9). Examples: DART success but facts still missing → `VERIFY_FAILED` (block Quant); Quant success but generation missing/stale → block publish; KRX success but stored max date still behind → `WAITING_SOURCE` or `VERIFY_FAILED`.

## 9. Smart Sync signature

```python
def job_smart_sync(
    as_of: str = "auto",
    lookback_days: int = 80,
    max_corps: int = 400,
    dart_batch_size: int = 50,
    trigger: str = "manual",  # manual | scheduler | retry
    mode: str = "normal",     # normal | recover
) -> dict[str, Any]:
    ...
```

Invalid `mode` fails closed. `trigger` continues to be ledgered. No separate `auto-recover` job kind. Scheduler keeps `smart-sync` `mode=normal` (recover is not the default scheduled path).

## 10. Concurrency

Single `RUNNER` (H10). Scheduler busy-skip preserved. No queue/auto-wait in v1. UI disables smart/recover while busy and names the running job (H11).

## 11. Season Last-Known-Good (display)

Keep build guards (H13). When current identity snapshot is absent, a data job/update is in progress, and a prior valid immutable snapshot exists, API may return that snapshot as **read-only** fallback with:

```json
{
  "state": "stale_while_revalidate",
  "snapshot_as_of": "...",
  "expected_as_of": "...",
  "is_current": false,
  "refresh_pending": true
}
```

UI banner: refreshing; showing verified older snapshot; will switch when current ready.

Forbidden for LKG (H14): label as today's candidate; use as publish evidence; trigger new JEV shadow evaluation; use as evidence for new "today" AI analysis. Corrupt LKG is not served. No LKG → keep existing pending/503.

## 12. APIs (minimum)

- `GET /api/pipeline/health`
- `GET /api/pipeline/plan?mode=normal|recover`
- `POST /api/jobs` with `kind=smart-sync` and `mode=normal|recover` (`JobIn.mode`)

Keep existing kind names where possible.

## 13. Publish safety

Do not weaken Pages guards (H15). Block publish on: KRX stale/not ready; Quant unverified; required artifact missing/corrupt; verify failure; cancel/interrupted. LKG season is not current publish evidence.

## 14. Out of scope

Sidebar IA; Research Lab collapse; Quant/season algorithms; JEV enable/thresholds/J3; AI providers; multi-runner; job queue; auto Full Update / auto long history.

## 15. Allowed file touch set (later phases)

**New:** `pipeline_health.py`, `pipeline_plan.py`  
**May modify:** `jobs.py`, `smart_ledger.py`, `app.py`, `season_snapshot.py`, `static/index.html`, `static/app.js`, plus unit/web tests  
**Forbidden:** `jev_research_gate.py`, `jev_calibration.py`, `season_jev_shadow.py`, `config/season_jev.json`, `config/jev_thresholds.json`, Quant factor/scoring core

## 16. Definition of done (v1)

- One primary daily CTA
- Repair diagnoses cause from artifacts
- Ledger cannot mask missing essential artifacts
- DART essential before Quant; bounded repair; post-verify; dependent stop
- Long jobs only in advanced
- Single RUNNER; busy disable + reason
- Season LKG with stale metadata; guards preserved
- Publish safety / J3/JEV / sidebar / Quant algorithms unchanged
- Full pytest exit 0 / 0 failed

## 17. Implementation phasing (see plan doc)

A0 Design Lock (this document) → A1 Health+Planner → A2 Smart Sync self-heal → A3 3-layer UI → A4 Season LKG → A5 certification. Each phase: separate commit, push feature branch only, STOP. No main merge until GPT verification.
