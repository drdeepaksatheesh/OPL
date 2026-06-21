\# ChatGPT-Assisted Windows Installation Guide



\## OpenPhysiologyLab v0.1-alpha



This guide is for users who are new to Python, Command Prompt, Git, or software installation.



Copy the prompt below and paste it into ChatGPT, Gemini, Claude, or another AI assistant.



The assistant should then guide you slowly, one step at a time.



\---



\## Copy-paste prompt



I want to install and run OpenPhysiologyLab v0.1-alpha on my Windows computer.



Please guide me slowly, one step at a time.



Important instructions for you:



1\. Do not give all steps at once.

2\. Ask me whether I have already downloaded the OpenPhysiologyLab repository.

3\. Ask me whether Python is installed.

4\. Ask me whether I am using Command Prompt or PowerShell.

5\. Prefer Command Prompt commands unless I say otherwise.

6\. Give only one or two commands at a time.

7\. After every command, wait for me to paste the result before continuing.

8\. If there is an error, explain it in simple language and help me fix it.

9\. Do not assume I know programming.

10\. Do not assume I know Git.

11\. Prefer the easiest method first.

12\. Help me reach the point where OpenPhysiologyLab opens successfully.

13\. After the software opens, guide me to the first ECG walkthrough.



Project details:



OpenPhysiologyLab v0.1-alpha is a Python application for ECG-like physiology recording and analysis using NPG Lite over USB serial.



The app folder is usually:



```text

software/OpenPhysiologyLab

```



The main launch file is:



```text

openphysiolab.py

```



The requirements file is:



```text

requirements.txt

```



The Windows launcher is:



```text

launch\_openphysiologylab.bat

```



The recommended manual installation commands are:



```bat

python -m venv .venv

```



```bat

.venv\\Scripts\\activate

```



```bat

python -m pip install --upgrade pip

```



```bat

python -m pip install -r requirements.txt

```



To launch the app manually:



```bat

python openphysiolab.py

```



Important hardware note:



For ECG-like recording, OpenPhysiologyLab v0.1-alpha expects NPG Lite to be connected over USB serial and to have compatible firmware uploaded.



Important safety note:



OpenPhysiologyLab is not a diagnostic medical device. It is for teaching, experimentation, validation, and understanding physiological signals. It should not be used for diagnosis, treatment, or emergency medical decisions.



Start by asking me whether I have downloaded OpenPhysiologyLab already.



