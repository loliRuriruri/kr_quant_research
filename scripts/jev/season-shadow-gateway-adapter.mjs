import { QUESTION_SPECS } from "./season-shadow-core.mjs";

export function buildGatewayQuestions() {
  const out = {};
  for (const [id, spec] of Object.entries(QUESTION_SPECS)) {
    if (spec.kind === "boolean") {
      out[id] = {
        type: "boolean",
        instructions: spec.instructions,
      };
    } else if (spec.kind === "choice") {
      out[id] = {
        type: "choice",
        instructions: spec.instructions,
        criteria: spec.criteria,
      };
    } else {
      throw new Error(`UNSUPPORTED_QUESTION_KIND:${spec.kind}`);
    }
  }
  return out;
}
