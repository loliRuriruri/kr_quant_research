# JEV Calibration Design

Status: Approved design direction, pending implementation plan

Date: 2026-09-19

Base: `dcaa92bbeccd42e2d82055949d7e70900d933770`

Approach: **A — Simple threshold calibration**

Related:

- Provider foundation: `docs/superpowers/specs/2026-09-19-jev-provider-foundation-design.md` (§9 Calibration Isolation)
- Current tracked JEV config (`config/season_jev.json`): `enabled=false`, `provider=typesafe_direct`, `model=jev-latest`, `evaluator_version=season-jev-shadow-v1`

---

## 1. Problem / Goal

JEV boolean heads emit a `probability` in `[0, 1]`. The existing runner helper `normalizeAnswers` in `scripts/jev/season-shadow-core.mjs` derives a **debug/display** field:

```text
decision = (probability >= 0.5)   // display/normalize only
```

That `0.5` cut is **not** a production routing threshold. Confusing the two is the core risk this design prevents.

### J2 goal

Build a calibration subsystem that:

1. Collects **blind** human labels for the seven boolean heads.
2. Compares those labels to JEV probabilities for a fixed calibration bucket.
3. Produces auditable **threshold sweep evidence** and candidate thresholds.
4. Keeps production routing **off** until a later explicit approval gate.

Calibration bucket identity (hard):

```text
provider + requested_model + evaluator_version
```

Metrics and threshold candidates are further sliced **per head**.

Until J2 tooling exists and thresholds are explicitly approved, every head remains:

```text
threshold == null  →  UNCALIBRATED / SHADOW_ONLY / no production decision
```

J2 does **not** set `config/season_jev.json` `enabled=true`. J2 does **not** turn on production routing.

---

## 2. Architecture Decision

### Selected: Approach A — raw probability threshold sweep

For each calibration bucket and each boolean head, evaluate candidate thresholds against human labels and report confusion-matrix metrics.

**Why A now**

- No human label dataset exists yet.
- Highest auditability and reproducibility.
- Makes provider/model drift visible without shared assumptions.
- Simple implementation and exact unit tests.
- Threshold provenance is explicit (chosen from a published sweep table).

### Deferred: Approach B — Platt / isotonic probability calibration

Future extension after sufficient labeled support. May reshape probabilities before a threshold sweep. Not in J2 scope.

### Deferred: Approach C — online / adaptive calibration

Future only. Excluded from J2 because continuous adaptation harms reproducibility and auditability, and invites automatic production application.

---

## 3. Calibration Identity

### Hard bucket key

```text
bucket_id = (provider, requested_model, evaluator_version)
```

Examples:

| provider | requested_model | evaluator_version |
|----------|-----------------|-------------------|
| `typesafe_direct` | `jev-latest` | `season-jev-shadow-v1` |
| `openrouter` | `typesafe/jev-1.13` | `season-jev-shadow-v1` |

### `resolved_model`

Stored on each sample as **observation metadata** (what the provider actually served). It is **not** part of the bucket key.

### Alias policy

OpenRouter alias `~typesafe/jev-latest` is **upgrade / shadow observation only**.

- It must **not** be used as a production calibration bucket.
- It must **not** share thresholds with `typesafe/jev-1.13` or Direct `jev-latest`.

### Alias / latest drift

If Direct `jev-latest` later resolves to a different underlying model version, follow provider-foundation policy: bump `evaluator_version` and/or open a **new** calibration bucket. Do not silently reuse prior thresholds.

### Isolation rules (hard)

- No threshold sharing across providers.
- No threshold sharing across `requested_model` values.
- No threshold sharing across `evaluator_version` values.
- No fallback from missing bucket/head to another bucket/head or to `0.5`.

---

## 4. Threshold Configuration Design

### Future file (not created by this spec commit)

```text
config/jev_thresholds.json
```

### Schema (`schema_version: 1`)

```json
{
  "schema_version": 1,
  "buckets": [
    {
      "provider": "typesafe_direct",
      "requested_model": "jev-latest",
      "evaluator_version": "season-jev-shadow-v1",
      "thresholds": {
        "materialNow": null,
        "needsCurrentYearCheck": null,
        "needsNews": null,
        "needsDart": null,
        "historicalConflict": null,
        "invalidationCheckNeeded": null,
        "needsDeepAI": null
      }
    },
    {
      "provider": "openrouter",
      "requested_model": "typesafe/jev-1.13",
      "evaluator_version": "season-jev-shadow-v1",
      "thresholds": {
        "materialNow": null,
        "needsCurrentYearCheck": null,
        "needsNews": null,
        "needsDart": null,
        "historicalConflict": null,
        "invalidationCheckNeeded": null,
        "needsDeepAI": null
      }
    }
  ]
}
```

Optional future bucket-level metadata (non-authoritative for routing): `updated_at`, `selection_policy_notes`, `approved_by`, `approved_at`. Metadata must never invent a numeric threshold when the head value is `null`.

### Null / missing semantics (hard)

| Condition | Status | Production decision |
|-----------|--------|---------------------|
| `threshold == null` | `UNCALIBRATED` / `SHADOW_ONLY` | Forbidden |
| Bucket absent from file | `UNCALIBRATED` / `SHADOW_ONLY` | Forbidden |
| Head key absent in bucket | `UNCALIBRATED` / `SHADOW_ONLY` | Forbidden |
| File absent | `UNCALIBRATED` / `SHADOW_ONLY` | Forbidden |

**Absolute bans**

- No default/fallback threshold (including `0.5`).
- No cross-provider or cross-model threshold fallback.
- Calibration engine must not auto-write production-approved thresholds without an explicit human approval gate outside J2 auto-flow.

When first created in a later implementation task, the tracked file must ship with **all heads null** for every seeded bucket.

---

## 5. Calibration Heads

### In scope (7 independent binary heads)

```text
materialNow
needsCurrentYearCheck
needsNews
needsDart
historicalConflict
invalidationCheckNeeded
needsDeepAI
```

These match existing `NOUL_HEADS` / `QUESTION_SPECS` boolean heads.

### Out of binary-threshold scope

`reviewClass` (choice head) is for **shadow / debug / qualitative explanation** only. It is **not** a J2 production binary routing threshold input and must not appear in `thresholds` maps.

### Head semantics (non-investment)

- **`materialNow`**: research-attention relevance given supplied evidence. **Not** a buy/sell or return forecast.
- **`needsDeepAI`**: after deterministic/source verification, whether deeper strong-LLM synthesis is likely to add material research value. **Not** a Quant score or rank signal.

Neither head may be combined with Quant score, rank, or expected return for routing.

---

## 6. Human Label Schema

For each of the seven heads, an independent label:

| Value | Meaning |
|-------|---------|
| `true` | Annotator judges the head affirmative |
| `false` | Annotator judges the head negative |
| `unknown` | Insufficient evidence / ambiguous / cannot reliably label |

### Hard rules

- Do **not** coerce `unknown` to `false` (or to `true`).
- Binary metrics use only labels in `{true, false}`.
- Reports must still include `unknown_count` and `unknown_rate` per head.

---

## 7. Sample Record Schema

Future calibration samples (JSON object / JSONL row) must include at least:

```text
sample_id
candidate_id
candidate_type
ticker
generation_id
selection_date

provider
requested_model
resolved_model
evaluator_version

state_hash
state

jev_answers

human_labels

annotation_version
labeled_at

split
blind
```

Optional metadata: `source_generation`, `notes`, `labeler_id`, shadow artifact path reference.

### Field rules

- `state`: JEV evidence state only. Must pass the same Quant-forbid rules as shadow evaluation (`assert_state_clean` / equivalent).
- `jev_answers`: per-head objects including at least `probability` (number in `[0,1]`) for each of the seven heads; may include display `decision` from normalize, which is **non-authoritative** for calibration.
- `human_labels`: map of head → `true` | `false` | `unknown`.
- `split`: `calibration` | `holdout`.
- `blind`: `true` if probabilities/threshold/prediction were hidden until after label commit; otherwise `false`.
- Prefer `blind=true` samples for any future production-threshold approval dataset.

### Quant reference separation

Labeler/debug UI **may** show Quant reference in a **separate panel** (rank/grade/score for human context).

Quant reference **must not** appear inside:

- `state`
- calibration model inputs
- threshold selection features

### Forbidden fields anywhere in `state` (and rejected if nested)

```text
quantReference
quant_reference
pre_entry_rank
grade
seasonality_score
score_breakdown
```

---

## 8. Sample Identity

### Deterministic `sample_id`

```text
sample_id = sha256_hex(
  provider + "\n" +
  requested_model + "\n" +
  evaluator_version + "\n" +
  state_hash
)
```

Encoding: UTF-8 string concatenation with literal newline separators as shown; hash = SHA-256 hex digest (lowercase).

### Dedup / revision

- A dataset must not contain two active rows with the same `sample_id` and conflicting labels without an explicit revision record.
- Label revisions **keep** the same `sample_id` and advance `annotation_version` (and revision metadata). Silent overwrite of committed labels is forbidden.
- Conflicting concurrent commits for the same `sample_id` must fail closed with a deterministic conflict error.

---

## 9. Blind Labeling Protocol

Human annotation order (hard for `blind=true`):

1. Show candidate identity, ticker, and `state` / evidence summary (optional separate Quant reference panel).
2. Hide JEV `probability`.
3. Hide configured/candidate `threshold`.
4. Hide predicted class (`probability >= threshold` or display `decision`).
5. Collect human labels for the seven heads (`true` / `false` / `unknown`).
6. Persist / commit labels.
7. Only after commit, optionally reveal probability / threshold / predicted class for reviewer education.

### Bias control

Samples where the annotator saw JEV probability before commit must be recorded as `blind=false` and kept distinguishable from the strict blind set.

---

## 10. Dataset Storage Design

### Future runtime root (not created by this spec commit)

```text
data/research/jev_calibration/
  labels/
  exports/
  reports/
```

Examples:

```text
labels/<dataset_id>.jsonl
exports/<dataset_id>.jsonl
reports/<dataset_id>.json
reports/<dataset_id>.md
```

### Artifact roles

- **`labels/`**: append-oriented raw annotation records (source of truth for human judgments). Prefer append-only JSONL; corrections via new revision rows, not silent mutation.
- **`exports/`**: frozen join of labels + JEV answers used for a specific report run (regenerable).
- **`reports/`**: regenerable metrics/sweep outputs (JSON + Markdown).

### Git tracking policy (current repo facts)

As of base `dcaa92b`, `.gitignore` ignores `data/research_snapshots/` (and other `data/*` lakes) but **does not** ignore `data/research/`.

**Policy for J2 implementation (future change, not this commit):**

1. Add `data/research/jev_calibration/` to `.gitignore` so labels/exports/reports stay local runtime artifacts (like shadow snapshots).
2. Keep `config/jev_thresholds.json` **tracked** when introduced, with all-null thresholds until an explicit approval updates values.
3. Do not commit raw label PII or API secrets into git.

---

## 11. Calibration / Holdout Split

### Hard rules

- Threshold **selection** uses the `calibration` split only.
- Holdout is **never** used to choose a threshold.
- Final published performance for a candidate threshold must report **holdout** metrics (and may also show calibration metrics as non-selection diagnostics).
- The same `state_hash` must always map to the same `split` within a dataset.
- Duplicate/revision rows for the same `sample_id` inherit the same `split`.

### Deterministic grouped split algorithm (`split_method_version`: `grouped-v1`)

Do **not** use independent per-row random splits.

1. Define group key:

```text
group_key = sha256_hex(ticker + "\n" + generation_id)
```

(`ticker` and `generation_id` UTF-8; missing `generation_id` uses empty string, but exporters should prefer always populating it.)

2. Map to bucket:

```text
split_bucket = int(group_key[0:8], 16) % 100   // 0..99
```

3. Assign:

```text
if split_bucket < 70:  split = "calibration"
else:                  split = "holdout"
```

(70/30 grouped split.)

4. Consistency checks (fail closed):

- All rows sharing `state_hash` must share the same assigned `split`; otherwise raise `SPLIT_STATE_HASH_CONFLICT`.
- All rows sharing `sample_id` must share the same `split`; otherwise raise `SPLIT_SAMPLE_CONFLICT`.

### Future optional validation

After sufficient volume, a **time-ordered** holdout (by `selection_date` / generation) may be added as an additional validation report. It does not replace `grouped-v1` for J2’s primary design and must still forbid using that holdout for threshold selection.

---

## 12. Minimum Support

Counts are **per bucket × head**, using valid labels only (`true`/`false`). `unknown` does not count toward valid support.

| Gate | Rule |
|------|------|
| Initial analysis allowed | `valid_labels >= 50` per head |
| Production routing **review** eligible (not auto-enable) | `valid_labels >= 100` per head |

Additionally report:

- `support_positive` (human `true`)
- `support_negative` (human `false`)

If either class support is below **10** valid labels for that head (while total valid ≥ 50), mark:

```text
INSUFFICIENT_CLASS_SUPPORT
```

Having 100 total samples does **not** auto-mark a head calibrated. Calibration status remains `UNCALIBRATED` while threshold is `null`, regardless of sample count.

---

## 13. Metrics

For each `(provider, requested_model, evaluator_version, head)` and each evaluated threshold:

| Field | Definition |
|-------|------------|
| `threshold` | Candidate or configured value |
| `TP` / `FP` / `TN` / `FN` | Confusion counts vs human `{true,false}` |
| `precision` | `TP / (TP+FP)` or `null` if denominator 0 |
| `recall` | `TP / (TP+FN)` or `null` if denominator 0 |
| `FPR` | `FP / (FP+TN)` or `null` if denominator 0 |
| `FNR` | `FN / (FN+TP)` or `null` if denominator 0 |
| `support_positive` / `support_negative` | Human class counts |
| `unknown_count` | Human `unknown` count (excluded from confusion) |
| `calibration_count` / `holdout_count` | Valid-label counts in each split |

**Division-by-zero:** emit JSON `null`. Do **not** invent `0.0` for undefined rates.

Invalid / non-finite / out-of-range probabilities: exclude the sample from that head’s metrics and increment an `invalid_probability_count` error counter.

---

## 14. Threshold Sweep

### Method (`sweep_method_version`: `observed-boundaries-v1`)

For each bucket × head on the **calibration** split:

1. Collect the set of finite probabilities in `[0, 1]` from valid-labeled samples.
2. Build candidate thresholds:

```text
candidates = sort_unique( {0.0, 1.0} ∪ observed_probabilities )
```

3. For each candidate `t`, predict positive when:

```text
probability >= t
```

4. Compute the full metrics table on calibration samples.
5. For each candidate (or for a shortlist), also compute **holdout** metrics **without** using holdout to pick `t`.

### Why observed boundaries (not a fixed fine grid)

- Only boundaries that change predictions on the labeled set matter.
- Reduces meaningless grid noise.
- Remains fully deterministic given the dataset.

### Display `decision` at 0.5

The normalizeAnswers `probability >= 0.5` display decision may appear as one row in the sweep **if and only if** `0.5` is in the candidate set (because `0.0`/`1.0`/observed values include it, or as an explicit diagnostic row labeled `display_normalize_0_5`). It must be labeled as **debug/display reference**, never as an auto-selected production threshold.

---

## 15. Threshold Selection Policy

### Engine vs approval

The calibration engine **produces**:

- full sweep tables
- candidate thresholds
- metrics (calibration + holdout)
- Pareto-style shortlists

The engine **must not**:

- auto-commit a production threshold into `config/jev_thresholds.json`
- auto-enable JEV
- auto-start production routing

Final numeric threshold adoption is a **separate human approval gate** after J2 tooling exists.

### High false-negative cost heads

Treat as FN-sensitive for reporting and shortlisting (not for invented numeric quotas):

```text
needsDart
historicalConflict
invalidationCheckNeeded
```

For these heads:

- Do **not** auto-pick “max accuracy” as the implied production choice.
- Report Pareto frontier tradeoffs among recall / FNR / precision / FPR.
- Prefer shortlists that surface low-FNR candidates alongside precision cost.

This design intentionally **does not** invent fixed targets such as “recall ≥ 0.9”.

### Other heads

Still no automatic production commit. Sweep + human review apply to all seven heads.

---

## 16. Calibration Report

Future report artifacts (`reports/<dataset_id>.{json,md}`) must include at least:

- Bucket identity: `provider`, `requested_model`, `evaluator_version`
- `dataset_id`, `dataset_hash`, `annotation_version`, `created_at`
- `split_method_version`, `sweep_method_version`
- Per head: valid labels, positive, negative, unknown, `INSUFFICIENT_CLASS_SUPPORT` flag when applicable
- Threshold sweep table
- Confusion metrics for each candidate
- Explicit candidate shortlist(s) with rationale tags (e.g. `fn_sensitive_pareto`) — still non-binding
- Holdout metrics for reported candidates
- `resolved_model` distribution observed in the dataset
- Optional: provider telemetry summary (latency, cost)

### Budget note in reports

OpenRouter `cost` fields are **observational**. Global JEV call caps remain authoritative:

```text
max_api_calls_per_generation
max_api_calls_per_day
```

Calibration collection must not bypass those caps.

---

## 17. Reproducibility

A report is reproducible when the same inputs yield the same outputs:

Required provenance fields:

```text
dataset_id
dataset_hash
provider
requested_model
evaluator_version
annotation_version
split_method_version          # grouped-v1
sweep_method_version          # observed-boundaries-v1
prediction_rule               # probability >= threshold
```

`dataset_hash`: SHA-256 over the canonical JSONL export bytes used for the run (or equivalent canonical serialization documented by the exporter).

---

## 18. UI / Visual Debug Concept

Not required to implement inside J2’s first engineering slice; design contract for a later debug/admin view.

### Blind labeling mode

Visible: candidate, ticker, evidence/`state` summary, human label controls.
Hidden: JEV probability, threshold, predicted class.

### Review mode (after label commit)

Visible: candidate, ticker, human label, JEV probability, threshold candidate(s), predicted class, provider, requested_model, resolved_model, evaluator_version, TP/FP/TN/FN category for a selected threshold.

### Placement

Do **not** expose J2 calibration controls on the general investor dashboard. Keep under research/debug/admin surfaces.

---

## 19. Error Handling

| Condition | Behavior |
|-----------|----------|
| Missing bucket | `UNCALIBRATED` / `SHADOW_ONLY` |
| `null` threshold | `SHADOW_ONLY`; no production decision |
| Invalid probability | Exclude from head metrics; increment error count |
| `unknown` human label | Exclude from binary confusion; count in unknown stats |
| Duplicate `sample_id` with conflict | Deterministic conflict error; no silent overwrite |
| Conflicting label revisions without version bump | Reject |
| `SPLIT_*_CONFLICT` | Fail closed |
| Unsupported / unknown provider-model-evaluator for a write path expecting a known bucket | Fail closed |
| Forbidden Quant fields in `state` | Reject sample |

---

## 20. Quant Isolation

Hard non-goals for J2 runtime behavior:

- No Quant score mutation
- No rank mutation
- No season snapshot mutation for trading
- No trade signal mutation

Quant reference remains label/debug side metadata only. Calibration never feeds Quant-forbidden fields into JEV state or threshold features.

Existing shadow helpers (`quant_reference_season` / `quant_reference_calendar`, `FORBIDDEN_STATE_KEYS`, `assert_state_clean`) define the isolation baseline this design extends.

---

## 21. Budget

Authoritative caps remain those in `config/season_jev.json` / `season_jev_budget.py`:

- `max_api_calls_per_generation`
- `max_api_calls_per_day`

Calibration jobs that invoke JEV must consume and respect the same budget ledger. Cost telemetry does not create a parallel allowance.

---

## 22. Testing Strategy (future implementation)

Minimum automated checks:

1. `null` threshold → `SHADOW_ONLY` / no production decision helper returns non-routing status
2. Missing bucket / missing head → same
3. Provider isolation: Direct thresholds never apply to OpenRouter rows
4. `requested_model` isolation
5. `evaluator_version` isolation
6. Alias bucket never merges with pinned/`jev-latest` Direct bucket
7. `unknown` excluded from TP/FP/TN/FN
8. Zero denominators → `null` rates
9. Duplicate `sample_id` detection
10. Calibration/holdout non-overlap of `state_hash` / `sample_id`
11. Same `state_hash` cannot cross splits
12. Sweep candidate set deterministic for a fixture dataset
13. Prediction rule `probability >= threshold` exact
14. Confusion matrix exact on fixtures
15. FN-sensitive heads: no auto production threshold writer
16. Forbidden Quant fields rejected from `state`
17. Quant bundle unchanged by calibration APIs
18. Loading thresholds never flips `season_jev.json` `enabled` to `true`
19. No provider fallback on missing key/threshold

---

## 23. J3 Handoff Condition

J3 (Research Gate Shadow) may be considered only when **all** of the following are true:

1. Calibration tooling exists (ingest labels, split, sweep, report).
2. Labels are collectable under the blind protocol.
3. Reports are reproducible from provenance fields.
4. Provider/model/evaluator buckets remain isolated.
5. Thresholds are still all `null`, **or** only values explicitly approved by a human gate are non-null.
6. `config/season_jev.json` can remain `enabled=false`.
7. J3 shadow work stays separated from production routing.

**Hard:** Completing J2 design or tooling does **not** automatically enable JEV production routing or set `enabled=true`.

---

## 24. Non-goals

Out of J2 scope:

- Platt scaling / isotonic regression (Approach B)
- Online / adaptive calibration (Approach C)
- Automatic threshold deployment to production
- Provider winner selection or cross-provider threshold transfer
- Quant ranking integration / score coupling
- Production trading decisions
- J3 / J4 implementation
- Public dashboard redesign
- Creating runtime data directories or `config/jev_thresholds.json` in this spec commit

---

## 25. Planned File Map (future implementation only)

Create candidates (names may be adjusted to repo CLI conventions during the implementation plan):

```text
config/jev_thresholds.json
src/kr_quant/research/jev_calibration.py
tests/unit/test_jev_calibration.py
scripts/jev_calibration_export.py
```

CLI naming note: existing scripts use verbs such as `evaluate_*`, `export_*`, `verify_*`. `scripts/jev_calibration_export.py` matches the `export_*` pattern; an alternate `scripts/evaluate_jev_calibration.py` is acceptable if the implementation plan prefers evaluate-style entrypoints.

Runtime data:

```text
data/research/jev_calibration/{labels,exports,reports}/
```

**This formal-spec commit creates none of the above files/directories**—documentation only.

---

## 26. Relationship to Existing Shadow Cache

Shadow reuse identity already includes:

```text
evaluator_version + provider + requested_model + state_hash
```

Calibration `sample_id` aligns with that reuse identity (same four logical components). Calibration may **read** existing shadow artifacts under `data/research_snapshots/season_jev_shadow/` as a JEV answer source. New API calls remain budget-gated. Calibration must not corrupt shadow files or widen Quant into state.

---

## 27. Definition of Done (this design document)

This specification explicitly defines:

- Selected Approach A
- Calibration identity
- Threshold JSON schema
- Null / missing semantics
- Seven boolean heads
- `reviewClass` excluded from binary thresholds
- Human label schema
- Blind labeling protocol
- Sample identity
- Storage layout + git policy
- Deterministic grouped split + holdout isolation
- Leakage prevention rules
- Minimum support + class support
- Metrics + null-safe rates
- Threshold sweep method + `>=` prediction rule
- Selection gate (no auto production threshold)
- FN-sensitive heads (report policy, no invented quotas)
- Report provenance
- Error handling
- Provider / model / evaluator / alias isolation
- Quant isolation
- Budget authority
- Debug UI concept
- Testing strategy
- J3 handoff conditions
- Non-goals

No placeholder sections remain.

---

## 28. Safety Summary

| Rule | Requirement |
|------|-------------|
| `enabled` | Stays `false` unless a later explicit task changes it |
| `0.5` | Display/normalize only; never auto production threshold |
| Null thresholds | `SHADOW_ONLY`; no routing |
| Holdout | Evaluation only; never threshold selection |
| Providers/models | Isolated buckets; no shared thresholds |
| Alias | Observation only; not production calibration |
| `unknown` | Not coerced to `false` |
| Quant | Forbidden in state; no score/rank mutation |
| Auto-deploy | Forbidden in J2 |
