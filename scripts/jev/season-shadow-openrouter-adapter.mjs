import { QUESTION_SPECS } from "./season-shadow-core.mjs";

export function buildOpenRouterQuestions() {
  const out = {};

  for (const [id, spec] of Object.entries(QUESTION_SPECS)) {
    if (spec.kind === "boolean") {
      out[id] = {
        type: "noul",
        instructions: spec.instructions,
      };
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
  const response = await fetchImpl(
    "https://openrouter.ai/api/alpha/decisions",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        state,
        questions,
      }),
      signal,
    },
  );

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
        requestId:
          data.id ??
          data.request_id ??
          null,
      },
    },
  };
}
