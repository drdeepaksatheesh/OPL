\# Launching OpenPhysiologyLab



\## OpenPhysiologyLab v0.1-alpha



This guide explains how to open OpenPhysiologyLab after installation.



OpenPhysiologyLab v0.1-alpha is currently a Python application. It does not yet have a one-click installer.



\---



\## Before launching



Make sure you have already:



1\. Downloaded OpenPhysiologyLab

2\. Installed Python

3\. Installed the required Python packages

4\. Gone to the correct software folder



The software folder is:



```text

software/OpenPhysiologyLab

```



The main launch file is:



```text

openphysiolab.py

```



\---



\## Method 1: Launch by double-clicking



On Windows, try double-clicking:



```text

launch\_openphysiologylab.bat

```



This file is inside:



```text

software/OpenPhysiologyLab

```



If the app opens, this is the easiest method.



If it does not open, use Method 2.



\---



\## Method 2: Launch from Command Prompt



Open Command Prompt.



Go to the OpenPhysiologyLab software folder:



```bat

cd /d path\\to\\OPL\\software\\OpenPhysiologyLab

```



Example:



```bat

cd /d D:\\Projects\\OPL\\software\\OpenPhysiologyLab

```



Then run:



```bat

python openphysiolab.py

```



\---



\## Method 3: Launch after activating virtual environment



If you installed OpenPhysiologyLab using a virtual environment, open Command Prompt and go to:



```bat

cd /d path\\to\\OPL\\software\\OpenPhysiologyLab

```



Activate the virtual environment:



```bat

.venv\\Scripts\\activate

```



Then launch:



```bat

python openphysiolab.py

```



\---



\## What should happen



If launch is successful, the OpenPhysiologyLab window should open.



You should see tabs such as:



\* Setup

\* Recorder

\* Analysis

\* Results

\* Compare

\* Machine



For the first ECG workflow, begin with the Setup tab.



\---



\## If the app does not open



\### Python is not recognized



If you see:



```text

python is not recognized

```



Python may not be installed or may not be added to PATH.



Go back to:



```text

docs/installation\_windows.md

```



\---



\### Missing module error



If you see something like:



```text

ModuleNotFoundError

```



install the requirements again:



```bat

python -m pip install -r requirements.txt

```



If you are using a virtual environment, activate it first:



```bat

.venv\\Scripts\\activate

```



Then install requirements:



```bat

python -m pip install -r requirements.txt

```



\---



\### The app opens but recording does not work



Opening the app and recording from NPG Lite are separate steps.



If the app opens but recording does not work, check:



\* NPG Lite is connected

\* correct COM port is selected

\* compatible firmware is uploaded

\* Arduino Serial Monitor is closed

\* another program is not using the serial port



Read:



```text

docs/firmware\_flashing\_npg\_lite.md

```



and:



```text

docs/walkthroughs/first\_ecg\_recording.md

```



\---



\## After launching



After the app opens, follow:



```text

docs/walkthroughs/first\_ecg\_recording.md

```



Start with:



```text

ECG\_HEADROOM\_60S

```



Do not start with long recordings until the short headroom test works.



\---



\## Safety note



OpenPhysiologyLab is not a diagnostic medical device.



Do not use it to diagnose disease, guide treatment, replace certified ECG equipment, or make emergency medical decisions.



