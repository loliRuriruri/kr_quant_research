# JEV Research Gate Shadow Implementation Plan (J3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a deterministic, offline, side-effect-free J3 Research Gate Shadow that converts existing JEV probabilities + exact calibration threshold state into auditable `SHADOW_ONLY` research-requirement decisions.

**Architecture:** Keep all new logic in a standalone research module (`jev_research_gate.py`). Consume J2 public calibration interfaces (`load_thresholds`, `lookup_threshold`, `BOOLEAN_HEADS`, status constants). Do **not** mutate J2 core unless a separately proven interface deficiency exists (then **STOP** and report — do not silently patch). No production routing. No network. No Quant coupling. Persistence is optional for pure unit evaluation but included in the first slice as atomic shadow artifacts under a dedicated directory.

**Tech Stack:** Python 3.11+, pytest, stdlib `json` / `hashlib` / `pathlib` / `math`, existing `kr_quant.atomic_io.write_json_atomic`. No new dependencies. Do not change `atomic_io.py`.

**Spec:** `docs/superpowers/specs/2026-09-20-jev-research-gate-shadow-design.md`
**Certified design base (origin/main at plan authoring):** `2685790eaca875d77aedcd987be9a6e3b9dc5f8c`

---

## Execution Notes

DO NOT run all tasks continuously.

After each implementation Task (Tasks 1–4 always; Task 5 if it produces a diff):

1. run that Task's targeted tests
2. run required invariance checks
3. stage **exact paths only** (never `git add .` / `git add -A`)
4. `git diff --cached --check` (must exit 0)
5. commit with the Task subject
6. push the implementation branch (**no force**)
7. return the Task verification packet
8. **STOP for GPT/user review**

Only start the next Task after explicit approval.

Work in an isolated worktree. Do not use a dirty primary checkout.

Recommended future implementation branch (create only when Task 1 starts — **not** during this planning commit):

```text
jev-j3-research-gate-impl
```

---

## Global Constraints

Hard constraints for every Task:

- Keep `config/season_jev.json` `enabled=false`, `provider=typesafe_direct`, `model=jev-latest`.
- Do **not** modify `config/jev_thresholds.json` (2 buckets × 7 BOOLEAN_HEADS, all `null` remain).
- No production routing / no enabling JEV.
- No actual research execution (news / DART / web / Deep-AI).
- No JEV provider calls / no live LLM calls.
- No Quant rank/score/snapshot/trade/portfolio mutation.
- No provider fallback, model fallback, evaluator fallback, or `0.5` fallback.
- `reviewClass` is diagnostic only (never routes or overrides thresholds).
- Evidence Verifier is excluded from J3.
- No UI / dashboard / Env Manager changes.
- Tests run offline with fixtures / `tmp_path` / in-memory threshold configs only.
- Do **not** invent production runtime artifacts under real data dirs just to look operational.
- Current runtime readiness remains: JEV shadow artifacts = 0, human labels = 0, locked selections = 0, holdout reports = 0 — J3 does not require them.

---

## Review Focus

Five critical risks (from the locked design). Primary Task owners:

| # | Risk | Primary Tasks |
| --- | --- | --- |
| 1 | Null threshold accidentally becoming false / 0.5 | 1, 2 |
| 2 | Provider / model / evaluator threshold crossing | 1, 2 |
| 3 | Shadow gate accidentally executing research | 2, 5 |
| 4 | J3 leaking into Quant rank/score logic | 2, 5 |
| 5 | Threshold / reuse identity becoming stale | 1, 4 |

---

## File Map

### Planned create

```text
src/kr_quant/research/jev_research_gate.py
tests/unit/test_jev_research_gate.py
```

### Planned modify

```text
(none in the first J3 slice — prefer zero edits to J2 modules)
```

### Expected unchanged (first slice)

```text
src/kr_quant/research/jev_calibration.py
src/kr_quant/research/season_jev_shadow.py
src/kr_quant/research/season_jev_budget.py
src/kr_quant/atomic_io.py

config/season_jev.json
config/jev_thresholds.json

scripts/
web/
dashboard / UI
```

### Explicitly out of first slice

```text
scripts/evaluate_jev_research_gate.py   # CLI deferred; not needed to prove contracts
```

### Runtime paths (not tracked; tests use tmp_path only)

```text
{settings.data_dir}/research_snapshots/season_jev_research_gate/
  {generation_id}__{provider_safe}__gate.json
```

Mirrors upstream shadow naming under `season_jev_shadow/` with an explicit `__gate` suffix.

---

## Fixed public interfaces (lock these names across Tasks)

### Constants

```python
GATE_SCHEMA_VERSION = 1
GATE_ARTIFACT_TYPE = "season_jev_research_gate"

MODE_SHADOW_ONLY = "SHADOW_ONLY"
MODE_ERROR = "ERROR"

BUCKET_MATCHED = "MATCHED"
BUCKET_MISSING = "MISSING"
```

### Import from J2 (do not duplicate)

```python
from kr_quant.research.jev_calibration import (
    BOOLEAN_HEADS,
    STATUS_SHADOW_ONLY,
    STATUS_UNCALIBRATED,
    CalibrationError,
    load_thresholds,
    lookup_threshold,
)
```

Do **not** redefine `BOOLEAN_HEADS`.

### J3-specific envelope failure

```python
class ResearchGateError(ValueError):
    """Envelope-level / operation-level failure (not a per-candidate ERROR object)."""
```

Candidate-level failures remain serialized `mode=ERROR` gate objects inside `results[]`.

### `threshold_config_hash`

```python
def threshold_config_hash(
    cfg: Mapping[str, Any],
    *,
    provider: str,
    requested_model: str,
    evaluator_version: str,
) -> str:
    ...
```

Returns exactly **64-char lowercase SHA-256 hex**.

Canonical UTF-8 JSON:

```text
sort_keys=True
ensure_ascii=False
separators=(",", ":")
```

Canonical payload fields:

```text
schema_version
provider
requested_model
evaluator_version
bucket_status
thresholds
```

**MATCHED** (exact bucket exists):

```json
{
  "schema_version": 1,
  "provider": "...",
  "requested_model": "...",
  "evaluator_version": "...",
  "bucket_status": "MATCHED",
  "thresholds": { "...": "exact raw threshold mapping from that bucket" }
}
```

Exact raw mapping: `null` stays `null`; numeric stays numeric; **absent head stays absent** (do not normalize absent → null for hashing).

**MISSING** (no exact bucket):

```json
{
  "schema_version": 1,
  "provider": "...",
  "requested_model": "...",
  "evaluator_version": "...",
  "bucket_status": "MISSING",
  "thresholds": null
}
```

Do **not**: hash the entire thresholds file; hash unrelated buckets; invent seven null heads; return `threshold_config_hash=null`; invent `0.5`.

### `evaluate_research_gate` (single candidate)

```python
def evaluate_research_gate(
    *,
    answers: Mapping[str, Any],
    threshold_cfg: Mapping[str, Any],
    provider: str,
    requested_model: str,
    evaluator_version: str,
    generation_id: str,
    candidate_id: str,
    state_hash: str,
    review_class: Any = None,
    resolved_model: Any = None,
) -> dict[str, Any]:
    ...
```

J3 evaluator does **not** accept Quant / state objects as inputs (structural Quant isolation).

Successful `SHADOW_ONLY` object includes:

```text
schema_version, mode, provider, requested_model, evaluator_version,
generation_id, candidate_id, state_hash, threshold_config_hash,
heads, research_requirements, material_now, historical_conflict,
calibrated_heads, uncalibrated_heads, all_heads_calibrated,
diagnostics, side_effects_executed=false
```

Decision rules:

- numeric threshold → `decision = (probability >= threshold)`, `reason = null`
- missing **required answer** BOOLEAN_HEAD → candidate structural failure: `mode=ERROR`, `error.code=MISSING_HEAD`, `side_effects_executed=false` (do **not** convert to UNCALIBRATED)
- valid answer probability present, but exact threshold lookup yields missing/null (including missing exact threshold entry, explicit null threshold, or valid config with missing exact bucket) → `mode=SHADOW_ONLY`, `decision=null`, `reason=UNCALIBRATED` (`STATUS_UNCALIBRATED`)
- never false-fallback / 0.5 / cross-bucket fallback

Candidate ERROR object:

```json
{
  "schema_version": 1,
  "mode": "ERROR",
  "error": { "code": "...", "message": "..." },
  "side_effects_executed": false
}
```

Carry `candidate_id` / audit identity when safely known.

Locked error codes:

```text
MISSING_ANSWERS
MISSING_HEAD
INVALID_PROBABILITY
INVALID_IDENTITY
UNSUPPORTED_PROVIDER
INVALID_THRESHOLD
THRESHOLD_CONFIG_UNREADABLE
STATE_HASH_MISMATCH
UNSUPPORTED_SCHEMA
```

### `evaluate_research_gate_generation` (envelope)

```python
def evaluate_research_gate_generation(
    shadow_payload: Mapping[str, Any],
    *,
    threshold_cfg: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

Consumes upstream shadow generation fields:

```text
generation_id, provider, requested_model, evaluator_version, results[]
```

Per candidate from `results[]`:

```text
candidate_id, state_hash, answers, resolved_model, reviewClass (diagnostic only)
```

No JEV calls. No network.

Envelope shape:

```json
{
  "schema_version": 1,
  "artifact_type": "season_jev_research_gate",
  "mode": "SHADOW_ONLY",
  "generation_id": "...",
  "provider": "...",
  "requested_model": "...",
  "evaluator_version": "...",
  "threshold_config_hash": "...",
  "results": [
    { "candidate_id": "...", "gate": { } }
  ],
  "side_effects_executed": false
}
```

- `gate.state_hash` is the single source of truth (no second authoritative `state_hash` beside `gate`).
- `results[]` sorted by `candidate_id` ascending.
- Duplicate `candidate_id` → reject generation (`ResearchGateError`).
- Candidate structural failure → that `gate.mode=ERROR`; siblings still evaluated.
- Envelope-level failure (missing/invalid generation identity fields; unreadable/structurally invalid `threshold_cfg` for the operation) → raise `ResearchGateError`; do not silently persist a partial artifact.
- No timestamps in the deterministic core/envelope.

### Persistence helpers

```python
def research_gate_dir(settings) -> Path: ...

def research_gate_path(
    settings,
    generation_id: str,
    provider: str,
) -> Path: ...

def write_research_gate_artifact(
    path: Path,
    payload: Mapping[str, Any],
) -> None: ...
```

`write_research_gate_artifact` MUST call `kr_quant.atomic_io.write_json_atomic`. Prefer `compact=True` if byte-stability tests lock that representation consistently; otherwise document the exact kwargs used in Task 4 GREEN and keep them stable.

### Reuse

Candidate reuse key (all eight must match):

```text
schema_version
generation_id
provider
requested_model
evaluator_version
candidate_id
state_hash
threshold_config_hash
```

Recommended helper:

```python
def load_reuse_index(...) -> dict: ...
```

(or equivalent private helper). Rules:

- same `candidate_id` + changed `state_hash` → no reuse
- same candidate + changed effective `threshold_config_hash` → no reuse
- unrelated provider threshold edit → reuse remains valid
- `MISSING` → `MATCHED` → no reuse
- malformed / wrong-schema artifacts → never reuse

### Config loading rule (critical J2 boundary)

**In-memory pure evaluator** (preferred in unit tests):

```text
threshold_cfg already supplied and structurally valid
→ threshold_config_hash(...)
→ lookup_threshold(...)
```

**Disk / future wrapper** (persistence Task and any loader helpers):

```text
load_thresholds(path)
→ on unreadable / structurally invalid cfg: J3 operation failure (ResearchGateError / ERROR path)
→ never hide malformed configs
```

**Do NOT** use:

```python
threshold_status_from_path(...)
```

as J3 generation-level config authority.

Why: J2 `threshold_status_from_path` currently converts missing/unreadable/invalid threshold-file situations into `SHADOW_ONLY` / `UNCALIBRATED`. That is **not** sufficient for the locked J3 distinction:

| Case | J3 outcome |
| --- | --- |
| Valid cfg + missing exact bucket | `SHADOW_ONLY` / UNCALIBRATED + deterministic MISSING-bucket hash |
| Unreadable / structurally invalid threshold config | ERROR / generation failure — **no** fabricated MISSING hash |

Do **not** modify J2 to change `threshold_status_from_path` or `lookup_threshold` for convenience. If an interface deficiency is proven during implementation: **STOP**, return evidence, await approval.

### Quant / network isolation

- Evaluator signature accepts no Quant/state input.
- Forbidden decision fields must never influence gate decisions (`quantReference`, `quant_reference`, `pre_entry_rank`, `grade`, `seasonality_score`, `score_breakdown`).
- Optional diagnostics `candidate_type` / `ticker` omitted in first slice unless audit later requires them (do not expand scope).
- Module must not import: `requests`, `httpx`, `aiohttp`, web clients, DART/news clients, JEV provider runners.
- No subprocess / Node / browser / environment API-key access.
- Task 5 includes static/import-oriented checks.

---

## Task 1: Threshold Identity Foundation

### Goal

Implement `threshold_config_hash`, MATCHED/MISSING payload construction, canonical hashing, and identity validation needed by the hash layer. Minimal scaffolding only for the module/package surface — **no** full candidate gate yet.

### Files

- CREATE `src/kr_quant/research/jev_research_gate.py`
- CREATE `tests/unit/test_jev_research_gate.py`

### Steps

- [ ] RED: write failing tests for hash contracts — **primary** design tests **33, 34, 36, 37, 38, 39**.
- [ ] Optional SECONDARY / prerequisite hash-facing fixtures for **5, 6, 7, 8, 12, 35** (hash identity / transition only). These do **not** complete those design contracts; primary ownership remains Task 2 (5–8,12) or Task 4 (35).
- [ ] GREEN: implement constants + `threshold_config_hash` (+ small helpers for locating exact bucket / validating identity fields as needed). No full candidate gate. No persistence/reuse.
- [ ] Prove (primary): MISSING → deterministic valid 64-hex; all-null MATCHED ≠ MISSING; absent head ≠ explicit null; unrelated provider edit unchanged; effective edit changes hash; malformed cfg fails closed (no fabricated MISSING hash).
- [ ] Targeted tests: `pytest tests/unit/test_jev_research_gate.py -q --tb=short` (Task-1 subset / whole file as tests grow).
- [ ] Invariants: no config writes; no network imports introduced; `enabled=false` untouched.
- [ ] Stage exact paths only → `git diff --cached --check` → commit → push → STOP.

### Commit subject

```text
feat(jev): add J3 threshold identity foundation
```

### STOP condition

Task verification packet returned; await GPT/user approval before Task 2.

### Expected verification packet fields

```text
IDENTITY, RED→GREEN evidence, hash fixtures (MATCHED/MISSING/absent/null/unrelated),
commands+exit codes, changed files, enabled=false, thresholds unchanged, STOP
```

---

## Task 2: Pure Single-Candidate Gate

### Goal

Implement `evaluate_research_gate(...)` end-to-end for one candidate.

### Files

- MODIFY `src/kr_quant/research/jev_research_gate.py`
- MODIFY `tests/unit/test_jev_research_gate.py`

### Steps

- [ ] RED: failing tests for design cases **1–19** (primary).
- [ ] GREEN: implement per-head decisions via `lookup_threshold`, aggregates (`research_requirements`, calibrated/uncalibrated lists), ERROR objects, diagnostics (`review_class` non-routing, `resolved_model` diagnostic).
- [ ] Prove: all-null → all `decision=null`; one calibrated head; mixed; exact `>=` boundary; provider / requested_model / evaluator_version isolation; missing bucket → UNCALIBRATED heads; no provider fallback; bad probability/threshold → ERROR; **missing required BOOLEAN_HEAD → `MISSING_HEAD` ERROR** (not UNCALIBRATED); `reviewClass` non-routing; `materialNow` / `historicalConflict` advisory only; `side_effects_executed=false`; Quant not consumed.
- [ ] No persistence. No generation wrapper.
- [ ] Targeted tests + invariants (no research calls; no config mutation).
- [ ] Stage exact paths → check → commit → push → STOP.

### Commit subject

```text
feat(jev): implement J3 candidate research gate
```

### STOP condition

Await approval before Task 3.

### Expected verification packet fields

```text
IDENTITY, cases 1–19 evidence, ERROR codes exercised, no side effects, STOP
```

---

## Task 3: Generation Envelope

### Goal

Implement `evaluate_research_gate_generation(...)` and envelope failure policy.

### Files

- MODIFY `src/kr_quant/research/jev_research_gate.py`
- MODIFY `tests/unit/test_jev_research_gate.py`

### Steps

- [ ] RED: failing tests for **24, 25, 26, 31, 32** (+ deterministic aspects of **21, 30**).
- [ ] GREEN: generation orchestration; `ResearchGateError` for envelope failures; candidate ERROR isolation; `candidate_id` ascending; duplicate rejection; single SoT for `state_hash`.
- [ ] No disk persistence yet.
- [ ] Targeted tests + invariants → commit → push → STOP.

### Commit subject

```text
feat(jev): add J3 generation envelope
```

### STOP condition

Await approval before Task 4.

### Expected verification packet fields

```text
IDENTITY, multi-candidate fixtures, ERROR isolation, envelope failure, ordering, STOP
```

---

## Task 4: Persistence and Reuse

### Goal

Implement `research_gate_dir`, `research_gate_path`, atomic artifact persistence, and candidate-level reuse with threshold-hash-aware invalidation.

### Files

- MODIFY `src/kr_quant/research/jev_research_gate.py`
- MODIFY `tests/unit/test_jev_research_gate.py`

### Steps

- [ ] RED: failing tests for **20, 21, 27, 28, 29, 30, 35** (primary).
- [ ] GREEN: path helpers + `write_research_gate_artifact` via `write_json_atomic`; `load_reuse_index` (or equivalent); reuse key enforcement.
- [ ] Tests use **`tmp_path` only** — never create production runtime directories.
- [ ] Prove: atomic write; correct path; reuse on identity match; `state_hash` change invalidates one candidate; threshold hash change invalidates; unrelated provider edit does not; byte-stable identical inputs; malformed artifacts never reused.
- [ ] Prove design **35**: MISSING hash → exact bucket added → MATCHED hash → hashes differ → persisted candidate reuse rejected.
- [ ] Disk load path (if any) uses `load_thresholds` + J3 fail-closed — **not** `threshold_status_from_path`.
- [ ] Targeted tests + invariants → commit → push → STOP.

### Commit subject

```text
feat(jev): persist and reuse J3 shadow gates
```

### STOP condition

Await approval before Task 5.

### Expected verification packet fields

```text
IDENTITY, path fixtures under tmp_path, reuse matrix, byte-stability, STOP
```

---

## Task 5: Safety / Invariance / Regression

### Goal

No feature expansion. Close verification gaps only.

### Files

- MODIFY tests only if needed for gap closure (`tests/unit/test_jev_research_gate.py`)
- Prefer **NO** production code changes

### Steps

- [ ] Confirm all **39** design cases are accounted for in `test_jev_research_gate.py` (mapping table below).
- [ ] Static/import checks: no network clients; no research runners; no Quant mutation helpers.
- [ ] Confirm `enabled=false`; thresholds unchanged; no CLI; no UI.
- [ ] Targeted:

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_research_gate.py -q --tb=short
```

- [ ] JEV regression:

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_jev_calibration.py tests/unit/test_season_jev_shadow.py tests/unit/test_jev_research_gate.py -q --tb=short
```

- [ ] Full suite:

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest -q --tb=short
```

Hard criterion: exit 0, **0 failed**. Do not hardcode total pass count (J3 adds new tests).

- [ ] If test-only cleanup is required:

```text
test(jev): certify J3 research gate invariants
```

- [ ] If no code/test changes are needed: **NO COMMIT** (empty commit forbidden).
- [ ] Push only if a real commit exists → STOP.

### STOP condition

Final verification packet; J3 implementation complete pending GPT accept of Task 5 evidence.

### Expected verification packet fields

```text
IDENTITY, 39-case coverage matrix, import/safety checks, pytest commands+results,
enabled=false, thresholds 2×7 null, commit SHA or NO COMMIT, STOP
```

---

## Spec Coverage Matrix (design tests → primary Task)

Every design test **1–39** has exactly one primary Task owner.

| Design # | Primary Task | Contract summary |
| --- | --- | --- |
| 1 | 2 | all-null thresholds → all decision=null / UNCALIBRATED |
| 2 | 2 | one calibrated head true/false; others null |
| 3 | 2 | mixed calibrated/null + aggregate lists |
| 4 | 2 | exact `>=` boundary |
| 5 | 2 | provider threshold isolation (gate) |
| 6 | 2 | requested-model threshold isolation (gate) |
| 7 | 2 | evaluator-version threshold isolation (gate) |
| 8 | 2 | missing bucket → UNCALIBRATED gate heads |
| 9 | 2 | malformed probability → ERROR |
| 10 | 2 | malformed threshold → ERROR |
| 11 | 2 | no 0.5 fallback |
| 12 | 2 | no provider fallback (gate) |
| 13 | 2 | reviewClass cannot route / override |
| 14 | 2 | materialNow advisory only |
| 15 | 2 | historicalConflict advisory only |
| 16 | 2 | no news call |
| 17 | 2 | no DART call |
| 18 | 2 | no Deep-AI call |
| 19 | 2 | Quant bundle unread for decisions |
| 20 | 4 | threshold change changes hash / invalidates reuse |
| 21 | 4 | output deterministic for identical inputs |
| 22 | 5 | enabled=false unchanged |
| 23 | 5 | runtime fixtures require no network |
| 24 | 3 | two candidates persist in one generation envelope |
| 25 | 3 | candidate_id uniqueness enforced |
| 26 | 3 | same generation with distinct state_hash valid |
| 27 | 4 | one candidate state_hash change invalidates only that reuse |
| 28 | 4 | threshold bucket change invalidates candidate reuse |
| 29 | 4 | unrelated provider threshold change does not invalidate |
| 30 | 4 | deterministic candidate ordering |
| 31 | 3 | candidate ERROR does not erase valid siblings |
| 32 | 3 | envelope identity corruption fails entire evaluation |
| 33 | 1 | missing bucket still yields deterministic threshold_config_hash |
| 34 | 1 | missing bucket hash differs by provider/model/evaluator |
| 35 | 4 | MISSING→MATCHED hash change invalidates persisted candidate reuse |
| 36 | 1 | explicit all-null MATCHED hash ≠ MISSING hash |
| 37 | 1 | absent head vs explicit-null head different MATCHED hashes |
| 38 | 1 | unrelated provider bucket edit does not change effective hash |
| 39 | 1 | malformed/unreadable config never gets fabricated MISSING hash |

Secondary coverage may appear elsewhere; primary ownership above is authoritative for Task STOP gates.

Primary ownership counts: Task1=6, Task2=19, Task3=5, Task4=7, Task5=2. Total=39.

---

## Final Verification

Before declaring J3 implementation done:

- [ ] J3 remains `SHADOW_ONLY` (no production routing)
- [ ] `enabled=false`
- [ ] thresholds still all null (2×7)
- [ ] no network / no research execution / no Quant mutation / no provider fallback
- [ ] all 39 design contracts covered in tests
- [ ] full `pytest -q --tb=short` exit 0 / 0 failed
- [ ] no CLI / UI / Evidence Verifier / threshold deployment shipped

---

## Definition of Done

J3 first slice is done when Tasks 1–5 are approved and:

1. `jev_research_gate.py` + `test_jev_research_gate.py` exist and pass
2. Public interfaces match this plan
3. Generation envelope + persistence/reuse behave per locked design
4. J2 modules and configs remain unchanged (unless a separately approved deficiency fix landed — none planned)
5. Full suite green; production JEV still disabled

---

## Forbidden Implementation Behaviors

- Using `threshold_status_from_path` to paper over unreadable/invalid threshold configs
- Silently modifying `jev_calibration.py` / `season_jev_shadow.py` without STOP + approval
- Implementing CLI / UI / Evidence Verifier / research clients in this slice
- Setting `enabled=true` or writing numeric thresholds
- Accepting Quant state into `evaluate_research_gate` inputs
- Empty commits in Task 5
- Continuous multi-task runs without STOP
- `git add .` / `git add -A` / force push

---

## Plan Non-Goals

Explicitly excluded from this plan / first slice:

```text
CLI
UI/dashboard
Evidence Verifier
actual news research
actual DART research
web research
Deep AI execution
threshold selection
threshold deployment
enabled=true
Quant score blending
trade logic
portfolio logic
provider winner selection
resolved-model auto rebinding
J4 naming
Group1 Env Manager
Group2 Dashboard WIP
```

---

## Plan Self-Review Checklist

- [x] Exactly 5 implementation Tasks
- [x] Task 1 threshold identity
- [x] Task 2 candidate gate
- [x] Task 3 generation envelope
- [x] Task 4 persistence/reuse
- [x] Task 5 invariance/regression
- [x] All design tests 1–39 mapped (no missing numbers; no duplicate primary ownership)
- [x] RED before GREEN in Tasks 1–4
- [x] Each Task has commit subject + STOP (Task 5 allows NO COMMIT)
- [x] No CLI first slice
- [x] No J2 modification planned
- [x] No config modification
- [x] No live calls
- [x] `threshold_status_from_path` warning documented
- [x] No implementation performed by this planning commit

---

**END OF J3 RESEARCH GATE SHADOW IMPLEMENTATION PLAN**
