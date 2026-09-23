# JEV Production Activation Implementation Plan (P1–P7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the existing JEV shadow / calibration / research-gate stack (J1–J3) to a safe Production v1 with explicit runtime modes, approval-gated thresholds, a bounded research executor, a mandatory evidence verifier, and canary-before-production, without ever mutating deterministic Quant.

**Architecture:** One new runtime module (`jev_runtime.py`) owns mode resolution, approval-gated eligibility, overlay/status persistence, and canary metrics. One new executor module (`jev_research_executor.py`) owns allowlisted, budgeted, idempotent research execution. One new evidence module (`jev_evidence.py`) owns evidence objects and verification. Existing J1–J3 contracts are consumed, not redesigned; any proven interface deficiency requires STOP + approval before editing.

**Tech Stack:** Python 3.11+, pytest, stdlib `json` / `hashlib` / `math` / `pathlib` / `datetime`, existing `kr_quant.atomic_io.write_json_atomic`, existing `season_jev_budget.BudgetLock`, existing J2/J3 modules. No new dependencies. No Node changes.

**Spec:** `docs/superpowers/specs/2026-09-23-jev-production-routing-design.md`
**Base:** `origin/main` @ `44b2c467be59d90851705e9ea7f0175a38203727`
**Design branch (already created):** `jev-production-v1-design`

---

## Execution Notes

DO NOT run all tasks continuously.

After each implementation Task:

1. run that Task's targeted tests
2. run required invariance checks
3. stage **exact paths only** (never `git add .` / `git add -A`)
4. `git diff --cached --check` (must exit 0)
5. commit with the Task subject
6. push the implementation branch (**no force**)
7. return the Task verification packet
8. **STOP for GPT/user review**

Only start the next Task after explicit approval.

Config-activation Tasks (1.4, 2.4 adoption, 5.3, 6.3) additionally require an
explicit GPT/user approval message **before** the config commit is created.

Work in an isolated worktree. Do not use a dirty primary checkout.

Recommended future implementation branch (create only when Task 1.1 starts —
**not** during this planning commit):

```text
jev-production-v1-impl
```

Recommended worktree:

```text
C:\Users\a4jud\kr_quant_research-jev-prod-impl
```

---

## Global Constraints

Hard constraints for every Task:

- Keep `config/season_jev.json` `enabled=false` and `config/jev_thresholds.json`
  all-null **until** an explicitly approved activation/adoption Task says
  otherwise (only Tasks 1.4, 2.4, 5.3, 6.3 may change them, each with its own
  approval and STOP gate).
- No production routing before P6.3; no research side effects before P5.3.
- No JEV provider calls or research calls in unit tests.
- No Quant rank/score/snapshot/trade/portfolio mutation anywhere.
- No provider fallback, model fallback, evaluator fallback, or `0.5` fallback.
- No `default true` / `default false` for null thresholds or failed evidence.
- No secrets in artifacts, logs, or fixtures.
- No new runtime artifacts under real data dirs in tests (`tmp_path` only).
- No `git add .` / `git add -A` / force push / amend.
- Runtime code never writes config files.

Test runner (venv lives in the main checkout; worktrees use this interpreter):

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest <target> -q --tb=short
```

Every Task below declares, explicitly:

```text
Files | Interfaces consumed | Interfaces produced | Tests (files) |
RED-first | Test command | Implementation | Verification command |
Commit subject | STOP gate
```

Config/operator Tasks declare `RED-first: N/A` explicitly with the reason and
carry a verification-only contract instead. No silent omissions.

---

## Review Focus

| # | Risk | Primary Tasks |
| --- | --- | --- |
| 1 | Mode conflict silently enabling canary/production | 1.1, 6.1 |
| 2 | Threshold adopted without approval record | 2.1, 2.2 |
| 3 | Executor running non-allowlisted or unbudgeted actions | 3.1, 3.2, 3.3 |
| 4 | Unverified evidence reaching an overlay as VERIFIED | 4.1, 4.2, 4.3 |
| 5 | JEV/research failure leaking into Quant | 1.3, 3.2, 7.2 |
| 6 | Canary exceeding caps or failing to roll back | 5.1, 5.2, 5.3 |
| 7 | Config changed outside approved activation tasks | 1.4, 2.4, 5.3, 6.3, 7.2 |

---

## File Map

### Planned create

```text
src/kr_quant/research/jev_runtime.py
src/kr_quant/research/jev_research_executor.py
src/kr_quant/research/jev_evidence.py
scripts/jev_threshold_approval.py
tests/unit/test_jev_runtime.py
tests/unit/test_jev_research_executor.py
tests/unit/test_jev_evidence.py
docs/superpowers/plans/2026-09-23-jev-production-v1-certification.md   (P7.3)
```

### Planned modify

```text
config/season_jev.json                 (only Tasks 1.4, 5.3, 6.3)
config/jev_thresholds.json             (only Task 2.4 adoption)
src/kr_quant/web/app.py                (P6.2 read-only endpoint)
src/kr_quant/web/static/app.js         (P6.2 read-only display)
tests/unit/test_web_app.py             (P6.2)
```

### Expected unchanged (all phases)

```text
src/kr_quant/research/season_jev_shadow.py
src/kr_quant/research/season_jev_budget.py
src/kr_quant/research/jev_calibration.py
src/kr_quant/research/jev_research_gate.py
src/kr_quant/atomic_io.py
scripts/jev_calibration_export.py
scripts/jev-season-shadow.mjs
scripts/jev-season-shadow-openrouter.mjs
```

If any of the above must change: **STOP**, return evidence, await approval.

### Runtime paths (not tracked; tests use tmp_path only)

```text
{data_dir}/research_snapshots/season_jev_runtime/{generation_id}__{provider_safe}__runtime.json
{data_dir}/research_snapshots/season_jev_evidence/{generation_id}__{provider_safe}__evidence.json
{data_dir}/research_snapshots/season_jev_runtime/_budget/{day_kst}.json + .lock
{data_dir}/research_snapshots/season_jev_runtime/reports/canary_metrics.json
{data_dir}/research/jev_calibration/approvals/{bucket_hash}__{head}.json
```

---

## Fixed public interfaces (lock these names across Tasks)

### `jev_runtime.py` constants

```python
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_ARTIFACT_TYPE = "season_jev_runtime_overlay"

MODE_DISABLED = "disabled"
MODE_SHADOW = "shadow"
MODE_CANARY = "canary"
MODE_PRODUCTION = "production"
MODES = (MODE_DISABLED, MODE_SHADOW, MODE_CANARY, MODE_PRODUCTION)

STATUS_ELIGIBLE = "ELIGIBLE"
STATUS_INELIGIBLE = "INELIGIBLE"

ACTIONABLE_HEADS = (
    "needsCurrentYearCheck", "needsNews", "needsDart",
    "needsDeepAI", "invalidationCheckNeeded",
)
```

Eligibility reason codes (locked):

```text
THRESHOLD_NULL, THRESHOLD_MALFORMED, BUCKET_MISSING, APPROVAL_MISSING,
APPROVAL_MISMATCH, REVIEW_NOT_ACCEPTED, HOLDOUT_NOT_PRISTINE,
SUPPORT_INSUFFICIENT
```

Mode resolution reasons (locked):

```text
CONFIG_MODE_INVALID, CONFIG_MODE_CONFLICT, LEGACY_ENABLED_TRUE,
CANARY_ELIGIBILITY_INCOMPLETE, PRODUCTION_ELIGIBILITY_INCOMPLETE,
RESEARCH_CONFIG_INVALID
```

### `jev_runtime.py` functions

```python
def load_raw_runtime_config(settings) -> dict: ...
def resolve_runtime_mode(raw_cfg: Mapping[str, Any]) -> dict: ...
    # -> {"mode": str, "reason": str|None, "errors": list[str]}

def run_shadow_gate_pass(settings, *, shadow_payload: Mapping[str, Any],
                         threshold_cfg: Mapping[str, Any]) -> dict: ...
    # disabled -> {"status": "SKIPPED", "reason": "MODE_DISABLED"} (no writes)
    # envelope error -> {"status": "ERROR", "error": {...}} (no writes)
    # ok -> {"status": "OK", "gate": <envelope>, "path": str}

def runtime_status(settings, *, threshold_cfg: Mapping[str, Any] | None = None) -> dict: ...
def bucket_hash(provider: str, requested_model: str, evaluator_version: str) -> str: ...
def build_approval_record(*, provider, requested_model, evaluator_version, head,
                          threshold, dataset_id, dataset_hash,
                          selection_manifest_hash, selection_locked_at,
                          holdout_report_hash, holdout_revealed_at,
                          holdout_pristine, review_status, support,
                          approved_by, approved_at) -> dict: ...
def approval_record_hash(record: Mapping[str, Any]) -> str: ...
def verify_approval_record(record: Mapping[str, Any], *, provider, requested_model,
                           evaluator_version, head, threshold) -> dict: ...
    # -> {"ok": bool, "reason": str|None}

def resolve_head_eligibility(*, threshold_cfg, approvals_dir, provider,
                             requested_model, evaluator_version, head) -> dict: ...
def resolve_mode_eligibility(*, mode, threshold_cfg, approvals_dir, provider,
                             requested_model, evaluator_version) -> dict: ...
    # -> {"mode_ok": bool, "reason": str|None, "eligible_heads": [...],
    #     "ineligible_heads": {head: reason}}

def resolve_research_config(mode: str, raw_cfg: Mapping[str, Any]) -> dict: ...
def canary_rollback_guard(*, metrics: Mapping[str, Any]) -> dict: ...
def compute_canary_metrics(*, overlays: list[dict], reviews: list[dict]) -> dict: ...
def runtime_overlay_path(settings, generation_id: str, provider: str) -> Path: ...
def evidence_bundle_path(settings, generation_id: str, provider: str) -> Path: ...
def write_runtime_overlay(path: Path, payload: Mapping[str, Any]) -> None: ...
def write_canary_metrics_report(settings, metrics: Mapping[str, Any]) -> Path: ...
```

### `jev_research_executor.py` constants

```python
EXECUTOR_SCHEMA_VERSION = 1

STATUS_NOT_REQUIRED = "NOT_REQUIRED"
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_VERIFIED = "VERIFIED"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED_BUDGET = "SKIPPED_BUDGET"
STATUS_SKIPPED_UNCALIBRATED = "SKIPPED_UNCALIBRATED"
STATUS_SKIPPED_DISALLOWED = "SKIPPED_DISALLOWED"
STATUS_STALE = "STALE"

REQUIREMENT_TYPES = (
    "current_year_check", "news", "dart", "deep_ai", "invalidation_check",
)
```

### `jev_research_executor.py` functions

```python
def build_execution_plan(*, gate_envelope: Mapping[str, Any], mode: str,
                         research_cfg: Mapping[str, Any],
                         eligibility: Mapping[str, Any]) -> dict: ...
def execution_key(*, generation_id, provider, requested_model, evaluator_version,
                  candidate_id, state_hash, requirement_type,
                  input_hash) -> tuple: ...
def run_execution_pass(*, settings, gate_envelope, plan, adapters,
                       now=None) -> dict: ...
def default_adapters(settings) -> dict: ...
def load_reusable_executions(settings, generation_id, provider) -> dict: ...
```

### `jev_evidence.py` constants

```python
EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_ARTIFACT_TYPE = "jev_evidence"

EVIDENCE_VERIFIED = "VERIFIED"
EVIDENCE_UNVERIFIED = "UNVERIFIED"
EVIDENCE_CONFLICT = "CONFLICT"
EVIDENCE_STALE = "STALE"
EVIDENCE_ERROR = "ERROR"

OVERLAY_REVIEW_REQUIRED = "REVIEW_REQUIRED"
OVERLAY_CONFLICT_FOUND = "CONFLICT_FOUND"
OVERLAY_NO_CONFLICT_FOUND = "NO_CONFLICT_FOUND"
OVERLAY_UNVERIFIED = "UNVERIFIED"

MAX_CLAIM_CHARS = 500
MAX_EXCERPT_CHARS = 2000

DEFAULT_MAX_AGE_DAYS = {
    "current_year_check": 45, "news": 14, "dart": 120,
    "deep_ai": 7, "invalidation_check": 30,
}
```

### `jev_evidence.py` functions

```python
def build_evidence(*, candidate_id, generation_id, state_hash, research_type,
                   source_provider, source_identity, source_date, retrieved_at,
                   claim, evidence_excerpt, input_hash) -> dict: ...
def evidence_artifact_hash(evidence: Mapping[str, Any]) -> str: ...
def validate_evidence(evidence: Mapping[str, Any]) -> dict: ...
    # -> {"ok": bool, "reason": str|None}
def verify_evidence(*, evidence: Mapping[str, Any],
                    max_age_days: Mapping[str, int],
                    now=None,
                    prior_verified: Sequence[Mapping[str, Any]] = ()) -> dict: ...
    # -> {"status": str, "failure_reason": str|None}
def write_evidence_bundle(path: Path, evidences: Sequence[Mapping[str, Any]]) -> None: ...
```

---

## Task 1.1: Runtime Mode Resolution

**Files**
- CREATE `src/kr_quant/research/jev_runtime.py`
- CREATE `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** raw `config/season_jev.json` (read-only), `Settings.root`.

**Interfaces produced:** module constants; `load_raw_runtime_config`;
`resolve_runtime_mode` (signature above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** write failing tests first (cases below), then implement GREEN.

- [ ] RED cases:
  - `mode` absent + `enabled=false` → `disabled`
  - `mode` absent + `enabled=true` → `shadow` + reason `LEGACY_ENABLED_TRUE`
  - `mode` absent + `enabled` absent → `disabled`
  - `mode="shadow"` + `enabled=true` → `shadow`
  - `mode="canary"` + `enabled=false` → `disabled` + `CONFIG_MODE_CONFLICT`
  - `mode="production"` + `enabled` non-bool → `disabled` + `CONFIG_MODE_INVALID`
  - `mode="bogus"` → `disabled` + `CONFIG_MODE_INVALID`
  - config file missing/unreadable → `disabled` + errors recorded
  - resolution is pure: input mapping never mutated; no file writes

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement constants, `load_raw_runtime_config`,
`resolve_runtime_mode` exactly per spec §4.3.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
git diff --check
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): add JEV runtime mode resolution`

**STOP gate:** Task verification packet returned; await approval before Task 1.2.

---

## Task 1.2: Shadow Gate Runtime Pass

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** `evaluate_research_gate_generation`,
`research_gate_path`, `write_research_gate_artifact`, `ResearchGateError`
(from `kr_quant.research.jev_research_gate`); `resolve_runtime_mode`.

**Interfaces produced:** `run_shadow_gate_pass` (signature above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - `disabled` → `SKIPPED`/`MODE_DISABLED`, no artifact written (tmp_path)
  - valid fixture envelope → gate artifact written atomically at the exact
    `research_gate_path`; returned gate equals persisted bytes
  - envelope corruption → `ERROR`, no artifact written
  - repeated calls with identical input → byte-identical artifact (no churn)
  - unsupported provider in payload → `ERROR` (`ResearchGateError`), no write

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement `run_shadow_gate_pass` using only
existing J3 functions; no J3 core edits.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_gate.py -q --tb=short
git diff -- config/ src/kr_quant/research/jev_research_gate.py    # must be empty
```

**Commit subject:** `feat(jev): wire shadow gate runtime pass`

**STOP gate:** Await approval before Task 1.3.

---

## Task 1.3: Runtime Status Snapshot

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** existing shadow artifacts, gate artifacts (read-only);
`resolve_runtime_mode`.

**Interfaces produced:** `runtime_status` (signature above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - counts reflect `evaluated/reused/skipped/error` from the latest shadow artifact
  - gate calibrated/uncalibrated head counts
  - mode + reason surfaced; missing dirs → zeros, no exception
  - `threshold_config_hash` present when a gate artifact exists
  - no file writes during `runtime_status`

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement `runtime_status`.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): add JEV runtime status snapshot`

**STOP gate:** Await approval before Task 1.4.

---

## Task 1.4: Activate Shadow Runtime Mode (config; explicit approval)

**Files**
- MODIFY `config/season_jev.json` only.

**Interfaces consumed:** `resolve_runtime_mode` (verification only).

**Interfaces produced:** none (config data).

**Tests (files):** none new; existing `tests/unit/test_jev_runtime.py` and
`tests/unit/test_season_jev_shadow.py` act as regression.

**RED-first:** N/A — config-only activation task. No new behavior is written;
the contract is verification-only (mode resolves to `shadow`; no other diff).

- [ ] REQUIRED: explicit GPT/user approval message recorded in the task packet.
- [ ] Edit exactly two fields: `"mode": "shadow"`, `"enabled": true`.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_season_jev_shadow.py -q --tb=short
```

**Implementation:** apply the two-field edit; stage only
`config/season_jev.json`.

**Verification command**

```powershell
git diff --cached -- config/season_jev.json        # exactly the two fields
git diff -- config/jev_thresholds.json             # must be empty
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -c "from pathlib import Path; from types import SimpleNamespace; from kr_quant.research.jev_runtime import load_raw_runtime_config, resolve_runtime_mode; s=SimpleNamespace(root=Path('.'), data_dir=Path('data')); print(resolve_runtime_mode(load_raw_runtime_config(s))['mode'])"
```

**Commit subject:** `chore(jev): activate JEV shadow runtime mode`

**STOP gate:** Await approval before Task 1.5.

---

## Task 1.5: Live Shadow Evidence Run (operator; no code)

**Files**
- None (no code or config change).

**Interfaces consumed:** existing shadow scheduling + `run_shadow_gate_pass`.

**Interfaces produced:** runtime artifacts under real data dirs (shadow +
gate only; no research, no evidence).

**Tests (files):** none (operator run).

**RED-first:** N/A — operator evidence task. Contract is observational
(counts + artifact presence); no code change, so empty commit is forbidden.

- [ ] Run the existing season snapshot / shadow path with `enabled=true`.
- [ ] Verify one shadow artifact exists under
  `data/research_snapshots/season_jev_shadow/` and one gate artifact under
  `data/research_snapshots/season_jev_research_gate/`.
- [ ] Record counts and the generation id in the verification packet.
- [ ] Confirm zero research calls and zero evidence artifacts.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** operate the pipeline once; no code changes.

**Verification command**

```powershell
Get-ChildItem data/research_snapshots/season_jev_shadow
Get-ChildItem data/research_snapshots/season_jev_research_gate
Get-ChildItem data/research_snapshots/season_jev_evidence -ErrorAction SilentlyContinue   # must be absent/empty
```

**Commit subject:** NO COMMIT (empty commit forbidden).

**STOP gate:** Return evidence; await approval before P2.

---

## Task 2.1: Approval Record Contract

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** none external; canonical JSON helpers local to the
module.

**Interfaces produced:** `bucket_hash`, `build_approval_record`,
`approval_record_hash`, `verify_approval_record` (signatures above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - valid record verifies (`ok=true`)
  - `threshold` mismatch with config value → `APPROVAL_MISMATCH`
  - `review_status="REJECT"` → `REVIEW_NOT_ACCEPTED`
  - `holdout_pristine=false` → `HOLDOUT_NOT_PRISTINE`
  - tampered `approval_hash` → `APPROVAL_MISMATCH`
  - `support.valid_count < 100` → `SUPPORT_INSUFFICIENT`
  - bucket mismatch → `APPROVAL_MISMATCH`
  - `bucket_hash` is deterministic 64-hex and identity-sensitive

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: canonical JSON (`sort_keys=True`,
`ensure_ascii=False`, compact separators) + the four functions.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): add threshold approval record contract`

**STOP gate:** Await approval before Task 2.2.

---

## Task 2.2: Approval-Gated Eligibility Resolution

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** `verify_approval_record`, `lookup_threshold`
(`kr_quant.research.jev_calibration`).

**Interfaces produced:** `resolve_head_eligibility`,
`resolve_mode_eligibility`, `resolve_research_config` (signatures above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases for every reason code:
  `THRESHOLD_NULL`, `THRESHOLD_MALFORMED`, `BUCKET_MISSING`,
  `APPROVAL_MISSING`, `APPROVAL_MISMATCH`, `REVIEW_NOT_ACCEPTED`,
  `HOLDOUT_NOT_PRISTINE`, `SUPPORT_INSUFFICIENT`; plus:
  - canary requires `>= 1` actionable head; production requires all five
  - advisory heads never affect `mode_ok`
  - `resolve_research_config` validates canary overrides `<=` production caps
    and returns `RESEARCH_CONFIG_INVALID` on violation

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement the three functions; fail closed.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_calibration.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): resolve approval-gated head eligibility`

**STOP gate:** Await approval before Task 2.3.

---

## Task 2.3: Approval CLI (offline)

**Files**
- CREATE `scripts/jev_threshold_approval.py`
- MODIFY `tests/unit/test_jev_runtime.py` (CLI import test, mirroring
  `_load_calibration_cli` style)

**Interfaces consumed:** `jev_runtime.build_approval_record`,
`verify_approval_record`, `write_json_atomic`; selection JSON and holdout
report JSON files.

**Interfaces produced:** subcommands `build` and `verify`; `build` writes the
approval artifact atomically; `verify` prints JSON `{ok, reason}` and exits 0/1.

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - `build` with valid selection + holdout report writes the exact approval path
  - `build` refuses `review_status != ACCEPT`
  - `verify` returns `ok=true` for a valid artifact and exit 0
  - `verify` returns `ok=false` for a tampered artifact and exit 1
  - CLI imports only `argparse/json/sys/pathlib` + `kr_quant` (no network)

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement the CLI with argparse; no network.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
git diff -- config/ scripts/jev_calibration_export.py    # must be empty
```

**Commit subject:** `feat(jev): add threshold approval CLI`

**STOP gate:** Await approval before Task 2.4.

---

## Task 2.4: Calibration + Threshold Adoption (operator; repeat per head)

**Files**
- MODIFY `config/jev_thresholds.json` (one head value per approved adoption).

**Interfaces consumed:** existing calibration CLI (`scripts/jev_calibration_export.py`),
new approval CLI (`scripts/jev_threshold_approval.py`), `resolve_head_eligibility`.

**Interfaces produced:** approval artifacts under
`data/research/jev_calibration/approvals/`; one config threshold value.

**Tests (files):** none new; `tests/unit/test_jev_runtime.py` is the regression.

**RED-first:** N/A — data-dependent operator adoption. Contract: value copied
verbatim from a verified approval record; exactly one config value changes;
eligibility flips to `ELIGIBLE`.

- [ ] Export/label/ingest/report with the existing CLI:

```powershell
python scripts/jev_calibration_export.py export-candidates --shadow <artifact> --out <dataset.jsonl>
python scripts/jev_calibration_export.py blind-template --dataset <dataset.jsonl> --out <labels_template.jsonl>
python scripts/jev_calibration_export.py ingest-labels --labels <labels_filled.jsonl> --dataset <dataset.jsonl> --out <dataset_labeled.jsonl>
python scripts/jev_calibration_export.py calibration-report --dataset <dataset_labeled.jsonl> --out <report.json>
python scripts/jev_calibration_export.py lock-selection --manifest <selection.json> --out <selection_locked.json>
python scripts/jev_calibration_export.py holdout-eval --dataset <dataset_labeled.jsonl> --selection <selection_locked.json> --out <holdout_report.json>
```

- [ ] Require holdout `review_status=ACCEPT` and `holdout_pristine=true`.
- [ ] Build + verify the approval artifact:

```powershell
python scripts/jev_threshold_approval.py build --selection <selection_locked.json> --holdout <holdout_report.json> --out <approvals_dir>\<bucket_hash>__<head>.json
python scripts/jev_threshold_approval.py verify --approval <approval.json> --config config/jev_thresholds.json
```

- [ ] MODIFY `config/jev_thresholds.json`: set exactly one value — copy
  `threshold` from the approval record for that head. Nothing else changes.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** run the chain; edit exactly one config value per head.

**Verification command**

```powershell
git diff --cached -- config/jev_thresholds.json    # exactly one value changed
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -c "import json; from pathlib import Path; from types import SimpleNamespace; from kr_quant.research.jev_runtime import resolve_head_eligibility; cfg=json.loads(Path('config/jev_thresholds.json').read_text(encoding='utf-8')); s=SimpleNamespace(root=Path('.'), data_dir=Path('data')); print(resolve_head_eligibility(threshold_cfg=cfg, approvals_dir=Path('data/research/jev_calibration/approvals'), provider='typesafe_direct', requested_model='jev-latest', evaluator_version='season-jev-shadow-v1', head='<head>'))"
```

**Commit subject (per head):** `chore(jev): adopt approved threshold for <head>`

**STOP gate:** Explicit approval per head; await approval before the next head or P3.

---

## Task 3.1: Bounded Execution Planning

**Files**
- CREATE `src/kr_quant/research/jev_research_executor.py`
- CREATE `tests/unit/test_jev_research_executor.py`

**Interfaces consumed:** J3 gate envelope structure (`results[].gate` with
`research_requirements`, `mode`, `state_hash`); `resolve_research_config`
output; `resolve_mode_eligibility` output.

**Interfaces produced:** module constants (`EXECUTOR_SCHEMA_VERSION`,
`STATUS_*`, `REQUIREMENT_TYPES`); `build_execution_plan`.

**Tests (files):** `tests/unit/test_jev_research_executor.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - `false` → `NOT_REQUIRED`; `null` → `SKIPPED_UNCALIBRATED`
  - type not in allowlist → `SKIPPED_DISALLOWED`
  - canary sampling: deterministic first-N by `candidate_id` ascending;
    others `PENDING` (`CANARY_SCOPE_DEFERRED`)
  - production: no sampling
  - gate candidate with `mode=ERROR` → skipped, never planned
  - `shadow` mode → planner refuses (`ValueError`, no plan)

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py -q --tb=short
```

**Implementation:** GREEN: implement `build_execution_plan` + constants.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py -q --tb=short
git diff -- config/ src/kr_quant/research/jev_research_gate.py    # must be empty
```

**Commit subject:** `feat(jev): add bounded research execution planning`

**STOP gate:** Await approval before Task 3.2.

---

## Task 3.2: Execution Loop, Budgets, Idempotency

**Files**
- MODIFY `src/kr_quant/research/jev_research_executor.py`
- MODIFY `tests/unit/test_jev_research_executor.py`

**Interfaces consumed:** `season_jev_budget.BudgetLock`;
`kr_quant.atomic_io.write_json_atomic`; plan output from Task 3.1.

**Interfaces produced:** `execution_key`, `run_execution_pass`,
`load_reusable_executions`, `runtime_overlay_path`, `write_runtime_overlay`
(signatures above).

**Tests (files):** `tests/unit/test_jev_research_executor.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases with injected fake adapters:
  - budget exhaustion → `SKIPPED_BUDGET`; deep_ai cap enforced separately
  - requirement timeout → `FAILED` (`TIMEOUT`), siblings continue
  - duplicate single-flight: two calls → one adapter invocation
  - stale `RUNNING` entry → `FAILED` (`CRASH_RECOVERED`) then retryable
  - reuse: same 9-tuple key with `VERIFIED` → reused, no adapter call
  - adapter exception → `FAILED` contained; overlay written atomically

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py -q --tb=short
```

**Implementation:** GREEN: implement the loop, ledger, reuse, overlay writers.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py tests/unit/test_season_jev_budget.py -q --tb=short
git diff -- config/ src/kr_quant/research/season_jev_budget.py    # must be empty
```

**Commit subject:** `feat(jev): execute bounded research requirements`

**STOP gate:** Await approval before Task 3.3.

---

## Task 3.3: Allowlisted Adapters

**Files**
- MODIFY `src/kr_quant/research/jev_research_executor.py`
- MODIFY `tests/unit/test_jev_research_executor.py`

**Interfaces consumed:** `kr_quant.ingest.recent_filings` (dart /
current_year_check), `kr_quant.ingest.naver_search` (news), existing analysis
LLM path `kr_quant.research.analyze` (deep_ai), deterministic state review
(invalidation_check); `Settings` credentials.

**Interfaces produced:** `default_adapters(settings) -> dict[str, Callable]`.

**Tests (files):** `tests/unit/test_jev_research_executor.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - `default_adapters` returns exactly the five allowlisted callables
  - credential missing → `FAILED` (`CREDENTIAL_MISSING`), no fallback
  - adapter output is normalized to raw evidence dicts (bounded, no secrets)
  - adapters are never called in shadow mode

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py -q --tb=short
```

**Implementation:** GREEN: implement `default_adapters` with lazy imports;
tests use fakes only.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py -q --tb=short
git diff -- src/kr_quant/research/season_jev_shadow.py    # must be empty
```

**Commit subject:** `feat(jev): add allowlisted research adapters`

**STOP gate:** Await approval before P4.

---

## Task 4.1: Evidence Object Contract

**Files**
- CREATE `src/kr_quant/research/jev_evidence.py`
- CREATE `tests/unit/test_jev_evidence.py`

**Interfaces consumed:** none external.

**Interfaces produced:** module constants; `build_evidence`,
`evidence_artifact_hash`, `validate_evidence` (signatures above).

**Tests (files):** `tests/unit/test_jev_evidence.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - valid evidence builds with exact locked fields
  - claim > 500 / excerpt > 2000 → truncated + `truncated=true`
  - secret-like fields (`api_key`, `token`, `secret`, `password`,
    `authorization`, `cookie`) → `SECRET_REJECTED`
  - source_identity with `..`, `/`, `\`, absolute path → `INVALID_SOURCE_IDENTITY`
  - `artifact_hash` recomputation exact; tamper → `ERROR`

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_evidence.py -q --tb=short
```

**Implementation:** GREEN: implement constants + three functions.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_evidence.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): add evidence object contract`

**STOP gate:** Await approval before Task 4.2.

---

## Task 4.2: Evidence Verifier

**Files**
- MODIFY `src/kr_quant/research/jev_evidence.py`
- MODIFY `tests/unit/test_jev_evidence.py`

**Interfaces consumed:** `validate_evidence`, `evidence_artifact_hash`.

**Interfaces produced:** `verify_evidence` (signature above).

**Tests (files):** `tests/unit/test_jev_evidence.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - `VERIFIED` on complete provenance within max age
  - `UNVERIFIED` when `source_date` null or provenance incomplete
  - `STALE` at max-age boundary (exact boundary tests)
  - `CONFLICT` when contradicting a prior verified evidence for the same
    candidate/type
  - `ERROR` on malformed input / hash mismatch / secret / path rejection
  - failure never returns `evidence=false`; status carries the failure

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_evidence.py -q --tb=short
```

**Implementation:** GREEN: implement `verify_evidence` with the locked
max-age table.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_evidence.py -q --tb=short
```

**Commit subject:** `feat(jev): verify evidence provenance and conflicts`

**STOP gate:** Await approval before Task 4.3.

---

## Task 4.3: Mandatory Verifier Flow

**Files**
- MODIFY `src/kr_quant/research/jev_research_executor.py`
- MODIFY `src/kr_quant/research/jev_evidence.py`
- MODIFY `tests/unit/test_jev_research_executor.py`
- MODIFY `tests/unit/test_jev_evidence.py`

**Interfaces consumed:** `verify_evidence`, `validate_evidence`.

**Interfaces produced:** `write_evidence_bundle`, `evidence_bundle_path`;
executor calls the verifier unconditionally.

**Tests (files):** `tests/unit/test_jev_research_executor.py`,
`tests/unit/test_jev_evidence.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - executor calls the verifier for every raw result; no overlay `VERIFIED`
    without verifier `VERIFIED`
  - verifier failure → requirement `FAILED`/`PARTIAL`, overlay `UNVERIFIED`
  - `NO_CONFLICT_FOUND` requires verified `invalidation_check`
  - evidence bundle written atomically at the locked path; bypass attempt
    raises (`RuntimeError`)

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py tests/unit/test_jev_evidence.py -q --tb=short
```

**Implementation:** GREEN: implement bundle persistence + mandatory verifier
call in `run_execution_pass`.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_executor.py tests/unit/test_jev_evidence.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): require evidence verification before overlay`

**STOP gate:** Await approval before P5.

---

## Task 5.1: Canary Scope and Rollback Guard

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** raw config `research` block; existing
`resolve_research_config` (extended).

**Interfaces produced:** extended `resolve_research_config`;
`canary_rollback_guard` (signatures above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - canary overrides validated (`<=` production caps) else
    `RESEARCH_CONFIG_INVALID`
  - `canary_rollback_guard` triggers per spec §9.5 table (each row)
  - guard never mutates config; returns `{triggered, action, reason}`

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement the validation + guard.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(jev): add canary scope and rollback guard`

**STOP gate:** Await approval before Task 5.2.

---

## Task 5.2: Canary Metrics Report

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** runtime overlays, human review records (fixtures).

**Interfaces produced:** `compute_canary_metrics`,
`write_canary_metrics_report` (signatures above).

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - every spec §9.4 metric present; zero denominator → `None` (never `0.0`)
  - rate math exact on fixtures
  - human review queue deterministic (`sha256(candidate_id)[0:8] % 5 == 0`)
  - report written atomically under the locked path

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: implement metrics + report writer.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Commit subject:** `feat(jev): add canary metrics report`

**STOP gate:** Await approval before Task 5.3.

---

## Task 5.3: Activate Canary (config; explicit approval)

**Files**
- MODIFY `config/season_jev.json` only: add the `research` block with
  `research.canary`, set `"mode": "canary"` (`enabled` stays `true`).

**Interfaces consumed:** `resolve_research_config`,
`resolve_mode_eligibility` (verification only).

**Interfaces produced:** none (config data).

**Tests (files):** none new; `tests/unit/test_jev_runtime.py` regression.

**RED-first:** N/A — config-only activation task; contract is verification-only
(`mode_ok=true` for canary; only the research block + mode field in the diff).

- [ ] REQUIRED: explicit GPT/user approval + canary scope review recorded.
- [ ] Prerequisites: `>= 1` eligible head (Task 2.4), `>= 10` gate artifacts
  from P1 evidence.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_executor.py -q --tb=short
```

**Implementation:** apply the config edit; stage only `config/season_jev.json`.

**Verification command**

```powershell
git diff --cached -- config/season_jev.json    # only research block + mode
git diff -- config/jev_thresholds.json         # must be empty
```

**Commit subject:** `chore(jev): activate JEV canary scope`

**STOP gate:** Await approval before P6.

---

## Task 6.1: Production Eligibility Enforcement

**Files**
- MODIFY `src/kr_quant/research/jev_runtime.py`
- MODIFY `tests/unit/test_jev_runtime.py`

**Interfaces consumed:** `resolve_mode_eligibility` (extended),
`resolve_head_eligibility`.

**Interfaces produced:** enforcement wiring in `resolve_mode_eligibility` and
the runtime overlay `mode` field.

**Tests (files):** `tests/unit/test_jev_runtime.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases:
  - production with 4/5 eligible → `mode_ok=false`,
    `PRODUCTION_ELIGIBILITY_INCOMPLETE`, no execution
  - production with 5/5 → `mode_ok=true`
  - canary with 0 eligible → `CANARY_ELIGIBILITY_INCOMPLETE`
  - runtime overlay `mode` field reflects the resolved mode

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py -q --tb=short
```

**Implementation:** GREEN: enforce 5/5 for production, `>= 1` for canary.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_executor.py -q --tb=short
```

**Commit subject:** `feat(jev): enforce production eligibility gate`

**STOP gate:** Await approval before Task 6.2.

---

## Task 6.2: Read-Only Observability Surface

**Files**
- MODIFY `src/kr_quant/web/app.py`
- MODIFY `src/kr_quant/web/static/app.js`
- MODIFY `tests/unit/test_web_app.py`

**Interfaces consumed:** `jev_runtime.runtime_status`.

**Interfaces produced:** read-only endpoint + display card; exact field set
from spec §12.

**Tests (files):** `tests/unit/test_web_app.py`

**RED-first:** failing tests before implementation.

- [ ] RED cases: endpoint returns the locked field set; missing artifacts →
  zeros/`null`; no mutation controls; no Quant payload changes.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_web_app.py -q --tb=short
```

**Implementation:** GREEN: add endpoint + read-only card/banner.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_web_app.py -q --tb=short
git diff -- config/    # must be empty
```

**Commit subject:** `feat(web): show JEV runtime overlay status`

**STOP gate:** Await approval before Task 6.3.

---

## Task 6.3: Activate Production (config; explicit approval)

**Files**
- MODIFY `config/season_jev.json` only: `"mode": "production"`.

**Interfaces consumed:** `resolve_mode_eligibility` (verification only).

**Interfaces produced:** none (config data).

**Tests (files):** none new; P7.1 failure-matrix suite is the regression.

**RED-first:** N/A — config-only activation task; contract is verification-only
(`mode_ok=true` for production; exactly one field changes).

- [ ] REQUIRED: explicit GPT/user approval + production readiness packet.
- [ ] Prerequisites: all five actionable heads eligible; canary metrics within
  rollback thresholds for the agreed window; failure matrix tests green (P7.1
  may run before this task if review requests it).

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_executor.py tests/unit/test_jev_evidence.py -q --tb=short
```

**Implementation:** apply the one-field config edit.

**Verification command**

```powershell
git diff --cached -- config/season_jev.json    # exactly one field
git diff -- config/jev_thresholds.json         # must be empty
```

**Commit subject:** `chore(jev): activate JEV production routing`

**STOP gate:** Await approval before P7.

---

## Task 7.1: Failure Matrix Certification

**Files**
- MODIFY `tests/unit/test_jev_runtime.py`
- MODIFY `tests/unit/test_jev_research_executor.py`
- MODIFY `tests/unit/test_jev_evidence.py`

**Interfaces consumed:** all runtime/executor/evidence public functions.

**Interfaces produced:** test-only (one test per failure-matrix row).

**Tests (files):** the three files above.

**RED-first:** RED→GREEN per row; test names
`test_failure_row_01_...` … `test_failure_row_24_...` mapping to spec §10.

- [ ] Each test asserts: statuses, side effects, retryability, and
  Quant-untouched (no Quant module import).

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_executor.py tests/unit/test_jev_evidence.py -q --tb=short
```

**Implementation:** add the 24 row tests; fix only genuine defects found.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_runtime.py tests/unit/test_jev_research_executor.py tests/unit/test_jev_evidence.py tests/unit/test_jev_research_gate.py tests/unit/test_jev_calibration.py tests/unit/test_season_jev_shadow.py -q --tb=short
```

**Commit subject:** `test(jev): certify production failure matrix`

**STOP gate:** Await approval before Task 7.2.

---

## Task 7.2: Invariance and Isolation Certification

**Files**
- MODIFY tests only if needed (prefer no production code changes).

**Interfaces consumed:** all new modules (static inspection).

**Interfaces produced:** test-only assertions.

**Tests (files):** `tests/unit/test_jev_runtime.py`,
`tests/unit/test_jev_research_executor.py`, `tests/unit/test_jev_evidence.py`

**RED-first:** add assertions first where gaps exist; otherwise N/A (gap-closure
task with explicit NO COMMIT allowed).

- [ ] Static AST checks: new modules import no `requests/httpx/aiohttp/urllib/
  socket/subprocess/selenium/playwright`, no `os.environ` key access, no Quant
  scoring modules.
- [ ] Config safety: `config/season_jev.json` and
  `config/jev_thresholds.json` unchanged by tests; mode resolution fail-closed
  cases covered.

**Test command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest -q --tb=short
```

**Implementation:** close gaps; no behavior changes.

**Verification command**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest -q --tb=short    # exit 0, 0 failed
git diff -- config/    # must be empty
```

Hard criterion: exit 0, **0 failed**. Do not hardcode pass counts.

**Commit subject (only if a real diff exists):**
`test(jev): certify production v1 invariants`

**STOP gate:** Await approval before Task 7.3.

---

## Task 7.3: Production Readiness Certification Record

**Files**
- CREATE `docs/superpowers/plans/2026-09-23-jev-production-v1-certification.md`

**Interfaces consumed:** all verification packets from P1–P7.

**Interfaces produced:** tracked certification document.

**Tests (files):** none (documentation).

**RED-first:** N/A — documentation task; contract is content completeness
(identity, mode state, threshold/approval inventory, failure matrix results,
full-suite result, canary metrics summary, rollback status, open risks,
Quant-untouched statement).

- [ ] Include all required sections; stage the exact path only.

**Test command**

```powershell
git diff --check
```

**Implementation:** write the certification record from verified evidence.

**Verification command**

```powershell
git diff --cached --check
git diff --cached --name-only    # exactly the one doc
```

**Commit subject:** `docs(jev): record production v1 certification`

**STOP gate:** Final packet; production v1 complete pending GPT accept.

---

## Spec Coverage Matrix (spec section → primary Task)

| Spec section | Primary Tasks |
| --- | --- |
| §4.1 mode semantics | 1.1, 6.1 |
| §4.2 config schema | 1.1, 5.1, 5.3, 6.3 |
| §4.3 backward compatibility | 1.1 |
| §4.4 migration | 1.4, 5.3, 6.3 |
| §5.3 approval record | 2.1, 2.3 |
| §5.4 eligibility rule | 2.2 |
| §5.5 mode eligibility | 2.2, 6.1 |
| §6.2 requirement types | 3.1 |
| §6.3 statuses | 3.1, 3.2 |
| §6.4 selection | 3.1 |
| §6.5 idempotency | 3.2 |
| §6.6 budgets | 3.2, 5.1 |
| §6.7 timeouts/isolation | 3.2 |
| §6.8 overlay schema | 3.2 |
| §6.9 adapter allowlist | 3.3 |
| §7.2 evidence schema | 4.1 |
| §7.3 verification statuses | 4.2 |
| §7.4 max-age table | 4.2 |
| §8 invalidation semantics | 4.3 |
| §9 canary design | 5.1, 5.2, 5.3 |
| §10 failure matrix | 7.1 |
| §11 readiness inventory | 1.5 (refresh) |
| §12 observability | 1.3, 6.2 |
| §13 security | 4.1, 7.2 |
| §14 persistence paths | 3.2, 4.3, 2.3 |
| §15 testing strategy | 7.1, 7.2 |

---

## Final Verification

Before declaring production v1 done:

- [ ] Modes resolve exactly per spec §4.3; conflicts fail closed
- [ ] No non-null threshold without an approval record
- [ ] Executor never runs non-allowlisted or unbudgeted actions
- [ ] Evidence verification mandatory; no unverified `VERIFIED`
- [ ] Failure matrix rows 1–24 tested
- [ ] Full `pytest -q --tb=short` exit 0 / 0 failed
- [ ] `config/season_jev.json` and `config/jev_thresholds.json` changed only
      by approved activation/adoption commits
- [ ] Quant untouched: no new imports of Quant scoring modules in new code
- [ ] Rollback ladder documented and operable via config-only commits

---

## Definition of Done

Production v1 is done when P1–P7 Tasks are approved and:

1. `jev_runtime.py`, `jev_research_executor.py`, `jev_evidence.py` +
   their tests exist and pass
2. Public interfaces match this plan
3. Approval-gated eligibility is enforced at runtime
4. Canary ran within caps and metrics are recorded
5. Production activation happened only after explicit approval
6. J1–J3 modules and configs remain unchanged except the approved
   activation/adoption commits
7. Full suite green; deterministic Quant unaffected

---

## Forbidden Implementation Behaviors

- Editing J1–J3 core modules without STOP + approval
- Any config write by runtime code
- Setting `enabled=true` / `mode != "disabled"` outside approved Tasks
- Writing non-null thresholds outside Task 2.4
- Executing research in shadow/disabled mode
- Any adapter call not in the allowlist
- Persisting secrets or raw provider payloads
- Quant imports in runtime/executor/evidence modules
- `git add .` / `git add -A` / force push / amend
- Empty commits
- Continuous multi-task runs without STOP

---

## Plan Non-Goals

```text
Quant score blending
trade / portfolio logic
automatic threshold deployment
provider winner selection
resolved-model auto rebinding
J1–J3 redesign
dashboard redesign beyond §12 read-only fields
Env Manager
J4 naming
```

---

## Plan Self-Review Checklist

- [x] All 24 Tasks declare Files / Interfaces consumed / Interfaces produced /
      Tests / RED-first (or explicit N/A with reason) / Test command /
      Implementation / Verification command / Commit subject / STOP gate
- [x] Config changes confined to approved activation/adoption Tasks
- [x] No TODO/TBD placeholders
- [x] Spec sections mapped to primary Tasks (coverage matrix)
- [x] No J1–J3 modifications planned
- [x] No live calls in tests
- [x] Failure matrix ownership assigned to P7.1
- [x] Rollback and certification explicit

---

**END OF JEV PRODUCTION ACTIVATION IMPLEMENTATION PLAN**
