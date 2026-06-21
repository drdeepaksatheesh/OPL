\# Start Here



\## OpenPhysiologyLab v0.1-alpha



This page is for first-time users.



OpenPhysiologyLab v0.1-alpha is a beginner-stage open-source physiology software project for ECG-like recording and analysis using NPG Lite.



It is not a diagnostic medical device.



\---



\## What you will do first



Your first goal is simple:



Record a short ECG-like signal from NPG Lite and open it in OpenPhysiologyLab.



Do not start with long recordings.



Do not start with multi-channel recording.



Do not start with EMG, EOG, or EEG.



Start with the ECG headroom test.



\---



\## Recommended order



Follow the documents in this order:



\### 1. Understand the hardware



Read:



```text id="57wq09"

docs/hardware\_npg\_lite.md

```



This explains the NPG Lite Beast Pack used during development and links to the official Upside Down Labs documentation and store page.



\---



\### 2. Install the software



Read:



```text id="ffqzgi"

docs/installation\_windows.md

```



This gives two options:



1\. Manual Windows installation

2\. ChatGPT-assisted Windows installation for beginners



If you are new to Python or Command Prompt, use the ChatGPT-assisted option.

To open the app after installation, see docs/launching_openphysiologylab.md.



\---



\### 3. Flash the NPG Lite firmware



Read:



```text id="i2zr06"

docs/firmware\_flashing\_npg\_lite.md

```



OpenPhysiologyLab v0.1-alpha expects NPG Lite to run compatible USB serial firmware.



If the firmware is not uploaded, the software may open but recording may not work.



\---



\### 4. Do the first ECG recording



Read:



```text id="s1hg0j"

docs/walkthroughs/first\_ecg\_recording.md

```



Start with:



```text id="obmdxr"

ECG\_HEADROOM\_60S

```



This helps you check whether the signal fits inside the ADC recording range.



\---



\### 5. Understand the digital physiology workflow



After your first recording, read:



```text id="z9z53f"

docs/walkthroughs/analogue\_to\_digital\_ecg.md

```



This explains how classical ECG recording ideas translate into the digital workflow used by OpenPhysiologyLab.



\---



\### 6. Learn validation thinking



After you can record and analyse a signal, read:



```text id="bvubhb"

docs/walkthroughs/ecg\_validation\_workflow.md

```



This explains how to think about signal quality, ADC headroom, clipping, raw data, filtering, and validation.



\---



\## Minimum first successful test



A first successful test means:



\* OpenPhysiologyLab opens

\* NPG Lite appears as a COM port

\* the Recorder tab receives data

\* the ECG headroom test records for 60 seconds

\* a raw CSV file is saved

\* the Analysis tab can open the recording

\* R peaks can be detected or manually corrected

\* a result can be saved



If these things work, your basic setup is successful.



\---



\## If something fails



\### Software does not open



Go back to:



```text id="i6su7h"

docs/installation\_windows.md

```



Check Python and package installation.



\---



\### No COM port appears



Check:



\* USB cable supports data

\* NPG Lite is connected

\* correct driver is installed if needed

\* another program is not using the port

\* firmware upload was successful



\---



\### COM port appears but no signal comes



Check:



\* compatible firmware is uploaded

\* correct baud rate is selected

\* Arduino Serial Monitor is closed

\* another program is not using the same port

\* the Recorder Start button was pressed



\---



\### Signal appears but looks clipped



Do not continue to long recordings.



Run the ECG headroom test again.



Check electrode placement and signal quality.



\---



\### Signal is noisy



Check:



\* electrode contact

\* loose wires

\* body movement

\* USB cable quality

\* laptop charger noise

\* nearby electrical equipment



Try recording with the laptop on battery power.



\---



\## Safety warning



OpenPhysiologyLab is not a diagnostic medical device.



Do not use it to:



\* diagnose disease

\* guide treatment

\* replace a certified ECG machine

\* make emergency medical decisions



Use it for:



\* physiology teaching

\* open experimentation

\* signal validation

\* learning biosignal acquisition

\* understanding digital physiology workflows



\---



\## Beginner rule



Do one step at a time.



First make the software open.



Then make the firmware work.



Then record 60 seconds.



Then analyse.



Then improve.



