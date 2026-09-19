import { evaluateCandidates } from "./jev/season-shadow-core.mjs";
import {
  buildOpenRouterQuestions,
  postOpenRouterDecision,
} from "./jev/season-shadow-openrouter-adapter.mjs";

async function readStdin() {
  const chunks = [];

  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  return Buffer.concat(chunks).toString("utf8");
}

function logErr(message) {
  process.stderr.write(`${message}\n`);
}

const raw = await readStdin();

let payload;

try {
  payload = JSON.parse(raw || "{}");
} catch {
  logErr("INVALID_STDIN_JSON");
  process.exit(2);
}

if (payload.provider !== "openrouter") {
  logErr("UNSUPPORTED_PROVIDER");
  process.exit(2);
}

const apiKey =
  (process.env.OPENROUTER_API_KEY || "").trim();

if (!apiKey) {
  logErr("OPENROUTER_API_KEY missing");
  process.exit(2);
}

const requestedModel =
  payload.requested_model ||
  payload.model ||
  "typesafe/jev-1.13";

const questions = buildOpenRouterQuestions();

try {
  const output = await evaluateCandidates(
    payload.candidates || [],
    {
      provider: "openrouter",
      requestedModel,
      questions,
      concurrency: payload.concurrency,
      candidateTimeoutMs:
        payload.candidate_timeout_ms,
      startCutoffMs:
        payload.process_start_cutoff_ms,
      softDeadlineMs:
        payload.process_soft_deadline_ms,
      maxApiCalls:
        payload.max_api_calls_per_generation,

      evaluateFn: ({
        state,
        questions: qs,
        signal,
        model,
      }) =>
        postOpenRouterDecision({
          state,
          questions: qs,
          model,
          apiKey,
          signal,
        }),
    },
  );

  process.stdout.write(
    `${JSON.stringify(output)}\n`,
  );
} catch (error) {
  logErr(
    error instanceof Error
      ? error.message
      : String(error),
  );

  process.exit(1);
}
