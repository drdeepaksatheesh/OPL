\# Manual Windows Installation Guide



\## OpenPhysiologyLab v0.1-alpha



This guide explains how to install and run OpenPhysiologyLab manually on Windows.



OpenPhysiologyLab v0.1-alpha is a source-run Python application. It does not yet have a one-click installer.



\---



\## 1. Install Python



Install Python 3.10 or 3.11.



During installation, enable:



```text

Add Python to PATH

```



After installation, open Command Prompt and check:



```bat

python --version

```



You should see a Python version number.



\---



\## 2. Download OpenPhysiologyLab



Download the repository from GitHub.



You can either:



1\. Use \*\*Code → Download ZIP\*\*, then extract the ZIP file



or



2\. Use Git:



```bat

git clone <repository-url>

```



If you do not know Git, use the ZIP download method.



\---



\## 3. Go to the software folder



Open Command Prompt.



Go to the OpenPhysiologyLab software folder:



```bat

cd /d path\\to\\OPL\\software\\OpenPhysiologyLab

```



Example:



```bat

cd /d D:\\Projects\\OPL\\software\\OpenPhysiologyLab

```



\---



\## 4. Create a virtual environment



Create a local Python environment:



```bat

python -m venv .venv

```



Activate it:



```bat

.venv\\Scripts\\activate

```



After activation, the command line should show something like:



```text

(.venv)

```



\---



\## 5. Install required packages



Upgrade pip:



```bat

python -m pip install --upgrade pip

```



Install OpenPhysiologyLab dependencies:



```bat

python -m pip install -r requirements.txt

```



Main dependencies include:



\* PyQt5

\* pyqtgraph

\* numpy

\* pandas

\* scipy

\* pyserial



\---



\## 6. Launch OpenPhysiologyLab



Run:



```bat

python openphysiolab.py

```



Alternatively, double-click:



```text

launch\_openphysiologylab.bat

```



If double-clicking does not work, use the Command Prompt method.



\---



\## 7. Hardware requirement for ECG-like recording



For ECG-like recording, OpenPhysiologyLab v0.1-alpha currently expects:



\* NPG Lite

\* USB connection

\* compatible USB serial firmware already uploaded to NPG Lite

\* three ECG gel electrodes



The included firmware source is located at:



```text

software/OpenPhysiologyLab/OpenPhysio\_NPG\_Lite\_FW\_v0\_1/OpenPhysio\_NPG\_Lite\_FW\_v0\_1.ino

```



Firmware upload instructions will be expanded in a future release.



\---



\## 8. First workflow to try



After launching OpenPhysiologyLab:



1\. Open the Setup tab

2\. Select ECG

3\. Select ECG Headroom Test - 60 s

4\. Click Use This Setup → Recorder

5\. Connect NPG Lite

6\. Select the correct COM port

7\. Record a short ECG-like signal

8\. Analyse and save results



For a guided introduction, read:



```text

docs/walkthroughs/first\_ecg\_recording.md

```



\---



\## 9. Troubleshooting



\### Python is not recognized



Python may not be added to PATH.



Try reinstalling Python and enabling:



```text

Add Python to PATH

```



\---



\### Missing module error



If you see an error like:



```text

ModuleNotFoundError

```



activate the virtual environment and reinstall requirements:



```bat

.venv\\Scripts\\activate

python -m pip install -r requirements.txt

```



\---



\### No COM port appears



Check:



\* NPG Lite is connected

\* USB cable supports data, not only charging

\* firmware is uploaded

\* correct USB driver is installed if required

\* another program is not already using the COM port



\---



\### App opens but no recording appears



Check:



\* correct COM port

\* compatible firmware

\* electrodes attached properly

\* Start button was pressed

\* NPG Lite is streaming data



\---



\## 10. Safety and interpretation warning



OpenPhysiologyLab is not a diagnostic medical device.



Do not use it to diagnose disease, guide treatment, replace certified ECG machines, or make emergency medical decisions.



Use it for teaching, experimentation, validation, and understanding physiology.



