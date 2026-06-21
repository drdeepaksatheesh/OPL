\# First ECG Recording



\## OpenPhysiologyLab v0.1-alpha Walkthrough



This walkthrough helps you make your first ECG-like recording using OpenPhysiologyLab and NPG Lite.



OpenPhysiologyLab v0.1-alpha is a teaching and research prototype. It is not a diagnostic ECG machine.



\---



\## 1. Aim



To record a short ECG-like signal, check whether the recording is usable, detect R peaks, analyse heart rate and RR intervals, and view a simple results report.



\---



\## 2. What you need



You need:



\* Computer with OpenPhysiologyLab installed

\* NPG Lite

\* USB cable

\* Three ECG gel electrodes

\* A quiet recording environment



\---



\## 3. What this recording represents



An ECG records electrical activity related to the heart.



A typical ECG beat contains:



\* P wave: atrial activation

\* QRS complex: ventricular activation

\* T wave: ventricular recovery



For this first workflow, the most important point is the R peak. R peaks are used to calculate heart rate and RR intervals.



\---



\## 4. Electrode placement



Use the current OpenPhysiologyLab v0.1-alpha practical ECG configuration:



| Body location    | NPG Lite input   |

| ---------------- | ---------------- |

| Right wrist / RA | A0P / CH input P |

| Left leg / LL    | A0N / CH input N |

| Right leg / RL   | REF / GND        |



This is called:



\*\*RA-LL limb ECG / Lead-II-like\*\*



Important: this is not a certified diagnostic Lead II ECG. It is a practical ECG-like configuration for teaching, research prototyping, and validation with NPG Lite.



\---



\## 5. Open OpenPhysiologyLab



Launch OpenPhysiologyLab.



The main tabs are:



\* Setup

\* Recorder

\* Analysis

\* Results

\* Compare

\* Machine



For the first recording, use:



1\. Setup

2\. Recorder

3\. Analysis

4\. Results



\---



\## 6. Select the protocol



Go to the Setup tab.



Choose:



\* Signal: ECG

\* Protocol: ECG Headroom Test - 60 s



Click:



\*\*Use This Setup → Recorder\*\*



This sends the selected ECG setup to the Recorder tab.



\---



\## 7. Check Recorder settings



In the Recorder tab, confirm:



\* Mode: ECG

\* Protocol: ECG\_HEADROOM\_60S

\* Channel: 1

\* Sampling rate: 500 Hz

\* Placement: RA-LL limb ECG / Lead-II-like



Check that the correct COM port is selected.



If the COM port is missing, connect NPG Lite and refresh the port list.



\---



\## 8. Prepare for recording



Before starting:



\* Sit comfortably.

\* Keep the hand and leg still.

\* Avoid pulling the electrode wires.

\* Make sure electrodes are firmly attached.

\* Avoid unnecessary movement.



Loose electrodes and cable movement can produce large artifacts.



\---



\## 9. Start recording



Click the Start button in the Recorder tab.



During recording, watch the trace.



A usable recording should show:



\* repeating heartbeat-like waves

\* visible R peaks

\* no flat line

\* no signal stuck at the top or bottom

\* no excessive movement artifact



\---



\## 10. ADC headroom



NPG Lite records the signal as ADC values.



The ADC range is approximately:



\*\*0 to 4095\*\*



If the signal reaches the lower or upper limit, it may be clipped.



Clipping means part of the signal is cut off because it went beyond the measurable range.



OpenPhysiologyLab checks ADC headroom and gives a machine/session status such as PASS, CAUTION, or FAIL.



\---



\## 11. Stop and save



After the 60-second recording is complete, OpenPhysiologyLab saves the recording folder.



The recording folder contains files such as:



\* raw.csv

\* metadata.json

\* machine/session evaluation information



The raw.csv file stores original ADC values. Filtering and display inversion should not overwrite raw data.



\---



\## 12. Analyse the recording



Go to the Analysis tab.



Load the recording folder.



Then follow this sequence:



1\. Apply filter

2\. Detect R peaks

3\. Visually inspect the detected peaks

4\. Add or remove peaks if needed

5\. Click Analyse

6\. Save Analysis



Do not blindly trust automatic detection. Always inspect the ECG trace.



\---



\## 13. View results



Go to the Results tab.



Load the latest saved analysis.



The Results tab can show:



\* heart rate

\* RR interval summary

\* basic HRV-style metrics

\* RR tachogram

\* RR histogram

\* Poincare plot

\* machine/session status



If the machine/session status is CAUTION or FAIL, interpret the result carefully.



\---



\## 14. Compare recordings



The Compare tab can compare two saved analysis reports.



This can be useful for comparing:



\* two recording sessions

\* two electrode placements

\* before and after exercise

\* recordings from different devices

\* clean and noisy recordings



\---



\## 15. Machine tab



The Machine tab stores information about device/session behaviour.



It helps track:



\* device identity

\* COM port

\* sampling settings

\* ADC headroom

\* clipping

\* latest machine/session evaluation



This is important because a signal is not only biological. It is also shaped by the machine, electrodes, wires, software, and operator.



\---



\## 16. Interpretation warning



OpenPhysiologyLab v0.1-alpha is not a diagnostic medical device.



Do not use it to diagnose disease, guide treatment, or replace a certified ECG machine.



Use it for teaching, experimentation, validation, and understanding physiology.



\---



\## 17. What to remember



A good first ECG recording needs:



\* correct electrode placement

\* stable wires

\* minimal movement

\* good ADC headroom

\* visible R peaks

\* visual verification before analysis



The software can calculate. The human must still judge.



