import assert from "node:assert/strict";
import test from "node:test";
import {
  NOUL_HEADS,
  QUESTION_SPECS,
  REVIEW_CLASS_OPTIONS,
  assertStateWhitelist,
  evaluateCandidates,
  extractUsage,
  normalizeAnswers,
} from "../../scripts/jev/season-shadow-core.mjs";
import { buildTypeSafeQuestions } from "../../scripts/jev/season-shadow-typesafe-adapter.mjs";

function evalOpts(extra = {}) {
  return { questions: buildTypeSafeQuestions(), provider: "typesafe_direct", ...extra };
}

test("seven noul heads and reviewClass choice options", () => {
  assert.deepEqual(NOUL_HEADS, [
    "materialNow",
    "needsCurrentYearCheck",
    "needsNews",
    "needsDart",
    "historicalConflict",
    "invalidationCheckNeeded",
    "needsDeepAI",
  ]);
  assert.deepEqual(REVIEW_CLASS_OPTIONS, [
    "no_action",
    "monitor",
    "verify_sources",
    "revalidate_thesis",
    "deep_review",
  ]);
});

test("quantReference is rejected as evaluate state", () => {
  assert.throws(() => assertStateWhitelist({ identity: { ticker: "005930" }, quantReference: { grade: "A" } }));
  assert.throws(() => assertStateWhitelist({ grade: "A" }));
});

test("noul adapter preserves probability", () => {
  const answers = normalizeAnswers({
    materialNow: { type: "noul", noul: 0.72 },
    reviewClass: { type: "choice", choice: "monitor", probabilities: { monitor: 1 }, confidence: 0.81 },
  });
  assert.equal(answers.materialNow.probability, 0.72);
  assert.equal(answers.materialNow.decision, true);
  assert.equal(answers.reviewClass.choice, "monitor");
  assert.equal(answers.reviewClass.confidence, 0.81);
});

test("evaluateCandidates keeps other workers after one failure", async () => {
  const seen = [];
  const output = await evaluateCandidates(
    [
      { id: "a", candidate_type: "season_pattern", ticker: "1", state: { identity: { ticker: "1" } }, state_hash: "h1" },
      { id: "b", candidate_type: "season_pattern", ticker: "2", state: { identity: { ticker: "2" } }, state_hash: "h2" },
      { id: "c", candidate_type: "season_pattern", ticker: "3", state: { identity: { ticker: "3" } }, state_hash: "h3" },
    ],
    evalOpts({
      concurrency: 2,
      candidateTimeoutMs: 1000,
      requestedModel: "jev-latest",
      evaluateFn: async ({ state, signal, timeout, retry, model }) => {
        seen.push(state.identity.ticker);
        assert.equal(model, "jev-latest");
        assert.equal(retry.maxRetries, 0);
        assert.ok(signal);
        assert.equal(typeof timeout, "number");
        if (state.identity.ticker === "2") throw new Error("boom");
        return {
          model: "jev-1.13.0",
          answers: { materialNow: { type: "noul", noul: 0.7 } },
          usage: { input_tokens: 1, output_tokens: 1 },
        };
      },
    }),
  );
  assert.equal(output.results.length, 2);
  assert.equal(output.errors.length, 1);
  assert.equal(output.results[0].resolved_model, "jev-1.13.0");
  assert.equal(output.results[0].requested_model, "jev-latest");
  assert.equal(output.results[0].answers.materialNow.probability, 0.7);
});

test("quantReference must not be passed into evaluateFn", async () => {
  let called = 0;
  const output = await evaluateCandidates(
    [{ id: "x", state: { identity: {} }, quantReference: { grade: "A" } }],
    evalOpts({ evaluateFn: async () => { called += 1; return { answers: {} }; } }),
  );
  assert.equal(called, 0);
  assert.equal(output.errors[0].error, "QUANT_REFERENCE_IN_EVALUATE_INPUT");
});

test("usage maps input_tokens", () => {
  const meta = extractUsage({ usage: { input_tokens: 11, output_tokens: 3 } });
  assert.equal(meta.inputTokens, 11);
  assert.equal(meta.outputTokens, 3);
});

test("soft deadline stops starting new candidates and keeps finished ones", async () => {
  const started = [];
  const output = await evaluateCandidates(
    [
      { id: "a", candidate_type: "season_pattern", ticker: "1", state: { identity: { ticker: "1" } }, state_hash: "h1" },
      { id: "b", candidate_type: "season_pattern", ticker: "2", state: { identity: { ticker: "2" } }, state_hash: "h2" },
      { id: "c", candidate_type: "season_pattern", ticker: "3", state: { identity: { ticker: "3" } }, state_hash: "h3" },
    ],
    evalOpts({
      concurrency: 1,
      candidateTimeoutMs: 1000,
      startCutoffMs: 25,
      softDeadlineMs: 80,
      evaluateFn: async ({ state, retry }) => {
        assert.equal(retry.maxRetries, 0);
        started.push(state.identity.ticker);
        await new Promise((resolve) => setTimeout(resolve, 40));
        return { model: "jev-latest", answers: { materialNow: { type: "noul", noul: 0.6 } } };
      },
    }),
  );
  assert.ok(started.length >= 1);
  assert.ok(started.length < 3);
  assert.equal(output.results.length, started.length);
  assert.ok(output.errors.some((item) => item.error === "SOFT_DEADLINE_NOT_STARTED"));
  assert.equal(output.results.length + output.errors.length, 3);
});


test("QUESTION_SPECS is provider-neutral source of truth", () => {
  assert.deepEqual(Object.keys(QUESTION_SPECS), [
    ...NOUL_HEADS,
    "reviewClass",
  ]);
  for (const id of NOUL_HEADS) {
    assert.equal(QUESTION_SPECS[id].kind, "boolean");
    assert.equal(typeof QUESTION_SPECS[id].instructions, "string");
    assert.ok(QUESTION_SPECS[id].instructions.length > 0);
  }
  assert.equal(QUESTION_SPECS.reviewClass.kind, "choice");
  assert.equal(
    QUESTION_SPECS.reviewClass.instructions,
    "Which research-attention class fits this candidate now?",
  );
  assert.deepEqual(Object.keys(QUESTION_SPECS.reviewClass.criteria), REVIEW_CLASS_OPTIONS);
  assert.deepEqual(REVIEW_CLASS_OPTIONS, [
    "no_action",
    "monitor",
    "verify_sources",
    "revalidate_thesis",
    "deep_review",
  ]);
});

test("typesafe adapter builds from QUESTION_SPECS", () => {
  const qs = buildTypeSafeQuestions();
  assert.deepEqual(Object.keys(qs), Object.keys(QUESTION_SPECS));
  for (const id of NOUL_HEADS) {
    assert.ok(qs[id]);
  }
  assert.ok(qs.reviewClass);
});


test("gateway boolean shape normalizes like direct noul", () => {
  const direct = normalizeAnswers({ materialNow: { type: "noul", noul: 0.72 } });
  const gateway = normalizeAnswers({ materialNow: { type: "boolean", probability: 0.72 } });
  assert.deepEqual(direct.materialNow, {
    type: "boolean",
    probability: 0.72,
    decision: true,
  });
  assert.deepEqual(gateway.materialNow, direct.materialNow);
});

test("choice confidence falls back to providerMetadata typesafe map", () => {
  const answers = normalizeAnswers(
    { reviewClass: { type: "choice", choice: "monitor", probabilities: { monitor: 1 } } },
    { typesafe: { confidence: { reviewClass: 0.81 } } },
  );
  assert.equal(answers.reviewClass.confidence, 0.81);
});

test("missing usage stays null and totals become null when any row misses", async () => {
  const output = await evaluateCandidates(
    [
      { id: "a", candidate_type: "season_pattern", ticker: "1", state: { identity: { ticker: "1" } }, state_hash: "h1" },
      { id: "b", candidate_type: "season_pattern", ticker: "2", state: { identity: { ticker: "2" } }, state_hash: "h2" },
    ],
    evalOpts({
      concurrency: 1,
      evaluateFn: async ({ state }) => {
        if (state.identity.ticker === "1") {
          return {
            model: "jev-1",
            answers: { materialNow: { type: "boolean", probability: 0.6 } },
            usage: { inputTokens: 2, outputTokens: 3, totalTokens: 5 },
          };
        }
        return {
          model: "jev-1",
          answers: { materialNow: { type: "boolean", probability: 0.4 } },
          usage: {},
        };
      },
    }),
  );
  assert.equal(output.provider, "typesafe_direct");
  assert.equal(output.results[0].provider, "typesafe_direct");
  assert.equal(output.results[0].usage.inputTokens, 2);
  assert.equal(output.results[1].usage.inputTokens, null);
  assert.equal(output.total_usage.inputTokens, null);
  assert.equal(output.total_usage.outputTokens, null);
  assert.equal(output.total_usage.totalTokens, null);
});


test("choice with numeric probability stays choice", () => {
  const answers = normalizeAnswers({
    reviewClass: {
      type: "choice",
      choice: "monitor",
      probability: 0.81,
      probabilities: { monitor: 0.81 },
      confidence: 0.81,
    },
  });
  assert.equal(answers.reviewClass.type, "choice");
  assert.equal(answers.reviewClass.choice, "monitor");
  assert.equal(answers.reviewClass.probability, 0.81);
});

test("evaluateCandidates rejects vercel_gateway as unsupported provider", async () => {
  await assert.rejects(
    () =>
      evaluateCandidates(
        [{ id: "x", candidate_type: "season_pattern", ticker: "TEST000", state: {}, state_hash: "h" }],
        evalOpts({ provider: "vercel_gateway", evaluateFn: async () => ({ answers: {} }) }),
      ),
    /UNSUPPORTED_EVAL_PROVIDER:vercel_gateway/,
  );
});
