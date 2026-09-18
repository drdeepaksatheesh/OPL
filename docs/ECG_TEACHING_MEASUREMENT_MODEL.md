# ECG Teaching Measurement Model

OpenPhysiologyLab should teach ECG morphology first as **baseline-relative geometry**.

## Core idea

A conventional ECG teaches the learner to identify an isoelectric reference and measure:

- how far a waveform moves above or below that reference;
- how long a wave, segment, or interval lasts.

OPL can preserve this logic even when the acquisition device has not yet earned an absolute millivolt calibration.

## Default public measurement units

### Horizontal axis

Time is physical and should be reported directly:

- seconds;
- milliseconds;
- optional ECG-style grid.

At 500 Hz, one sample is 2 ms.

### Vertical axis

Until a validated hardware calibration profile exists, use:

- **Raw ADC** — original digitized value;
- **ΔADC from baseline** — preferred teaching measurement;
- **Normalized amplitude** — optional dimensionless view.

Only show **mV** when a validated device calibration profile is active.

## Baseline-relative measurements

For a user-selected or algorithm-suggested baseline B:

- P amplitude = P_peak - B
- Q amplitude = Q_nadir - B
- R amplitude = R_peak - B
- S amplitude = S_nadir - B
- T amplitude = T_peak - B
- ST displacement = ST_measurement_point - B

Positive and negative signs must be preserved.

Example:

- baseline = 2050 ADC
- R = 3500 ADC -> +1450 ΔADC
- S = 1800 ADC -> -250 ΔADC

The physiological teaching question is therefore visible even without an absolute mV conversion.

## Intervals and segments

Durations are independent of voltage calibration:

- P duration
- PR interval
- QRS duration
- QT interval
- RR interval
- ST segment duration

These should always be reported in ms.

## Baseline choice

OPL should make the baseline explicit rather than pretending it is objectively known.

Initial teaching workflow:

1. suggest an isoelectric region;
2. allow the learner to move/confirm the baseline;
3. show all amplitudes relative to that selected baseline;
4. retain the baseline location in exported measurements.

For teaching, PR/TP isoelectric regions may be offered as selectable references depending on the measurement being demonstrated. OPL should not imply diagnostic ST-segment interpretation unless that workflow is separately validated.

## Grid behavior

The ECG-style grid is a visual ruler, not the source of the measurement.

Zooming must not change the underlying ΔADC or time values.

The display may show:

- small horizontal subdivisions tied to time;
- small vertical subdivisions tied to a fixed ΔADC increment for that view.

Do not label a vertical subdivision as 0.1 mV unless a calibrated mV profile is active.

## Comparison rule

Baseline-relative ADC measurements are valid within a recording when hardware/settings are unchanged.

Do not present raw ΔADC amplitudes from different devices, hardware revisions, gain configurations, electrode placements, or sessions as directly equivalent physical voltages unless those acquisition chains have been calibrated accordingly.

## Public wording

Recommended default:

> Amplitude measurements are reported relative to the selected isoelectric baseline in ADC units. Absolute millivolt values are shown only when a validated device calibration profile is available.

This keeps the first OPL ECG teaching release scientifically honest while preserving the familiar ECG-caliper workflow.
