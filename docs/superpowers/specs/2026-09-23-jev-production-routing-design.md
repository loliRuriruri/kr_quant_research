# JEV Production Routing v1 — Design Specification

**Status:** DESIGN_READY_FOR_PLAN
**Date:** 2026-09-23
**Base:** `origin/main` @ `44b2c467be59d90851705e9ea7f0175a38203727` (certified Pipeline A v1 tip; ACCEPT_WITH_NOTES)
**Mode:** DESIGN ONLY (no implementation, no config change, no runtime writes in this commit)
**Supersedes nothing:** J1/J2/J3 designs remain authoritative for their own surfaces.

---

## 1. Status / Base / Scope

### 1.1 Status

This document locks the design required to take the already-built JEV
shadow / calibration / research-gate stack to a **safe Production v1**.

This is a **P0 design + implementation-plan** deliverable. It does **not**
authorize implementation. The companion plan is:

```text
docs/superpowers/plans/2026-09-23-jev-production-activation-implementation.md
```

### 1.2 Base

- Git: `44b2c467be59d90851705e9ea7f0175a38203727` (`origin/main`)
- Local `refs/heads/main` `5ca60a8a1c67b5d34917f3a5c3f8a23aac74dbf4` is a
  separate preserved local chore tip. It is **not** a base for this work and
  must not be reset, rebased, merged, cherry-picked, or deleted.
- This design branch: `jev-production-v1-design` (worktree
  `C:\Users\a4jud\kr_quant_research-jev-prod`), based on `origin/main`.

### 1.3 Production state at design time (verified)

```text
config/season_jev.json
  enabled = false
  provider = typesafe_direct
  model = jev-latest
  evaluator_version = season-jev-shadow-v1

config/jev_thresholds.json
  schema_version = 1
  buckets = 2 (typesafe_direct/jev-latest, openrouter/typesafe/jev-1.13)
  heads per bucket = 7 (BOOLEAN_HEADS)
  null thresholds = 14 / 14
  non-null thresholds = 0 / 14
```

### 1.4 Scope

In scope for this design:

- Explicit runtime lifecycle: `disabled | shadow | canary | production`
- Backward compatibility with `enabled: false|true` and minimal migration
- Calibration activation contract (threshold promotion, approval, eligibility)
- Isolated Research Executor design
- Isolated Evidence Verifier design
- Invalidation semantics (research overlay only)
- Canary design (scope, budgets, metrics, rollback)
- Fail-closed failure matrix
- Runtime readiness inventory (read-only)
- UI / observability contract (design only)
- Security / privacy locks
- P1–P7 implementation plan (separate document)

Out of scope for this commit:

- Any `src/` / `scripts/` / `tests/` / `config/` change
- Any runtime data write
- Any live JEV / news / DART / Deep-AI provider call
- Any `enabled=true` change
- Any non-null threshold write
- Dashboard implementation

---

## 2. Production v1 Definition

### 2.1 Locked flow

```text
Quant / Season candidate (deterministic; authoritative ranking)
        ↓  (identity + state only; never a score input)
JEV evaluator (existing shadow provider pipeline, provider-isolated)
        ↓  (persisted shadow generation artifact)
calibrated Research Gate (J3; exact provider+requested_model+evaluator bucket)
        ↓  (research_requirements: true | false | null)
Research Executor (bounded, allowlisted, budgeted)
        ↓  (evidence objects with provenance)
Evidence Verifier (VERIFIED | UNVERIFIED | CONFLICT | STALE | ERROR)
        ↓
source-backed research overlay / status (REVIEW_REQUIRED | CONFLICT_FOUND |
                                        NO_CONFLICT_FOUND | UNVERIFIED)
```

### 2.2 Production v1 MUST NOT

- mutate deterministic Quant factor values
- mutate Quant score
- mutate Quant rank
- mutate `seasonality_score`
- mutate `pre_entry_rank`
- execute trades
- alter portfolio weights
- silently hide a candidate
- fabricate evidence
- make Quant unavailable when JEV is unavailable

### 2.3 Quant isolation (hard)

- Quant remains the authoritative deterministic ranking engine.
- JEV failure must remain isolated from deterministic Quant.
- The research overlay is additive metadata only. A candidate is never
  removed, re-ranked, or re-scored by JEV in v1.
- The Research Executor and Evidence Verifier must not import or read Quant
  scoring modules; their inputs are gate results, shadow identity, and
  external source evidence only.
- Forbidden state keys remain exactly as locked by J2/J3
  (`quantReference`, `quant_reference`, `pre_entry_rank`, `grade`,
  `seasonality_score`, `score_breakdown`).

---

## 3. Current System Inventory (verified against code at base)

### 3.1 Implemented surfaces consumed, not reinvented

| Surface | File | Role |
| --- | --- | --- |
| Shadow evaluator + persistence | `src/kr_quant/research/season_jev_shadow.py` | provider-isolated shadow generation artifacts; Quant isolation; reuse; budget integration |
| Daily budget ledger + lock | `src/kr_quant/research/season_jev_budget.py` | `reserve_daily_slot` / `refund_daily_slot`, KST day ledger, file lock |
| Calibration tooling | `src/kr_quant/research/jev_calibration.py` | `BOOLEAN_HEADS`, `lookup_threshold`, split, metrics, sweep, selection lock, holdout eval, export/ingest |
| Research gate (J3) | `src/kr_quant/research/jev_research_gate.py` | pure gate decisions, generation envelope, atomic persistence, reuse index |
| Calibration CLI | `scripts/jev_calibration_export.py` | export-candidates, blind-template, ingest-labels, calibration-report, lock-selection, holdout-eval |
| Providers | `scripts/jev-season-shadow.mjs`, `scripts/jev-season-shadow-openrouter.mjs` | TypeSafe Direct / OpenRouter runners |

### 3.2 Locked existing contracts this design builds on

- Bucket identity: `provider + requested_model + evaluator_version`.
- Prediction rule: `probability >= threshold` (`predict_positive`).
- Null threshold: `decision=null`, `reason=UNCALIBRATED` — never `false`, never `0.5`.
- Gate modes: `SHADOW_ONLY` or `ERROR` only; `side_effects_executed=false`.
- Gate error codes: `MISSING_ANSWERS`, `MISSING_HEAD`, `INVALID_PROBABILITY`,
  `INVALID_IDENTITY`, `UNSUPPORTED_PROVIDER`, `INVALID_THRESHOLD`,
  `THRESHOLD_CONFIG_UNREADABLE`, `STATE_HASH_MISMATCH`, `UNSUPPORTED_SCHEMA`.
- Calibration states: `CALIBRATION_OPEN` → `SELECTION_LOCKED` → `HOLDOUT_REVEALED`.
- Review statuses: `ACCEPT` | `REJECT` | `COLLECT_MORE_LABELS`.
- Support gates: analysis `valid_labels >= 50`, production review eligible `>= 100`,
  `INSUFFICIENT_CLASS_SUPPORT` when a class < 10.
- FN-sensitive heads: `needsDart`, `historicalConflict`, `invalidationCheckNeeded`.
- Budget authority: `max_api_calls_per_generation` / `max_api_calls_per_day`
  (shadow ledger); research calls get a **separate** ledger (§6.6).
- Storage convention: `{data_dir}/research_snapshots/season_jev_shadow/{generation_id}__{provider}.json`
  and `{data_dir}/research_snapshots/season_jev_research_gate/{generation_id}__{provider_safe}__gate.json`.

### 3.3 Doc ↔ code comparison notes (differences that matter for this design)

1. **Gate persistence is implemented but has no runtime caller today.** No
   `src/` or `scripts/` module invokes `evaluate_research_gate_generation` /
   `write_research_gate_artifact`. The only existing JEV hook is
   `season_snapshot._schedule_shadow` → `season_jev_shadow.request_shadow_evaluation`
   (fire-and-forget, current completed 5-year bundle only, never LKG serving).
   §4.5 locks the single authoritative orchestrator entrypoint and the
   production hook that replaces that delegation in P1.
2. **`lookup_threshold` returns `SHADOW_ONLY` even for numeric thresholds**
   (J3 Task 1 note). Therefore production eligibility cannot be derived from
   lookup status alone; the approval layer in §5 is mandatory.
3. **`season_holdout.py` / `season_holdout_store.py` are NOT the JEV
   calibration holdout.** They implement the season-strategy year-split
   diagnostic. The JEV calibration holdout is
   `jev_calibration.evaluate_holdout_locked` + `attach_review_status`.
   The two must never be cross-wired.
4. **`threshold_status_from_path` treats unreadable configs as UNCALIBRATED.**
   J3 deliberately does not use it as generation-level authority. The runtime
   layer must use the J3 `_load_threshold_cfg` boundary semantics (fail closed
   on unreadable config, no fabricated MISSING hash).
5. **The calibration CLI has no approval subcommand.** Promotion stops at
   holdout evaluation today. P2 adds approval records + CLI.
6. **`config/season_jev.json` has no `mode` field** and
   `season_jev_shadow.load_config` filters unknown keys out of its DEFAULTS
   view. Mode resolution must therefore live in the new runtime module and
   read the raw config file.
7. **The calibration storage root `data/research/jev_calibration/`** is
   implemented (`calibration_root`), with `labels/`, `exports/`, `reports/`
   as spec conventions and `selections/` as a plan-level convention. This
   design adds `approvals/` to that root.
8. **J3 `evaluate_research_gate_generation` raises `ResearchGateError`** for
   envelope corruption and never persists partial envelopes. The runtime
   layer must catch this and record an ERROR overlay — never fabricate a
   gate artifact.
9. **Shadow reuse keys are 4-tuple** (`evaluator_version, provider,
   requested_model, state_hash`); gate reuse keys are 8-tuple. Runtime reuse
   for execution is a separate 9-tuple key (§6.5). Do not merge these.
10. **Shadow artifacts persist `status` per record** (`GENERATED`, `REUSED`,
    `SKIPPED`, `ERROR`) with skip reasons `API_CAP_GENERATION`,
    `API_CAP_DAILY`, `API_BUDGET_UNAVAILABLE`. The gate consumes only
    `answers`; runtime must skip non-`GENERATED`/`REUSED` records and mark
    them `SKIPPED_UNCALIBRATED`/`SKIPPED_BUDGET` in its overlay (§6.4).

---

## 4. Runtime Lifecycle Modes

### 4.1 Mode semantics (locked)

| Mode | JEV provider may evaluate | Gate may evaluate | Research executor | Side effects allowed | Quant affected |
| --- | --- | --- | --- | --- | --- |
| `disabled` | NO | NO | NO | none | NO |
| `shadow` | YES (existing budget) | YES | NO | none | NO |
| `canary` | YES | YES (eligible heads only) | YES, bounded scope + budgets | research calls only, allowlisted | NO |
| `production` | YES | YES (eligible heads only) | YES, full eligible set + budgets | research calls only, allowlisted | NO |

Additional hard rules:

- `disabled`: no shadow scheduling, no gate evaluation, no overlay writes.
- `shadow`: shadow evaluations persist as today; gate artifacts persist; **no
  runtime overlay, no evidence, no research execution**.
- `canary`: requires at least one **eligible** requirement head (§5.5);
  otherwise runtime fails closed to shadow behavior with reason
  `CANARY_ELIGIBILITY_INCOMPLETE` and records no research side effects.
- `production`: requires **all five** actionable requirement heads eligible
  (`current_year_check`, `news`, `dart`, `deep_ai`, `invalidation_check`);
  otherwise runtime fails closed to shadow behavior with reason
  `PRODUCTION_ELIGIBILITY_INCOMPLETE` and records no research side effects.
- Advisory heads (`materialNow`, `historicalConflict`) never gate mode
  eligibility; `historicalConflict` maps to overlay semantics only (§8).

### 4.2 Config schema (future; NOT written in P0)

`config/season_jev.json` gains exactly two additive fields:

```json
{
  "mode": "disabled",
  "enabled": false,
  "... existing keys unchanged ...": null,
  "research": {
    "max_requirements_per_generation": 20,
    "max_research_calls_per_day": 30,
    "max_deep_ai_calls_per_day": 3,
    "requirement_timeout_ms": 15000,
    "generation_timeout_ms": 120000,
    "evidence_max_age_days": {
      "current_year_check": 45,
      "news": 14,
      "dart": 120,
      "deep_ai": 7,
      "invalidation_check": 30
    },
    "allowed_action_types": [
      "current_year_check", "news", "dart", "deep_ai", "invalidation_check"
    ],
    "canary": {
      "max_candidates_per_generation": 5,
      "max_research_calls_per_day": 10,
      "max_deep_ai_calls_per_day": 1,
      "allowed_action_types": ["current_year_check", "news", "dart"]
    }
  }
}
```

- `mode` is authoritative when present.
- `research` block is required for `canary` / `production`; missing or
  malformed → runtime fails closed to `shadow` behavior with
  `RESEARCH_CONFIG_INVALID` (no side effects).
- `config/jev_thresholds.json` schema is unchanged by this design.

### 4.3 Backward compatibility with `enabled: false|true`

Resolution algorithm (locked, pure, no config writes):

```text
resolve_runtime_mode(raw_cfg) -> (mode, reason, errors)

1. mode_present = "mode" in raw_cfg
2. enabled_present = "enabled" in raw_cfg
3. if mode_present:
     mode must be one of {"disabled","shadow","canary","production"}
       else -> ("disabled", "CONFIG_MODE_INVALID", [detail])
     if enabled_present:
       enabled must be bool else -> ("disabled", "CONFIG_MODE_INVALID", ...)
       if enabled != (mode != "disabled") -> ("disabled", "CONFIG_MODE_CONFLICT", ...)
     return (mode, None, [])
4. legacy (no mode):
     if enabled_present and enabled is True -> ("shadow", "LEGACY_ENABLED_TRUE", [])
     otherwise -> ("disabled", None, [])
```

Hard rules:

- Legacy resolution can only ever produce `shadow` or `disabled`. It can
  never produce `canary` or `production`.
- Any conflict or invalid value resolves to `disabled` (fail closed) and the
  runtime records the reason in its status surface.
- The runtime **never writes** `config/season_jev.json` or
  `config/jev_thresholds.json`. Mode/threshold changes are explicit
  human/GPT-approved commits only.

### 4.4 Minimal migration

| Step | Action | Approval |
| --- | --- | --- |
| M0 (today) | `enabled=false`, no `mode` → resolves `disabled` | none |
| M1 (P1) | add `"mode": "shadow"` and set `"enabled": true` in the same commit | explicit GPT/user approval required |
| M2 (P5) | add `research.canary` block + `"mode": "canary"` | explicit approval + canary scope review |
| M3 (P6) | set `"mode": "production"` after all five heads eligible | explicit approval + production readiness packet |

Rollback is the reverse of the same table (each step is a config-only commit).

### 4.5 Runtime Orchestration and Production Hook (locked)

Authoritative entrypoint (locked name):

```python
def request_runtime_evaluation(settings, bundle: Mapping[str, Any]) -> None:
    ...
```

- Lives in `src/kr_quant/research/jev_runtime.py`.
- Fire-and-forget: spawns one daemon worker thread and returns immediately;
  the caller (Season snapshot completion) never waits for JEV.
- One generation is single-flight (in-process lock + persisted artifacts).
- Any exception is logged to the runtime status surface; it must never
  propagate to the caller, never fail the Season snapshot, and never mutate
  deterministic Quant/Season artifacts.
- `bundle` must be a current completed 5-year Season bundle with a
  `generation_id` and `identity.lookback == 5`; otherwise return without
  side effects.

Mode behavior (locked):

```text
disabled:
  return; zero provider calls, zero gate writes, zero research

shadow:
  evaluate/persist JEV shadow  (existing season_jev_shadow path)
  → evaluate/persist gate       (run_shadow_gate_pass)
  → STOP (no executor, no evidence, no overlay)

canary:
  shadow → gate → eligibility → bounded executor → evidence verifier → overlay

production:
  same complete chain for all eligible candidates within budget
```

Production hook (locked):

- The single existing hook site is
  `src/kr_quant/web/season_snapshot.py::_schedule_shadow` (currently calls
  `season_jev_shadow.request_shadow_evaluation`).
- P1 replaces that call with `jev_runtime.request_runtime_evaluation`
  (delegation only; the hook's existing guard conditions stay:
  current completed bundle only, `lookback == 5`, never LKG serving).
- `season_snapshot.py` is the only production integration surface for P1–P6;
  no other caller may invoke the orchestrator implicitly.
- A CLI/operator command (`scripts/jev_runtime.py`, subcommand `runtime-pass`)
  is the second, explicitly documented entrypoint for operator runs and for
  P1.7 evidence. Both entrypoints call the same orchestrator function.
- LKG (`stale_while_revalidate` serving) must never trigger JEV.

### 4.6 Restart / Resume and Idempotency (locked)

For one generation, the orchestrator resumes from persisted artifacts:

```text
shadow exists, gate missing                              → resume at gate
shadow + gate exist, overlay missing (canary/production) → resume at executor
verified evidence exists with exact execution identity   → reuse (no side effects)
stale / mismatched identity                              → do not reuse
concurrent duplicate runtime request                     → single-flight (one worker)
process restart                                          → bounded resume from persisted artifacts
```

- No duplicate provider calls or research calls may occur merely because the
  web/server process restarted.
- Execution reuse identity is the 9-tuple in §6.5; gate reuse identity is the
  8-tuple in J3 §16.1; shadow reuse identity is the 4-tuple in §3.3 item 9.
- A resumed pass records `resumed=true` in the runtime overlay counts.

---

## 5. Calibration Activation Contract

### 5.1 Exact bucket identity (unchanged, hard)

```text
provider + requested_model + evaluator_version
```

Production eligibility is computed **per head** inside an exact bucket. No
cross-bucket transfer, no alias transfer, no evaluator fallback.

### 5.2 Threshold promotion lifecycle (locked)

```text
null
  → candidate threshold          (calibration sweep shortlist row, calibration split only)
  → calibration-selected         (human locks exactly one threshold per head; selection manifest hash recorded)
  → holdout-reviewed             (locked threshold evaluated once on pristine holdout; review_status attached)
  → explicitly approved locked   (approval record written; config value edited by explicit approved commit)
```

Hard rules:

- The engine never auto-writes a production threshold.
- `0.5`, hand-waved values, and cross-bucket values are forbidden.
- Holdout must be pristine at selection lock (`holdout_revealed=false`);
  re-selection after holdout reveal is not pristine validation.
- A threshold adopted into `config/jev_thresholds.json` without a matching
  approval record is **ineligible** for canary/production (fail closed).

### 5.3 Approval record (new artifact; locked schema)

Path:

```text
{data_dir}/research/jev_calibration/approvals/{bucket_hash}__{head}.json
```

`bucket_hash` = lowercase SHA-256 hex of the canonical UTF-8 JSON
(`sort_keys=True`, `ensure_ascii=False`, `separators=(",",":")`) of:

```json
{"provider": "...", "requested_model": "...", "evaluator_version": "..."}
```

Record:

```json
{
  "schema_version": 1,
  "approval_type": "jev_threshold_approval",
  "provider": "typesafe_direct",
  "requested_model": "jev-latest",
  "evaluator_version": "season-jev-shadow-v1",
  "head": "needsNews",
  "threshold": 0.64,
  "dataset_id": "labels-2026-09",
  "dataset_hash": "<64-hex>",
  "selection_manifest_hash": "<64-hex>",
  "selection_locked_at": "2026-09-23T00:00:00Z",
  "holdout_report_hash": "<64-hex>",
  "holdout_revealed_at": "2026-09-23T00:00:00Z",
  "holdout_pristine": true,
  "review_status": "ACCEPT",
  "support": {"valid_count": 0, "positive_count": 0, "negative_count": 0},
  "approved_by": "human",
  "approved_at": "2026-09-23T00:00:00Z",
  "approval_hash": "<64-hex over this record excluding approval_hash>"
}
```

Validation (locked):

- `threshold` must be finite in `[0,1]` and exactly equal to the config value
  at eligibility time.
- `review_status` must be `ACCEPT`.
- `holdout_pristine` must be `true`.
- `selection_manifest_hash` must match the locked selection's recomputed
  `selection_manifest_hash`.
- `holdout_report_hash` must match the canonical hash of the holdout report
  excluding its own hash field.
- `support.valid_count >= 100` (production review gate) and no
  `INSUFFICIENT_CLASS_SUPPORT` on the selection dataset.
- `approval_hash` must recompute exactly.

### 5.4 Runtime verification rule

```text
eligible(head) :=
    config_threshold(head) is finite in [0,1]
AND exact bucket exists in config
AND approval record exists for (bucket_hash, head)
AND approval.threshold == config_threshold(head)
AND approval_hash valid
AND review_status == "ACCEPT"
AND holdout_pristine == true
AND support gates satisfied
```

Otherwise the head is `INELIGIBLE` with a deterministic reason code
(`THRESHOLD_NULL`, `THRESHOLD_MALFORMED`, `BUCKET_MISSING`,
`APPROVAL_MISSING`, `APPROVAL_MISMATCH`, `REVIEW_NOT_ACCEPTED`,
`HOLDOUT_NOT_PRISTINE`, `SUPPORT_INSUFFICIENT`).

### 5.5 Mode eligibility thresholds

| Mode | Requirement |
| --- | --- |
| `shadow` | none (all heads may be null) |
| `canary` | `>= 1` of the five actionable heads eligible; canary `allowed_action_types` only |
| `production` | all five actionable heads eligible |

Ineligible heads in canary/production produce `decision=null` →
`SKIPPED_UNCALIBRATED` requirements (§6). They never silently become `false`.

---

## 6. Research Executor Design

### 6.1 Module and boundary

Future file: `src/kr_quant/research/jev_research_executor.py`
Future tests: `tests/unit/test_jev_research_executor.py`

Input (locked):

- a persisted Research Gate envelope (J3 artifact) for one
  `(generation_id, provider, requested_model, evaluator_version, threshold_config_hash)`
- resolved runtime mode (`canary` | `production`; `shadow`/`disabled` never
  reach the executor)
- raw runtime config (`research` block)
- injected adapter callables (allowlisted; tests inject offline fakes)

Output (locked):

- execution overlay artifact (§6.8)
- evidence objects handed to the verifier (§7) — the executor cannot bypass it

The executor MUST NOT:

- read or write Quant artifacts / scores / ranks
- call any function not in the action allowlist
- accept command names, module names, or paths from model output
- mutate gate artifacts, shadow artifacts, config, or calibration artifacts
- run in `shadow` / `disabled`

### 6.2 Requirement types (locked)

```text
current_year_check
news
dart
deep_ai
invalidation_check
```

Mapping from gate heads is fixed by J3 `_REQUIREMENT_MAP`:

| Head | Requirement |
| --- | --- |
| `needsCurrentYearCheck` | `current_year_check` |
| `needsNews` | `news` |
| `needsDart` | `dart` |
| `needsDeepAI` | `deep_ai` |
| `invalidationCheckNeeded` | `invalidation_check` |

`materialNow` / `historicalConflict` are advisory only and never produce
executor requirements.

### 6.3 Statuses (locked exact names)

```text
NOT_REQUIRED
PENDING
RUNNING
VERIFIED
PARTIAL
FAILED
SKIPPED_BUDGET
SKIPPED_UNCALIBRATED
SKIPPED_DISALLOWED
STALE
```

Semantics:

| Status | Meaning |
| --- | --- |
| `NOT_REQUIRED` | gate decision is `false` |
| `PENDING` | decision `true`; eligible; not yet executed (queued, deferred, or awaiting model-drift review) |
| `RUNNING` | execution in progress (single process; persisted for crash recovery) |
| `VERIFIED` | evidence executed and verifier returned `VERIFIED` |
| `PARTIAL` | some sub-evidence verified, some failed/unverified |
| `FAILED` | action or verification failed (evidence `ERROR`/`FAILED` reason) |
| `SKIPPED_BUDGET` | research budget exhausted |
| `SKIPPED_UNCALIBRATED` | gate decision is `null` or head ineligible |
| `SKIPPED_DISALLOWED` | requirement type absent from the mode's allowlist |
| `STALE` | previously verified evidence exceeded `evidence_max_age_days` |

### 6.4 Execution selection (locked)

For each candidate in the gate envelope `results[]`:

1. `gate.mode != "SHADOW_ONLY"` → candidate skipped (`SKIPPED_UNCALIBRATED`),
   never executed.
2. For each actionable requirement:
   - `false` → `NOT_REQUIRED`
   - `null` → `SKIPPED_UNCALIBRATED`
   - `true` → eligible for execution.
3. Mode allowlist check: type not in `research.allowed_action_types`
   (canary uses `research.canary.allowed_action_types`) → `SKIPPED_DISALLOWED`.
4. Canary sampling: candidates with `>= 1` executable requirement are sorted by
   `candidate_id` ascending (UTF-8) and the first
   `research.canary.max_candidates_per_generation` are executed; all others
   get `PENDING` with reason `CANARY_SCOPE_DEFERRED` and no side effects.
5. Production: no sampling; all eligible candidates execute.

### 6.5 Idempotency and reuse (locked)

Execution key (9-tuple):

```text
schema_version, generation_id, provider, requested_model, evaluator_version,
candidate_id, state_hash, requirement_type, input_hash
```

- `input_hash` = SHA-256 hex of canonical JSON of
  `{candidate_id, state_hash, requirement_type, state}` where `state` is the
  candidate state stored in the shadow artifact (clean state only).
- A prior overlay entry with the same key and `VERIFIED` evidence is reused
  (`VERIFIED`, `reused=true`); no new side effects.
- Same key with non-`VERIFIED` status may be retried within budget.
- Duplicate requests inside one runtime pass are single-flight (in-process
  lock + persisted `RUNNING` marker).

### 6.6 Budgets (locked)

- Research calls use a **separate** ledger from the JEV provider ledger:
  `{data_dir}/research_snapshots/season_jev_runtime/_budget/{day_kst}.json`
  with `{day_kst}.lock`, reusing `season_jev_budget.BudgetLock`.
- Caps: `research.max_requirements_per_generation` (per generation),
  `research.max_research_calls_per_day` (per KST day),
  `research.max_deep_ai_calls_per_day` (deep_ai only, tighter).
- Canary overrides: `research.canary.max_research_calls_per_day`,
  `research.canary.max_deep_ai_calls_per_day` (must be `<=` production caps;
  invalid override → `RESEARCH_CONFIG_INVALID`, no side effects).
- Exhaustion → `SKIPPED_BUDGET`; the ledger is written atomically under lock;
  crashes must never double-spend (reserve-then-execute; refund only on
  pre-call failure, mirroring `refund_daily_slot` semantics).
- JEV provider budget authority is unchanged and never consumed by the
  executor.

### 6.7 Timeouts and failure isolation (locked)

- Per requirement: `research.requirement_timeout_ms`.
- Per generation: `research.generation_timeout_ms`.
- Timeout → `FAILED` (reason `TIMEOUT`) for that requirement only; sibling
  requirements continue.
- Adapter exceptions are contained per requirement; one failure never
  aborts the generation.
- Process crash/restart: on next pass, persisted `RUNNING` entries older than
  `requirement_timeout_ms` are reclassified `FAILED` (reason
  `CRASH_RECOVERED`) and may be retried within budget.

### 6.8 Execution overlay (locked schema)

Path:

```text
{data_dir}/research_snapshots/season_jev_runtime/{generation_id}__{provider_safe}__runtime.json
```

```json
{
  "schema_version": 1,
  "artifact_type": "season_jev_runtime_overlay",
  "mode": "canary",
  "generation_id": "gen-A",
  "provider": "typesafe_direct",
  "requested_model": "jev-latest",
  "evaluator_version": "season-jev-shadow-v1",
  "threshold_config_hash": "<64-hex>",
  "gate_artifact_hash": "<64-hex>",
  "eligibility": {
    "eligible_heads": ["needsNews"],
    "ineligible_heads": {"needsDart": "THRESHOLD_NULL"},
    "mode_ok": true
  },
  "candidates": [
    {
      "candidate_id": "candidate-1",
      "state_hash": "<64-hex>",
      "requirements": {
        "news": {"status": "VERIFIED", "evidence_hash": "<64-hex>", "reused": false}
      },
      "overlay_status": "NO_CONFLICT_FOUND"
    }
  ],
  "budget": {"day_used": 1, "day_cap": 10, "deep_ai_used": 0, "deep_ai_cap": 1},
  "counts": {"requested": 1, "executed": 1, "verified": 1, "failed": 0,
             "skipped_budget": 0, "skipped_uncalibrated": 0,
             "skipped_disallowed": 0, "reused": 0},
  "side_effects_executed": true,
  "started_at": "...",
  "finished_at": "..."
}
```

- `side_effects_executed` is `true` only when at least one allowlisted
  research action actually ran in this pass (reuse-only passes stay `false`).
- No secrets, no raw provider payloads, no key material.
- Overlay writes are atomic; existing overlays are never partially overwritten.

### 6.9 Adapter allowlist (locked interface)

The executor calls exactly one function per requirement type, injected at
construction time; production wiring uses existing repo services where they
exist:

| Requirement | Adapter contract | Existing backend candidate |
| --- | --- | --- |
| `current_year_check` | `(ticker, as_of) -> raw evidence` | `kr_quant.ingest.recent_filings` (OpenDART) |
| `news` | `(ticker, company, as_of) -> raw evidence` | `kr_quant.ingest.naver_search.search_news` / `company_bundle` |
| `dart` | `(ticker, as_of) -> raw evidence` | OpenDART filings via `recent_filings` / DART ingest |
| `deep_ai` | `(state, verified_evidence) -> raw evidence` | existing analysis LLM path (`kr_quant.research.analyze` provider routing) with tight cap |
| `invalidation_check` | `(state, verified_evidence) -> raw evidence` | deterministic review of `invalidatingConditions` / `invalidatingRule` + verified evidence |

- The model never chooses the function, module, URL, or command.
- Adapters must not accept model-provided executable strings.
- Missing API keys / credentials for an adapter → `FAILED` (reason
  `CREDENTIAL_MISSING`) or `SKIPPED_DISALLOWED` if the mode allowlist excludes
  it; never a fallback to another source.
- P3 ships the executor with injected adapters; real adapter wiring is its own
  reviewed task and never enables a source that is not in the allowlist.

### 6.10 Shadow Status Preservation and Join Identity (locked)

J3 `evaluate_research_gate_generation` evaluates every `results[]` record and
does not itself preserve shadow SKIPPED semantics. The runtime layer solves
this without changing J3:

A. Only shadow records with `status` `GENERATED` or `REUSED` are gate
   candidates. `SKIPPED` / `ERROR` records are never passed to the gate.
B. Shadow `SKIPPED` / `ERROR` records retain their original `status` and
   `skip_reason` / `error` in runtime processing and in the overlay.
C. Runtime mapping (locked, deterministic):

```text
GENERATED / REUSED               → gate candidate
SKIPPED + API_CAP_GENERATION     → runtime SKIPPED_BUDGET (reason retained)
SKIPPED + API_CAP_DAILY          → runtime SKIPPED_BUDGET (reason retained)
SKIPPED + API_BUDGET_UNAVAILABLE → runtime SKIPPED_BUDGET (reason retained)
ERROR (provider/evaluation)      → runtime FAILED (original error retained)
```

D. A skipped API-budget record must never be converted into
   `MISSING_ANSWERS`, `MISSING_HEAD`, or generic uncalibrated merely because
   its `answers` is `{}`.
E. Gate artifacts contain only gate-eligible records (`GENERATED`/`REUSED`);
   the J3 envelope schema is unchanged. The runtime overlay carries the
   non-eligible records with their original provenance.
F. Runtime execution has access to both the original shadow record and the
   corresponding gate result, joined by the locked join key:

```text
generation_id + provider + requested_model + evaluator_version
+ candidate_id + state_hash
```

- Gate envelope `results[]` order and content are untouched by the runtime
  (no J3 schema change, no J3 core edit).
- A shadow record with missing/empty `state_hash` is not a gate candidate and
  is surfaced as `FAILED` with reason `STATE_HASH_MISSING`.

---

## 7. Evidence Verifier Design

### 7.1 Module and boundary

Future file: `src/kr_quant/research/jev_evidence.py`
Future tests: `tests/unit/test_jev_evidence.py`

- The executor's raw action output MUST be converted into Evidence objects and
  passed through the verifier before it can appear in an overlay as `VERIFIED`.
- The verifier performs no network calls in tests; in production it may perform
  bounded re-checks only through the same allowlisted adapters.
- The verifier never mutates gate/shadow/Quant artifacts.

### 7.2 Evidence object (locked schema)

```json
{
  "schema_version": 1,
  "evidence_type": "jev_evidence",
  "candidate_id": "candidate-1",
  "generation_id": "gen-A",
  "state_hash": "<64-hex>",
  "research_type": "news",
  "source_provider": "naver_news",
  "source_identity": "https://... or stable reference id",
  "source_date": "2026-09-22",
  "retrieved_at": "2026-09-23T10:00:00Z",
  "claim": "bounded claim text",
  "evidence_excerpt": "bounded excerpt",
  "excerpt_sha256": "<64-hex or null>",
  "truncated": false,
  "verification_status": "VERIFIED",
  "failure_reason": null,
  "input_hash": "<64-hex>",
  "artifact_hash": "<64-hex over this object excluding artifact_hash>"
}
```

Hard rules:

- `claim` <= 500 chars; `evidence_excerpt` <= 2000 chars; over-limit input is
  truncated and `truncated=true`.
- No secrets: objects containing key-like fields (`api_key`, `token`,
  `secret`, `password`, `authorization`, `cookie`) are rejected with
  `failure_reason=SECRET_REJECTED`.
- `source_identity` must be a stable URL or reference; local filesystem paths
  and `..` traversal are rejected (`failure_reason=INVALID_SOURCE_IDENTITY`).
- `artifact_hash` recomputation must be exact; mismatched or missing hash →
  `ERROR`.

### 7.3 Verification statuses (locked)

| Status | Rule |
| --- | --- |
| `VERIFIED` | all required provenance fields present; excerpt/hash valid; `source_date` within `evidence_max_age_days[research_type]`; source_identity stable |
| `UNVERIFIED` | provenance incomplete or source cannot be re-checked |
| `CONFLICT` | contradicts another verified evidence for the same candidate/type, or contradicts the candidate state (invalidation found) |
| `STALE` | `source_date` older than the per-type max age |
| `ERROR` | malformed evidence, adapter failure, hash mismatch, secret/path rejection |

Hard rules:

- Evidence failure must never silently become `evidence=false`. The
  requirement status reflects the failure (`FAILED` / `PARTIAL` / `STALE`) and
  the overlay exposes `UNVERIFIED` / `REVIEW_REQUIRED`.
- A candidate may not be marked `NO_CONFLICT_FOUND` unless the
  `invalidation_check` evidence is `VERIFIED`.

### 7.4 Max-age table (locked)

```text
current_year_check: 45 days
news:               14 days
dart:              120 days
deep_ai:             7 days
invalidation_check: 30 days
```

`source_date` null → `UNVERIFIED` (never `VERIFIED`).

---

## 8. Invalidation Semantics

### 8.1 Trigger mapping (locked)

| Gate signal | Executor action | Overlay result |
| --- | --- | --- |
| `invalidationCheckNeeded=true` | run `invalidation_check` | `CONFLICT_FOUND` if verifier returns `CONFLICT`; `NO_CONFLICT_FOUND` if `VERIFIED` and no conflict; `UNVERIFIED` if `UNVERIFIED`/`STALE`; `REVIEW_REQUIRED` if `FAILED`/`ERROR` |
| `historicalConflict=true` (advisory) | run `invalidation_check` (same requirement) | same mapping; advisory flag itself never routes |
| `historicalConflict=false` | no additional action | `NO_CONFLICT_FOUND` only if a verified `invalidation_check` exists; else `UNVERIFIED` |

### 8.2 Absolute prohibitions (hard)

`historicalConflict` / `invalidationCheckNeeded` MUST NOT directly:

- subtract Quant score
- change rank
- remove a candidate
- make a trade decision
- hide a candidate from the dashboard

They may only produce the overlay statuses above plus evidence references.
Overlay statuses are never inputs to deterministic Quant ranking.

---

## 9. Canary Design

### 9.1 Scope (locked)

- Deterministic sampling: eligible candidates sorted by `candidate_id`
  ascending; first `research.canary.max_candidates_per_generation`.
- Max research calls/day: `research.canary.max_research_calls_per_day`.
- Deep-AI tighter budget: `research.canary.max_deep_ai_calls_per_day`.
- Allowed action types: `research.canary.allowed_action_types`
  (default excludes `deep_ai` and `invalidation_check`).
- Canary never mutates Quant; rollback ladder never touches Quant.

### 9.2 Canary activation prerequisites (locked)

- `>= 1` actionable head eligible with an approval record.
- Shadow runtime has produced `>= 10` generation artifacts with gate results
  (P1 evidence).
- Research budget ledger and overlay paths verified writable (tmp-only in tests).
- Explicit GPT/user approval commit for `mode: canary`.

### 9.3 Comparison against human review (locked)

- Every Nth canary-executed candidate (deterministic:
  `int(sha256(candidate_id)[0:8], 16) % 5 == 0`) is queued for human review.
- Human review outcome values: `ACCEPT` | `REJECT` | `COLLECT_MORE_LABELS`
  (reusing J2 review vocabulary).
- Canary metrics on reviewed subsets are reported separately from unreviewed
  counts; no metric is fabricated when its denominator is 0 (report `null`).

### 9.4 Metrics (locked list)

```text
precision                     (TP / (TP+FP) or null)
recall                        (labelable subset only; null when undefined)
false_positive_research_rate  (executed requirement judged unnecessary by human review)
false_negative_research_rate  (human-flagged missing research for a candidate)
evidence_verified_rate        (VERIFIED / executed)
evidence_conflict_rate        (CONFLICT / executed)
provider_failure_rate         (FAILED+ERROR / attempted)
latency_p50_ms, latency_p95_ms (per requirement)
calls_per_candidate           (research calls / executed candidates)
cost_per_candidate_usd        (nullable; only when adapter reports cost)
budget_exhaustion_rate        (SKIPPED_BUDGET / requested)
reuse_rate                    (reused / (reused + executed))
resolved_model_change_rate    (candidates whose resolved_model differs from the approval-record distribution)
```

### 9.5 Rollback ladder and triggers (locked)

```text
production → canary → shadow → disabled
```

Triggers (evaluated on the latest metrics report; operator executes the
config-only rollback commit):

| Trigger | Action |
| --- | --- |
| `evidence_conflict_rate > 0.10` over `>= 20` executed requirements | reduce one level |
| `provider_failure_rate > 0.25` | reduce to `shadow` |
| `budget_exhaustion_rate > 0.50` | reduce one level |
| `resolved_model_change_rate > 0` | reduce to `shadow` pending review |
| any Quant-side anomaly, config conflict, or gate artifact corruption | reduce to `disabled` immediately |
| any credential leak suspicion in artifacts/logs | `disabled` immediately |

The runtime must also refuse to operate above its configured eligibility at
all times (defense in depth), independent of the operator ladder.

### 9.6 Observability (canary metrics artifact)

Path:

```text
{data_dir}/research_snapshots/season_jev_runtime/reports/canary_metrics.json
```

Contains per-generation counters and the aggregate metrics above with
`generated_at`, `window_days`, `reviewed_count`, `unreviewed_count`.

---

## 10. Fail-Closed / Failure Matrix

Columns: **JEV status** (runtime-visible), **research status**, **side effects
allowed?**, **Quant affected?**, **retry allowed?**, **user-visible state**.

| # | Scenario | JEV status | Research status | Side effects | Quant | Retry | User-visible |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | JEV API key absent | `JEV_NO_KEY` | `SKIPPED_UNCALIBRATED` (all) | NO | NO | YES (after key set) | overlay: `UNVERIFIED`, banner "JEV 키 없음" |
| 2 | Provider unavailable | `JEV_PROVIDER_ERROR` | `FAILED` per requirement, candidate `UNVERIFIED` | NO (failed before action) | NO | YES (next pass) | overlay: `UNVERIFIED` |
| 3 | Provider timeout | `JEV_TIMEOUT` | `FAILED` (`TIMEOUT`) | NO | NO | YES | overlay: `UNVERIFIED` |
| 4 | Malformed JEV answer | `JEV_MALFORMED_ANSWER` (shadow record `ERROR`) | `SKIPPED_UNCALIBRATED` | NO | NO | YES (re-evaluate) | overlay: `UNVERIFIED` |
| 5 | Missing head | `JEV_HEAD_MISSING` (gate `MISSING_HEAD`) | `SKIPPED_UNCALIBRATED` | NO | NO | YES | overlay: `UNVERIFIED` |
| 6 | Invalid probability | `JEV_PROBABILITY_INVALID` (gate `INVALID_PROBABILITY`) | `SKIPPED_UNCALIBRATED` | NO | NO | YES | overlay: `UNVERIFIED` |
| 7 | Threshold null | `JEV_THRESHOLD_NULL` | `SKIPPED_UNCALIBRATED` | NO | NO | YES (after approval) | overlay: `UNVERIFIED` |
| 8 | Threshold malformed | `JEV_THRESHOLD_MALFORMED` (gate `INVALID_THRESHOLD`) | `SKIPPED_UNCALIBRATED` | NO | NO | NO (fix config) | overlay: `UNVERIFIED`, config error banner |
| 9 | Exact threshold bucket missing | `JEV_BUCKET_MISSING` | `SKIPPED_UNCALIBRATED` | NO | NO | NO (add bucket) | overlay: `UNVERIFIED` |
| 10 | Resolved model differs | `JEV_RESOLVED_MODEL_DRIFT` | `PENDING` (`MODEL_DRIFT_REVIEW`) | NO | NO | NO (operator review) | overlay: `REVIEW_REQUIRED` |
| 11 | Calibration identity mismatch | `JEV_CALIBRATION_IDENTITY_MISMATCH` | `SKIPPED_UNCALIBRATED` | NO | NO | NO (fix approval/config) | overlay: `UNVERIFIED` |
| 12 | Research Executor timeout | unchanged | `FAILED` (`TIMEOUT`) for that requirement | partial (other requirements may run) | NO | YES | overlay: `REVIEW_REQUIRED` |
| 13 | News unavailable | unchanged | `FAILED` (`SOURCE_UNAVAILABLE`) | NO | NO | YES | overlay: `UNVERIFIED` |
| 14 | DART unavailable | unchanged | `FAILED` (`SOURCE_UNAVAILABLE`) | NO | NO | YES | overlay: `UNVERIFIED` |
| 15 | Deep-AI unavailable | unchanged | `FAILED` (`SOURCE_UNAVAILABLE`) or `SKIPPED_BUDGET` | NO | NO | YES | overlay: `UNVERIFIED` |
| 16 | Evidence malformed | unchanged | `FAILED` (`EVIDENCE_MALFORMED`) | NO | NO | YES | overlay: `UNVERIFIED` |
| 17 | Evidence conflict | unchanged | `VERIFIED` + `CONFLICT` | YES (research ran) | NO | NO (review) | overlay: `CONFLICT_FOUND` |
| 18 | Evidence stale | unchanged | `STALE` | YES (earlier run) | NO | YES (refresh) | overlay: `REVIEW_REQUIRED` |
| 19 | Source identity changes during work | unchanged | `FAILED` (`SOURCE_CHANGED`) | NO (publish withheld) | NO | YES | overlay: `UNVERIFIED` |
| 20 | Budget exhausted | unchanged | `SKIPPED_BUDGET` | NO | NO | YES (next day) | overlay: `PENDING`, budget banner |
| 21 | Process crash/restart | unchanged | `FAILED` (`CRASH_RECOVERED`) → retryable | NO (idempotent keys) | NO | YES | overlay: `PENDING` |
| 22 | Duplicate request | unchanged | single-flight: one `RUNNING`, others `PENDING`/reused | NO duplicate calls | NO | n/a | overlay unchanged |
| 23 | Stale generation | unchanged | overlay marked `STALE`, no execution | NO | NO | NO | overlay: `REVIEW_REQUIRED`, stale badge |
| 24 | Quant candidate disappears/replaces generation | unchanged | orphan overlay retained as audit; no new execution | NO | NO | NO | orphan listed read-only |

Cross-cutting rules:

- No row may produce `default true`, `default false`, `0.5`, provider
  fallback, Quant mutation, or silent candidate hiding.
- "Side effects allowed?" refers to research actions only; no row authorizes
  Quant or config writes.

---

## 11. Runtime Readiness Inventory (read-only, 2026-09-23)

| Item | Value |
| --- | --- |
| Season JEV shadow generations | 0 (`data/research_snapshots/season_jev_shadow/` absent) |
| Shadow budget ledger | 0 (`_budget/` absent) |
| JEV calibration labels / annotations | 0 (`data/research/jev_calibration/` absent) |
| Calibration locks | 0 (`selections/` absent) |
| JEV holdout reports | 0 (`reports/` absent) |
| Threshold approval records | 0 (`approvals/` absent) |
| Research gate persisted artifacts | 0 (`season_jev_research_gate/` absent) |
| Non-null thresholds | 0 / 14 |
| `config/season_jev.json` | `enabled=false`; no `mode`; provider `typesafe_direct`; model `jev-latest` |
| `TYPESAFE_API_KEY` | PRESENT |
| `OPENROUTER_API_KEY` | PRESENT |
| Season-strategy holdout artifacts (NOT JEV) | 12 files (`data/research_snapshots/season_holdout/`, latest 2026-09-08) |

Consequences:

- P1 shadow readiness work must be fixture-driven; the live shadow run is a
  separate, explicitly approved operator step.
- No production eligibility can exist today (0 approvals, 0 non-null thresholds).
- Runtime readiness for production is **UNPROVEN** until P1/P2 produce real
  shadow artifacts, labels, and approval records.

---

## 12. UI / Observability Contract (design only; P0 implements none)

Future read-only fields (minimum):

```text
jev_mode
provider
requested_model
resolved_models[]
generation_id
evaluated_count / reused_count / skipped_count / error_count
gate_calibrated_heads / gate_uncalibrated_heads
research_requested_count / research_executed_count /
  research_verified_count / research_failed_count
budget_day_used / budget_day_cap
budget_generation_used / budget_generation_cap
last_success_at / last_error
threshold_config_hash
approval_set_hash            (SHA-256 over sorted approval hashes for the bucket)
evidence_artifact_identity   (path hash + artifact_hash)
```

- P0/P1 add no UI. P6 may surface the overlay read-only; it must not add
  controls that mutate Quant or config.
- The overlay is additive; existing cards keep their current meaning.

---

## 13. Security / Privacy (locked)

- No API key or credential persistence in any artifact (overlay, evidence,
  approval, reports).
- No API key in logs; log presence only (`PRESENT` / `ABSENT`).
- No arbitrary shell command produced by model output.
- The model cannot choose executable command names, modules, or URLs; the
  executor uses allowlisted functions only.
- External content (news, filings) is untrusted input: bounded excerpt +
  hash; never executed, never interpreted as instructions.
- Path traversal rejected for `generation_id`, `provider`, `candidate_id`,
  `source_identity` (reject `..`, `/`, `\`, absolute paths, control chars).
- Atomic writes for every persisted artifact (`write_json_atomic` /
  `write_csv_atomic` conventions; no partial overwrite).
- Evidence objects reject secret-like fields (§7.2).
- Failure of any JEV/research component must not affect Quant availability.

---

## 14. Persistence Paths and Artifact Identity (locked)

```text
JEV shadow            {data_dir}/research_snapshots/season_jev_shadow/{generation_id}__{provider}.json      (existing)
Research gate         {data_dir}/research_snapshots/season_jev_research_gate/{generation_id}__{provider_safe}__gate.json  (existing)
Runtime overlay       {data_dir}/research_snapshots/season_jev_runtime/{generation_id}__{provider_safe}__runtime.json      (new)
Evidence bundle       {data_dir}/research_snapshots/season_jev_evidence/{generation_id}__{provider_safe}__evidence.json    (new)
Research budget       {data_dir}/research_snapshots/season_jev_runtime/_budget/{day_kst}.json + .lock                      (new)
Canary metrics        {data_dir}/research_snapshots/season_jev_runtime/reports/canary_metrics.json                         (new)
Calibration labels    {data_dir}/research/jev_calibration/labels/<dataset_id>.jsonl                                        (existing convention)
Calibration exports   {data_dir}/research/jev_calibration/exports/<dataset_id>.jsonl                                       (existing convention)
Calibration reports   {data_dir}/research/jev_calibration/reports/<dataset_id>*.json                                       (existing convention)
Calibration locks     {data_dir}/research/jev_calibration/selections/<dataset_id>__<head>.json                             (existing convention)
Threshold approvals   {data_dir}/research/jev_calibration/approvals/{bucket_hash}__{head}.json                             (new)
```

Artifact identity rules:

- Every new artifact carries `schema_version` and a canonical
  `artifact_hash` (SHA-256 over the canonical JSON excluding the hash field).
- Gate artifact identity is unchanged (J3); overlay/evidence reference it by
  hash.
- `provider_safe` follows the existing sanitizer pattern
  (`[A-Za-z0-9._-]` preserved, others `_`).
- Runtime artifacts are excluded from git via the existing
  `data/research_snapshots/` ignore rule; approvals live under
  `data/research/jev_calibration/` which is gitignored by J2 policy.

---

## 15. Testing Strategy (future implementation)

All new tests are offline fixtures (`tmp_path`, injected adapters, in-memory
configs). No network, no live provider calls, no production runtime dirs.

Required new test files:

```text
tests/unit/test_jev_runtime.py            (mode resolution, eligibility, approval, overlay, budget, canary scope)
tests/unit/test_jev_research_executor.py  (statuses, allowlist, budgets, idempotency, timeout, isolation)
tests/unit/test_jev_evidence.py           (schema, statuses, bounding, secret/path rejection, hashing)
tests/unit/test_jev_runtime_integration.py (hook + orchestration integration contracts)
```

`tests/unit/test_season_snapshot.py` is modified to cover the hook contract
(current bundle only, LKG never triggers JEV, runtime failure does not fail
the snapshot).

Mandatory coverage classes:

1. Mode resolution: legacy `enabled` mapping; conflict/invalid fail closed.
2. Eligibility: null/malformed/missing/approval-mismatch/not-accepted/
   not-pristine/insufficient-support → ineligible with exact reason.
3. Executor: `false`→`NOT_REQUIRED`; `null`→`SKIPPED_UNCALIBRATED`;
   disallowed→`SKIPPED_DISALLOWED`; budget→`SKIPPED_BUDGET`; timeout→`FAILED`;
   idempotent reuse; duplicate single-flight; crash recovery.
4. Evidence: all five statuses; excerpt bounding; secret rejection; path
   rejection; hash recomputation.
5. Invalidation overlay mapping (all four statuses).
6. Canary: deterministic sampling; cap enforcement; deep-AI tighter cap;
   metrics null-safety on zero denominators.
7. Failure matrix: one test per row 1–24 (P6.3 pre-production gate).
8. Invariance: no config writes; `enabled=false` until approved activation;
   thresholds 14/14 null until approved adoption; no Quant imports in new
   modules; no network imports (static AST checks mirroring J3 Task 5).
9. Integration contracts (locked, 12): (1) current Season bundle → orchestrator
   called exactly once; (2) disabled → no provider call, no gate write, no
   executor, no evidence; (3) shadow → shadow + gate written, executor/evidence
   never called; (4) shadow SKIPPED budget record retains original skip reason
   and is never converted to `MISSING_ANSWERS`; (5) shadow ERROR record is
   isolated and accurately surfaced; (6) canary executes only the deterministic
   bounded candidate subset; (7) production executes only eligible `true`
   requirements; (8) verifier is mandatory before any `VERIFIED` overlay;
   (9) runtime exception leaves the Season snapshot valid/current; (10) LKG
   serve does not schedule runtime JEV; (11) duplicate same generation causes
   no duplicate provider/research side effect; (12) process resume continues
   from existing exact artifacts.

---

## 16. Phase Decomposition

P1–P7 are retained with three locked adjustments required by the P0 review:

- P1 now includes the authoritative runtime orchestrator
  (`request_runtime_evaluation`) and the real production hook
  (`season_snapshot._schedule_shadow` delegation) plus integration tests, so
  the chain is reachable from a continuously executed runtime path — not just
  defined.
- P5 adds an explicitly authorized live canary operation task after config
  activation; config mode alone is not accepted as evidence.
- P6 places the pre-production certification gate (failure matrix, runtime
  integration, isolation, full suite, canary metrics, rollback) **before**
  production activation; P7 then holds final invariance certification and the
  readiness record.

Justification for the ordering:

- P1 is the only phase that touches live providers, and it is shadow-only —
  isolating it first produces the runtime evidence P2+ needs.
- P2 separates *calibration correctness* (labels, locks, holdout) from
  *execution safety* (P3/P4), so an error in either cannot silently combine.
- P3 (executor) and P4 (verifier) are separate modules and separate review
  gates because the verifier is the trust boundary for external content.
- P5 (canary) precedes P6 (production) so live research scope is proven under
  caps before full eligibility is required.
- Certification precedes activation so production cannot be enabled before
  the failure/isolation evidence exists.

No phase may skip its STOP/review gate. No phase changes Quant behavior.

---

## 17. Non-Goals

- Quant score blending or any Quant mutation
- Trade execution / portfolio weighting
- Automatic threshold deployment
- Provider winner selection or cross-provider fallback
- Redesign of J1/J2/J3 contracts
- Dashboard redesign beyond the read-only observability contract
- Env Manager work
- Naming a "J4" phase

---

## 18. Definition of Done (future, per phase in the plan)

Production v1 is done only when:

- Modes resolve exactly as specified and fail closed on conflict.
- Every canary/production head is approval-gated per §5.
- Executor runs only allowlisted, budgeted, idempotent actions.
- Evidence verification is mandatory and fail-closed.
- Failure matrix rows 1–24 have executable tests, green **before** production
  activation (P6.3 gate).
- The orchestrator entrypoint is reachable from the production hook
  (`_schedule_shadow`) and from the documented operator CLI; no
  function-only dead code.
- Integration contracts in §15 item 9 are green.
- `config/jev_thresholds.json` non-null values exist only with approval
  records; `config/season_jev.json` mode changes only via approved commits.
- Full pytest suite green; no Quant regression.
- GPT/user accepts the P7 production readiness packet.

---

## 19. Safety Summary

| Invariant | Lock |
| --- | --- |
| Quant ranking authority | unchanged, deterministic |
| JEV failure isolation | mandatory |
| `disabled` default | yes (no `mode` → `disabled`) |
| Legacy `enabled=true` | resolves to `shadow` only |
| Production threshold | approval record + config edit only |
| `0.5` / defaults / cross-bucket | forbidden |
| Research execution | allowlisted, budgeted, canary-gated |
| Evidence failure | never becomes `evidence=false` |
| Invalidation signals | overlay only; no score/rank effect |
| Config writes by runtime | forbidden |
| Secrets in artifacts/logs | forbidden |
| Network in tests | forbidden |
| Runtime orchestrator | single authoritative entrypoint; fire-and-forget |
| Season snapshot hook | `_schedule_shadow` delegation only; current bundle only |
| LKG serving | never triggers JEV |
| Shadow SKIPPED/ERROR | provenance preserved; never converted to gate errors |
| Production activation | blocked until the P6.3 pre-production certification gate passes |

## Self-Review Checklist (author)

- [x] Modes locked with exact semantics and fail-closed resolution
- [x] Backward compatibility + minimal migration specified
- [x] Threshold promotion chain locked (null → approved)
- [x] Executor statuses locked (10 exact names)
- [x] Evidence schema + statuses locked (5 exact names)
- [x] Invalidation overlay statuses locked (4 exact names)
- [x] Canary scope, budgets, metrics, rollback locked
- [x] Failure matrix covers all 24 required scenarios
- [x] Runtime readiness inventory recorded (read-only)
- [x] Observability fields listed; P0 implements none
- [x] Security/privacy rules locked
- [x] Doc↔code comparison notes recorded
- [x] Runtime orchestrator entrypoint + production hook locked
- [x] Shadow status preservation + join identity locked
- [x] Restart/resume + single-flight rules locked
- [x] Integration test contracts (12) locked
- [x] Certification ordered before production activation
- [x] No TODO/TBD placeholders
- [x] No implementation in this commit

---

**END OF JEV PRODUCTION ROUTING V1 DESIGN**
