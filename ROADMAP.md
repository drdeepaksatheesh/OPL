\# OpenPhysiologyLab Roadmap



OpenPhysiologyLab is being developed as an open-source physiology teaching and research platform.



The roadmap is intentionally staged. Each release should provide a working vertical slice rather than a large unfinished promise.



\---



\## v0.1-alpha: ECG-like vertical slice



Status: current first public release target



Primary goal:



Build a working ECG-like acquisition, analysis, reporting, comparison, and machine/session tracking workflow using NPG Lite over USB serial.



Scope:



\* ECG-like recording from NPG Lite over USB serial

\* one-channel acquisition

\* ECG headroom test

\* resting ECG / basic RR analysis workflow

\* raw CSV recording

\* metadata storage

\* machine/session evaluation

\* ADC headroom and clipping checks

\* filtering for review and analysis

\* R-peak detection

\* manual peak correction

\* heart rate and RR interval metrics

\* basic HRV-style metrics

\* results dashboard

\* comparison of saved analysis reports

\* walkthrough documentation



Platform status:



\* Windows 11: tested

\* macOS: expected to work, not yet fully tested

\* Linux: expected to work, not yet fully tested



Boundary:



OpenPhysiologyLab v0.1-alpha is not a diagnostic medical device and should not be used for diagnosis or treatment decisions.



\---



\## v0.2-alpha: ECG validation strengthening



Planned goals:



\* improve ECG recording stability

\* refine ADC headroom evaluation

\* improve signal quality reporting

\* improve R-peak detection reliability

\* improve manual peak editing workflow

\* add clearer recording quality flags

\* add better example datasets

\* add simulator-based testing workflow if available

\* improve documentation for validation against reference systems



Possible additions:



\* ECG simulator input guide

\* adjacent electrode validation guide

\* ADInstruments comparison workflow

\* EDAN/reference ECG comparison notes

\* exportable validation summary



\---



\## v0.3-alpha: Packaging and installation



Planned goals:



\* improve installation instructions

\* improve Windows launcher

\* test macOS launcher

\* test Linux launch workflow

\* add environment setup guide

\* consider virtual environment setup script

\* consider PyInstaller or similar packaging

\* reduce dependency friction for non-programmers



Possible additions:



\* `install\_windows.md`

\* `install\_macos.md`

\* `install\_linux.md`

\* troubleshooting guide

\* screenshots for setup and recording



\---



\## v0.4-alpha: EMG workflow



Planned goals:



\* add surface EMG recording preset

\* add graded contraction protocol

\* add rest versus contraction analysis

\* add RMS/envelope workflow

\* add artifact warnings

\* document electrode placement

\* document limitations of NPG Lite EMG workflow



Possible applications:



\* muscle activation demonstration

\* fatigue teaching workflow

\* basic motor control teaching

\* low-cost practical physiology demonstrations



\---



\## v0.5-alpha: EOG workflow



Planned goals:



\* add horizontal EOG workflow

\* add vertical EOG workflow

\* add blink detection

\* add eye movement polarity documentation

\* add baseline drift handling

\* add teaching walkthrough



Possible applications:



\* blink reflex demonstrations

\* horizontal eye movement recording

\* vertical eye movement recording

\* sleep/alertness teaching examples



\---



\## v0.6-alpha: Multi-channel acquisition



Planned goals:



\* expose multi-channel recording safely

\* document sampling-rate versus channel-count trade-offs

\* improve channel plotting

\* improve metadata for multiple channels

\* improve per-channel quality checks

\* improve channel naming and electrode mapping



Important caution:



Multi-channel support should not be exposed publicly until the timing, bandwidth, and display behaviour are well tested.



\---



\## v0.7-alpha: EEG demonstration workflow



Planned goals:



\* add basic EEG eyes-open / eyes-closed workflow

\* document electrode placement

\* document noise limitations

\* document safety and interpretation boundaries

\* add alpha demonstration analysis if technically reliable



Boundary:



EEG workflow should be presented as a teaching demonstration only unless stronger validation is completed.



\---



\## v0.8-alpha: Hardware and firmware documentation



Planned goals:



\* document compatible hardware

\* document firmware flashing

\* document serial protocol

\* document firmware identity/version handling

\* document device limitations

\* document electrode connection safety boundaries



Possible additions:



\* NPG Lite firmware notes

\* serial protocol notes

\* simulator input guide

\* safe electrode handling notes



\---



\## v0.9-alpha: Validation datasets and examples



Planned goals:



\* add anonymized example recordings

\* add demo analysis reports

\* add clean versus noisy examples

\* add PASS / CAUTION / FAIL examples

\* add example comparison reports

\* add teaching datasets



Data rules:



\* no personally identifiable data

\* no clinical claims

\* no patient data without proper ethics and consent

\* example recordings should be clearly labelled as demonstration data



\---



\## v1.0 target



A future v1.0 release should aim for:



\* stable ECG-like recording workflow

\* stable analysis workflow

\* stable report generation

\* stable comparison workflow

\* documented installation

\* documented limitations

\* tested hardware compatibility

\* tested platform behaviour

\* reproducible example dataset

\* clear licensing

\* clear contributor guidelines



OpenPhysiologyLab v1.0 should still not imply diagnostic medical device status unless formal regulatory work is done.



\---



\## Long-term vision



OpenPhysiologyLab aims to become a transparent open physiology workbench for:



\* teaching

\* practical physiology laboratories

\* low-cost biosignal acquisition

\* reproducible physiological signal analysis

\* open hardware integration

\* experimental physiology education

\* frugal biomedical engineering



The long-term goal is not only to record signals.



The goal is to make the full signal chain understandable:



electrode → machine → raw data → analysis → report → interpretation.



