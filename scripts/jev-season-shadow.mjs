import { TypeSafeClient } from "@typesafe-ai/sdk";
import { evaluateCandidates, buildTypeSafeQuestions } from "./jev/season-shadow-core.mjs";

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

function logErr(message) {
  process.stderr.write(`${message}\n`);
}

const raw = await readStdin();
let payload;
try {
  payload = JSON.parse(raw);
} catch {
  logErr("INVALID_STDIN_JSON");
  process.exit(2);
}

if ((payload.provider || "typesafe_direct") !== "typesafe_direct") {
  logErr("UNSUPPORTED_PROVIDER");
  process.exit(2);
}

const requestedModel = payload.requested_model || payload.model || "jev-latest";
const client = new TypeSafeClient({ defaultModel: requestedModel, retry: { maxRetries: 0 } });
const questions = buildTypeSafeQuestions();

try {
  const output = await evaluateCandidates(payload.candidates || [], {
    evaluateFn: ({ state, questions: qs, signal, timeout, retry, model }) =>
      client.systemOne(
        { state, questions: qs, model },
        { signal, timeout, retry },
      ),
    questions,
    concurrency: payload.concurrency,
    candidateTimeoutMs: payload.candidate_timeout_ms,
    startCutoffMs: payload.process_start_cutoff_ms,
    softDeadlineMs: payload.process_soft_deadline_ms,
    requestedModel,
    maxApiCalls: payload.max_api_calls_per_generation,
  });
  process.stdout.write(`${JSON.stringify(output)}\n`);
} catch (error) {
  logErr(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
