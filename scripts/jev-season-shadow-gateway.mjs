import { gateway } from "@ai-sdk/gateway";
import { experimental_evaluate as evaluate } from "ai";
import { evaluateCandidates } from "./jev/season-shadow-core.mjs";
import { buildGatewayQuestions } from "./jev/season-shadow-gateway-adapter.mjs";

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function logErr(message) {
  process.stderr.write(`${message}` + "\n");
}

const raw = await readStdin();
let payload;
try {
  payload = JSON.parse(raw);
} catch {
  logErr("INVALID_STDIN_JSON");
  process.exit(2);
}

if (payload.provider !== "vercel_gateway") {
  logErr("UNSUPPORTED_PROVIDER");
  process.exit(2);
}

const requestedModel = payload.requested_model || payload.model || "jev-latest";
const model = gateway.evaluationModel("typesafe-ai/jev-latest");
const questions = buildGatewayQuestions();

try {
  const output = await evaluateCandidates(payload.candidates || [], {
    provider: "vercel_gateway",
    evaluateFn: async ({ state, questions: qs, signal }) => {
      const result = await evaluate({
        model,
        state,
        questions: qs,
        maxRetries: 0,
        abortSignal: signal,
      });
      return {
        model: result.response?.modelId ?? null,
        answers: result.answers,
        usage: result.usage,
        providerMetadata: result.providerMetadata,
      };
    },
    questions,
    concurrency: payload.concurrency,
    candidateTimeoutMs: payload.candidate_timeout_ms,
    startCutoffMs: payload.process_start_cutoff_ms,
    softDeadlineMs: payload.process_soft_deadline_ms,
    requestedModel,
    maxApiCalls: payload.max_api_calls_per_generation,
  });
  process.stdout.write(`${JSON.stringify(output)}` + "\n");
} catch (error) {
  logErr(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
