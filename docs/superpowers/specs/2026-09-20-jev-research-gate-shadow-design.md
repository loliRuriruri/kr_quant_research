# J3 Research Gate Shadow — Design Specification

**Status:** DESIGN_READY_FOR_PLAN
**Date:** 2026-09-20
**Base:** `origin/main` / `main` @ `c1411867e6337482b41430300fce2ec4f548a313`
**Certified regression:** 897 passed / 0 failed
**Mode:** DESIGN ONLY (no implementation in this commit)

---

## 1. Status / Base / Scope

### Status

This document formally locks **J3 — Research Gate Shadow** for KR Quant Research.

### Base

- Git: `c1411867e6337482b41430300fce2ec4f548a313`
- J2: CLOSED (provider foundation + calibration tooling + seeded null thresholds)
- Production JEV: `config/season_jev.json` → `enabled=false`, `provider=typesafe_direct`, `model=jev-latest`
- Thresholds: `config/jev_thresholds.json` → 2 buckets × 7 heads, all `null`

### Scope

In scope for J3 design (and later implementation under a separate plan):

- Pure, side-effect-free research-gate **shadow** decisions
- Consumption of existing JEV shadow answers + J2 `lookup_threshold(...)`
- Fixture-based unit tests (no network / no live JEV)

Out of scope for this design commit:

- Any `src/` / `tests/` / `scripts/` / `config/` code changes
- Runtime data generation
- Threshold selection / non-null writes
- Live JEV / news / DART / Deep-AI calls

---

## 2. J3 Formal Definition

```text
J3 — Research Gate Shadow
```

J3 consumes existing normalized JEV shadow results and J2 calibration threshold state to produce an **auditable research-requirement shadow decision**.

Conceptual flow:

```text
Quant candidate (identity/context only; not a score input)
        ↓
existing JEV shadow result (probabilities + identity)
        ↓
exact calibration bucket lookup via lookup_threshold(...)
        ↓
Research Gate Shadow (pure compare / null-safe)
        ↓
"would require research" shadow flags
```

J3 answers only:

> What would the research gate request if these thresholds were used?

J3 does **not** execute that research.

J3 is **not**:

- Evidence Verifier
- Production JEV enablement (`enabled=true`)
- Threshold deployment / automatic adoption
- Quant/JEV score blending
- Automatic provider routing / fallback
- Automatic research execution
- Dashboard / UI work
- Env Manager WIP

---

## 3. Current System State

### Implemented (J2 / foundation) — consumed, not reinvented

| Surface | Role |
| --- | --- |
| `season_jev_shadow.py` | Shadow evaluation persistence; Quant isolation; provider isolation |
| `jev_calibration.py` | `BOOLEAN_HEADS`, `lookup_threshold`, support/lock/holdout/export/blind ingest |
| `config/jev_thresholds.json` | Seeded buckets; all thresholds `null` → UNCALIBRATED / SHADOW_ONLY |
| `config/season_jev.json` | `enabled=false`; Direct default provider/model/evaluator |

### Authoritative comparison rule (J2)

From `jev_calibration.py`:

```text
prediction_rule: probability >= threshold
implementation: float(probability) >= float(threshold)
```

J3 MUST reuse this exact rule for numeric thresholds.

### Runtime data readiness (this machine, 2026-09-20)

| Artifact | Status |
| --- | --- |
| `data/research_snapshots/season_jev_shadow/` | ABSENT (0 generations) |
| `data/research/jev_calibration/` | ABSENT (0 labels / locks / holdouts) |

Therefore J3 implementation and tests MUST be fixture-driven. This design does **not** authorize fabricating production runtime artifacts to simulate readiness.

---

## 4. Goals

1. Define a pure Research Gate Shadow decision layer over existing JEV answers.
2. Make null / UNCALIBRATED thresholds produce `decision=null` (never false, never 0.5).
3. Make numeric thresholds produce `decision = (probability >= threshold)` while remaining SHADOW_ONLY.
4. Support mixed calibrated/null heads in one output object.
5. Preserve provider / requested_model / evaluator_version isolation.
6. Preserve Quant isolation (no rank/score/portfolio/execution effects).
7. Preserve `enabled=false` and forbid research side effects.
8. Enable offline unit tests with fixtures only.

---

## 5. Non-goals

Explicitly excluded from J3 (design + later implementation of this phase):

- `enabled=true`
- Automatic threshold deployment / adoption
- Production routing
- Actual news fetch / DART fetch / web search / Deep-AI invocation
- Evidence Verifier
- Quant score/rank mutation or blending
- Trade / portfolio / execution logic
- Provider winner selection
- Provider fallback
- Threshold optimization / reopening holdout
- Dashboard redesign
- Env Manager WIP
- Naming the next phase “J4” (later phases stay unnumbered until separately locked)

---

## 6. Architecture

```text
                    [fixtures OR existing shadow JSON]
                                    |
                                    v
                         +----------------------+
                         |  Research Gate Shadow |
                         |  (pure function)      |
                         +----------+-----------+
                                    |
              +---------------------+---------------------+
              |                                           |
              v                                           v
   lookup_threshold(cfg,                          shadow decision JSON
     provider, requested_model,                   (mode=SHADOW_ONLY,
     evaluator_version, head)                      side_effects_executed=false)
              ^
              |
     config/jev_thresholds.json
     (or fixture cfg)
```

### Component boundaries

| Component | Authority |
| --- | --- |
| JEV shadow input | Provides probabilities + identity; already produced upstream |
| `lookup_threshold` | **Only** threshold authority |
| Research Gate Shadow core | Pure mapping → decision object |
| Optional persistence | Write-only artifact under dedicated path; never mutates Quant/J2 labels |
| Optional CLI | Thin wrapper; no network |

### Side-effect-free boundary

The J3 core MAY:

- read JEV answers
- read provider / requested_model / evaluator_version / state_hash
- read thresholds via `lookup_threshold`
- validate probabilities
- compare `probability >= threshold`
- produce a shadow decision object
- (optional) persist that object to the J3 artifact path

The J3 core MUST NOT:

- call JEV provider / news / DART / web / Deep AI
- change Quant ranks, scores, screens, portfolio, trades
- change config / write thresholds / set `enabled=true`
- invent thresholds or cross buckets

---

## 7. Inputs

### 7.1 Required identity

| Field | Type | Notes |
| --- | --- | --- |
| `provider` | string | Exact bucket key (`typesafe_direct` or `openrouter`) |
| `requested_model` | string | Exact bucket key (`jev-latest` or `typesafe/jev-1.13` today) |
| `evaluator_version` | string | Exact bucket key (`season-jev-shadow-v1`) |
| `state_hash` | string | Per-candidate identity from upstream shadow / `state_hash(...)` |
| `generation_id` | string | Shadow generation identity (required for persistence/reuse) |
| `candidate_id` | non-empty string | Upstream shadow `candidate_id` / record id (required audit identity) |

Optional diagnostic identity (MUST NOT affect gate decisions):

| Field | Notes |
| --- | --- |
| `candidate_type` | Upstream type label if present |
| `ticker` | Upstream ticker if present |

### 7.2 Required boolean-head probabilities

All seven `BOOLEAN_HEADS` from J2:

```text
materialNow
needsCurrentYearCheck
needsNews
needsDart
historicalConflict
invalidationCheckNeeded
needsDeepAI
```

Each probability MUST be a finite number satisfying:

```text
0.0 <= p <= 1.0
```

Invalid examples (fail-closed):

- `bool`
- `NaN`
- `+Inf` / `-Inf`
- string / null missing where required
- out-of-range (`<0` or `>1`)

### 7.3 Threshold config input

- In-memory mapping compatible with `lookup_threshold` **or**
- Path loadable by `threshold_status_from_path` / equivalent loader

J3 MUST NOT parse ad-hoc threshold formats.

### 7.4 Optional diagnostics (non-routing)

- `reviewClass` (string/enum from upstream) — diagnostics/display only
- `resolved_model` — diagnostics; see §12 Model Drift
- Upstream Quant reference blobs — **not readable for gate logic** (see §13)

---

## 8. Calibration / Threshold Contract

### 8.1 Authority

The ONLY threshold authority is:

```python
lookup_threshold(
    cfg,
    provider=...,
    requested_model=...,
    evaluator_version=...,
    head=...,
)
```

J3 MUST NOT:

- invent `0.5`
- use display normalization as a gate
- search another provider bucket
- fall back to another model
- transfer thresholds across evaluator versions

Bucket identity remains exactly:

```text
provider + requested_model + evaluator_version
```

### 8.2 Null / UNCALIBRATED semantics (HARD)

If lookup yields:

```text
threshold = null
reason = UNCALIBRATED
status = SHADOW_ONLY
```

(or equivalent `_uncalibrated()` outcome), then for that head:

```text
decision = null
reason = "UNCALIBRATED"
```

NOT `false`. NOT `probability >= 0.5`. No research action.

### 8.3 Numeric threshold semantics

Only if lookup returns a numeric threshold under the exact bucket:

```text
decision = (probability >= threshold)   # exact J2 rule
status remains SHADOW_ONLY
side_effects_executed = false
```

### 8.4 Mixed calibration state

Allowed and required to support:

```text
some heads calibrated (numeric) → decision true|false
some heads null → decision null + reason UNCALIBRATED
```

The gate object MUST expose aggregate fields:

| Field | Meaning |
| --- | --- |
| `calibrated_heads` | list of head names with numeric thresholds |
| `uncalibrated_heads` | list of head names with null / UNCALIBRATED |
| `all_heads_calibrated` | boolean: all seven BOOLEAN_HEADS have numeric thresholds |

Partial evidence is valid SHADOW_ONLY output. Do **not** require all seven thresholds merely to emit an object.

---

## 9. Head Semantics

### 9.1 Research-requirement heads (actionable shadow flags)

| JEV head | `research_requirements` key |
| --- | --- |
| `needsCurrentYearCheck` | `current_year_check` |
| `needsNews` | `news` |
| `needsDart` | `dart` |
| `needsDeepAI` | `deep_ai` |
| `invalidationCheckNeeded` | `invalidation_check` |

Each maps to:

```text
true | false | null
```

where `null` means uncalibrated / no decision.

Even when `true`, J3 executes nothing.

### 9.2 Advisory heads

| JEV head | Output field | Meaning |
| --- | --- | --- |
| `materialNow` | `material_now` | Shadow advisory: materiality signal (`true`/`false`/`null`) |
| `historicalConflict` | `historical_conflict` | Shadow advisory: conflict signal (`true`/`false`/`null`) |

These MUST NOT automatically convert into news/DART/Deep-AI calls, Quant penalties, or trade decisions.

### 9.3 `reviewClass` policy

`reviewClass` MAY be copied into output under `diagnostics.review_class` for display/debug.

J3 MUST NOT use `reviewClass` as:

- a calibrated binary threshold
- a production route
- an override of boolean heads

Any such behavior requires a separately approved later phase.

---

## 10. Shadow Decision Contract

### 10.1 Top-level output (locked schema)

```json
{
  "schema_version": 1,
  "mode": "SHADOW_ONLY",
  "provider": "typesafe_direct",
  "requested_model": "jev-latest",
  "evaluator_version": "season-jev-shadow-v1",
  "state_hash": "<hex>",
  "generation_id": "<id>",
  "candidate_id": "candidate-1",
  "threshold_config_hash": "<hex>",
  "heads": {
    "materialNow": {
      "probability": 0.41,
      "threshold": null,
      "decision": null,
      "reason": "UNCALIBRATED"
    },
    "needsCurrentYearCheck": {
      "probability": 0.22,
      "threshold": null,
      "decision": null,
      "reason": "UNCALIBRATED"
    },
    "needsNews": {
      "probability": 0.72,
      "threshold": 0.64,
      "decision": true,
      "reason": null
    },
    "needsDart": {
      "probability": 0.55,
      "threshold": null,
      "decision": null,
      "reason": "UNCALIBRATED"
    },
    "historicalConflict": {
      "probability": 0.10,
      "threshold": null,
      "decision": null,
      "reason": "UNCALIBRATED"
    },
    "invalidationCheckNeeded": {
      "probability": 0.05,
      "threshold": null,
      "decision": null,
      "reason": "UNCALIBRATED"
    },
    "needsDeepAI": {
      "probability": 0.80,
      "threshold": 0.70,
      "decision": true,
      "reason": null
    }
  },
  "research_requirements": {
    "current_year_check": null,
    "news": true,
    "dart": null,
    "deep_ai": true,
    "invalidation_check": null
  },
  "material_now": null,
  "historical_conflict": null,
  "calibrated_heads": ["needsNews", "needsDeepAI"],
  "uncalibrated_heads": [
    "materialNow",
    "needsCurrentYearCheck",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded"
  ],
  "all_heads_calibrated": false,
  "diagnostics": {
    "review_class": null,
    "resolved_model": null
  },
  "side_effects_executed": false
}
```

### 10.2 Field locks

| Field | Locked values / rules |
| --- | --- |
| `schema_version` | integer `1` for this design |
| `mode` | always `"SHADOW_ONLY"` for successful gate objects |
| `candidate_id` | required non-empty string (upstream audit identity) |
| `threshold_config_hash` | always 64-char lowercase SHA-256 hex on successful SHADOW_ONLY (MATCHED or MISSING; §16.2) |
| `side_effects_executed` | always `false` for J3 core |
| per-head `decision` | `true` \| `false` \| `null` only |
| per-head `reason` | `null` on numeric decision; `"UNCALIBRATED"` on null threshold; error reasons only on ERROR objects |

### 10.3 ERROR object (structural failure)

When structural/input corruption occurs (see §11), emit:

```json
{
  "schema_version": 1,
  "mode": "ERROR",
  "error": {
    "code": "<CODE>",
    "message": "<stable message>"
  },
  "side_effects_executed": false
}
```

Do not invent default research requirements on ERROR.

### 10.4 Per-candidate vs generation envelope

Section 10 defines the **per-candidate** Research Gate Shadow object.

One upstream shadow generation may contain many candidates, each with its own `candidate_id` and `state_hash`. Persistence of many candidates in one file is defined in §15 (generation envelope). `state_hash` is **not** an artifact-level singleton identity.

ERROR objects for a single candidate SHOULD still carry `candidate_id` and identity fields when known, so sibling candidates in a generation envelope remain independently auditable.

---

## 11. Failure Semantics

### 11.1 Partial failure policy (LOCKED)

| Class | Behavior |
| --- | --- |
| Per-candidate structural / input corruption | That candidate's gate object → `mode=ERROR` |
| Valid input + null threshold for a head | Valid SHADOW_ONLY object; that head `decision=null` |
| Valid input + numeric threshold | That head `decision=true|false` |
| Envelope-level identity / threshold-config corruption | **Entire generation evaluation / persistence FAILS** |

Per-candidate structural corruption includes:

- missing answers object
- missing required boolean head
- bad probability (type/NaN/Inf/OOR)
- wrong / missing provider, requested_model, evaluator_version
- missing threshold file / unreadable cfg
- missing bucket (treated as UNCALIBRATED per head via `lookup_threshold` — **not** ERROR by itself)
- malformed numeric threshold (non-finite / OOR) for a head that claims numeric
- state identity mismatch when persistence/reuse requires matching `state_hash`
- unsupported `schema_version` on persisted inputs

Clarification:

- **Missing bucket / null threshold** → per-head UNCALIBRATED (`decision=null`), object remains SHADOW_ONLY, with a deterministic MISSING- or MATCHED-bucket `threshold_config_hash` (§16.2).
- **Malformed probability or malformed claimed numeric threshold** → that candidate's gate is ERROR (fail closed; no silent coercion). Sibling candidates in the same generation remain independently evaluable.
- **Envelope-level corruption** (missing `generation_id` / `provider` / `requested_model` / `evaluator_version`, or invalid/unreadable threshold config for the generation operation) → fail the **entire** generation evaluation/persistence; do not write a partial envelope silently; do **not** fabricate a MISSING-bucket `threshold_config_hash` for unreadable/invalid config.
- Duplicate `candidate_id` inside one envelope → ERROR / reject persistence.

### 11.2 Forbidden fallbacks

No failure path may produce:

- default `true`
- default `false` for null thresholds
- `0.5` fallback
- provider fallback
- research execution
- Quant mutation

### 11.3 Error codes (locked set)

| Code | When |
| --- | --- |
| `MISSING_ANSWERS` | answers mapping absent |
| `MISSING_HEAD` | required BOOLEAN_HEAD absent |
| `INVALID_PROBABILITY` | bad type/range/NaN/Inf |
| `INVALID_IDENTITY` | provider/model/evaluator missing or empty |
| `UNSUPPORTED_PROVIDER` | provider not in `{typesafe_direct, openrouter}` |
| `INVALID_THRESHOLD` | numeric path but value not finite in `[0,1]` |
| `THRESHOLD_CONFIG_UNREADABLE` | cfg path/load failure |
| `STATE_HASH_MISMATCH` | reuse/persistence identity failure |
| `UNSUPPORTED_SCHEMA` | unsupported schema_version on input artifact |

---

## 12. Provider / Model Isolation

### 12.1 Provider isolation

Direct bucket:

```text
typesafe_direct + jev-latest + season-jev-shadow-v1
```

OpenRouter bucket:

```text
openrouter + typesafe/jev-1.13 + season-jev-shadow-v1
```

MUST NEVER share thresholds or decisions. No cross-provider fallback. No alias transfer.

### 12.2 Model drift (`requested_model` vs `resolved_model`)

Calibration authority remains tied to **`requested_model`**.

- Gate identity / `lookup_threshold` keys use `requested_model`.
- `resolved_model` may be recorded under `diagnostics.resolved_model` only.
- If resolved-model drift is observed as material in operations, this is a **later-review trigger** (do not silently transfer calibration trust; do not auto-rebind buckets). Implementation of drift policy is out of J3.

---

## 13. Quant Isolation

J3 MUST NOT read or write the following for gate decision logic:

```text
quantReference
quant_reference
pre_entry_rank
grade
seasonality_score
score_breakdown
```

Quant metadata may remain separate upstream debug/reference data already allowed by shadow contracts, but J3 MUST ignore it for decisions.

J3 MUST NOT affect:

```text
ranking
screen eligibility
portfolio
execution
trade signals
seasonality score
```

---

## 14. reviewClass Policy

Restated for lock:

- Allowed: diagnostics copy (`diagnostics.review_class`)
- Forbidden: routing, threshold substitute, override of BOOLEAN_HEADS
- Future change requires a separate approved design

---

## 15. Storage / Persistence

### 15.1 Optional persistence

J3 outputs MAY be persisted. Persistence is optional for unit-tested pure evaluation.

If persisted, artifacts MUST be separate from:

- Quant snapshots
- Original season JEV shadow inputs
- J2 calibration labels
- J2 holdout artifacts

### 15.2 Planned path (do not create in this design task)

```text
{data_dir}/research_snapshots/season_jev_research_gate/
  {generation_id}__{provider_safe}__gate.json
```

Mirrors the upstream shadow convention (`season_jev_shadow/{generation_id}__{provider}.json` containing `results[]`) with an explicit `__gate` suffix and dedicated directory.

One file represents:

```text
one generation
+ one provider
+ one requested_model
+ one evaluator_version
+ one threshold_config_hash
```

and contains `results[]` for all evaluated candidates.

### 15.3 Generation persistence envelope (locked)

Preferred minimal envelope (single source of truth for `state_hash` inside each gate object):

```json
{
  "schema_version": 1,
  "artifact_type": "season_jev_research_gate",
  "mode": "SHADOW_ONLY",
  "generation_id": "gen-A",
  "provider": "typesafe_direct",
  "requested_model": "jev-latest",
  "evaluator_version": "season-jev-shadow-v1",
  "threshold_config_hash": "<hex>",
  "results": [
    {
      "candidate_id": "candidate-1",
      "gate": {
        "schema_version": 1,
        "mode": "SHADOW_ONLY",
        "candidate_id": "candidate-1",
        "state_hash": "<hex>",
        "generation_id": "gen-A",
        "provider": "typesafe_direct",
        "requested_model": "jev-latest",
        "evaluator_version": "season-jev-shadow-v1",
        "threshold_config_hash": "<hex>",
        "heads": {},
        "research_requirements": {},
        "side_effects_executed": false
      }
    }
  ],
  "side_effects_executed": false
}
```

Rules:

- Do **not** keep a second independently authoritative `state_hash` beside `gate.state_hash`.
- `results[]` may contain N candidate gate objects.
- Each `candidate_id` MUST be unique within the envelope; duplicates reject persistence.
- Different candidates MAY have different `state_hash` and different gate decisions in the same generation artifact.
- Persist `results[]` in **`candidate_id` ascending** order (byte-stability).
- A candidate with structural invalid input stores `gate.mode=ERROR` for that candidate only; valid siblings remain.

### 15.4 Artifact-level identity (envelope)

Artifact-level identity fields:

```text
schema_version
artifact_type
generation_id
provider
requested_model
evaluator_version
threshold_config_hash
```

There is **no** artifact-level singleton `state_hash`.

Per-candidate identity:

```text
candidate_id
state_hash
```

### 15.5 Overwrite / reuse policy

See §16. Persistence writes MUST be atomic (follow existing `write_json_atomic` convention when implemented).

---

## 16. Reuse / Identity

### 16.1 Candidate-level reuse key

Reuse is defined at the **candidate result** level (not merely whole-file level).

A prior candidate gate result may be reused only when all eight match:

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

Same `candidate_id` with a different `state_hash` MUST NOT reuse the old result.

### 16.2 `threshold_config_hash` (effective-bucket scoped; MATCHED | MISSING)

`threshold_config_hash` is a **64-character lowercase SHA-256 hex** of a canonical UTF-8 JSON payload.

#### Canonical JSON rules

- recursive sorted keys
- compact separators (no insignificant whitespace)
- `ensure_ascii=false`
- UTF-8 bytes hashed
- no timestamps
- **no unrelated** provider / requested_model / evaluator buckets

#### Canonical payload fields (locked)

```text
schema_version
provider
requested_model
evaluator_version
bucket_status
thresholds
```

#### MATCHED bucket (`bucket_status = "MATCHED"`)

When an exact `provider` + `requested_model` + `evaluator_version` bucket exists:

```json
{
  "schema_version": 1,
  "provider": "typesafe_direct",
  "requested_model": "jev-latest",
  "evaluator_version": "season-jev-shadow-v1",
  "bucket_status": "MATCHED",
  "thresholds": {
    "...": "exact raw threshold mapping from that matching bucket"
  }
}
```

Exact raw threshold mapping means:

- `null` remains `null`
- numeric remains numeric
- an **absent** head remains **absent**

Do **NOT** normalize an absent head into `null` merely for hashing.

Missing vs explicit-null configurations MUST remain distinguishable artifacts for hash identity, even though lookup semantics may treat both as UNCALIBRATED for that head.

#### MISSING bucket (`bucket_status = "MISSING"`)

When no exact bucket exists:

Lookup behavior is unchanged:

```text
status / mode path → SHADOW_ONLY
threshold → null
decision → null
reason → UNCALIBRATED
```

But `threshold_config_hash` MUST still be a deterministic valid SHA-256 hex of:

```json
{
  "schema_version": 1,
  "provider": "<requested provider>",
  "requested_model": "<requested model>",
  "evaluator_version": "<requested evaluator>",
  "bucket_status": "MISSING",
  "thresholds": null
}
```

Do **NOT**:

- hash the entire thresholds config file
- hash another provider's bucket
- invent seven `null` thresholds as if a bucket existed
- return `threshold_config_hash=null`
- invent `0.5`

Therefore missing bucket A ≠ missing bucket B when provider / model / evaluator identity differs.

#### Invalid / unreadable threshold config

Distinguish:

| Case | Gate outcome | `threshold_config_hash` |
| --- | --- | --- |
| Valid config + exact bucket missing | SHADOW_ONLY / UNCALIBRATED | deterministic MISSING-bucket hash |
| Unreadable / structurally invalid threshold config | ERROR / generation failure (§11) | do **not** fabricate a MISSING-bucket hash |

Examples of invalid config: unreadable JSON/path; malformed top-level schema; duplicate/ambiguous exact bucket if the loader treats that as invalid; invalid numeric threshold.

Do not change existing J2 `lookup_threshold` behavior unless an implementation plan later proves a deficiency.

#### Successful SHADOW_ONLY objects

Successful SHADOW_ONLY gate objects **ALWAYS** contain:

```text
threshold_config_hash = 64-char lowercase SHA-256 hex
```

including:

- all-null matching bucket
- partially populated matching bucket
- missing exact bucket

ERROR objects need not pretend a valid `threshold_config_hash` exists when threshold-config parsing itself failed.

#### Reuse consequences

- **MISSING → MATCHED** (exact bucket later added): `bucket_status` changes → hash changes → prior candidate reuse invalidated
- **Matching bucket threshold edit**: hash changes → reuse invalidated
- **Unrelated provider bucket edit**: effective canonical payload unchanged → hash unchanged → current provider candidate reuse remains valid
- **Different requested model/evaluator while still MISSING**: identity fields differ → hash differs

Do not reuse an output created under a different effective threshold set / bucket_status payload.

### 16.3 Determinism

For identical:

```text
generation_id
provider
requested_model
evaluator_version
effective threshold bucket
candidate set
candidate_id
state_hash
answers
```

the persisted artifact MUST be byte-stable.

No timestamps in the deterministic core/envelope. `results[]` order is `candidate_id` ascending.

---

## 17. Budget / Network Policy

| Call type | J3 policy |
| --- | --- |
| JEV provider | FORBIDDEN |
| News / DART / web / Deep AI | FORBIDDEN |
| Local fixture read | ALLOWED |
| Local threshold cfg read | ALLOWED |
| Local optional artifact write | ALLOWED |

J3 does not consume JEV API budgets. `season_jev.json` call budgets remain owned by shadow evaluation (upstream), not by Research Gate Shadow.

---

## 18. Security

- No secrets in J3 outputs
- No API keys in fixtures committed to git
- No logging of secrets
- Fail closed on malformed inputs
- No network in normal unit tests

---

## 19. Runtime Readiness

Current certified machine state:

```text
JEV shadow artifacts = 0
human labels = 0
locked selections = 0
holdout reports = 0
```

Therefore:

- J3 **Definition & Design** may proceed (this document).
- J3 **implementation** MUST support fixtures without live JEV.
- Non-null calibrated thresholds are not required to emit SHADOW_ONLY objects with `decision=null`.
- Do not create fake production runtime artifacts to claim readiness.

---

## 20. Testing Strategy

Future unit tests (offline fixtures) MUST cover at least:

1. all-null thresholds → all `decision=null`, `reason=UNCALIBRATED`
2. one calibrated head → that head true/false; others null
3. mixed calibrated/null heads + aggregate lists
4. exact `>=` boundary (`p == threshold` → true)
5. provider isolation (Direct thresholds never applied to OpenRouter identity)
6. requested-model isolation
7. evaluator-version isolation
8. missing bucket → UNCALIBRATED heads (not provider fallback)
9. malformed probability → ERROR
10. malformed threshold → ERROR
11. no 0.5 fallback
12. no provider fallback
13. `reviewClass` cannot route / override
14. `materialNow` advisory only
15. `historicalConflict` advisory only
16. no news call
17. no DART call
18. no Deep-AI call
19. Quant bundle unchanged / unread for decisions
20. threshold change changes `threshold_config_hash` and invalidates reuse
21. output deterministic for identical inputs
22. `enabled=false` unchanged (config not written)
23. runtime fixtures require no network
24. two candidates persist in one generation envelope
25. candidate_id uniqueness enforced
26. same generation with distinct state_hash values is valid
27. one candidate state_hash change invalidates only that candidate reuse
28. threshold bucket change invalidates candidate reuse
29. unrelated provider threshold change does not invalidate this provider
30. deterministic candidate ordering (`candidate_id` ascending)
31. candidate ERROR does not erase valid sibling results
32. envelope identity corruption fails the entire evaluation
33. missing exact bucket still yields deterministic `threshold_config_hash`
34. missing bucket hash differs by provider/model/evaluator identity
35. adding formerly-missing exact bucket changes `threshold_config_hash` and invalidates reuse
36. explicit all-null matching bucket hash differs from missing-bucket hash
37. missing head vs explicit-null head produces different matching-bucket hash while both remain UNCALIBRATED for that head
38. unrelated provider bucket edit does not change effective hash
39. malformed/unreadable config never receives fabricated MISSING-bucket hash

### Five critical review-focus risks → tests

| # | Risk | Mapped tests |
| --- | --- | --- |
| 1 | Null threshold accidentally becoming false/0.5 | 1, 2, 3, 11 |
| 2 | Threshold bucket crossing provider/model/evaluator | 5, 6, 7, 8, 12 |
| 3 | Shadow decision accidentally executing research | 16, 17, 18, assert `side_effects_executed=false` |
| 4 | J3 leaking into Quant ranking/scoring | 19 + static import/forbid checks |
| 5 | Threshold/reuse identity stale after calibration changes | 20, 21, 27, 28, 29, 33, 34, 35, 36, 37, 38, 39 |

---

## 21. Planned File Map

### Create (future implementation; not this commit)

```text
src/kr_quant/research/jev_research_gate.py
tests/unit/test_jev_research_gate.py
```

Recommended API layers (names illustrative; Implementation Plan locks finals):

```text
evaluate_research_gate(...)
  → one per-candidate Research Gate Shadow object (§10)

evaluate_research_gate_generation(...)
  → one upstream shadow generation → envelope with results[] (§15)
```

### Optional thin CLI (only if justified later)

```text
scripts/evaluate_jev_research_gate.py
```

### Possible future persistence integration

```text
{data_dir}/research_snapshots/season_jev_research_gate/
```

### Modify

Prefer **no** modifications to J2 core (`jev_calibration.py`, `season_jev_shadow.py`) unless an interface deficiency is proven during implementation planning. Prefer consuming public J2 interfaces (`lookup_threshold`, `BOOLEAN_HEADS`, status constants).

### Config

Do **not** modify `config/season_jev.json` or `config/jev_thresholds.json` for J3 design/implementation of the pure gate. Persistence paths are data-dir conventions only.

---

## 22. Implementation Task Boundaries

Suggested future task split (plan phase; not started here):

1. Types + pure evaluate function + ERROR codes
2. RED/GREEN unit tests for null/numeric/mixed/isolation
3. Optional persistence + `threshold_config_hash` + reuse
4. Optional CLI (fixtures only)
5. Invariance: no config writes; `enabled` remains false; no network

Each task remains docs/tests/code scoped to Research Gate Shadow only.

---

## 23. Definition of Done (future implementation)

J3 implementation is done when:

- All §20 tests pass offline
- `mode` is always `SHADOW_ONLY` or `ERROR`
- Null thresholds never become false/0.5
- Numeric decisions use exact `>=`
- No network / research / Quant mutations in tests or core
- `config/season_jev.json` remains `enabled=false`
- Thresholds file unchanged unless a **separately approved** human adoption task (explicitly not J3)
- GPT/user accepts the implementation verification packet

---

## 24. Future Handoff

Do **not** assign “J4” unless a later audit locks the number.

Separately gated future work (unnumbered):

| Future gate | Depends on |
| --- | --- |
| Research execution / orchestration | J3 shadow flags + explicit human/policy allowlist |
| Evidence Verifier | Own design (currently undefined) |
| Production threshold adoption | Labels, lock, holdout review, human approval |
| Production routing enablement | Adopted thresholds + explicit `enabled=true` approval |

J3 completing does **not** authorize any of the above.

---

## 25. Safety Summary

| Invariant | Lock |
| --- | --- |
| Production routing | OFF (`enabled=false`) |
| Null threshold | `decision=null` |
| Numeric threshold | `probability >= threshold` |
| 0.5 fallback | FORBIDDEN |
| Provider fallback | FORBIDDEN |
| Research execution | FORBIDDEN |
| Quant mutation | FORBIDDEN |
| Evidence Verifier | EXCLUDED |
| Mixed heads | ALLOWED |
| Tests | Fixtures only / no network |
| Runtime artifacts today | NOT READY (acknowledged) |

---

## Self-Review Checklist (author)

- [x] J3 explicitly named Research Gate Shadow
- [x] `enabled=false` preserved
- [x] null → `decision=null`
- [x] no 0.5 fallback
- [x] numeric → `probability >= threshold`
- [x] `reviewClass` non-routing
- [x] no network calls
- [x] no research execution
- [x] no Quant mutation
- [x] no automatic fallback
- [x] no production routing
- [x] Evidence Verifier excluded
- [x] runtime data absence acknowledged
- [x] fixture-only implementation possible
- [x] No TODO/TBD placeholders

---

**END OF J3 RESEARCH GATE SHADOW DESIGN**
