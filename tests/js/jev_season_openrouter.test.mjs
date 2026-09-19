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
  assert.equal(
    qs.reviewClass.instructions,
    QUESTION_SPECS.reviewClass.instructions,
  );
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
          usage: {
            input_tokens: 10,
            output_tokens: 4,
          },
          cost: 0.0001,
        }),
    };
  };

  const controller = new AbortController();

  const result = await postOpenRouterDecision({
    state,
    questions: buildOpenRouterQuestions(),
    model: "typesafe/jev-1.13",
    apiKey: "test-key-not-for-logging",
    fetchImpl,
    signal: controller.signal,
  });

  assert.equal(calls.length, 1);
  assert.equal(
    calls[0].url,
    "https://openrouter.ai/api/alpha/decisions",
  );
  assert.equal(calls[0].init.method, "POST");
  assert.equal(
    calls[0].init.headers.Authorization,
    "Bearer test-key-not-for-logging",
  );
  assert.equal(
    calls[0].init.headers["Content-Type"],
    "application/json",
  );
  assert.equal(calls[0].init.signal, controller.signal);

  const body = JSON.parse(calls[0].init.body);

  assert.deepEqual(
    Object.keys(body).sort(),
    ["model", "questions", "state"].sort(),
  );
  assert.equal(body.model, "typesafe/jev-1.13");
  assert.deepEqual(body.state, state);
  assert.deepEqual(
    Object.keys(body.questions),
    Object.keys(QUESTION_SPECS),
  );

  assert.equal(result.model, "typesafe/jev-1.13-20260917");
  assert.equal(result.providerMetadata.openrouter.provider, "TypeSafe");
  assert.equal(result.providerMetadata.openrouter.cost, 0.0001);
  assert.equal(result.providerMetadata.openrouter.requestId, "gen-test");
  assert.equal(result.usage.input_tokens, 10);
  assert.equal(result.usage.output_tokens, 4);
});

test("postOpenRouterDecision accepts cost from usage.cost", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () =>
      JSON.stringify({
        id: "gen-usage-cost",
        model: "typesafe/jev-1.13-20260917",
        provider: "TypeSafe",
        answers: {},
        usage: {
          input_tokens: 10,
          output_tokens: 4,
          cost: 0.0002,
        },
      }),
  });

  const result = await postOpenRouterDecision({
    state,
    questions: buildOpenRouterQuestions(),
    model: "typesafe/jev-1.13",
    apiKey: "k",
    fetchImpl,
  });

  assert.equal(result.providerMetadata.openrouter.cost, 0.0002);
});

test("postOpenRouterDecision keeps missing optional fields null-safe", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    text: async () =>
      JSON.stringify({
        model: "typesafe/jev-1.13-20260917",
        answers: {
          materialNow: {
            type: "noul",
            noul: 0.1,
          },
        },
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
  assert.equal(result.providerMetadata.openrouter.provider, null);
  assert.equal(result.providerMetadata.openrouter.cost, null);
  assert.equal(result.providerMetadata.openrouter.requestId, null);
});

test("postOpenRouterDecision sanitizes non-200 without exposing response body", async () => {
  await assert.rejects(
    () =>
      postOpenRouterDecision({
        state,
        questions: buildOpenRouterQuestions(),
        model: "typesafe/jev-1.13",
        apiKey: "SECRET_KEY_MUST_NOT_APPEAR",
        fetchImpl: async () => ({
          ok: false,
          status: 401,
          text: async () =>
            "unauthorized SECRET_KEY_MUST_NOT_APPEAR raw-provider-body",
        }),
      }),
    (error) => {
      const message =
        error instanceof Error ? error.message : String(error);

      assert.equal(message, "OPENROUTER_HTTP_401");
      assert.equal(message.includes("SECRET_KEY_MUST_NOT_APPEAR"), false);
      assert.equal(message.includes("raw-provider-body"), false);

      return true;
    },
  );
});

test("postOpenRouterDecision rejects invalid JSON with sanitized code", async () => {
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
          text: async () => "{not-json SECRET",
        }),
      }),
    (error) => {
      const message =
        error instanceof Error ? error.message : String(error);

      assert.equal(message, "OPENROUTER_BAD_JSON");
      assert.equal(message.includes("SECRET"), false);

      return true;
    },
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

test("openrouter path rejects quantReference before evaluateFn", async () => {
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
      requestedModel: "typesafe/jev-1.13",
      evaluateFn: async () => {
        called += 1;
        throw new Error("FETCH_MUST_NOT_RUN");
      },
    },
  );

  assert.equal(called, 0);
  assert.equal(output.results.length, 0);
  assert.equal(
    output.errors[0].error,
    "QUANT_REFERENCE_IN_EVALUATE_INPUT",
  );
});

test("evaluateCandidates preserves openrouter telemetry from adapter shape", async () => {
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
      requestedModel: "typesafe/jev-1.13",
      evaluateFn: async () => ({
        model: "typesafe/jev-1.13-20260917",
        answers: {
          materialNow: {
            type: "noul",
            noul: 0.2,
          },
        },
        usage: {
          input_tokens: 10,
          output_tokens: 4,
        },
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

  assert.equal(rec.provider, "openrouter");
  assert.equal(rec.requested_model, "typesafe/jev-1.13");
  assert.equal(
    rec.resolved_model,
    "typesafe/jev-1.13-20260917",
  );
  assert.equal(rec.provider_name, "TypeSafe");
  assert.equal(rec.cost, 0.0001);
  assert.equal(rec.request_id, "gen-test");
});
