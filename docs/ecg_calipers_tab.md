\# ECG Calipers Tab



ECG Calipers is a planned OpenPhysiologyLab app page for beat-wise ECG waveform measurement after recording.



It is separate from the existing Analysis tab.



The Analysis tab focuses on whole-recording analysis such as R peak detection, RR intervals, heart rate, HRV-style metrics, signal quality, and reports.



The ECG Calipers tab focuses on measuring selected ECG complexes using manual or semi-manual calipers.



\## Purpose



The purpose of ECG Calipers is to help learners understand how ECG waveform measurements are made directly from the trace.



The user should be able to load an ECG recording, view the raw or filtered signal, choose a beat, mark ECG landmarks, and calculate amplitudes, durations, and intervals.



This is intended as an educational morphology measurement tool, not a diagnostic ECG interpretation system.



\## App workflow



The ECG Calipers tab should support two workflows.



First, after recording:



Recorder -> ECG Calipers



The latest recording should be available automatically.



Second, later review:



ECG Calipers -> Load raw.csv or Load recording folder



The user should be able to manually load an older recording.



\## Signal view



The tab should show the ECG signal in a large plot area.



The user should be able to switch between:



\- raw signal view

\- filtered signal view



Filtering is for visualization and measurement assistance.



The original raw.csv must not be overwritten.



The measurement export should record whether the measurement was made using raw or filtered view.



\## Filters



Initial ECG filter options may include:



\- raw view

\- ECG bandpass, for example 0.5 to 40 Hz

\- optional notch filter for mains noise



Filter choices should be visible to the user.



\## Selected beat context view



The ECG Calipers tab should not show the selected ECG complex in isolation only.



When the user selects a beat, the screen should show:



previous ECG complex -> selected ECG complex -> next ECG complex



The selected beat should be visually highlighted.



This gives the user rhythm context and helps with caliper placement.



Showing the previous and next PQRST complexes helps the user understand:



\- whether the selected beat is early or late

\- whether the rhythm around the selected beat is regular

\- whether the T wave of one beat blends into the next P wave

\- where to place onset and offset markers more confidently



\## RR interval context



Showing the previous and next complexes allows calculation of:



\- pre-RR interval

\- post-RR interval



pre-RR interval = selected R time minus previous R time



post-RR interval = next R time minus selected R time



These should be shown for the selected beat.



This allows the selected ECG complex to be interpreted with immediate rhythm context.



\## Measurement view



A future version may include two linked views:



1\. Context view:

&#x20;  A wider view showing previous beat, selected beat, and next beat.



2\. Zoomed caliper view:

&#x20;  A zoomed view centered on the selected beat for precise placement of ECG markers.



For the first version, a single large plot showing previous, selected, and next complexes is acceptable.



\## ECG landmarks



The first version should use manual caliper placement.



The user should be able to mark:



\- P onset

\- P peak

\- P offset

\- Q point

\- R peak

\- S point

\- J point

\- T peak

\- T offset

\- baseline reference



Automatic landmark suggestion can be added later, but manual correction should remain possible.



\## Measurements



From the marked points, OPL can calculate:



\- P wave duration

\- P wave amplitude

\- PR interval

\- Q amplitude or Q depth

\- R amplitude

\- S depth

\- QRS duration

\- ST level or ST segment measurement

\- QT interval

\- T wave amplitude

\- pre-RR interval

\- post-RR interval



\## Amplitude caution



For NPG Lite recordings, amplitudes should initially be reported in raw ADC units or arbitrary units.



Amplitude in mV should only be shown after calibration.



\## Export



The tab should eventually export beat-wise measurements as CSV.



Possible export file:



beat\_measurements.csv



The export should include:



\- recording name or folder

\- channel

\- filter/view used

\- selected beat time

\- previous R time

\- next R time

\- pre-RR interval

\- post-RR interval

\- landmark times

\- landmark amplitudes

\- calculated intervals

\- calculated amplitudes



\## Relationship with existing Analysis tab



ECG Calipers should not create a competing HRV pipeline.



If R peaks are already detected by the existing Analysis system, ECG Calipers may reuse them.



If R peaks are not available, ECG Calipers may call the same existing R peak detector.



The goal is one shared R peak source, not conflicting R peak results.



\## Development stages



Stage 1:

Create an ECG Calipers tab with load recording, raw/filtered view, and plot display.



Stage 2:

Add selected beat navigation around R peaks, showing previous, selected, and next complexes.



Stage 3:

Add manual caliper markers.



Stage 4:

Calculate ECG intervals and amplitudes from markers.



Stage 5:

Export beat-wise ECG measurements.



Stage 6:

Add optional automatic landmark suggestions.



\## Safety



OpenPhysiologyLab ECG Calipers is for education, experimentation, and physiology learning.



It is not a diagnostic ECG system.



It should not be used for clinical diagnosis, emergency decisions, or treatment decisions.

