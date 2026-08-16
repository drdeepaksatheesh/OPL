# OpenPhysiologyLab v0.2.0-alpha

Release date: 2026-08-16

## Major addition

### OPL-native 4D Cardiac Anatomy

This release adds a **4D Cardiac Anatomy** tab to OpenPhysiologyLab while
preserving the established OPL visual shell.

The tab provides:

- open-data 3D cardiac anatomy with cardiac-cycle motion;
- OPL-native playback, anatomical-view and phase controls;
- cardiac timing ribbon with ED, ES and next-ED landmarks;
- AV and semilunar valve-state display;
- loading and review of recorded OPL/NPG Lite ECG;
- synchronized ECG cursor, 3D cardiac motion and phase playhead;
- playback across the full sequence of complete reviewed R-R cycles;
- beat number, R-R duration, recording-time position and phase-time context;
A loaded recording drives playback across all complete reviewed R-R cycles.

## Scientific boundary

Reviewed ECG R-trigger timing and R-R intervals are measured from the ECG.

Mechanical phase boundaries, valve-state timing and wall motion remain
model-based estimates for physiology teaching and exploratory visualization.
They are not patient-specific mechanical measurements and are not diagnostic
output.

## Third-party anatomy and motion provenance

See:

software/OpenPhysiologyLab/third_party/open_4d_cardiac_anatomy_integration/OPL_INTEGRATION_NOTICE.md

for source, attribution, licensing and scientific-provenance information.

## Status

Alpha software intended for physiology education, software development and
exploratory research workflows.
