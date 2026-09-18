export const ECG_TEACHING_QUESTIONS = Object.freeze([
  {
    id: "raw-preservation",
    prompt: "When studying what filtering changes, which signal should remain available unchanged?",
    options: [
      "Only the filtered trace",
      "The original raw digital recording",
      "A screenshot of the ECG",
      "Only the R-peak locations"
    ],
    answer: 1,
    explanation: "The original digital samples are the reference. Filtering can create a new view, but it should not overwrite the source recording."
  },
  {
    id: "sample-time",
    prompt: "This ECG-ID record is sampled at 500 Hz. How much time does one sample represent?",
    options: ["0.5 ms", "1 ms", "2 ms", "5 ms"],
    answer: 2,
    explanation: "500 samples per second means 1000/500 = 2 ms per sample."
  },
  {
    id: "relative-amplitude",
    prompt: "Why does this OPL teaching view report vertical measurements as ΔADC rather than automatically calling them millivolts?",
    options: [
      "ECG has no voltage information",
      "ADC values can never be measured",
      "Relative digital amplitude is valid, but absolute input-referred mV needs a justified physical calibration",
      "Millivolts are only used for EEG"
    ],
    answer: 2,
    explanation: "The digitized geometry is useful for teaching and within-trace measurement. An absolute mV claim needs a documented physical conversion."
  },
  {
    id: "boxes",
    prompt: "If the vertical small-box scale is 50 ΔADC and a wave rises 8 small boxes above the selected baseline, what is the relative amplitude?",
    options: ["+100 ΔADC", "+200 ΔADC", "+400 ΔADC", "+800 ΔADC"],
    answer: 2,
    explanation: "8 × 50 ΔADC = +400 ΔADC relative to the selected baseline."
  },
  {
    id: "source-filtered",
    prompt: "In this first ECG-ID lab, what does “source filtered” mean?",
    options: [
      "Filtered by your phone",
      "Filtered by OPL after loading",
      "A filtered channel supplied by the original ECG-ID dataset",
      "A clinically corrected diagnostic ECG"
    ],
    answer: 2,
    explanation: "OPL keeps the dataset-provided filtered channel distinct from any future OPL filtering algorithm."
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
