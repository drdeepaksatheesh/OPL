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


---

---

## Serial Monitor test after flashing

The OpenPhysiologyLab NPG Lite firmware is command-based.

After flashing, the board may not continuously stream data until the correct command is sent.

In Arduino IDE Serial Monitor:

1. Select the correct NPG Lite COM port.
2. Set baud rate to:

```text
230400
```

3. Set line ending to:

```text
Newline
```

or:

```text
Both NL & CR
```

Do not use `No line ending` when sending commands such as `HELP`, `STATUS`, or `START`.

---

## Important ESP32-C6 setting

For ESP32-C6 boards, make sure this Arduino IDE option is enabled if available:

```text
Tools → USB CDC On Boot → Enabled
```

If USB CDC On Boot is disabled, the board may upload successfully and a COM port may appear, but `Serial.print()` output may not appear correctly over USB.

Recommended Arduino IDE settings:

```text
Board: ESP32C6 Dev Module
USB CDC On Boot: Enabled
Port: the NPG Lite COM port
Serial Monitor baud: 230400
Serial Monitor line ending: Newline
```

---

## Command test

After flashing the firmware, open Serial Monitor and type:

```text
HELP
```

Press Enter.

The firmware should print a list of available commands.

Then type:

```text
STATUS
```

Press Enter.

The firmware should print firmware/session status.

Then type:

```text
START
```

Press Enter.

After `START`, the board should begin printing sample data.

Expected output should include lines similar to:

```text
STARTED
sample,time_us,ch1,ch2,ch3,ch4,ch5,ch6
```

followed by numeric sample rows.

---

## If Serial Monitor is blank

If Serial Monitor is blank at 230400 baud:

1. Confirm the selected COM port is really NPG Lite:

   * unplug NPG Lite
   * see which COM port disappears
   * plug it back in
   * use the COM port that appears again

2. Confirm Arduino IDE settings:

   * Board: ESP32C6 Dev Module
   * USB CDC On Boot: Enabled
   * Port: NPG Lite COM port
   * Baud: 230400
   * Line ending: Newline

3. Upload the firmware again.

4. After upload:

   * press Reset once, or unplug/replug NPG Lite
   * reopen Serial Monitor
   * set baud to 230400
   * set line ending to Newline
   * type `HELP`

If Serial Monitor is still blank, OpenPhysiologyLab will not be able to record because the board is not sending serial data.

---

## Meaning of `b''` in Python serial testing

If Python opens the COM port but prints:

```text
b''
```

this means the port opened, but no serial bytes were received before timeout.

This usually suggests:

* wrong COM port
* firmware not flashed correctly
* firmware not streaming
* USB CDC On Boot disabled
* wrong baud rate
* another program is using the serial port
* command such as `START` was not sent

OpenPhysiologyLab can only record after the NPG Lite firmware is confirmed to send data through Serial Monitor.

\## Safety note



Do not connect human electrodes while flashing firmware.



Flash the board first, confirm that the app can detect the board, and only then proceed to ECG-like recording.



OpenPhysiologyLab is not a diagnostic medical device and must not be used for diagnosis, treatment, or emergency decisions.



