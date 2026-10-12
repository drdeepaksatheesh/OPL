# SGAMP a1t18 — independent numerical audit, 2026-10-12

**Status:** original binary master independently decoded and verified; independent physiology teaching sign-off still pending.

Source: PhysioNet SGAMP v1.0.0, DOI https://doi.org/10.13026/C25C73 (ODC-BY 1.0). Original: Paydarfar, Forger & Clay, J Neurophysiol. 2006;96:3338–3348.

### Binary-master checks
- `a1t18.dat` SHA-256: `d74534b5d67d7f582694e597e4d4c86adccfdb1f4597379af45323059cafffb9`.
- `a1t18.hea` SHA-256: `9dd10bf0703219b08be82f69444d25ae9e4c81f5f419f998b422c9ab72f66e0c`.
- Two synchronized original WFDB format-16 channels; 250,001 samples each at 125,000 Hz (sample period 0.008 ms).
- Independently decoded ADC gain and baseline; PhysioNet instrument scaling applied, with **no arbitrary current DC-offset removal, waveform smoothing, or polarity inversion**.

### Threshold-defined exploratory results
| Parameter | Value |
|---|---:|
| Membrane baseline median (990–999 ms) | −40.2994 mV |
| Current baseline median (990–999 ms), uncorrected | +0.024416 µA/cm² |
| First pulse onset, current >1 µA/cm² | 1000.016 ms |
| Pulse duration, threshold 1 µA/cm² | 1.008 ms |
| First positive Vm peak | +39.0619 mV at 1001.160 ms |
| Pulse onset → positive peak | **1.144 ms** |

Sensitivity check: thresholds 0.5 and 1 µA/cm² agree in event timing; threshold 4 µA/cm² moves the onset to 1000.024 ms (one 8-µs sample). These values do **not** identify exact action-potential initiation and are not external expert-adjudicated labels.

### v0.5 development in progress
A complete locally tested synchronized two-channel browser viewer, independent raw-binary audit script, executable fixtures/tests, source candidate register, master archive and updated handover have been prepared as a separate v0.5 project bundle. **Only this summary is currently committed to GitHub; the new viewer and scripts have not been staged in the pull request at this point.**

Browser interaction was checked for desktop/mobile by injecting exact original-derived fixtures; because browser navigation is administratively blocked, the **UI test uses a controlled digest stub**. Original master and derived CSV SHA-256 checks are independently tested unmocked in Python. HTTPS/localhost with native Web Crypto remains an acceptance gate.

Next review tasks: commit exact prototype source; run unmocked HTTPS browser end-to-end; independent physiological annotation; verify raw frog-muscle and isolated-organ rights before acquisition; decide on permanent versioned archive/DOI.
