import test from "node:test";
import assert from "node:assert/strict";
import {ECG_TEACHING_QUESTIONS, evaluateAnswer, scoreQuiz} from "../reference/ecg-id/teaching.mjs";

test("teaching question bank has stable unique ids", () => {
  assert.equal(ECG_TEACHING_QUESTIONS.length, 5);
  assert.equal(new Set(ECG_TEACHING_QUESTIONS.map(q => q.id)).size, ECG_TEACHING_QUESTIONS.length);
});

test("each teaching question has one valid answer", () => {
  for (const question of ECG_TEACHING_QUESTIONS) {
    assert.ok(question.options.length >= 2);
    assert.ok(Number.isInteger(question.answer));
    assert.ok(question.answer >= 0 && question.answer < question.options.length);
    assert.ok(question.explanation.length > 10);
  }
});

test("quiz scoring and feedback are deterministic", () => {
  const responses = Object.fromEntries(ECG_TEACHING_QUESTIONS.map(q => [q.id, q.answer]));
  assert.deepEqual(scoreQuiz(responses), {correct: 5, total: 5});
  const q = ECG_TEACHING_QUESTIONS[0];
  assert.equal(evaluateAnswer(q, q.answer).correct, true);
  assert.equal(evaluateAnswer(q, (q.answer + 1) % q.options.length).correct, false);
});
