"""Evidence-bounded normal-adult cardiac-cycle timing.

The bundled CT statistical model supplies ED-to-ES-to-ED geometry, not valve-event
timestamps. This module therefore keeps measured evidence and pedagogic allocation
separate: Bachani et al. constrain total mechanical systole/diastole, while the
within-cycle phases are an explicit normal-adult teaching model. Chung et al.
support the rate response used here: early and atrial filling change relatively
little with rate, whereas diastasis is preferentially lost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache


TIMING_MODEL_NAME = "Normal-adult echo-constrained phase teaching model"
TIMING_MODEL_DOIS = (
    "10.1016/j.ihj.2025.02.005",
    "10.1152/ajpheart.00404.2004",
)
MIN_SUPPORTED_HEART_RATE = 60
MAX_SUPPORTED_HEART_RATE = 100


@dataclass(frozen=True)
class CardiacCyclePhase:
    """One estimated mechanical phase within a normal-adult cardiac cycle."""

    key: str
    name: str
    short_name: str
    category: str
    start_ms: float
    end_ms: float
    av_valves: str
    semilunar_valves: str
    teaching_note: str

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class NormalAdultCycleTiming:
    """Mechanical cycle timing for the supported resting-rate range."""

    heart_rate_bpm: float
    cycle_ms: float
    systole_ms: float
    diastole_ms: float
    systolic_fraction: float
    diastolic_fraction: float
    phases: tuple[CardiacCyclePhase, ...]

    def phase_by_key(self, key: str) -> CardiacCyclePhase:
        for phase in self.phases:
            if phase.key == key:
                return phase
        raise KeyError(key)

    def phase_at_fraction(
        self, cycle_fraction: float
    ) -> tuple[CardiacCyclePhase, float]:
        """Return the phase and its local 0--1 progress at a cycle fraction."""

        elapsed_ms = (float(cycle_fraction) % 1.0) * self.cycle_ms
        for index, phase in enumerate(self.phases):
            if elapsed_ms < phase.end_ms or index == len(self.phases) - 1:
                local = (elapsed_ms - phase.start_ms) / max(phase.duration_ms, 1e-9)
                return phase, min(1.0, max(0.0, local))
        return self.phases[-1], 1.0


def healthy_adult_diastolic_fraction(heart_rate_bpm: int) -> float:
    """Estimate mechanical-diastolic fraction from observed healthy-adult bins.

    Bachani et al. measured a 0.61 mean fraction at 60--70 bpm and 0.53
    above 90 bpm. The unreported interval between those bins is explicitly
    linearly interpolated. Values outside the study-supported 60--100 bpm
    range are rejected rather than extrapolated.
    """

    heart_rate = int(heart_rate_bpm)
    if not MIN_SUPPORTED_HEART_RATE <= heart_rate <= MAX_SUPPORTED_HEART_RATE:
        raise ValueError(
            f"Heart rate must be {MIN_SUPPORTED_HEART_RATE}--"
            f"{MAX_SUPPORTED_HEART_RATE} bpm for this timing model"
        )
    if heart_rate <= 70:
        return 0.61
    if heart_rate >= 90:
        return 0.53
    return 0.61 - (heart_rate - 70) * (0.08 / 20.0)


def _phase(
    key: str,
    name: str,
    short_name: str,
    category: str,
    start_ms: float,
    duration_ms: float,
    av_valves: str,
    semilunar_valves: str,
    teaching_note: str,
) -> CardiacCyclePhase:
    return CardiacCyclePhase(
        key=key,
        name=name,
        short_name=short_name,
        category=category,
        start_ms=float(start_ms),
        end_ms=float(start_ms + duration_ms),
        av_valves=av_valves,
        semilunar_valves=semilunar_valves,
        teaching_note=teaching_note,
    )


def _build_phases(
    heart_rate: int, cycle_ms: float, systole_ms: float, diastole_ms: float
) -> tuple[CardiacCyclePhase, ...]:
    """Allocate total timing to eight explicitly approximate teaching phases."""

    # At 60 bpm the illustrative systolic allocation is 50/120/180/40 ms.
    # Subdivisions scale together because this dataset has no valve-event ECG.
    systolic_weights = (50.0, 120.0, 180.0, 40.0)
    systolic_scale = systole_ms / sum(systolic_weights)
    ivc_ms, rapid_ejection_ms, reduced_ejection_ms, protodiastole_ms = (
        value * systolic_scale for value in systolic_weights
    )

    # Chung et al. found that E- and A-wave durations are comparatively resistant
    # to increased HR and that diastasis absorbs most of the shortening.
    rate_fraction = (heart_rate - MIN_SUPPORTED_HEART_RATE) / (
        MAX_SUPPORTED_HEART_RATE - MIN_SUPPORTED_HEART_RATE
    )
    ivr_ms = 80.0 - 15.0 * rate_fraction
    rapid_filling_ms = 180.0 * (1.0 - 0.12 * rate_fraction)
    atrial_systole_ms = 100.0 * (1.0 - 0.11 * rate_fraction)
    diastasis_ms = diastole_ms - ivr_ms - rapid_filling_ms - atrial_systole_ms
    if diastasis_ms < 0.0:
        fixed = ivr_ms + rapid_filling_ms + atrial_systole_ms
        scale = diastole_ms / fixed
        ivr_ms *= scale
        rapid_filling_ms *= scale
        atrial_systole_ms *= scale
        diastasis_ms = 0.0

    phases: list[CardiacCyclePhase] = []
    cursor = 0.0

    def append(*args):
        nonlocal cursor
        phase = _phase(*args[:4], cursor, *args[4:])
        phases.append(phase)
        cursor = phase.end_ms

    append(
        "isovolumetric_contraction", "Isovolumetric contraction", "IVC", "systole",
        ivc_ms, "closed", "closed",
        "AV valves have closed; ventricular pressure rises while model volume is held at ED.",
    )
    append(
        "rapid_ejection", "Rapid ejection", "Rapid eject.", "systole",
        rapid_ejection_ms, "closed", "open",
        "Semilunar valves open and most early ventricular ejection occurs.",
    )
    append(
        "reduced_ejection", "Reduced ejection", "Reduced eject.", "systole",
        reduced_ejection_ms, "closed", "open",
        "Ventricular outflow continues at a lower rate as the model approaches ES.",
    )
    append(
        "protodiastole", "Protodiastole", "Protodiastole", "systole",
        protodiastole_ms, "closed", "closing",
        "Forward ejection ends and the semilunar leaflets move toward closure.",
    )
    append(
        "isovolumetric_relaxation", "Isovolumetric relaxation", "IVR", "diastole",
        ivr_ms, "closed", "closed",
        "All valves are closed while ventricular pressure falls; model volume is held at ES.",
    )
    append(
        "rapid_filling", "Rapid ventricular filling", "Rapid fill", "diastole",
        rapid_filling_ms, "open", "closed",
        "AV valves open and the early filling wave returns most of the ED geometry.",
    )
    append(
        "diastasis", "Diastasis (slow filling)", "Diastasis", "diastole",
        diastasis_ms, "open", "closed",
        "Atrial and ventricular pressures nearly equilibrate; this interval is preferentially lost as HR rises.",
    )
    append(
        "atrial_systole", "Atrial systole (atrial kick)", "Atrial kick", "diastole",
        atrial_systole_ms, "open then closing", "closed",
        "Atrial contraction completes ventricular filling before the next AV-valve closure.",
    )

    last = phases[-1]
    phases[-1] = CardiacCyclePhase(**{**last.__dict__, "end_ms": float(cycle_ms)})
    return tuple(phases)


@lru_cache(maxsize=64)
def healthy_adult_cycle_timing(heart_rate_bpm: int) -> NormalAdultCycleTiming:
    """Return cycle, systolic, diastolic and phase durations in milliseconds."""

    heart_rate = int(heart_rate_bpm)
    diastolic_fraction = healthy_adult_diastolic_fraction(heart_rate)
    systolic_fraction = 1.0 - diastolic_fraction
    cycle_ms = 60000.0 / heart_rate
    systole_ms = cycle_ms * systolic_fraction
    diastole_ms = cycle_ms * diastolic_fraction
    return NormalAdultCycleTiming(
        heart_rate_bpm=heart_rate,
        cycle_ms=cycle_ms,
        systole_ms=systole_ms,
        diastole_ms=diastole_ms,
        systolic_fraction=systolic_fraction,
        diastolic_fraction=diastolic_fraction,
        phases=_build_phases(heart_rate, cycle_ms, systole_ms, diastole_ms),
    )


def ecg_gated_cycle_timing(rr_ms: float) -> NormalAdultCycleTiming:
    """Return an exact R--R cycle with evidence-bounded phase allocation.

    The measured R--R duration is preserved exactly.  When the instantaneous
    rate falls outside the 60--100 bpm range supported by the bundled adult
    timing evidence, phase *proportions* are limited to the nearest supported
    boundary instead of being extrapolated.  This affects only the teaching
    overlay; it does not alter the ECG or claim measured valve events.
    """

    duration_ms = float(rr_ms)
    if not math.isfinite(duration_ms) or duration_ms <= 0.0:
        raise ValueError("R–R duration must be a positive finite number")
    actual_rate = 60000.0 / duration_ms
    reference_rate = int(
        round(min(MAX_SUPPORTED_HEART_RATE, max(MIN_SUPPORTED_HEART_RATE, actual_rate)))
    )
    diastolic_fraction = healthy_adult_diastolic_fraction(reference_rate)
    systolic_fraction = 1.0 - diastolic_fraction
    systole_ms = duration_ms * systolic_fraction
    diastole_ms = duration_ms * diastolic_fraction
    return NormalAdultCycleTiming(
        heart_rate_bpm=actual_rate,
        cycle_ms=duration_ms,
        systole_ms=systole_ms,
        diastole_ms=diastole_ms,
        systolic_fraction=systolic_fraction,
        diastolic_fraction=diastolic_fraction,
        phases=_build_phases(reference_rate, duration_ms, systole_ms, diastole_ms),
    )


def _return_motion_progress(phase_key: str, local_fraction: float) -> float:
    local = min(1.0, max(0.0, float(local_fraction)))
    if phase_key == "rapid_filling":
        return 0.78 * local
    if phase_key == "diastasis":
        return 0.78 + 0.12 * local
    if phase_key == "atrial_systole":
        return 0.90 + 0.10 * local
    return 0.0


def motion_phase_from_time_phase(
    time_phase: float,
    heart_rate_bpm: int,
    model_end_systole_phase: float,
) -> float:
    """Map elapsed time to stored ED-to-ES-to-ED motion by physiological phase."""

    timing = healthy_adult_cycle_timing(heart_rate_bpm)
    return motion_phase_from_timing(time_phase, timing, model_end_systole_phase)


def motion_phase_from_timing(
    time_phase: float,
    timing: NormalAdultCycleTiming,
    model_end_systole_phase: float,
) -> float:
    """Map elapsed time through an explicitly supplied mechanical timing model."""

    phase, local = timing.phase_at_fraction(time_phase)
    model_es = float(model_end_systole_phase)
    if not 0.0 < model_es < 1.0:
        raise ValueError("Model end-systole phase must be between zero and one")
    if phase.key == "isovolumetric_contraction":
        return 0.0
    if phase.key in {"rapid_ejection", "reduced_ejection"}:
        start = timing.phase_by_key("rapid_ejection").start_ms
        end = timing.phase_by_key("reduced_ejection").end_ms
        elapsed = (float(time_phase) % 1.0) * timing.cycle_ms
        return model_es * min(1.0, max(0.0, (elapsed - start) / (end - start)))
    if phase.key in {"protodiastole", "isovolumetric_relaxation"}:
        return model_es
    return model_es + (1.0 - model_es) * _return_motion_progress(phase.key, local)


def time_phase_from_motion_phase(
    motion_phase: float,
    heart_rate_bpm: int,
    model_end_systole_phase: float,
) -> float:
    """Map a source position to one canonical time despite isovolumetric plateaus."""

    timing = healthy_adult_cycle_timing(heart_rate_bpm)
    return time_phase_from_timing(motion_phase, timing, model_end_systole_phase)


def time_phase_from_timing(
    motion_phase: float,
    timing: NormalAdultCycleTiming,
    model_end_systole_phase: float,
) -> float:
    """Map source motion to canonical time for an explicitly supplied timing model."""

    motion = float(motion_phase) % 1.0
    model_es = float(model_end_systole_phase)
    if not 0.0 < model_es < 1.0:
        raise ValueError("Model end-systole phase must be between zero and one")
    if motion <= 1e-9:
        return 0.0
    if motion < model_es:
        start = timing.phase_by_key("rapid_ejection").start_ms
        end = timing.phase_by_key("reduced_ejection").end_ms
        return (start + (motion / model_es) * (end - start)) / timing.cycle_ms
    if abs(motion - model_es) <= 1e-9:
        return timing.phase_by_key("protodiastole").end_ms / timing.cycle_ms
    progress = (motion - model_es) / (1.0 - model_es)
    rapid = timing.phase_by_key("rapid_filling")
    diastasis = timing.phase_by_key("diastasis")
    atrial = timing.phase_by_key("atrial_systole")
    if progress <= 0.78:
        elapsed = rapid.start_ms + (progress / 0.78) * rapid.duration_ms
    elif progress <= 0.90:
        elapsed = diastasis.start_ms + ((progress - 0.78) / 0.12) * diastasis.duration_ms
    else:
        elapsed = atrial.start_ms + ((progress - 0.90) / 0.10) * atrial.duration_ms
    return min(elapsed / timing.cycle_ms, 1.0 - 1e-12)


def valve_open_fraction(
    valve_label: int, time_phase: float, heart_rate_bpm: int
) -> float:
    """Return a smooth 0--1 pedagogic opening state for an atlas valve mesh."""

    label = int(valve_label)
    if label not in {12, 13, 14, 15}:
        return 0.0
    timing = healthy_adult_cycle_timing(heart_rate_bpm)
    phase, local = timing.phase_at_fraction(time_phase)

    def smooth(value: float) -> float:
        value = min(1.0, max(0.0, value))
        return value * value * (3.0 - 2.0 * value)

    if label in {12, 13}:
        if phase.key == "rapid_filling":
            return smooth(local / 0.18)
        if phase.key == "diastasis":
            return 1.0
        if phase.key == "atrial_systole":
            return 1.0 if local <= 0.82 else smooth((1.0 - local) / 0.18)
        return 0.0
    if phase.key == "rapid_ejection":
        return smooth(local / 0.18)
    if phase.key == "reduced_ejection":
        return 1.0
    if phase.key == "protodiastole":
        return smooth(1.0 - local)
    return 0.0


def valve_state_summary(time_phase: float, heart_rate_bpm: int) -> str:
    timing = healthy_adult_cycle_timing(heart_rate_bpm)
    phase, _ = timing.phase_at_fraction(time_phase)
    return f"AV valves {phase.av_valves} • semilunar valves {phase.semilunar_valves}"
