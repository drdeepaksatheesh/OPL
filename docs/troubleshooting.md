No COM port detected
Recording not starting
Flat line
Clipping
Noisy ECG
PyQt errors
Cable issues



\---



\## COM port appears but no data is recorded



If OpenPhysiologyLab detects a COM port but recording remains stuck at checking status, the computer may be seeing the board but not receiving serial data.



A COM port appearing only proves that Windows can see a USB serial device. It does not prove that the NPG Lite firmware is streaming sample data.



First test the board in Arduino Serial Monitor.



Use:



```text

Baud: 230400

Line ending: Newline

```



Send:



```text

HELP

```



Then:



```text

STATUS

```



Then:



```text

START

```



If Serial Monitor does not show data after `START`, OpenPhysiologyLab will not be able to record.



For ESP32-C6 boards, check:



```text

Tools → USB CDC On Boot → Enabled

```



Then re-upload the firmware.



If Python serial testing prints only:



```text

b''

```



the port opened, but no data was received before timeout. This is usually a firmware, baud, COM port, or USB CDC issue rather than a Recorder display issue.



Also make sure Arduino Serial Monitor, Chords Web, and other serial programs are closed before starting OpenPhysiologyLab. Usually only one program can use the COM port at a time.



