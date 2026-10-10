# Practical: real squid axon recordings — stimulus, action potential and repeated firing

**Source:** Paydarfar D, Forger DB, Clay JR. *Noisy Inputs and the Induction of On–Off Switching Behavior in a Neuronal Pacemaker.* J Neurophysiol 2006;96:3338–3348. Raw dataset: PhysioNet SGAMP v1.0.0 (DOI 10.13026/C25C73), ODC-BY 1.0. Record `a1t18`, **original real biological recording**, not a simulation. Attribution to original authors and PhysioNet required. *Teaching analysis is exploratory; no independent faculty-reviewed answer key yet.*

## Preparation

An isolated squid giant axon was recorded simultaneously for membrane voltage and applied stimulus current. Original acquisition time base is 125,000 samples/s (one sample every **0.008 ms**). The dataset reports original gain-calibration instructions. Preserved original binary and header passed SHA-256, first-sample and channel checksum checks on GitHub Actions; full, calibrated channels and originals are in the downloadable GitHub Actions artifact. The 992–1030 ms excerpt distributed in this repository is a **contiguous, unfiltered extraction** from that checked record.

## Student procedure

1. Open `web/index.html` on localhost or GitHub Pages, then click **Load verified squid axon: membrane potential**. The browser confirms the excerpt SHA-256; otherwise it refuses to label the waveform verified.
2. Inspect 992–1030 ms. Set cursors at the stable pre-stimulus baseline and first positive peak. Record the difference in mV; mention that cursors may snap to a nearby sample.
3. Click **Load verified squid axon: stimulus current**. Identify the beginning of the pulse, its duration and maximum magnitude. Do not automatically subtract the DC offset. Load membrane potential again and calculate the latency to its first positive peak.
4. Identify subsequent spikes and estimate the first interspike interval. Compare peak-to-peak spacing with recording resolution (0.008 ms). Consider how the same events would look if shown over the entire 2-second record.
5. Describe how the raw ADC, voltage gain, original units, waveform polarity, current-channel offset and stimulus markers affect interpretation. Cite dataset DOI and identify both original file hashes.

## Provisional numerical reference (not a blinded educational validation)

A separate NumPy analysis of original interleaved 16-bit ADC counts and exported CSV was used to verify scaling and timing. Pulse detections used **stimulus current >1 µA/cm²**; action-potential peaks used **voltage >+10 mV**, **prominence >30 mV**, **minimum separation 3 ms**. These are transparent analysis choices, not original-author event annotations.

- Resting pre-stimulation 0–900 ms median membrane potential approximately **−40.33 mV** (not necessarily a universal true resting potential).
- First detected pulse onset **1000.016 ms**, high-current segment duration approximately **1.008 ms**; maximum recorded stimulus-channel value **5.023 µA/cm²** (includes any baseline offset).
- First positive membrane peak **1001.160 ms**, **+39.06 mV**; onset-to-peak separation **1.144 ms**. This is **not** the stimulus-to-action-potential-onset latency.
- Next peak **1011.808 ms**, separated by **10.648 ms**; later near-periodic firing is visible in the complete recording.
- The entire 2-second trial contains two threshold-detected stimulus pulses, near **1000.016 and 1888.072 ms**, and 92 voltage peaks under the chosen detector. The second pulse occurs during established repetitive activity, complicating simple causal attribution.

**Pedagogy:** Do not require students to get precisely these numbers from unzoomed graphical cursors. Accept physically plausible ranges tied to the sample period, noise, and explicit event definitions. The correct scientific skill is supporting a measurement with verifiable provenance and declared uncertainty.

## Remaining editorial checks

- Compare original trial-specific experimental protocol in the full 2006 paper and `Recording-Info.ods`.
- Obtain independent physiology educator review of membrane-spike identification, terminology and answer ranges.
- Measure repeatability of student measurements across desktop and phone screen sizes; screen pixel error must be assessed.
- Do not treat these nonhuman experimental recordings as clinical decision-support data or request new animal experiments for the lesson.
