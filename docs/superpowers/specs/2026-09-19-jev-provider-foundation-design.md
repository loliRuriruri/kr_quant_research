# JEV Provider Foundation Design

**Status:** Approved architecture, pending implementation plan  
**Date:** 2026-09-19  
**Base:** 98d91f2c41f3150337e919d68440b57136c89b10

This document is a **formal design specification only**. The file map in Section 14 is a planned implementation outline, not an authorization to implement code in this commit.

---

## 1. Scope

### In scope

- Keep TypeSafe Direct as the default JEV provider
- Design OpenRouter as an explicitly selected second provider
- Keep shared `QUESTION_SPECS`
- Keep shared `normalizeAnswers`
- Keep shared usage normalization (`extractUsage` / `aggregateUsage`)
- Separate provider/model identity
- Separate cache and calibration identity by provider/model
- Define live smoke and validation requirements for a future implementation phase

### Out of scope

- J2 threshold calibration
- Research Gate
- Evidence Verifier
- UI
- Quant ranking/scoring changes
- Production routing enablement
- Automatic provider fallback
- Vercel AI Gateway (removed; must not be reintroduced)

---

## 2. Existing State

On `origin/main` at `98d91f2c41f3150337e919d68440b57136c89b10`:

```text
config/season_jev.json
  provider = typesafe_direct
  model = jev-latest
  enabled = false

SUPPORTED_PROVIDERS = frozenset({"typesafe_direct"})

PROVIDER_RUNNERS:
  typesafe_direct -> scripts/jev-season-shadow.mjs

package dependency:
  @typesafe-ai/sdk = 0.6.0

Vercel Gateway runner/adapter/deps:
  absent
```

Current runtime path:

```text
Python strict provider layer
  -> typesafe_direct
  -> scripts/jev-season-shadow.mjs
  -> @typesafe-ai/sdk
  -> shared season-shadow-core.mjs
  -> normalizeAnswers
  -> shadow result persistence
```

Must preserve:

```text
QUESTION_SPECS
NOUL_HEADS
REVIEW_CLASS_OPTIONS
assertStateWhitelist
assert_state_clean
normalizeAnswers
aggregateUsage
state_hash
reuse_key
requested_model
resolved_model
resolved_models
provider
wall_latency_ms
usage
quant_reference separation
enabled=false default behavior
Quant invariance on JEV failure
```

---

## 3. Approved Architecture

Approved B-option architecture:

```text
JEV Provider
├─ typesafe_direct
│   ├─ @typesafe-ai/sdk
│   ├─ TYPESAFE_API_KEY
│   └─ logical model: jev-latest
│
└─ openrouter
    ├─ POST /api/alpha/decisions
    ├─ OPENROUTER_API_KEY
    ├─ production candidate: typesafe/jev-1.13
    └─ upgrade/shadow candidate: ~typesafe/jev-latest
```

Layering:

```text
Python strict provider router
        │
        ├── typesafe_direct
        │      └── existing TypeSafe runner
        │
        └── openrouter
               └── new small OpenRouter runner/adapter
                          │
                          ▼
                shared QUESTION_SPECS
                shared normalizeAnswers
                shared aggregateUsage
```

Design principles:

1. Provider-specific code owns only transport, auth, and model namespace.
2. Question text is not duplicated into provider adapters.
3. Answer semantics are normalized in shared core.
4. Python provider routing is a strict allowlist.
5. A provider error never automatically falls back to another provider.
6. JEV failure never mutates Quant results.
7. OpenRouter results are stored in the existing unified schema.

---

## 4. Provider Contracts

### 4.1 TypeSafe Direct

```text
provider = typesafe_direct
key = TYPESAFE_API_KEY
runner = scripts/jev-season-shadow.mjs
sdk = @typesafe-ai/sdk 0.6.0
requested model = jev-latest
```

Live evidence (reference):

```text
requested_model = jev-latest
resolved_model = jev-1.13.0
```

Note: `jev-latest` is an alias and may drift in the future.

### 4.2 OpenRouter

```text
provider = openrouter
key = OPENROUTER_API_KEY
endpoint = POST https://openrouter.ai/api/alpha/decisions
production requested model = typesafe/jev-1.13
upgrade/shadow model = ~typesafe/jev-latest
```

Live spike evidence (reference, TEMP-only, no implementation):

Pinned:

```text
HTTP 200
requested = typesafe/jev-1.13
returned = typesafe/jev-1.13-20260917
provider field = TypeSafe
7 noul probabilities valid
reviewClass valid
confidence present
usage present
cost present
```

Latest alias:

```text
HTTP 200
requested = ~typesafe/jev-latest
returned = typesafe/jev-1.13-20260917
```

OpenRouter raw answer semantics:

```text
boolean question:
  type = noul
  noul = numeric probability in [0, 1]

reviewClass:
  type = choice
  choice = one of no_action | monitor | verify_sources | revalidate_thesis | deep_review
  probabilities = optional map
  confidence = optional number
```

These shapes are semantically compatible with existing `normalizeAnswers()`.

---

## 5. Model Identity Policy

Always distinguish:

```text
provider
requested_model
resolved_model
```

Examples:

```text
typesafe_direct
  requested_model = jev-latest
  resolved_model = jev-1.13.0

openrouter
  requested_model = typesafe/jev-1.13
  resolved_model = typesafe/jev-1.13-20260917
```

Rules:

1. Cache identity includes at least:
   - `evaluator_version`
   - `provider`
   - `requested_model`
   - `state_hash`
2. Providers must not share cache entries.
3. Direct `jev-latest` and OpenRouter `typesafe/jev-1.13` must not share a calibration bucket.
4. `~typesafe/jev-latest` is never a production calibration source.
5. If a floating alias moves to a new resolved model:
   - do not transfer calibration trust
   - bump `evaluator_version` or open a new calibration bucket

---

## 6. OpenRouter Adapter Boundary

OpenRouter adapter/runner owns:

```text
- Authorization: Bearer OPENROUTER_API_KEY
- POST https://openrouter.ai/api/alpha/decisions
- requested OpenRouter model ID
- AbortSignal / timeout propagation
- response JSON parsing
- raw answers handoff
- snake_case usage handoff
- provider / cost / resolved-model metadata handoff
```

Shared core owns:

```text
- state whitelist
- timeout envelope
- concurrency
- max API call cap
- QUESTION_SPECS
- normalizeAnswers
- extractUsage
- aggregateUsage
- result schema
```

OpenRouter adapter must not:

```text
- duplicate question text
- apply probability thresholds
- change Quant scores
- fall back to another provider
- make calibration decisions
- change ranks
```

---

## 7. Unified Output Contract

Minimum per-result schema:

```text
id
candidate_type
ticker
state_hash
provider
answers
usage:
  inputTokens
  outputTokens
  totalTokens
requested_model
resolved_model
wall_latency_ms
```

Optional OpenRouter telemetry metadata:

```text
provider_name
cost
request_id
```

Rules:

- Optional metadata must not break the shared success contract.
- Missing values stay `null`.
- Do not invent zeros for missing usage/cost.
- `reviewClass.confidence` remains on the normalized answer object.

---

## 8. No Automatic Fallback

Hard rule:

```text
typesafe_direct failure
≠ automatic openrouter call

openrouter failure
≠ automatic typesafe_direct call
```

Provider is selected explicitly in config.

Reasons:

```text
- auditability
- cache identity
- calibration reproducibility
- cost attribution
- probability-distribution drift control
```

---

## 9. Calibration Isolation

Before J2, enforce:

```text
calibration bucket =
  provider
+ requested_model
+ evaluator_version
```

One-sample Direct vs OpenRouter deltas of about `0.01`–`0.03` were observed. Therefore:

- Do not assume shared thresholds across providers/models.
- Compute metrics per provider/model.
- Do not enable production routing before enough labels exist.

Initial thresholds remain `null`.

---

## 10. UV_HANDLE_CLOSING Policy

Windows Node `v24.14.1` observations:

Spike (one OpenRouter call path):

```text
successful JSON write
then UV_HANDLE_CLOSING assert
non-zero process exit observed
```

Formal diagnostic:

```text
5 pinned runs + 2 additional launches
HTTP 200
JSON valid
UV assert count = 0
exit = 0
```

Classification:

```text
INTERMITTENT ENVIRONMENTAL/RUNTIME RISK
```

Policy for this foundation:

```text
- no workaround in this feature
- do not force Connection: close
- do not force process.exit(0)
- do not swap HTTP libraries for this feature
- do not couple Node downgrade/upgrade to this feature
```

If the runner process exits non-zero, treat the evaluation as failure even if a JSON body was already written. Do not trust that process as success. Quant remains unchanged.

If recurrence becomes materially frequent, open a separate debugging task.

---

## 11. Security

Keys:

```text
TYPESAFE_API_KEY
OPENROUTER_API_KEY
```

Rules:

```text
- never log key values
- never put key values in reports
- never store keys in git-tracked files
- print environment presence only (PRESENT / MISSING)
```

---

## 12. Budget

Global JEV budget remains authoritative across providers:

```text
max_api_calls_per_generation
max_api_calls_per_day
```

OpenRouter `cost` is observational telemetry only and does not replace call-count caps.

---

## 13. Testing Strategy

Implementation must be TDD.

### Provider routing

RED → GREEN:

```text
provider=openrouter accepted
provider=typesafe_direct accepted
unknown provider rejected
vercel_gateway rejected
no fallback
```

### Key routing

```text
typesafe_direct -> TYPESAFE_API_KEY
openrouter -> OPENROUTER_API_KEY
missing selected-provider key -> skip/fail harmlessly
presence of the other provider key must not trigger fallback
```

### OpenRouter transport mock

Verify:

```text
exact endpoint
Authorization header present (value not printed)
exact model
exact state
exact questions
AbortSignal forwarded
non-200 normalized error
malformed JSON normalized error
timeout contained
```

### Shared schema

Verify:

```text
OpenRouter raw noul -> boolean probability
choice -> unified choice schema
snake_case usage -> camelCase unified usage
missing usage -> null
cost optional
resolved model preserved
```

### Safety

Verify:

```text
forbidden Quant fields rejected
JEV failure does not mutate Quant
enabled=false behavior unchanged
cache isolated by provider
state_hash changes with provider/model
```

### Live smoke

One candidate each:

```text
TypeSafe Direct: jev-latest
OpenRouter: typesafe/jev-1.13
```

`~typesafe/jev-latest` is upgrade/shadow validation only.

---

## 14. Implementation File Map

**Plan-only candidates for a later implementation phase.** Creating or modifying these files is out of scope for this doc-only commit.

Create (planned):

```text
scripts/jev-season-shadow-openrouter.mjs
scripts/jev/season-shadow-openrouter-adapter.mjs
tests/js/jev_season_openrouter.test.mjs
```

Modify (planned):

```text
src/kr_quant/research/season_jev_shadow.py
scripts/jev/season-shadow-core.mjs
tests/js/jev_season_shadow.test.mjs
tests/unit/test_season_jev_shadow.py
```

Prefer no new package dependency. Prefer Node built-in `fetch`. Reconfirm Node version support in the implementation plan.

---

## 15. Explicit Non-Goals

This provider foundation does not include:

```text
- J2 thresholds
- human-label calibration
- Research Gate
- Evidence Verifier
- UI
- final investment decisions
- automatic provider selection
- automatic fallback
- dynamic cheapest-provider routing
- OpenRouter latest as production default
- Quant score blending
```

---

## 16. Definition of Done

Provider foundation implementation is complete only when:

```text
1. Direct provider regressions pass
2. OpenRouter provider tests pass
3. both providers require explicit selection
4. no fallback
5. same QUESTION_SPECS
6. unified answers
7. provider-specific keys
8. provider/model cache isolation
9. pinned OpenRouter live smoke passes
10. Direct live smoke passes
11. enabled=false
12. Quant before/after unchanged
13. full pytest passes
14. no Vercel code/dependency reintroduced
```

---

## Self-review checklist

- [x] No TODO/TBD placeholders
- [x] Consistent with approved B option
- [x] Vercel Gateway not redesigned as a provider
- [x] TypeSafe Direct remains default
- [x] OpenRouter pinned `typesafe/jev-1.13` is the production candidate
- [x] `~typesafe/jev-latest` is shadow/upgrade only
- [x] Automatic fallback prohibited
- [x] Provider/model cache isolation documented
- [x] Calibration isolation documented
- [x] Shared QUESTION_SPECS documented
- [x] Shared normalizer documented
- [x] Quant invariance documented
- [x] enabled=false documented
- [x] UV assert policy documented
- [x] Implementation file map explicitly plan-only
