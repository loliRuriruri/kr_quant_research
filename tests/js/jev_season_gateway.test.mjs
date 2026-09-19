import assert from "node:assert/strict";
import test from "node:test";
import {
  NOUL_HEADS,
  QUESTION_SPECS,
  REVIEW_CLASS_OPTIONS,
  normalizeAnswers,
} from "../../scripts/jev/season-shadow-core.mjs";
import { buildGatewayQuestions } from "../../scripts/jev/season-shadow-gateway-adapter.mjs";

test("gateway questions share QUESTION_SPECS identities", () => {
  const qs = buildGatewayQuestions();
  assert.deepEqual(Object.keys(qs), Object.keys(QUESTION_SPECS));
  for (const id of NOUL_HEADS) {
    assert.equal(qs[id].type, "boolean");
    assert.equal(qs[id].instructions, QUESTION_SPECS[id].instructions);
  }
  assert.equal(qs.reviewClass.type, "choice");
  assert.equal(qs.reviewClass.instructions, QUESTION_SPECS.reviewClass.instructions);
  assert.deepEqual(Object.keys(qs.reviewClass.criteria), REVIEW_CLASS_OPTIONS);
  assert.deepEqual(qs.reviewClass.criteria, QUESTION_SPECS.reviewClass.criteria);
});

test("gateway adapter does not invent extra question ids", () => {
  const qs = buildGatewayQuestions();
  assert.equal(Object.keys(qs).length, Object.keys(QUESTION_SPECS).length);
});

test("gateway raw boolean normalizes to unified schema", () => {
  const answers = normalizeAnswers({ materialNow: { type: "boolean", probability: 0.72 } });
  assert.deepEqual(answers.materialNow, {
    type: "boolean",
    probability: 0.72,
    decision: true,
  });
});
