export const QUESTION_SPECS = {
  materialNow: {
    kind: "boolean",
    instructions:
      "Based only on the supplied evidence, is this candidate materially relevant for current research attention? This is NOT a prediction of price direction or investment return.",
  },
  needsCurrentYearCheck: {
    kind: "boolean",
    instructions:
      "Does this thesis materially depend on current-year facts such as event timing, product schedules, regulation, policy, business status, index eligibility, conference dates, earnings timing, or other facts that may differ from historical years?",
  },
  needsNews: {
    kind: "boolean",
    instructions:
      "Would checking recent reliable news materially reduce uncertainty about whether the supplied seasonal or event thesis is currently valid?",
  },
  needsDart: {
    kind: "boolean",
    instructions:
      "Would checking current Korean DART filings materially help confirm, invalidate, or update this thesis?",
  },
  historicalConflict: {
    kind: "boolean",
    instructions:
      "Does the supplied current evidence or known failure history materially conflict with the historical seasonal/event thesis?",
  },
  invalidationCheckNeeded: {
    kind: "boolean",
    instructions:
      "Is there enough uncertainty or contrary evidence that the stated invalidation conditions should be checked now?",
  },
  needsDeepAI: {
    kind: "boolean",
    instructions:
      "After deterministic evidence and source verification, is this case complex enough that deeper analytical synthesis by a stronger LLM would likely add material value?",
  },
  reviewClass: {
    kind: "choice",
    instructions: "Which research-attention class fits this candidate now?",
    criteria: {
      no_action: "The supplied evidence is sufficient and no additional research is currently warranted.",
      monitor: "The candidate is worth monitoring but does not currently require source verification or deep analysis.",
      verify_sources: "Fresh news, filings, schedules, or other primary/secondary sources should be checked.",
      revalidate_thesis:
        "Current evidence materially conflicts with the historical seasonal or event thesis and the thesis should be revalidated.",
      deep_review:
        "Multiple interacting uncertainties make deeper analytical synthesis worthwhile after source verification.",
    },
  },
};

export const NOUL_HEADS = Object.keys(QUESTION_SPECS).filter((id) => QUESTION_SPECS[id].kind === "boolean");
export const REVIEW_CLASS_OPTIONS = Object.keys(QUESTION_SPECS.reviewClass.criteria);

const FORBIDDEN = new Set(["pre_entry_rank", "grade", "seasonality_score", "score_breakdown"]);

export function assertStateWhitelist(state) {
  const stack = [state];
  while (stack.length) {
    const value = stack.pop();
    if (!value || typeof value !== "object") continue;
    for (const [key, child] of Object.entries(value)) {
      if (FORBIDDEN.has(key) || key === "quantReference" || key === "quant_reference") {
        throw new Error(`FORBIDDEN_STATE_FIELD:${key}`);
      }
      if (child && typeof child === "object") stack.push(child);
    }
  }
}

export function extractUsage(result) {
  const usage = result?.usage || {};
  return {
    inputTokens: usage.inputTokens ?? usage.input_tokens ?? null,
    outputTokens: usage.outputTokens ?? usage.output_tokens ?? null,
    totalTokens: usage.totalTokens ?? usage.total_tokens ?? null,
  };
}

export function normalizeAnswers(answers, providerMetadata = null) {
  const out = {};
  const confMap =
    providerMetadata && typeof providerMetadata === "object"
      ? providerMetadata.typesafe?.confidence || providerMetadata.typesafe?.confidences || null
      : null;
  for (const [key, value] of Object.entries(answers || {})) {
    if (!value || typeof value !== "object") continue;
    if (typeof value.noul === "number" || value.type === "noul") {
      const probability = value.noul;
      out[key] = {
        type: "boolean",
        probability,
        decision: typeof probability === "number" ? probability >= 0.5 : null,
      };
      continue;
    }
    if (value.type === "boolean") {
      const probability = typeof value.probability === "number" ? value.probability : null;
      out[key] = {
        type: "boolean",
        probability,
        decision: typeof probability === "number" ? probability >= 0.5 : null,
      };
      continue;
    }
    let confidence = value.confidence ?? null;
    if (confidence == null && confMap && typeof confMap === "object" && key in confMap) {
      confidence = confMap[key];
    }
    out[key] = {
      type: value.type || "choice",
      probability: value.probability ?? null,
      choice: value.choice ?? null,
      probabilities: value.probabilities ?? null,
      confidence,
    };
  }
  return out;
}

export function aggregateUsage(rows) {
  if (!rows.length) {
    return { inputTokens: null, outputTokens: null, totalTokens: null };
  }
  const fields = ["inputTokens", "outputTokens", "totalTokens"];
  const out = {};
  for (const field of fields) {
    const values = rows.map((row) => row?.usage?.[field]);
    if (values.some((v) => typeof v !== "number")) {
      out[field] = null;
    } else {
      out[field] = values.reduce((a, b) => a + b, 0);
    }
  }
  return out;
}

export async function runPool(items, concurrency, worker, hooks = {}) {
  const limit = Math.max(1, Number(concurrency) || 1);
  const results = new Array(items.length);
  let cursor = 0;
  async function pump() {
    while (true) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      const item = items[index];
      if (hooks.shouldStart && !hooks.shouldStart(item, index)) {
        results[index] = { ok: false, error: "SOFT_DEADLINE_NOT_STARTED", id: item?.id };
        continue;
      }
      try {
        results[index] = { ok: true, value: await worker(item, index) };
      } catch (error) {
        results[index] = {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
          id: item?.id,
        };
      }
    }
  }
  const workers = Array.from({ length: Math.min(limit, Math.max(items.length, 1)) }, () => pump());
  await Promise.all(workers);
  return results;
}

function withTimeout(promise, ms) {
  const timeoutMs = Math.max(1, Number(ms) || 8000);
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("CANDIDATE_TIMEOUT")), timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

export async function evaluateCandidates(candidates, options = {}) {
  const evaluateFn = options.evaluateFn;
  if (typeof evaluateFn !== "function") {
    throw new Error("EVALUATE_FN_REQUIRED");
  }
  const concurrency = options.concurrency ?? 4;
  const timeoutMs = options.candidateTimeoutMs ?? 8000;
  const requestedModel = options.requestedModel || options.model || "jev-latest";
  const nowFn = options.now || Date.now;
  const startedAt = nowFn();
  const startCutoffAt = startedAt + Number(options.startCutoffMs ?? 160000);
  const finalizeAt = startedAt + Number(options.softDeadlineMs ?? 170000);
  const questions = options.questions;
  if (!questions || typeof questions !== "object") {
    throw new Error("QUESTIONS_REQUIRED");
  }
  const provider = options.provider;
  if (provider !== "typesafe_direct" && provider !== "vercel_gateway") {
    throw new Error(`UNSUPPORTED_EVAL_PROVIDER:${provider}`);
  }
  const maxApiCalls = options.maxApiCalls == null ? Infinity : Number(options.maxApiCalls);
  let apiStarted = 0;

  const pooled = await runPool(
    candidates,
    concurrency,
    async (candidate) => {
      if (candidate?.quantReference != null || candidate?.quant_reference != null) {
        throw new Error("QUANT_REFERENCE_IN_EVALUATE_INPUT");
      }
      const remaining = finalizeAt - nowFn();
      if (remaining <= 0) {
        throw new Error("SOFT_DEADLINE");
      }
      if (apiStarted >= maxApiCalls) {
        throw new Error("API_CAP_GENERATION");
      }
      const state = candidate.state;
      assertStateWhitelist(state);
      const started = nowFn();
      apiStarted += 1;
      const slice = Math.min(timeoutMs, Math.max(1, remaining));
      const controller = new AbortController();
      const abortTimer = setTimeout(() => controller.abort(), slice);
      try {
        const result = await withTimeout(
          evaluateFn({
            model: requestedModel,
            state,
            questions,
            signal: controller.signal,
            timeout: slice,
            retry: { maxRetries: 0 },
          }),
          slice,
        );
        const meta = extractUsage(result);
        const answers = normalizeAnswers(result?.answers, result?.providerMetadata);
        const provider = options.provider;
        if (provider !== "typesafe_direct" && provider !== "vercel_gateway") {
          throw new Error(`UNSUPPORTED_EVAL_PROVIDER:${provider}`);
        }
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
          typesafe_confidence: answers.reviewClass?.confidence ?? null,
          wall_latency_ms: nowFn() - started,
        };
      } finally {
        clearTimeout(abortTimer);
      }
    },
    { shouldStart: () => nowFn() < startCutoffAt },
  );

  const results = [];
  const errors = [];
  for (const item of pooled) {
    if (item.ok) {
      results.push(item.value);
    } else {
      errors.push({ id: item.id, error: item.error });
    }
  }
  return {
    provider,
    results,
    errors,
    total_usage: aggregateUsage(results),
    requested_model: requestedModel,
  };
}
