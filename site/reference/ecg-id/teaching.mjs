export const ECG_TEACHING_QUESTIONS = Object.freeze([
  {
    id: "ideal-purpose",
    prompt: "Why does OPL begin with an idealized ECG before showing the real recording?",
    options: [
      "Because synthetic ECG is more biologically accurate than real ECG",
      "To make the notation, baseline and measurement ruler unambiguous before introducing biological uncertainty",
      "Because real ECG cannot be measured",
      "To replace the need for real reference data"
    ],
    answer: 1,
    explanation: "The ideal trace is a teaching model. It establishes what P-Q-R-S-T notation and a measurement mean; validation still comes from real reference data."
  },
  {
    id: "sample-time",
    prompt: "A 500 Hz ECG has how much time between consecutive samples?",
    options: ["0.5 ms", "1 ms", "2 ms", "5 ms"],
    answer: 2,
    explanation: "500 samples per second means 1000/500 = 2 ms per sample."
  },
  {
    id: "baseline-uncertain",
    prompt: "In a real trace, the baseline wanders enough that no local isoelectric reference can be defended. What should OPL do?",
    options: [
      "Choose zero automatically and report amplitude anyway",
      "Smooth the trace until the baseline looks flat",
      "Withhold the vertical amplitude claim while retaining defensible time measurements",
      "Discard all timing information including R–R intervals"
    ],
    answer: 2,
    explanation: "Uncertainty is part of the result. A doubtful baseline invalidates the specific vertical reference assumption; it does not automatically invalidate sample timing."
  },
  {
    id: "rr-baseline-wander",
    prompt: "Can R–R timing remain useful when slow baseline wander is present?",
    options: [
      "Never",
      "Yes, if R peaks remain reliably identifiable and beat detection itself has been validated",
      "Yes, regardless of whether R peaks can be detected",
      "Only after converting the signal to absolute millivolts"
    ],
    answer: 1,
    explanation: "HRV is fundamentally a beat-timing problem. Baseline drift may complicate morphology/amplitude while R-peak timing can remain usable if detection is reliable."
  },
  {
    id: "source-filtered",
    prompt: "In the ECG-ID view, what does “source filtered” mean?",
    options: [
      "Filtered by the phone",
      "Filtered by OPL after loading",
      "A filtered channel supplied by the original ECG-ID dataset",
      "A clinically corrected diagnostic ECG"
    ],
    answer: 2,
    explanation: "OPL keeps the dataset-provided filtered channel distinct from the raw channel and from any future OPL filtering algorithm."
  }
]);

export function scoreQuiz(responses, questions = ECG_TEACHING_QUESTIONS) {
  let correct = 0;
  for (const question of questions) {
    if (responses?.[question.id] === question.answer) correct += 1;
  }
  return {correct, total: questions.length};
}

export function evaluateAnswer(question, optionIndex) {
  if (!question) throw new Error("question is required");
  if (!Number.isInteger(optionIndex)) throw new Error("optionIndex must be an integer");
  return {
    correct: optionIndex === question.answer,
    explanation: question.explanation
  };
}
