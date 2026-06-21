\# Analogue to Digital ECG



\## OpenPhysiologyLab v0.1-alpha Walkthrough



This walkthrough explains OpenPhysiologyLab using the language of the classical physiology laboratory: electrodes, amplifier, baseline, gain, timebase, noise, clipping, and recording paper.



The aim is to connect the older analogue way of thinking with the newer digital workflow.



OpenPhysiologyLab v0.1-alpha is a teaching and research prototype. It is not a diagnostic ECG machine.



\---



\## 1. The old physiology lab idea



In a traditional physiology laboratory, an ECG recording often involved:



\* subject preparation

\* electrode placement

\* amplifier connection

\* setting sensitivity or gain

\* choosing timebase

\* recording the trace

\* identifying waves and intervals

\* interpreting whether the trace was technically acceptable



OpenPhysiologyLab follows the same logic, but the recording is stored digitally.



The paper trace becomes a plotted digital signal.



The amplifier output becomes ADC values.



The laboratory notebook becomes metadata.



The machine check becomes machine/session evaluation.



\---



\## 2. What changes in the digital workflow?



In an analogue system, one mainly sees the final trace.



In OpenPhysiologyLab, the recording also stores:



\* raw ADC data

\* sampling rate

\* COM port

\* protocol

\* electrode placement

\* device status

\* machine/session evaluation

\* analysis report



This makes the experiment easier to audit later.



A trace is no longer just a picture. It becomes a reproducible recording folder.



\---



\## 3. The ECG configuration used here



OpenPhysiologyLab v0.1-alpha uses an ECG-like limb recording with NPG Lite.



Current practical configuration:



| Body location    | NPG Lite input   |

| ---------------- | ---------------- |

| Right wrist / RA | A0P / CH input P |

| Left leg / LL    | A0N / CH input N |

| Right leg / RL   | REF / GND        |



This is documented as:



\*\*RA-LL limb ECG / Lead-II-like\*\*



Important: this is not a certified diagnostic Lead II ECG. It is a practical ECG-like teaching and validation configuration.



\---



\## 4. Relating analogue terms to OpenPhysiologyLab



| Analogue laboratory term | OpenPhysiologyLab equivalent                |

| ------------------------ | ------------------------------------------- |

| Electrodes               | Gel electrodes connected to NPG Lite inputs |

| Amplifier                | NPG Lite front-end                          |

| Recording cable          | USB serial connection                       |

| Recording paper          | Digital plot window                         |

| Timebase                 | Time window / time axis                     |

| Gain / sensitivity       | ADC range, headroom, display amplitude      |

| Baseline                 | ADC baseline / median signal level          |

| Saturation               | ADC clipping                                |

| Artifact                 | Movement noise, cable tug, poor contact     |

| Manual measurement       | Analysis tab and saved report               |

| Lab notebook             | metadata.json and analysis\_report.json      |



\---



\## 5. Why ADC headroom matters



In an analogue chart recorder, if the pen strikes the top or bottom limit, the recording becomes technically poor.



In digital recording, the equivalent problem is ADC clipping.



NPG Lite records values approximately between:



\*\*0 and 4095\*\*



If the signal reaches too close to 0 or 4095, part of the waveform may be lost.



OpenPhysiologyLab checks this automatically and gives a machine/session status:



\* PASS

\* CAUTION

\* FAIL



A recording may still be usable for R-peak timing even when amplitude or morphology is not reliable. This distinction is important.



\---



\## 6. Setup tab



The Setup tab is the experiment selection area.



For v0.1-alpha, choose:



\* Signal: ECG

\* Protocol: ECG Headroom Test - 60 s



This protocol is intended as the first technical check before longer recordings.



Click:



\*\*Use This Setup → Recorder\*\*



This is similar to choosing the practical exercise before starting the recording.



\---



\## 7. Recorder tab



The Recorder tab is the digital equivalent of the recording instrument.



It shows:



\* COM port

\* recording mode

\* protocol

\* sampling rate

\* duration

\* electrode placement

\* live trace

\* ADC status

\* markers

\* recording controls



For v0.1-alpha, the expected settings are:



\* Mode: ECG

\* Channel: 1

\* Sampling rate: 500 Hz

\* Placement: RA-LL limb ECG / Lead-II-like



\---



\## 8. Live trace



During recording, observe the trace like a classical ECG tracing.



Look for:



\* repeating cardiac rhythm

\* visible R peaks

\* stable baseline

\* no flat line

\* no severe wandering

\* no clipping at upper or lower limit

\* no large movement artifacts



If the trace is poor, do not rush to analyse it. First fix the recording.



Most bad physiology data are born before analysis begins.



\---



\## 9. Filtering



OpenPhysiologyLab can apply filtering for review and analysis.



For ECG, the typical v0.1-alpha filter settings are:



\* Low cut: 0.5 Hz

\* High cut: 40 Hz

\* 50 Hz notch: enabled



Filtering helps reduce baseline drift and electrical noise.



However, filtering does not magically repair a bad recording. Loose electrodes, clipping, and movement artifacts remain technical problems.



\---



\## 10. Analysis tab



The Analysis tab is where the recording is inspected and analysed.



The usual sequence is:



1\. Load recording folder

2\. Apply filter

3\. Detect R peaks

4\. Visually inspect detected peaks

5\. Add or remove peaks if needed

6\. Analyse

7\. Save analysis



The R peak detection is a tool, not an authority.



The trace must still be inspected by a human.



\---



\## 11. Results tab



The Results tab reads the saved analysis report.



It may show:



\* heart rate

\* RR interval summary

\* basic HRV-style metrics

\* RR tachogram

\* RR histogram

\* Poincare plot

\* machine/session status

\* recording metadata



This is like a clean post-practical report generated from the recording folder.



\---



\## 12. Compare tab



The Compare tab allows two saved analysis reports to be compared.



This can be useful for:



\* comparing two recordings from the same subject

\* comparing two electrode placements

\* comparing clean and noisy recordings

\* comparing before and after an intervention

\* comparing different recording sessions



Comparison is especially useful in teaching because students can see how technical quality affects interpretation.



\---



\## 13. Machine tab



The Machine tab is the instrument record room.



It stores machine/session information such as:



\* machine UID

\* latest COM port

\* sample rate

\* channel count

\* device status

\* latest evaluation

\* ADC headroom

\* clipping information



This helps separate biological interpretation from technical reliability.



A good result should not only ask, “What did the heart do?”



It should also ask, “Was the machine recording properly?”



\---



\## 14. Digital advantage



The digital workflow gives several advantages:



\* raw data can be saved

\* metadata can be preserved

\* analysis can be repeated

\* machine quality can be documented

\* reports can be compared

\* teaching examples can be archived

\* errors can be traced more easily



This is not a rejection of the analogue tradition.



It is the same physiology discipline carried into a reproducible digital format.



\---



\## 15. Caution



OpenPhysiologyLab v0.1-alpha is not a diagnostic medical device.



It should not be used to diagnose disease, guide treatment, or replace certified ECG equipment.



It is meant for teaching, open experimentation, validation, and understanding physiological signals.



\---



\## 16. Core message



The old physiology laboratory trained the eye.



The digital physiology laboratory must train both the eye and the audit trail.



OpenPhysiologyLab tries to keep both alive.



