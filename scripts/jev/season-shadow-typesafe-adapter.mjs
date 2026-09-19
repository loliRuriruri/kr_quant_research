import { noul, choice } from "@typesafe-ai/sdk";
import { QUESTION_SPECS } from "./season-shadow-core.mjs";

export function buildTypeSafeQuestions() {
  const out = {};
  for (const [id, spec] of Object.entries(QUESTION_SPECS)) {
    if (spec.kind === "boolean") {
      out[id] = noul(spec.instructions);
    } else if (spec.kind === "choice") {
      out[id] = choice(spec.instructions, spec.criteria);
    } else {
      throw new Error(`UNSUPPORTED_QUESTION_KIND:${spec.kind}`);
    }
  }
  return out;
}
