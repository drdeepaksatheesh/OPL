\# Flashing NPG Lite Firmware



\## OpenPhysiologyLab v0.1-alpha



OpenPhysiologyLab v0.1-alpha expects NPG Lite to run compatible USB serial firmware.



The included firmware source is located at:



```text

software/OpenPhysiologyLab/OpenPhysio\_NPG\_Lite\_FW\_v0\_1/OpenPhysio\_NPG\_Lite\_FW\_v0\_1.ino

```



This guide explains the basic Arduino IDE method for uploading the firmware.



\---



\## Important warning



Flashing firmware changes what the NPG Lite does.



If your NPG Lite is currently working with Chords Web or another firmware, flashing OpenPhysiologyLab firmware may replace that behaviour.



Only flash this firmware if you want to use NPG Lite with OpenPhysiologyLab v0.1-alpha.



\---



\## What you need



\* NPG Lite

\* USB-C data cable

\* Windows computer

\* Arduino IDE 2.x

\* OpenPhysiologyLab repository

\* included OpenPhysiologyLab NPG Lite firmware file



Use a USB cable that supports data. Some USB-C cables are charge-only and will not work for flashing.



\---



\## Step 1: Install Arduino IDE



Install Arduino IDE 2.x from the official Arduino website.



After installation, open Arduino IDE.



\---



\## Step 2: Install ESP32 board support



NPG Lite uses an ESP32-C6 microcontroller.



In Arduino IDE:



1\. Open Boards Manager

2\. Search for:



```text

esp32

```



3\. Install the ESP32 board package by Espressif Systems



If Arduino IDE asks for an additional board manager URL, use the official Espressif Arduino-ESP32 package instructions.



\---



\## Step 3: Open the OpenPhysiologyLab firmware



In Arduino IDE:



1\. Go to File → Open

2\. Open:



```text

software/OpenPhysiologyLab/OpenPhysio\_NPG\_Lite\_FW\_v0\_1/OpenPhysio\_NPG\_Lite\_FW\_v0\_1.ino

```



Make sure the opened file name is:



```text

OpenPhysio\_NPG\_Lite\_FW\_v0\_1.ino

```



\---



\## Step 4: Select the board



In Arduino IDE, select an ESP32-C6 board target.



If a specific NPG Lite board option is not available, start with:



```text

ESP32C6 Dev Module

```



The exact board name may vary depending on the installed ESP32 board package version.



\---



\## Step 5: Select the port



Connect NPG Lite to the computer using USB-C.



In Arduino IDE, select the correct port.



On Windows it will usually appear as:



```text

COM3

COM4

COM5

```



or a similar COM port.



If no port appears:



\* check the USB cable

\* try another USB port

\* reconnect the NPG Lite

\* close other programs using the port

\* check whether a USB driver is required



\---



\## Step 6: Upload the firmware



Click Upload in Arduino IDE.



Wait until the upload completes.



If upload works, Arduino IDE will show a successful upload message.



\---



\## Step 7: If upload fails



If upload fails, the board may need to enter bootloader mode.



Try this:



1\. Hold the Boot/User button on NPG Lite

2\. Click Upload in Arduino IDE

3\. When Arduino IDE says it is connecting or uploading, release the Boot/User button

4\. Wait for upload to finish

5\. Press Reset if needed



If it still fails:



\* disconnect and reconnect USB

\* try another USB cable

\* try another USB port

\* close Serial Monitor

\* close OpenPhysiologyLab

\* confirm correct board and port



\---



\## Step 8: Test serial output



After upload, open Serial Monitor in Arduino IDE.



Set the baud rate to:



```text

230400

```



The OpenPhysiologyLab app currently uses 230400 baud by default.



If the output looks unreadable, check the baud rate used inside the firmware source.



Close Serial Monitor before opening OpenPhysiologyLab, because only one program can usually use the serial port at a time.



\---



\## Step 9: Launch OpenPhysiologyLab



Open OpenPhysiologyLab.



Go to the Recorder tab.



Select:



\* correct COM port

\* baud rate 230400

\* one channel

\* ECG mode



Then try:



```text

ECG\_HEADROOM\_60S

```



If the app receives data, the firmware upload was successful.



\---



\## Step 10: First recording workflow



After firmware upload, read:



```text

docs/walkthroughs/first\_ecg\_recording.md

```



Start with the ECG headroom test before doing longer recordings.



\---



\## Safety note



Do not connect human electrodes while flashing firmware.



Flash the board first, confirm that the app can detect the board, and only then proceed to ECG-like recording.



OpenPhysiologyLab is not a diagnostic medical device and must not be used for diagnosis, treatment, or emergency decisions.



