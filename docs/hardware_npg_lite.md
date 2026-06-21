\# NPG Lite Hardware Notes



\## OpenPhysiologyLab v0.1-alpha



OpenPhysiologyLab v0.1-alpha currently targets ECG-like recording using \*\*Neuro PlayGround Lite (NPG Lite)\*\* over USB serial.



NPG Lite is developed by \*\*Upside Down Labs\*\*.



Official documentation:



https://docs.upsidedownlabs.tech/hardware/bioamp/neuro-play-ground-lite/index.html



Official Beast Pack store page:



https://store.upsidedownlabs.tech/product/npg-lite-beast/



\---



\## Hardware used during OpenPhysiologyLab v0.1-alpha development



The current OpenPhysiologyLab ECG workflow was developed and tested using:



\*\*Neuro PlayGround Lite (NPG Lite) Beast Pack\*\*



The Beast Pack was used because it provides the most complete NPG Lite configuration and allows future expansion beyond one-channel ECG-like recording.



\---



\## Basic NPG Lite description



NPG Lite is a compact bio-physiological signal acquisition board intended for recording signals such as:



\* ECG

\* EMG

\* EOG

\* EEG



The board is based on an ESP32-C6 microcontroller and supports USB-C connectivity, wireless communication, battery-powered use, and expansion through Playmate and FeatherWing-style add-on boards.



\---



\## NPG Lite Beast Pack



The NPG Lite Beast Pack is the most expanded NPG Lite package.



According to the official Upside Down Labs documentation, the Beast Pack includes:



\* NPG Lite board

\* VibZ+ Playmate

\* 6-channel BioAmp capability

\* 24 gel electrodes

\* 13 snap cables

\* 8 alligator cables

\* battery cable

\* LiPo battery

\* 3D printed case

\* USB cable



This makes it suitable for users who want a more complete NPG Lite setup and possible future expansion into multi-channel physiological recordings.



\---



\## Current OpenPhysiologyLab compatibility



OpenPhysiologyLab v0.1-alpha currently uses only a narrow part of the NPG Lite capability:



\* USB serial connection

\* one-channel ECG-like recording

\* ECG headroom test

\* resting ECG / RR interval analysis workflow



The Beast Pack supports more channels, but OpenPhysiologyLab v0.1-alpha intentionally exposes only one ECG-like channel to keep the first release stable and understandable.



Future versions may expand toward:



\* EMG

\* EOG

\* multi-channel recording

\* EEG demonstration workflows



\---



\## Important firmware note



OpenPhysiologyLab v0.1-alpha expects the NPG Lite board to be running compatible USB serial firmware.



The included firmware source is located at:



```text

software/OpenPhysiologyLab/OpenPhysio\_NPG\_Lite\_FW\_v0\_1/OpenPhysio\_NPG\_Lite\_FW\_v0\_1.ino

```



For basic firmware upload instructions, see docs/firmware_flashing_npg_lite.md.



\---



\## Independence statement



OpenPhysiologyLab is an independent project.



It is not officially affiliated with, sponsored by, or endorsed by Upside Down Labs unless explicitly stated.



NPG Lite, BioAmp, Chords, and related names belong to their respective creators.



Links to Upside Down Labs documentation and store pages are provided so that users can identify the hardware used and find official information.



