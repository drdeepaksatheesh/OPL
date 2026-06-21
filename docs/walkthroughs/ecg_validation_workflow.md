\# ECG Validation Workflow



\## OpenPhysiologyLab v0.1-alpha Walkthrough



This walkthrough describes the validation mindset for ECG-like recordings in OpenPhysiologyLab.



The focus is not only on whether a waveform appears, but whether the recording can be trusted for timing, amplitude, morphology, teaching, or comparison.



OpenPhysiologyLab v0.1-alpha is a teaching and research prototype. It is not a diagnostic ECG machine.



\---



\## 1. Aim



To record, inspect, analyse, and document an ECG-like signal in a reproducible way using OpenPhysiologyLab and NPG Lite.



The workflow focuses on:



\* raw data preservation

\* electrode mapping

\* sampling settings

\* ADC headroom

\* clipping detection

\* R-peak timing

\* analysis provenance

\* report comparison

\* machine/session documentation



\---



\## 2. Scope of v0.1-alpha



OpenPhysiologyLab v0.1-alpha supports:



\* ECG-like recording from NPG Lite over USB serial

\* one-channel acquisition

\* 500 Hz sampling

\* ECG headroom test

\* resting ECG / basic HRV-style analysis

\* raw CSV storage

\* metadata storage

\* analysis report generation

\* comparison of saved reports

\* machine/session evaluation



It does not claim diagnostic ECG capability.



\---



\## 3. Hardware and software chain



A recording depends on the full chain:



1\. Subject

2\. Skin-electrode interface

3\. Electrode wires

4\. NPG Lite input configuration

5\. Firmware

6\. USB serial transport

7\. OpenPhysiologyLab recorder

8\. Raw CSV storage

9\. Analysis settings

10\. Results report



A poor recording may arise from any part of this chain.



Validation means documenting enough of the chain that the result can be understood later.



\---



\## 4. Electrode configuration



Current OpenPhysiologyLab v0.1-alpha ECG configuration:



| Body location    | NPG Lite input   |

| ---------------- | ---------------- |

| Right wrist / RA | A0P / CH input P |

| Left leg / LL    | A0N / CH input N |

| Right leg / RL   | REF / GND        |



This is documented as:



\*\*RA-LL limb ECG / Lead-II-like\*\*



This wording is deliberate.



It describes the practical NPG Lite configuration used by OpenPhysiologyLab. It should not be described as certified diagnostic Lead II.



\---



\## 5. Recommended first protocol



Start with:



\*\*ECG\_HEADROOM\_60S\*\*



Purpose:



\* check baseline position

\* check ADC headroom

\* check clipping

\* check R-peak visibility

\* check whether timing analysis may be usable



Do not start with long recordings until the headroom test is technically acceptable.



\---



\## 6. Recorder checks before acquisition



Before recording, verify:



\* correct COM port

\* Mode: ECG

\* Protocol: ECG\_HEADROOM\_60S or ECG\_RESTING\_5MIN

\* Channel: 1

\* Sampling rate: 500 Hz

\* Placement: RA-LL limb ECG / Lead-II-like

\* electrodes firmly attached

\* subject stable

\* wires not under tension



Document any unusual condition in the notes field.



\---



\## 7. Raw data policy



OpenPhysiologyLab saves original ADC values in:



\*\*raw.csv\*\*



The raw file should remain unchanged.



Filtering, display inversion, and analysis operations should not overwrite raw.csv.



This is essential for reproducibility.



A valid analysis report must be traceable back to the original recording folder.



\---



\## 8. Metadata policy



The recording folder should preserve metadata such as:



\* recording mode

\* protocol name

\* subject/session labels

\* electrode placement

\* sampling rate

\* channel count

\* COM port

\* firmware identity where available

\* machine/session evaluation

\* timing and integrity information



Metadata is not decoration.



Metadata is the memory of the experiment.



\---



\## 9. ADC headroom



NPG Lite ADC values are approximately in the range:



\*\*0 to 4095\*\*



Important checks:



\* minimum value

\* maximum value

\* median baseline

\* peak-to-peak range

\* lower headroom

\* upper headroom

\* low-rail clipping

\* high-rail clipping



If the signal touches the ADC limits, waveform morphology and amplitude may be unreliable.



R-peak timing may still be usable in some caution cases, but only after visual inspection.



\---



\## 10. PASS, CAUTION, and FAIL



A recording may receive a machine/session status:



\### PASS



ADC headroom is acceptable. Timing and basic morphology may be usable, provided R peaks are correct.



\### CAUTION



Some technical problem is present, such as mild clipping or poor centering. Timing may still be usable, but amplitude and morphology should be interpreted cautiously.



\### FAIL



The recording has significant technical problems. Do not use it for amplitude or morphology interpretation. Timing should also be trusted only if R peaks are clearly valid after visual inspection.



\---



\## 11. Filtering



Typical ECG review filter settings:



\* Low cut: 0.5 Hz

\* High cut: 40 Hz

\* 50 Hz notch: enabled



Filtering may improve visualisation and peak detection.



However:



\* filtering does not restore clipped data

\* filtering does not fix loose electrodes

\* filtering does not make poor sampling reliable

\* filtering must not overwrite raw.csv



Always document filter settings in the analysis report.



\---



\## 12. R-peak detection



R-peak detection should be treated as semi-automatic.



Recommended workflow:



1\. Apply filter

2\. Detect R peaks

3\. Inspect the trace visually

4\. Check missed beats

5\. Check false peaks

6\. Manually add or remove peaks when needed

7\. Analyse only after correction



The peak list is the foundation of HR and RR analysis.



Bad peaks produce bad metrics.



\---



\## 13. HR and RR interpretation



Heart rate and RR metrics depend on correct R-peak timing.



Before interpreting results, check:



\* whether detected peaks sit on true R peaks

\* whether ectopic/noisy segments are present

\* whether movement artifact produced false peaks

\* whether clipping distorted peak shape

\* whether the selected segment is appropriate



RR analysis is only as clean as the peak train.



\---



\## 14. Basic HRV-style metrics



OpenPhysiologyLab may report basic time-domain HRV-style values such as:



\* mean RR

\* median RR

\* SDNN

\* RMSSD

\* pNN50



These values require clean R-peak detection and a sufficiently appropriate recording context.



For serious HRV research, longer recordings, stricter preprocessing, artefact handling, and formal methodology are required.



Do not overclaim from short or technically weak recordings.



\---



\## 15. Results report



The Results tab displays the saved analysis report.



The report should be interpreted together with:



\* recording summary

\* machine/session status

\* signal quality

\* peak detection information

\* HR/RR metrics

\* RR tachogram

\* RR histogram

\* Poincare plot

\* raw signal handling



The report is not just a result sheet. It is a technical audit of the recording.



\---



\## 16. Compare workflow



The Compare tab allows two saved analysis reports to be compared.



Useful comparisons include:



\* same subject, two sessions

\* before and after exercise

\* different electrode placements

\* different NPG Lite devices

\* clean versus noisy recording

\* PASS versus CAUTION recording



Comparison should focus not only on physiology, but also on recording quality.



A difference in results may be biological, technical, or both.



\---



\## 17. Machine tab



The Machine tab documents the instrument side of the experiment.



It helps answer:



\* Which machine/profile was used?

\* What was the latest connection?

\* What was the sampling rate?

\* What was the device status?

\* Did the session pass ADC headroom checks?

\* Was there clipping?

\* Is the recording usable for timing, amplitude, morphology, or teaching?



This is important for open science because the machine is part of the experiment.



\---



\## 18. Recommended validation ladder



For stronger validation, follow this ladder:



1\. Confirm software launches and records serial data.

2\. Run ECG\_HEADROOM\_60S.

3\. Check ADC headroom and clipping.

4\. Confirm visible R peaks.

5\. Analyse and save report.

6\. Repeat recording to check consistency.

7\. Compare reports.

8\. Test with known signal source or simulator when available.

9\. Compare with a reference system if available.

10\. Document limitations clearly.



Do not jump to publication claims before completing the lower steps.



\---



\## 19. Common failure modes



Common technical problems include:



\* no COM port selected

\* loose electrode

\* poor skin contact

\* cable movement

\* baseline drift

\* 50 Hz noise

\* signal clipping

\* wrong polarity documentation

\* false R-peak detection

\* missing samples

\* recording folder not saved

\* analysis report not saved



Most problems are fixable if they are documented early.



\---



\## 20. Minimum documentation for a useful recording



A useful recording should include:



\* raw.csv

\* metadata.json

\* analysis\_report.json

\* electrode placement

\* sampling rate

\* protocol name

\* machine/session status

\* filter settings

\* peak detection status

\* notes on artifacts or unusual events



If these are missing, the recording may still be interesting, but it is weaker as scientific evidence.



\---



\## 21. Interpretation boundary



OpenPhysiologyLab v0.1-alpha should be used for:



\* teaching

\* demonstration

\* research prototyping

\* signal validation

\* open physiology education

\* development of low-cost workflows



It should not be used for:



\* clinical diagnosis

\* treatment decisions

\* emergency assessment

\* replacing certified ECG systems

\* claiming diagnostic equivalence



\---



\## 22. Core message



Validation is not a button.



Validation is a chain of evidence.



OpenPhysiologyLab tries to make that chain visible: from electrode to raw data, from raw data to peaks, from peaks to results, and from results back to the machine.



