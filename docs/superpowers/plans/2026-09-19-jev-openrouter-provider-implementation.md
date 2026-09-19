# JEV OpenRouter Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenRouter as an explicitly selected JEV provider while keeping TypeSafe Direct as the default, preserving shared question/normalization logic, provider/model cache isolation, no fallback, and Quant invariance.

**Architecture:** Keep Python as the strict provider router. TypeSafe Direct continues through the existing SDK runner; OpenRouter gets a small fetch-based runner/adapter for `/api/alpha/decisions`, while shared `QUESTION_SPECS`, normalization, usage aggregation, budget rules, state guards, and persistence contracts remain centralized.

**Tech Stack:** Python 3.11+, Node.js built-in `fetch`, @typesafe-ai/sdk 0.6.0, node:test, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-jev-provider-foundation-design.md` (commit `cce3df19896e0ee4e3e7b8fa40a895398f13d809`)

## Global Constraints

- TypeSafe Direct remains default.
- OpenRouter is explicit optional provider only.
- No automatic fallback in either direction.
- OpenRouter production requested model is `typesafe/jev-1.13`.
- `~typesafe/jev-latest` is TEMP/live upgrade comparison only; it is not allowed on the normal production `evaluate_generation()` config path.
- If `provider=openrouter` and `model` is anything other than `typesafe/jev-1.13`, fail closed with `UNSUPPORTED_JEV_MODEL:openrouter:<model>` before transport.
- `config/season_jev.json` remains `enabled=false` with Direct defaults.
- No Quant score/rank/factor mutation.
- Shared `QUESTION_SPECS` and `normalizeAnswers` remain source of truth.
- Provider/model cache identity remains isolated.
- Calibration buckets are `provider + requested_model + evaluator_version`.
- Vercel Gateway must not be reintroduced.
- No new npm dependency; built-in `fetch` only.
- Missing usage/cost remains `null`, never invented zero.
- Non-zero Node runner exit is failure even if stdout contained JSON; exact contract is `status=ERROR` and `errors=[{"error":"RUNNER:RuntimeError"}]`.
- Global JEV call caps remain authoritative across providers.
- Secret values must never appear in logs or tests.
- Do not start J2, Research Gate, Evidence Verifier, UI, or production enablement.

## Review Focus

1. **Selected provider key isolation** (Task 1): `OPENROUTER_API_KEY` presence must never make `typesafe_direct` fall back to or use it; `TYPESAFE_API_KEY` presence must never make `openrouter` fall back to or use it.
2. **OpenRouter process/API failure after partial stdout** (Task 4): non-zero process exit must remain failure; never trust stdout-only success (`NODE_EXIT_*` -> persisted `ERROR` / `RUNNER:RuntimeError`).
3. **Model/cache isolation** (Task 1 + Task 4): same state under `typesafe_direct`/`jev-latest` vs `openrouter`/`typesafe/jev-1.13` must not reuse the same cache/state identity; invalid OpenRouter model never reaches `run_node`.
4. **Incomplete OpenRouter response / telemetry** (Task 2 + Task 3): missing usage/cost/optional metadata must normalize to `null`; optional OpenRouter telemetry must survive `evaluateCandidates()` into runner stdout.
5. **Forbidden Quant leakage** (Task 2 + Task 3): OpenRouter path must reject `quantReference` before transport starts.

---

## File Structure

### Existing / modify

| Path | Responsibility |
|---|---|
| `src/kr_quant/research/season_jev_shadow.py` | Strict provider allowlist, runner map, `provider_name`, `provider_runner_path`, `provider_key`, new `requested_model(cfg)`, `state_hash`, `reuse_key`, `run_node` (`NODE_EXIT_*`), `evaluate_generation`, persistence of optional telemetry |
| `scripts/jev/season-shadow-core.mjs` | `QUESTION_SPECS`, whitelist, `normalizeAnswers`, usage helpers, `extractProviderTelemetry`, `evaluateCandidates` allowlist + telemetry passthrough |
| `tests/unit/test_season_jev_shadow.py` | Python router/key/model/cache/no-fallback/NODE_EXIT/invariance tests |
| `tests/js/jev_season_shadow.test.mjs` | Shared-core regressions including openrouter accept + telemetry preservation |

### Planned create

| Path | Responsibility |
|---|---|
| `scripts/jev-season-shadow-openrouter.mjs` | stdin JSON runner; sanitized stderr via `logErr`; try/catch around `evaluateCandidates`; exit 1 on thrown errors; no secret logging |
| `scripts/jev/season-shadow-openrouter-adapter.mjs` | `buildOpenRouterQuestions()` + exact `postOpenRouterDecision({state, questions, model, apiKey, fetchImpl=fetch, signal})` |
| `tests/js/jev_season_openrouter.test.mjs` | mocked `fetch` transport + adapter + Quant-leakage + telemetry tests |

### Expected unchanged

| Path | Note |
|---|---|
| `package.json` / `package-lock.json` | Only `@typesafe-ai/sdk` `0.6.0` |
| `config/season_jev.json` | `provider=typesafe_direct`, `model=jev-latest`, `enabled=false` |
| `src/kr_quant/research/season_jev_budget.py` | No change |
| `scripts/jev-season-shadow.mjs` | Direct runner remains |
| `scripts/jev/season-shadow-typesafe-adapter.mjs` | Unchanged |

### Fixed interfaces

OpenRouter transport export (exact):

```js
export async function postOpenRouterDecision({
  state,
  questions,
  model,
  apiKey,
  fetchImpl = fetch,
  signal,
})
```

OpenRouter `evaluateFn` / `postOpenRouterDecision` return shape (exact):

```js
{
  model: data.model ?? null,
  answers: data.answers ?? {},
  usage: data.usage ?? {},
  providerMetadata: {
    openrouter: {
      provider: data.provider ?? null,
      cost: typeof data.cost === "number"
        ? data.cost
        : typeof data.usage?.cost === "number"
          ? data.usage.cost
          : null,
      requestId: data.id ?? data.request_id ?? null,
    },
  },
}
```

Shared-core telemetry helper (exact):

```js
export function extractProviderTelemetry(result, provider) {
  if (provider !== "openrouter") {
    return {
      providerName: null,
      cost: null,
      requestId: null,
    };
  }
  const meta = result?.providerMetadata?.openrouter || {};
  return {
    providerName: meta.provider ?? null,
    cost: typeof meta.cost === "number" ? meta.cost : null,
    requestId: meta.requestId ?? null,
  };
}
```

`evaluateCandidates()` success row must include:

```js
provider_name: telemetry.providerName,
cost: telemetry.cost,
request_id: telemetry.requestId,
```

Persisted optional Python fields (when present):

```text
provider_name
cost
request_id
```

Missing values stay `null`. Direct must not invent `cost=0`.

### Model IDs (exact)

```text
TypeSafe Direct default requested model: jev-latest
OpenRouter production requested model: typesafe/jev-1.13
OpenRouter floating upgrade alias: ~typesafe/jev-latest  (TEMP smoke only)
```

### Whitelist-valid minimal state fixture (exact; reuse everywhere needed)

```js
const state = { identity: { ticker: "TEST000" } };
```

```python
state = {"identity": {"ticker": "TEST000"}}
shadow.assert_state_clean(state)
```

---

### Task 1: Python provider contract + key routing + OpenRouter model policy

**Files:**
- Create: none
- Modify: `src/kr_quant/research/season_jev_shadow.py`, `tests/unit/test_season_jev_shadow.py`
- Test: `tests/unit/test_season_jev_shadow.py`

**Interfaces:**
- Consumes: `cfg["provider"]`, `cfg["model"]`, env `TYPESAFE_API_KEY`, env `OPENROUTER_API_KEY`
- Produces: `SUPPORTED_PROVIDERS={"typesafe_direct","openrouter"}`; `PROVIDER_RUNNERS["openrouter"]="scripts/jev-season-shadow-openrouter.mjs"`; `provider_key(cfg)` selected-provider only; `requested_model(cfg)` fail-closed for OpenRouter

- [ ] **Step 1: Write the failing tests**

```python
def test_provider_name_accepts_openrouter():
    assert shadow.provider_name({"provider": "openrouter"}) == "openrouter"


def test_provider_runner_path_selects_openrouter_script(tmp_path):
    s = _settings(tmp_path)
    path = shadow.provider_runner_path(s, {"provider": "openrouter"})
    assert path == Path(s.root) / "scripts" / "jev-season-shadow-openrouter.mjs"


def test_provider_key_routes_selected_provider_only(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setenv("OPENROUTER_API_KEY", "or-only")
    assert shadow.provider_key({"provider": "openrouter"}) == "or-only"
    assert shadow.provider_key({"provider": "typesafe_direct"}) is None

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-only")
    assert shadow.provider_key({"provider": "typesafe_direct"}) == "ts-only"
    assert shadow.provider_key({"provider": "openrouter"}) is None


def test_openrouter_missing_key_does_not_fallback_to_typesafe(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "direct-must-not-run")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []


def test_typesafe_missing_key_does_not_fallback_to_openrouter(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-must-not-run")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []


def test_provider_name_rejects_vercel_gateway():
    with pytest.raises(ValueError, match=r"UNSUPPORTED_JEV_PROVIDER:vercel_gateway"):
        shadow.provider_name({"provider": "vercel_gateway"})


def test_openrouter_requires_pinned_production_model():
    with pytest.raises(
        ValueError,
        match=r"UNSUPPORTED_JEV_MODEL:openrouter:jev-latest",
    ):
        shadow.requested_model({
            "provider": "openrouter",
            "model": "jev-latest",
        })


def test_openrouter_accepts_pinned_production_model():
    assert shadow.requested_model({
        "provider": "openrouter",
        "model": "typesafe/jev-1.13",
    }) == "typesafe/jev-1.13"


def test_invalid_openrouter_model_never_runs_node(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "jev-latest"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    ran = []
    monkeypatch.setattr(shadow, "run_node", lambda *a, **k: ran.append(1) or {})
    out = shadow.evaluate_generation(s, _bundle())
    assert out is None
    assert ran == []
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py -q --tb=line -k "openrouter or provider_key_routes or typesafe_missing_key_does_not_fallback or provider_name_rejects_vercel or invalid_openrouter_model"
```

Set `PYTHONPATH=<worktree>\src` when using the shared venv.

Expected: RED because `openrouter` is unsupported and `requested_model()` helper is missing.

- [ ] **Step 3: Write minimal implementation**

```python
SUPPORTED_PROVIDERS = frozenset({"typesafe_direct", "openrouter"})
PROVIDER_RUNNERS = {
    "typesafe_direct": "scripts/jev-season-shadow.mjs",
    "openrouter": "scripts/jev-season-shadow-openrouter.mjs",
}

def provider_key(cfg: dict[str, Any] | None = None) -> str | None:
    name = provider_name(cfg)
    env_name = "OPENROUTER_API_KEY" if name == "openrouter" else "TYPESAFE_API_KEY"
    value = (os.environ.get(env_name) or "").strip()
    return value or None

def requested_model(cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or {}
    provider = provider_name(cfg)
    model = str(cfg.get("model") or DEFAULTS["model"]).strip()
    if provider == "openrouter":
        if model != "typesafe/jev-1.13":
            raise ValueError(f"UNSUPPORTED_JEV_MODEL:{provider}:{model}")
        return model
    return model or "jev-latest"
```

Use `requested_model(cfg)` consistently in `has_shadow`, `collect_candidates`, `evaluate_generation`, and `state_hash`/`reuse_key` call sites. Catch invalid-model `ValueError` in `evaluate_generation`/`request_shadow_evaluation` the same way unsupported providers are skipped/contained, without calling `run_node`.

Do not create the OpenRouter runner file in this Task. Do not change `config/season_jev.json`.

- [ ] **Step 4: Run test to verify it passes**

Same pytest `-k` command as Step 2. Expected: PASS.

- [ ] **Step 5: Run related regression**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py tests/unit/test_season_jev_budget.py -q --tb=line
```

Expected: all pass.

- [ ] **Step 6: Review diff**

```powershell
git diff --check
git diff --stat
```

- [ ] **Step 7: Commit**

```powershell
git add src/kr_quant/research/season_jev_shadow.py
git add tests/unit/test_season_jev_shadow.py
git commit -m "feat(jev): add openrouter provider routing"
```

---

### Task 2: Shared core provider-neutral evaluator + telemetry passthrough

**Files:**
- Create: none
- Modify: `scripts/jev/season-shadow-core.mjs`, `tests/js/jev_season_shadow.test.mjs`
- Test: `tests/js/jev_season_shadow.test.mjs`

**Interfaces:**
- Consumes: `options.provider` ∈ {`typesafe_direct`,`openrouter`}, `options.questions`, `options.evaluateFn`, `result.providerMetadata`
- Produces: unified result rows with optional `provider_name`/`cost`/`request_id`; rejects `vercel_gateway`

- [ ] **Step 1: Write the failing tests**

```js
import assert from "node:assert/strict";
import test from "node:test";
import {
  evaluateCandidates,
  normalizeAnswers,
} from "../../scripts/jev/season-shadow-core.mjs";
import { buildTypeSafeQuestions } from "../../scripts/jev/season-shadow-typesafe-adapter.mjs";

const state = { identity: { ticker: "TEST000" } };

function evalOpts(extra = {}) {
  return { questions: buildTypeSafeQuestions(), provider: "typesafe_direct", ...extra };
}

test("evaluateCandidates accepts openrouter with shared noul normalization", async () => {
  const output = await evaluateCandidates(
    [{ id: "x", candidate_type: "season_pattern", ticker: "TEST000", state, state_hash: "h" }],
    evalOpts({
      provider: "openrouter",
      evaluateFn: async () => ({
        model: "typesafe/jev-1.13-20260917",
        answers: {
          materialNow: { type: "noul", noul: 0.42 },
          reviewClass: {
            type: "choice",
            choice: "monitor",
            probabilities: { monitor: 0.7 },
            confidence: 0.7,
          },
        },
        usage: { input_tokens: 3, output_tokens: 2 },
      }),
    }),
  );
  assert.equal(output.results[0].provider, "openrouter");
  assert.equal(output.results[0].answers.materialNow.type, "boolean");
  assert.equal(output.results[0].answers.materialNow.probability, 0.42);
  assert.equal(output.results[0].answers.reviewClass.type, "choice");
  assert.equal(output.results[0].answers.reviewClass.choice, "monitor");
});

test("evaluateCandidates preserves optional openrouter telemetry", async () => {
  const output = await evaluateCandidates(
    [{
      id: "x",
      candidate_type: "season_pattern",
      ticker: "TEST000",
      state,
      state_hash: "h",
    }],
    {
      provider: "openrouter",
      questions: buildTypeSafeQuestions(),
      evaluateFn: async () => ({
        model: "typesafe/jev-1.13-20260917",
        answers: {
          materialNow: { type: "noul", noul: 0.2 },
        },
        usage: { input_tokens: 10, output_tokens: 4 },
        providerMetadata: {
          openrouter: {
            provider: "TypeSafe",
            cost: 0.0001,
            requestId: "gen-test",
          },
        },
      }),
    },
  );
  const rec = output.results[0];
  assert.equal(rec.provider_name, "TypeSafe");
  assert.equal(rec.cost, 0.0001);
  assert.equal(rec.request_id, "gen-test");
});

test("evaluateCandidates missing openrouter telemetry stays null", async () => {
  const output = await evaluateCandidates(
    [{
      id: "x",
      candidate_type: "season_pattern",
      ticker: "TEST000",
      state,
      state_hash: "h",
    }],
    {
      provider: "openrouter",
      questions: buildTypeSafeQuestions(),
      evaluateFn: async () => ({
        model: "typesafe/jev-1.13-20260917",
        answers: { materialNow: { type: "noul", noul: 0.1 } },
        usage: {},
      }),
    },
  );
  const rec = output.results[0];
  assert.equal(rec.provider_name, null);
  assert.equal(rec.cost, null);
  assert.equal(rec.request_id, null);
});

test("evaluateCandidates rejects vercel_gateway as unsupported provider", async () => {
  await assert.rejects(
    () =>
      evaluateCandidates(
        [{ id: "x", candidate_type: "season_pattern", ticker: "TEST000", state, state_hash: "h" }],
        evalOpts({ provider: "vercel_gateway", evaluateFn: async () => ({ answers: {} }) }),
      ),
    /UNSUPPORTED_EVAL_PROVIDER:vercel_gateway/,
  );
});

test("evaluateCandidates rejects quantReference before evaluateFn for openrouter", async () => {
  let called = 0;
  const output = await evaluateCandidates(
    [{
      id: "x",
      candidate_type: "season_pattern",
      ticker: "TEST000",
      state,
      state_hash: "h",
      quantReference: { grade: "A" },
    }],
    {
      provider: "openrouter",
      questions: buildTypeSafeQuestions(),
      evaluateFn: async () => {
        called += 1;
        throw new Error("FETCH_MUST_NOT_RUN");
      },
    },
  );
  assert.equal(called, 0);
  assert.equal(output.results.length, 0);
  assert.equal(output.errors[0].error, "QUANT_REFERENCE_IN_EVALUATE_INPUT");
});
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
node --test tests/js/jev_season_shadow.test.mjs
```

Expected: RED on openrouter accept and/or telemetry fields missing from result assembly.

- [ ] **Step 3: Write minimal implementation**

Allowlist:

```js
if (provider !== "typesafe_direct" && provider !== "openrouter") {
  throw new Error(`UNSUPPORTED_EVAL_PROVIDER:${provider}`);
}
```

Add `extractProviderTelemetry` as specified above. In success result assembly:

```js
const telemetry = extractProviderTelemetry(result, provider);
return {
  id: candidate.id,
  candidate_type: candidate.candidate_type,
  ticker: candidate.ticker,
  state_hash: candidate.state_hash,
  provider,
  answers,
  usage: {
    inputTokens: meta.inputTokens,
    outputTokens: meta.outputTokens,
    totalTokens: meta.totalTokens,
  },
  requested_model: requestedModel,
  resolved_model: result?.model ?? null,
  provider_name: telemetry.providerName,
  cost: telemetry.cost,
  request_id: telemetry.requestId,
  typesafe_confidence: answers.reviewClass?.confidence ?? null,
  wall_latency_ms: nowFn() - started,
};
```

Keep existing Direct fields. `null` for missing telemetry. Never force `cost: 0`.

- [ ] **Step 4: Run test to verify it passes**

```powershell
node --test tests/js/jev_season_shadow.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Run related regression**

```powershell
node --check scripts/jev/season-shadow-core.mjs
node --check scripts/jev-season-shadow.mjs
```

Expected: exit 0.

- [ ] **Step 6: Review diff**

Confirm no OpenRouter transport code.

- [ ] **Step 7: Commit**

```powershell
git add scripts/jev/season-shadow-core.mjs
git add tests/js/jev_season_shadow.test.mjs
git commit -m "refactor(jev): make shadow core provider neutral"
```

---

### Task 3: OpenRouter adapter + transport runner

**Files:**
- Create: `scripts/jev/season-shadow-openrouter-adapter.mjs`, `scripts/jev-season-shadow-openrouter.mjs`, `tests/js/jev_season_openrouter.test.mjs`
- Modify: none
- Test: `tests/js/jev_season_openrouter.test.mjs`

**Interfaces:**
- Consumes: stdin payload `provider="openrouter"`, `requested_model`/`model`, candidates; env `OPENROUTER_API_KEY`; `QUESTION_SPECS`
- Produces: stdout unified JSON including optional telemetry; stderr sanitized via `logErr`

- [ ] **Step 1: Write the failing tests**

```js
import assert from "node:assert/strict";
import test from "node:test";
import { evaluateCandidates, QUESTION_SPECS } from "../../scripts/jev/season-shadow-core.mjs";
import {
  buildOpenRouterQuestions,
  postOpenRouterDecision,
} from "../../scripts/jev/season-shadow-openrouter-adapter.mjs";

const state = { identity: { ticker: "TEST000" } };

test("buildOpenRouterQuestions maps QUESTION_SPECS to noul/choice without inventing ids", () => {
  const qs = buildOpenRouterQuestions();
  assert.deepEqual(Object.keys(qs), Object.keys(QUESTION_SPECS));
  for (const id of Object.keys(QUESTION_SPECS)) {
    if (QUESTION_SPECS[id].kind === "boolean") {
      assert.equal(qs[id].type, "noul");
      assert.equal(qs[id].instructions, QUESTION_SPECS[id].instructions);
    }
  }
  assert.equal(qs.reviewClass.type, "choice");
  assert.deepEqual(
    Object.keys(qs.reviewClass.criteria),
    Object.keys(QUESTION_SPECS.reviewClass.criteria),
  );
});

test("postOpenRouterDecision posts exact decisions contract via mocked fetch", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          id: "gen-test",
          model: "typesafe/jev-1.13-20260917",
          provider: "TypeSafe",
          answers: {
            materialNow: { type: "noul", noul: 0.2 },
            reviewClass: {
              type: "choice",
              choice: "monitor",
              confidence: 0.5,
              probabilities: { monitor: 0.5 },
            },
          },
          usage: { input_tokens: 10, output_tokens: 4 },
          cost: 0.0001,
        }),
    };
  };
  const result = await postOpenRouterDecision({
    state,
    questions: buildOpenRouterQuestions(),
    model: "typesafe/jev-1.13",
    apiKey: "test-key-not-for-logging",
    fetchImpl,
    signal: AbortSignal.timeout(1000),
  });
  assert.equal(calls[0].url, "https://openrouter.ai/api/alpha/decisions");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, "Bearer test-key-not-for-logging");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.model, "typesafe/jev-1.13");
  assert.deepEqual(body.state, state);
  assert.deepEqual(Object.keys(body.questions), Object.keys(QUESTION_SPECS));
  assert.equal(result.model, "typesafe/jev-1.13-20260917");
  assert.equal(result.providerMetadata.openrouter.provider, "TypeSafe");
  assert.equal(result.providerMetadata.openrouter.cost, 0.0001);
  assert.equal(result.providerMetadata.openrouter.requestId, "gen-test");
});

test("postOpenRouterDecision maps missing usage/cost to null semantics", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () =>
      JSON.stringify({
        model: "typesafe/jev-1.13-20260917",
        answers: { materialNow: { type: "noul", noul: 0.1 } },
      }),
  });
  const result = await postOpenRouterDecision({
    state,
    questions: buildOpenRouterQuestions(),
    model: "typesafe/jev-1.13",
    apiKey: "k",
    fetchImpl,
  });
  assert.deepEqual(result.usage, {});
  assert.equal(result.providerMetadata.openrouter.cost, null);
});

test("postOpenRouterDecision sanitizes non-200 without including body", async () => {
  await assert.rejects(
    () =>
      postOpenRouterDecision({
        state,
        questions: buildOpenRouterQuestions(),
        model: "typesafe/jev-1.13",
        apiKey: "k",
        fetchImpl: async () => ({
          ok: false,
          status: 401,
          text: async () => "unauthorized secret=abc",
        }),
      }),
    (err) => {
      assert.match(String(err.message), /OPENROUTER_HTTP_401/);
      assert.equal(String(err.message).includes("secret=abc"), false);
      assert.equal(String(err.message).includes("unauthorized"), false);
      return true;
    },
  );
});

test("postOpenRouterDecision rejects invalid JSON", async () => {
  await assert.rejects(
    () =>
      postOpenRouterDecision({
        state,
        questions: buildOpenRouterQuestions(),
        model: "typesafe/jev-1.13",
        apiKey: "k",
        fetchImpl: async () => ({
          ok: true,
          status: 200,
          text: async () => "{not-json",
        }),
      }),
    /OPENROUTER_BAD_JSON/,
  );
});

test("postOpenRouterDecision forwards AbortSignal and does not retry", async () => {
  let calls = 0;
  const controller = new AbortController();
  const fetchImpl = async (_url, init) => {
    calls += 1;
    assert.equal(init.signal, controller.signal);
    throw new Error("abort-me");
  };
  await assert.rejects(
    () =>
      postOpenRouterDecision({
        state,
        questions: buildOpenRouterQuestions(),
        model: "typesafe/jev-1.13",
        apiKey: "k",
        fetchImpl,
        signal: controller.signal,
      }),
    /abort-me/,
  );
  assert.equal(calls, 1);
});

test("openrouter path rejects quantReference before fetch", async () => {
  let called = 0;
  const output = await evaluateCandidates(
    [{
      id: "x",
      candidate_type: "season_pattern",
      ticker: "TEST000",
      state,
      state_hash: "h",
      quantReference: { grade: "A" },
    }],
    {
      provider: "openrouter",
      questions: buildOpenRouterQuestions(),
      evaluateFn: async () => {
        called += 1;
        throw new Error("FETCH_MUST_NOT_RUN");
      },
    },
  );
  assert.equal(called, 0);
  assert.equal(output.results.length, 0);
  assert.equal(output.errors[0].error, "QUANT_REFERENCE_IN_EVALUATE_INPUT");
});

test("evaluateCandidates preserves openrouter telemetry from postOpenRouterDecision shape", async () => {
  const output = await evaluateCandidates(
    [{
      id: "x",
      candidate_type: "season_pattern",
      ticker: "TEST000",
      state,
      state_hash: "h",
    }],
    {
      provider: "openrouter",
      questions: buildOpenRouterQuestions(),
      evaluateFn: async () => ({
        model: "typesafe/jev-1.13-20260917",
        answers: { materialNow: { type: "noul", noul: 0.2 } },
        usage: { input_tokens: 10, output_tokens: 4 },
        providerMetadata: {
          openrouter: {
            provider: "TypeSafe",
            cost: 0.0001,
            requestId: "gen-test",
          },
        },
      }),
    },
  );
  const rec = output.results[0];
  assert.equal(rec.provider_name, "TypeSafe");
  assert.equal(rec.cost, 0.0001);
  assert.equal(rec.request_id, "gen-test");
});
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
node --test tests/js/jev_season_openrouter.test.mjs
```

Expected: `ERR_MODULE_NOT_FOUND` for adapter exports.

- [ ] **Step 3: Write minimal implementation**

`scripts/jev/season-shadow-openrouter-adapter.mjs`:

```js
import { QUESTION_SPECS } from "./season-shadow-core.mjs";

export function buildOpenRouterQuestions() {
  const out = {};
  for (const [id, spec] of Object.entries(QUESTION_SPECS)) {
    if (spec.kind === "boolean") {
      out[id] = { type: "noul", instructions: spec.instructions };
      continue;
    }
    if (spec.kind === "choice") {
      out[id] = {
        type: "choice",
        instructions: spec.instructions,
        criteria: spec.criteria,
      };
      continue;
    }
    throw new Error(`UNSUPPORTED_QUESTION_KIND:${spec.kind}`);
  }
  return out;
}

export async function postOpenRouterDecision({
  state,
  questions,
  model,
  apiKey,
  fetchImpl = fetch,
  signal,
}) {
  const response = await fetchImpl("https://openrouter.ai/api/alpha/decisions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model, state, questions }),
    signal,
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`OPENROUTER_HTTP_${response.status}`);
  }
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("OPENROUTER_BAD_JSON");
  }
  return {
    model: data.model ?? null,
    answers: data.answers ?? {},
    usage: data.usage ?? {},
    providerMetadata: {
      openrouter: {
        provider: data.provider ?? null,
        cost:
          typeof data.cost === "number"
            ? data.cost
            : typeof data.usage?.cost === "number"
              ? data.usage.cost
              : null,
        requestId: data.id ?? data.request_id ?? null,
      },
    },
  };
}
```

`scripts/jev-season-shadow-openrouter.mjs`:

```js
import { evaluateCandidates } from "./jev/season-shadow-core.mjs";
import {
  buildOpenRouterQuestions,
  postOpenRouterDecision,
} from "./jev/season-shadow-openrouter-adapter.mjs";

function logErr(message) {
  process.stderr.write(`${message}\n`);
}

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
let payload;
try {
  payload = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
} catch {
  logErr("INVALID_JSON_STDIN");
  process.exit(2);
}
if (payload.provider !== "openrouter") {
  logErr(`UNSUPPORTED_PROVIDER:${payload.provider}`);
  process.exit(2);
}
const apiKey = (process.env.OPENROUTER_API_KEY || "").trim();
if (!apiKey) {
  logErr("OPENROUTER_API_KEY missing");
  process.exit(2);
}
const requestedModel = payload.requested_model || payload.model || "typesafe/jev-1.13";
const questions = buildOpenRouterQuestions();
try {
  const output = await evaluateCandidates(payload.candidates || [], {
    provider: "openrouter",
    requestedModel,
    questions,
    concurrency: payload.concurrency ?? 1,
    candidateTimeoutMs: payload.candidate_timeout_ms ?? 8000,
    softDeadlineMs: payload.process_soft_deadline_ms ?? 170000,
    startCutoffMs: payload.process_start_cutoff_ms ?? 160000,
    maxApiCalls: payload.max_api_calls_per_generation ?? Infinity,
    evaluateFn: async ({ state, signal }) =>
      postOpenRouterDecision({
        state,
        questions,
        model: requestedModel,
        apiKey,
        signal,
      }),
  });
  process.stdout.write(`${JSON.stringify(output)}\n`);
} catch (error) {
  logErr(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
```

Never print API key values or raw response bodies. No retries. No forced `process.exit(0)`.

- [ ] **Step 4: Run test to verify it passes**

```powershell
node --test tests/js/jev_season_openrouter.test.mjs
node --check scripts/jev-season-shadow-openrouter.mjs
node --check scripts/jev/season-shadow-openrouter-adapter.mjs
```

Expected: exit 0.

- [ ] **Step 5: Run related regression**

```powershell
node --test tests/js/jev_season_shadow.test.mjs tests/js/jev_season_openrouter.test.mjs
```

Expected: all pass.

- [ ] **Step 6: Review diff**

Confirm no `package.json` changes and no live network calls in unit tests.

- [ ] **Step 7: Commit**

```powershell
git add scripts/jev/season-shadow-openrouter-adapter.mjs
git add scripts/jev-season-shadow-openrouter.mjs
git add tests/js/jev_season_openrouter.test.mjs
git commit -m "feat(jev): add openrouter decision runner"
```

---

### Task 4: Python persistence / cache / telemetry integration

**Files:**
- Create: none
- Modify: `src/kr_quant/research/season_jev_shadow.py`, `tests/unit/test_season_jev_shadow.py`
- Test: `tests/unit/test_season_jev_shadow.py`

**Interfaces:**
- Consumes: OpenRouter runner stdout unified schema including optional `provider_name`/`cost`/`request_id` produced by Task 2 core
- Produces: persisted shadow records; exact NODE_EXIT failure contract

- [ ] **Step 1: Write the failing tests**

```python
def test_openrouter_generated_record_stores_provider(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])

    def runner(settings, payload, timeout):
        assert payload["provider"] == "openrouter"
        assert payload.get("requested_model") == "typesafe/jev-1.13" or payload.get("model") == "typesafe/jev-1.13"
        item = payload["candidates"][0]
        return {
            "provider": "openrouter",
            "requested_model": "typesafe/jev-1.13",
            "results": [{
                "id": item["id"],
                "candidate_type": item["candidate_type"],
                "ticker": item["ticker"],
                "state_hash": item["state_hash"],
                "provider": "openrouter",
                "answers": _complete_answers(),
                "usage": {"inputTokens": 2, "outputTokens": 2, "totalTokens": 4},
                "requested_model": "typesafe/jev-1.13",
                "resolved_model": "typesafe/jev-1.13-20260917",
                "wall_latency_ms": 9,
                "provider_name": "TypeSafe",
                "cost": 0.0001,
                "request_id": "gen-test",
            }],
            "errors": [],
            "total_usage": {"inputTokens": 2, "outputTokens": 2, "totalTokens": 4},
        }

    out = shadow.evaluate_generation(s, _bundle(), runner=runner)
    assert out["provider"] == "openrouter"
    assert out["requested_model"] == "typesafe/jev-1.13"
    assert out["resolved_models"] == ["typesafe/jev-1.13-20260917"]
    rec = out["results"][0]
    assert rec["provider"] == "openrouter"
    assert rec["resolved_model"] == "typesafe/jev-1.13-20260917"
    assert rec.get("provider_name") == "TypeSafe"
    assert rec.get("cost") == 0.0001
    assert rec.get("request_id") == "gen-test"


def test_state_hash_differs_by_provider_and_requested_model():
    state = {"identity": {"ticker": "TEST000"}}
    shadow.assert_state_clean(state)
    h_direct = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="typesafe_direct",
        requested_model="jev-latest",
    )
    h_or = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="openrouter",
        requested_model="typesafe/jev-1.13",
    )
    h_or_latest = shadow.state_hash(
        state,
        "season-jev-shadow-v1",
        provider="openrouter",
        requested_model="~typesafe/jev-latest",
    )
    assert h_direct != h_or
    assert h_or != h_or_latest


def test_reuse_index_never_crosses_provider(tmp_path):
    s = _settings(tmp_path)
    gen = "gen-test"
    cfg = {"provider": "typesafe_direct", "model": "jev-latest", "evaluator_version": "season-jev-shadow-v1"}
    path = shadow.shadow_path(s, gen, "openrouter")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "generation_id": gen,
        "provider": "openrouter",
        "requested_model": "typesafe/jev-1.13",
        "evaluator_version": "season-jev-shadow-v1",
        "status": "COMPLETE",
    }), encoding="utf-8")
    assert shadow.has_shadow(s, gen, cfg) is False


def test_run_node_nonzero_exit_is_failure(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    scripts = Path(s.root) / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "jev-season-shadow-openrouter.mjs").write_text("", encoding="utf-8")
    monkeypatch.setattr(shadow.shutil, "which", lambda name: "node")

    class Completed:
        returncode = 1
        stdout = '{"results":[{"id":"x"}],"errors":[],"provider":"openrouter"}'
        stderr = "UV_HANDLE_CLOSING"

    monkeypatch.setattr(shadow.subprocess, "run", lambda *a, **k: Completed())
    with pytest.raises(RuntimeError, match=r"NODE_EXIT_1"):
        shadow.run_node(s, {"provider": "openrouter", "candidates": []}, timeout=5)


def test_openrouter_failure_does_not_mutate_quant_bundle(tmp_path, monkeypatch):
    s = _settings(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or")
    cfg_path = Path(s.root) / "config" / "season_jev.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["provider"] = "openrouter"
    cfg["model"] = "typesafe/jev-1.13"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(shadow, "source_identity", lambda *a, **k: _bundle()["identity"])
    monkeypatch.setattr(shadow, "collect_candidates", lambda *a, **k: [_cand(0)])
    monkeypatch.setattr(
        shadow,
        "run_node",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("NODE_EXIT_1")),
    )
    before = copy.deepcopy(_bundle())
    bundle = _bundle()
    out = shadow.evaluate_generation(s, bundle)
    assert out["status"] == "ERROR"
    assert out["errors"] == [{"error": "RUNNER:RuntimeError"}]
    assert bundle == before
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py -q --tb=line -k "openrouter_generated or state_hash_differs_by_provider or never_crosses_provider or run_node_nonzero or openrouter_failure_does_not_mutate"
```

Expected: RED until persistence/telemetry/error-contract wiring is complete.

- [ ] **Step 3: Write minimal implementation**

- Persist optional `provider_name`/`cost`/`request_id` when present on result objects; otherwise store `null` / omit without forcing Direct zeros.
- Keep `run_node` raising `RuntimeError(f"NODE_EXIT_{completed.returncode}")` on non-zero even if stdout parses.
- Ensure `evaluate_generation` maps that RuntimeError into the exact stored ERROR contract above without mutating the Quant bundle.
- Keep `state_hash` / `reuse_key` including provider + requested_model via `requested_model(cfg)`.

- [ ] **Step 4: Run test to verify it passes**

Same pytest `-k` as Step 2 → PASS.

- [ ] **Step 5: Run related regression**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py tests/unit/test_season_jev_budget.py -q --tb=line
```

Expected: all pass; `season_jev_budget.py` unchanged.

- [ ] **Step 6: Review diff**

Confirm `config/season_jev.json` and `package.json` untouched.

- [ ] **Step 7: Commit**

```powershell
git add src/kr_quant/research/season_jev_shadow.py
git add tests/unit/test_season_jev_shadow.py
git commit -m "feat(jev): persist openrouter shadow metadata"
```

---

### Task 5: Full regression + fail-closed safety

**Files:**
- Create: none
- Modify: none unless a regression failure forces a minimal fix discovered by this gate
- Test: JS + Python suites below

**Interfaces:**
- Consumes: branch after Tasks 1–4
- Produces: fresh pass evidence

- [ ] **Step 1: Confirm package/config invariants**

```powershell
Get-Content package.json
Get-Content config\season_jev.json
```

Expected:

```text
package.json dependencies: only @typesafe-ai/sdk 0.6.0
config: enabled=false, provider=typesafe_direct, model=jev-latest
```

- [ ] **Step 2: JS regression**

```powershell
node --test tests/js/jev_season_shadow.test.mjs tests/js/jev_season_openrouter.test.mjs
node --check scripts/jev-season-shadow.mjs
node --check scripts/jev-season-shadow-openrouter.mjs
```

Expected: exit 0.

- [ ] **Step 3: Python JEV regression**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest tests/unit/test_season_jev_shadow.py tests/unit/test_season_jev_budget.py -q --tb=line
```

Expected: exit 0.

- [ ] **Step 4: Full pytest**

```powershell
C:\Users\a4jud\kr_quant_research\.venv\Scripts\python.exe -m pytest -q --tb=short
```

Expected: 0 failed. If season fixture pollution appears in isolated worktree, use TEMP mirror cleanup only; never edit main lake.

- [ ] **Step 5: Diff hygiene + Vercel/package verification**

```powershell
git diff --check
git status --short

$prodHits = Get-ChildItem scripts,src -Recurse -File |
  Select-String -Pattern 'vercel_gateway|@ai-sdk/gateway'

if ($prodHits) {
  $prodHits
  throw "VERCEL_PRODUCTION_CODE_REINTRODUCED"
}

$pkg = Get-Content package.json -Raw | ConvertFrom-Json
$deps = @($pkg.dependencies.PSObject.Properties.Name)

if ($deps.Count -ne 1 -or $deps[0] -ne '@typesafe-ai/sdk') {
  $deps
  throw "UNEXPECTED_NODE_DEPENDENCIES"
}
```

Tests may still contain the literal `vercel_gateway` to prove fail-closed behavior.

- [ ] **Step 6: Commit only if a minimal test-only fix was required**

Otherwise no commit. Do not create cosmetic commits.

---

### Task 6: Real dual-provider smoke + final validation

**Files:**
- Create: TEMP-only smoke artifacts under `%TEMP%`
- Modify: none in repo
- Test: live smoke evidence + invariance

**Interfaces:**
- Consumes: `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` (PRESENT/MISSING only)
- Produces: smoke report fields; no git changes

- [ ] **Step 1: Key presence with exact User-scope refresh**

```powershell
if ([string]::IsNullOrWhiteSpace($env:TYPESAFE_API_KEY)) {
  $env:TYPESAFE_API_KEY =
    [Environment]::GetEnvironmentVariable("TYPESAFE_API_KEY", "User")
}

if ([string]::IsNullOrWhiteSpace($env:OPENROUTER_API_KEY)) {
  $env:OPENROUTER_API_KEY =
    [Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY", "User")
}

$hasDirect = -not [string]::IsNullOrWhiteSpace($env:TYPESAFE_API_KEY)
$hasOr = -not [string]::IsNullOrWhiteSpace($env:OPENROUTER_API_KEY)

"TYPE_SAFE_KEY=" + $(if ($hasDirect) {"PRESENT"} else {"MISSING"})
"OPENROUTER_KEY=" + $(if ($hasOr) {"PRESENT"} else {"MISSING"})
```

Never print values. Missing provider → `SKIPPED_NO_KEY` for that provider only.

- [ ] **Step 2: Build one production-shaped state outside repo**

TEMP Python helper using `project_season_state` + `assert_state_clean`. Candidate id `JEV-OR-IMPL-SMOKE-001`. Confirm forbidden Quant fields absent.

- [ ] **Step 3: Direct smoke (if key PRESENT)**

```powershell
# payload provider=typesafe_direct, requested_model=jev-latest
Get-Content <temp>\typesafe_direct.payload.json -Raw |
  node scripts/jev-season-shadow.mjs 1> <temp>\direct.out.json 2> <temp>\direct.err.txt
```

Require exit 0, 7 booleans valid, reviewClass valid, concrete resolved model, state_hash match.

- [ ] **Step 4: OpenRouter pinned smoke (if key PRESENT)**

```powershell
# payload provider=openrouter, requested_model=typesafe/jev-1.13
Get-Content <temp>\openrouter.payload.json -Raw |
  node scripts/jev-season-shadow-openrouter.mjs 1> <temp>\openrouter.out.json 2> <temp>\openrouter.err.txt
```

Require exit 0 and optional telemetry fields present or null. If non-zero (including intermittent UV assert), record failure evidence; do not add workaround code.

- [ ] **Step 5: Optional upgrade alias comparison only**

Only after pinned success, optional one TEMP call with `~typesafe/jev-latest`. Not a production smoke gate and not allowed via normal production config path.

- [ ] **Step 6: Invariance**

```powershell
git status --short
Get-FileHash config\season_jev.json -Algorithm SHA256
```

Require clean tracked tree relative to implementation commits, config hash unchanged, `enabled=false`, smoke files only under `%TEMP%`.

- [ ] **Step 7: Whole-branch code review before claiming complete**

```text
BASE_SHA = implementation-start commit (the corrected plan commit)
HEAD_SHA = final implementation branch HEAD
```

Review the exact implementation diff `BASE_SHA...HEAD_SHA`. The final execution report must resolve both to concrete SHAs.

Do not declare foundation complete until Tasks 1–6 evidence exists.

No commit for this Task unless a prior Task left an unfinished required code fix.

---

## Verification order (branch completion)

1. OpenRouter JS tests (`tests/js/jev_season_openrouter.test.mjs`)
2. Shared JEV JS tests (`tests/js/jev_season_shadow.test.mjs`)
3. Python JEV unit tests (`test_season_jev_shadow.py`)
4. Budget tests (`test_season_jev_budget.py`) — expected untouched
5. Full pytest
6. `git diff --check`
7. `git status`
8. Live Direct smoke if key PRESENT
9. Live OpenRouter pinned smoke if key PRESENT
10. Quant/config invariance check
11. Whole branch code review over `BASE_SHA...HEAD_SHA`

Completion claims require fresh evidence after the above.

---

## Spec coverage map

| Spec section | Covered by |
|---|---|
| 1 Scope | Global Constraints + Tasks 1–6 |
| 2 Existing State | File Structure + Task 2/5 |
| 3 Approved Architecture | Tasks 1–3 |
| 4 Provider Contracts | Tasks 1, 3, 6 |
| 5 Model Identity | Tasks 1, 4, 6 |
| 6 Adapter Boundary | Task 3 |
| 7 Unified Output | Tasks 2–4 |
| 8 No Automatic Fallback | Tasks 1, 4 |
| 9 Calibration Isolation | Task 4 + Constraints |
| 10 UV policy | Task 4 NODE_EXIT + Task 6 |
| 11 Security | Tasks 1, 3, 6 |
| 12 Budget | Task 5 unchanged budget file |
| 13 Testing Strategy | Tasks 1–6 |
| 14 File Map | File Structure |
| 15 Non-Goals | Global Constraints |
| 16 Definition of Done | Verification order |

## Review Focus → tests

| Focus | Test steps |
|---|---|
| 1 Key isolation | Task 1 key routing + missing-key no-fallback tests |
| 2 Non-zero exit | Task 4 `test_run_node_nonzero_exit_is_failure` + exact ERROR contract |
| 3 Cache/model isolation | Task 1 invalid-model fail-closed; Task 4 hash/reuse tests |
| 4 Missing usage/cost + telemetry | Task 2/3 evaluateCandidates telemetry tests; Task 3 missing usage/cost |
| 5 Forbidden Quant leakage | Task 2/3 quantReference rejection before fetch |

## Self-review checklist

- [x] No deferred-work placeholders in task steps
- [x] Exact fixtures and exact exported interfaces
- [x] Complete Quant leakage test present
- [x] Telemetry survives JS core into runner stdout
- [x] Python persists telemetry only after real runner/core can produce it
- [x] Invalid OpenRouter model fails closed before transport
- [x] Latest alias not allowed in normal production config path
- [x] Runner sanitized catch present
- [x] Exact NODE_EXIT failure contract present
- [x] Corrected Vercel/package verification command present
- [x] Exact User-env key refresh present
- [x] Whole-branch review range defined
- [x] J2 still excluded
- [x] Config remains enabled=false / Direct default
