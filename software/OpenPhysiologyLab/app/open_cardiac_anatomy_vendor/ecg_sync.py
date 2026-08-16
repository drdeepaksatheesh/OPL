"""Translate reviewed ECG landmarks into an evidence-labelled teaching clock.

Electrical events can be measured on the loaded trace.  Mechanical boundaries
cannot be measured from ECG alone, so this module treats ECG-derived placement
as an estimate and gives explicit manual PCG/echo markers precedence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .ecg import ECGGatingRecording
from .timing import CardiacCyclePhase, NormalAdultCycleTiming, ecg_gated_cycle_timing


@dataclass(frozen=True)
class ECGMechanicalSync:
    timing: NormalAdultCycleTiming
    boundary_sources: dict[str, str]
    reference: str

    @property
    def has_manual_mechanical_markers(self) -> bool:
        return any(value == "manual mechanical annotation" for value in self.boundary_sources.values())


def _relative_ms(recording: ECGGatingRecording, kind: str, beat: int, start_s: float) -> float | None:
    value = recording.landmark_time_s(kind, beat)
    return None if value is None else (value - start_s) * 1000.0


def _manual_relative_ms(
    recording: ECGGatingRecording, kind: str, beat: int, start_s: float
) -> float | None:
    item = recording.landmark(kind, beat)
    if item is None or item.source != "manual" or item.group != "mechanical":
        return None
    return (float(recording.time_s[item.sample_index]) - start_s) * 1000.0


def _phase(
    key: str,
    name: str,
    short_name: str,
    category: str,
    start_ms: float,
    end_ms: float,
    av_valves: str,
    semilunar_valves: str,
    note: str,
) -> CardiacCyclePhase:
    return CardiacCyclePhase(
        key=key,
        name=name,
        short_name=short_name,
        category=category,
        start_ms=float(start_ms),
        end_ms=float(end_ms),
        av_valves=av_valves,
        semilunar_valves=semilunar_valves,
        teaching_note=note,
    )


def ecg_informed_cycle_timing(
    recording: ECGGatingRecording, beat_index: int
) -> ECGMechanicalSync:
    """Build one QRS-gated cycle with reviewed electrical anchors.

    P/QRS offsets are reviewed on one dominant R-aligned median template and
    projected onto accepted R triggers. Valve events remain estimates unless
    the corresponding manual mechanical marker is present. T morphology is
    deliberately not used for synchronization.
    """

    beat = int(np.clip(beat_index, 0, max(0, recording.beat_count - 1)))
    start_s = recording.beat_start_time_s(beat)
    cycle_ms = recording.beat_duration_ms(beat)
    empirical = ecg_gated_cycle_timing(cycle_ms)
    sources: dict[str, str] = {}

    av_close = _manual_relative_ms(recording, "av_close_s1", beat, start_s)
    if av_close is not None:
        sources["av_close"] = "manual mechanical annotation"
        ivc_note = (
            f"Manual AV-close/S1 marker at {av_close:.0f} ms; ED geometry is held "
            "from the reviewed R trigger through the pre-ejection interval."
        )
    else:
        sources["av_close"] = "not measured; cycle begins at reviewed R trigger"
        ivc_note = "Estimated after the reviewed R trigger; direct AV closure requires PCG/echo."

    qrs_end = _relative_ms(recording, "qrs_offset", beat, start_s)
    manual = _manual_relative_ms(recording, "semilunar_open", beat, start_s)
    if manual is not None:
        semilunar_open = manual
        sources["semilunar_open"] = "manual mechanical annotation"
    else:
        qrs_anchor = qrs_end + 15.0 if qrs_end is not None else empirical.phase_by_key("rapid_ejection").start_ms
        semilunar_open = qrs_anchor
        sources["semilunar_open"] = "ECG-informed estimate"
    semilunar_open = float(np.clip(semilunar_open, 35.0, min(145.0, 0.24 * cycle_ms)))

    manual = _manual_relative_ms(recording, "semilunar_close_s2", beat, start_s)
    if manual is not None:
        systole_end = manual
        sources["semilunar_close"] = "manual mechanical annotation"
    else:
        systole_end = empirical.systole_ms
        sources["semilunar_close"] = "rate-model estimate"
    systole_end = float(np.clip(systole_end, semilunar_open + 120.0, 0.70 * cycle_ms))

    proto_start = systole_end - empirical.phase_by_key("protodiastole").duration_ms
    sources["protodiastole"] = "rate-model estimate"
    proto_start = float(np.clip(proto_start, semilunar_open + 80.0, systole_end - 18.0))
    rapid_end = semilunar_open + 0.46 * (proto_start - semilunar_open)

    manual = _manual_relative_ms(recording, "av_open", beat, start_s)
    if manual is not None:
        ivr_end = manual
        sources["av_open"] = "manual mechanical annotation"
    else:
        ivr_end = systole_end + empirical.phase_by_key("isovolumetric_relaxation").duration_ms
        sources["av_open"] = "ECG-informed rate estimate"
    ivr_end = float(np.clip(ivr_end, systole_end + 35.0, min(cycle_ms - 170.0, systole_end + 120.0)))

    manual = _manual_relative_ms(recording, "early_filling_end", beat, start_s)
    if manual is not None:
        rapid_fill_end = manual
        sources["rapid_filling_end"] = "manual mechanical annotation"
    else:
        rapid_fill_end = ivr_end + empirical.phase_by_key("rapid_filling").duration_ms
        sources["rapid_filling_end"] = "rate-model estimate"

    manual = _manual_relative_ms(recording, "atrial_mechanical_onset", beat, start_s)
    if manual is not None:
        atrial_start = manual
        sources["atrial_systole"] = "manual mechanical annotation"
    else:
        next_p = _relative_ms(recording, "p_onset", beat + 1, start_s)
        if next_p is not None:
            # Atrial contraction follows P-wave onset; 68 ms is a published
            # normal-subject mean, used only as a visibly labelled estimate.
            atrial_start = next_p + 68.0
            sources["atrial_systole"] = "estimated from next P onset + 68 ms"
        else:
            atrial_start = cycle_ms - empirical.phase_by_key("atrial_systole").duration_ms
            sources["atrial_systole"] = "rate-model estimate"

    atrial_start = float(np.clip(atrial_start, ivr_end + 50.0, cycle_ms - 25.0))
    rapid_fill_end = float(np.clip(rapid_fill_end, ivr_end + 45.0, atrial_start))

    phases = (
        _phase(
            "isovolumetric_contraction", "Isovolumetric contraction", "IVC", "systole",
            0.0, semilunar_open, "closed", "closed",
            ivc_note,
        ),
        _phase(
            "rapid_ejection", "Rapid ejection", "Rapid eject.", "systole",
            semilunar_open, rapid_end, "closed", "open",
            "Estimated ejection interval; semilunar opening is not measured by ECG.",
        ),
        _phase(
            "reduced_ejection", "Reduced ejection", "Reduced eject.", "systole",
            rapid_end, proto_start, "closed", "open",
            "Estimated late ejection from the rate-constrained mechanical model.",
        ),
        _phase(
            "protodiastole", "Protodiastole", "Proto-D", "systole",
            proto_start, systole_end, "closed", "closing",
            "Estimated pre-closure interval; valve closure requires PCG/echo.",
        ),
        _phase(
            "isovolumetric_relaxation", "Isovolumetric relaxation", "IVR", "diastole",
            systole_end, ivr_end, "closed", "closed",
            "Estimated from the ECG-informed end of systole and rate model.",
        ),
        _phase(
            "rapid_filling", "Rapid ventricular filling", "Rapid fill", "diastole",
            ivr_end, rapid_fill_end, "open", "closed",
            "Estimated filling interval; direct AV opening requires Doppler/echo.",
        ),
        _phase(
            "diastasis", "Diastasis (slow filling)", "Diastasis", "diastole",
            rapid_fill_end, atrial_start, "open", "closed",
            "Estimated low-flow interval between early filling and atrial contraction.",
        ),
        _phase(
            "atrial_systole", "Atrial systole (atrial kick)", "Atrial kick", "diastole",
            atrial_start, cycle_ms, "open then closing", "closed",
            "Estimated from reviewed P onset plus atrial electromechanical delay.",
        ),
    )
    timing = NormalAdultCycleTiming(
        heart_rate_bpm=60000.0 / cycle_ms,
        cycle_ms=cycle_ms,
        systole_ms=systole_end,
        diastole_ms=cycle_ms - systole_end,
        systolic_fraction=systole_end / cycle_ms,
        diastolic_fraction=1.0 - systole_end / cycle_ms,
        phases=phases,
    )
    return ECGMechanicalSync(
        timing=timing,
        boundary_sources=sources,
        reference=recording.cycle_reference_name,
    )
