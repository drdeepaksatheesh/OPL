"""Reviewable ECG landmark suggestions and sidecar annotation support.

The detector is intentionally conservative.  It proposes electrical landmarks
from the filtered review trace; it does not diagnose rhythm or claim that an ECG
directly measures valve motion.  Users may correct every marker and may add
separately-labelled mechanical observations from PCG/echo.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


LANDMARK_SPECS = {
    "p_onset": ("P onset", "#74D3AE", "electrical"),
    "p_peak": ("P peak", "#48C9A5", "electrical"),
    "qrs_onset": ("QRS onset", "#FFD166", "electrical"),
    "r_peak": ("R peak", "#F5C542", "electrical"),
    "qrs_offset": ("QRS end", "#FFB347", "electrical"),
    "t_peak": ("T peak", "#7DB7FF", "electrical"),
    "t_end": ("T end", "#A88BFF", "electrical"),
    "av_close_s1": ("AV close / S1", "#FF7A7A", "mechanical"),
    "semilunar_open": ("Semilunar open", "#FF9A62", "mechanical"),
    "semilunar_close_s2": ("Semilunar close / S2", "#E46C9A", "mechanical"),
    "av_open": ("AV open", "#31C5C7", "mechanical"),
    "early_filling_end": ("Early filling end", "#56C596", "mechanical"),
    "atrial_mechanical_onset": ("Atrial contraction onset", "#C58BE2", "mechanical"),
}

# T-wave labels remain in ``LANDMARK_SPECS`` only so older sidecars can be
# opened without failing.  They are deliberately excluded from review and
# synchronization: a single noisy lead is not a reliable basis for projecting
# per-beat T delineation onto a statistical mechanical model.
ELECTRICAL_KINDS = (
    "p_onset",
    "p_peak",
    "qrs_onset",
    "r_peak",
    "qrs_offset",
)
TEMPLATE_EDITABLE_KINDS = (
    "p_onset",
    "p_peak",
    "qrs_onset",
    "qrs_offset",
)
LEGACY_T_KINDS = ("t_peak", "t_end")
MECHANICAL_KINDS = tuple(
    key for key, (_, _, group) in LANDMARK_SPECS.items() if group == "mechanical"
)


@dataclass
class ECGLandmark:
    kind: str
    sample_index: int
    beat_index: int
    source: str = "automatic"
    confidence: float = 0.0
    note: str = ""

    @property
    def group(self) -> str:
        return LANDMARK_SPECS.get(self.kind, (self.kind, "#FFFFFF", "unknown"))[2]

    @property
    def label(self) -> str:
        return LANDMARK_SPECS.get(self.kind, (self.kind, "#FFFFFF", "unknown"))[0]


@dataclass
class ECGMedianTemplate:
    """Dominant R-aligned morphology used for P/QRS review.

    Each accepted complex is baseline-corrected and scaled by its QRS
    amplitude before the sample-wise median and interquartile envelope are
    calculated.  The original ECG and every accepted R marker remain intact.
    """

    offsets_s: np.ndarray
    median_signal: np.ndarray
    lower_signal: np.ndarray
    upper_signal: np.ndarray
    included_beat_indices: tuple[int, ...]
    excluded_beat_indices: tuple[int, ...]
    landmark_offsets_s: dict[str, float]
    landmark_sources: dict[str, str]

    def offset(self, kind: str) -> float | None:
        value = self.landmark_offsets_s.get(str(kind))
        return None if value is None else float(value)


def _moving_average(values: np.ndarray, width: int) -> np.ndarray:
    width = max(1, int(width))
    if width == 1:
        return np.asarray(values, dtype=float)
    kernel = np.ones(width, dtype=float) / float(width)
    return np.convolve(np.asarray(values, dtype=float), kernel, mode="same")


def _robust_mad(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return 0.0
    centre = float(np.median(values))
    return float(np.median(np.abs(values - centre)) * 1.4826)


def _t_wave_landmarks(
    signal: np.ndarray,
    t_trace: np.ndarray,
    qrs_onset: int,
    qrs_offset: int,
    r_peak: int,
    next_r: int,
    fs_hz: float,
) -> tuple[int, int, float, float, str] | None:
    """Return conservative RR-aware T peak/end suggestions.

    The T-wave trace is deliberately smoother than the review trace. Peak
    selection is constrained by an RR-scaled QT prior, while T end uses the
    intersection of the steepest terminal-limb tangent with the pre-QRS
    isoelectric baseline. This prevents late noise, U waves, or the following
    P wave from being labelled confidently as T activity.
    """

    n = len(t_trace)
    rr_s = float(np.clip((int(next_r) - int(r_peak)) / fs_hz, 0.35, 2.0))
    # A neutral teaching prior, not a QT diagnosis or correction formula.
    # Cube-root RR scaling only defines a conservative search window.
    expected_qt_s = float(np.clip(0.405 * np.cbrt(rr_s), 0.28, 0.48))
    t_start = max(
        int(qrs_offset) + int(round(0.045 * fs_hz)),
        int(qrs_onset) + int(round(0.100 * fs_hz)),
    )
    t_peak_stop = min(
        int(qrs_onset) + int(round(0.90 * expected_qt_s * fs_hz)),
        int(next_r) - int(round(0.180 * fs_hz)),
        n - 2,
    )
    if t_peak_stop - t_start < int(round(0.080 * fs_hz)):
        return None

    baseline_start = max(0, int(qrs_onset) - int(round(0.040 * fs_hz)))
    baseline_stop = max(baseline_start + 2, int(qrs_onset) - int(round(0.008 * fs_hz)))
    baseline_segment = t_trace[baseline_start:baseline_stop]
    baseline = float(np.median(baseline_segment))
    residual = signal[t_start:t_peak_stop] - t_trace[t_start:t_peak_stop]
    noise = max(
        _robust_mad(baseline_segment),
        0.35 * _robust_mad(residual),
        np.finfo(float).eps,
    )

    local = t_trace[t_start:t_peak_stop]
    deviation = np.abs(local - baseline)
    expected_peak = int(qrs_onset) + int(round(0.62 * expected_qt_s * fs_hz))
    indices = np.arange(t_start, t_peak_stop, dtype=float)
    sigma = max(0.060 * fs_hz, 0.22 * expected_qt_s * fs_hz)
    timing_prior = np.exp(-0.5 * ((indices - expected_peak) / sigma) ** 2)
    # Keep a small prior floor so unusual morphology is not forbidden, while
    # strongly disfavoring late baseline drift and following atrial activity.
    score = deviation * (0.15 + 0.85 * timing_prior)
    if len(score) > 4:
        local_maximum = np.r_[
            False,
            (deviation[1:-1] >= deviation[:-2]) & (deviation[1:-1] >= deviation[2:]),
            False,
        ]
        candidates = np.flatnonzero(local_maximum)
        peak_local = int(candidates[np.argmax(score[candidates])]) if len(candidates) else int(np.argmax(score))
    else:
        peak_local = int(np.argmax(score))
    t_peak = int(t_start + peak_local)
    amplitude = float(deviation[peak_local])
    snr = amplitude / noise

    half_height = 0.50 * amplitude
    left = peak_local
    right = peak_local
    while left > 0 and deviation[left - 1] >= half_height:
        left -= 1
    while right + 1 < len(deviation) and deviation[right + 1] >= half_height:
        right += 1
    half_width_s = float((right - left + 1) / fs_hz)
    width_score = float(np.clip((half_width_s - 0.020) / 0.070, 0.0, 1.0))
    snr_score = float(np.clip((snr - 2.0) / 6.0, 0.0, 1.0))
    timing_score = float(timing_prior[peak_local])
    peak_confidence = float(
        np.clip(0.55 * snr_score + 0.25 * timing_score + 0.20 * width_score, 0.0, 1.0)
    )
    # A faint local extremum in the expected time range is not sufficient.
    # If morphology/timing confidence remains below the review threshold,
    # omit the automatic T pair and let the user place it manually.
    if snr < 2.4 or peak_confidence < 0.45:
        return None

    end_cap = min(
        int(qrs_onset) + int(round(1.22 * expected_qt_s * fs_hz)),
        int(next_r) - int(round(0.160 * fs_hz)),
        n - 2,
    )
    end_search_start = t_peak + int(round(0.020 * fs_hz))
    if end_cap - end_search_start < int(round(0.035 * fs_hz)):
        return None

    polarity = 1.0 if float(t_trace[t_peak]) >= baseline else -1.0
    derivative = np.gradient(t_trace)
    terminal = -polarity * derivative[end_search_start:end_cap]
    slope_local = int(np.argmax(terminal))
    slope_index = int(end_search_start + slope_local)
    slope = float(derivative[slope_index])
    slope_noise = max(_robust_mad(np.gradient(baseline_segment)), np.finfo(float).eps)
    slope_snr = float(max(0.0, terminal[slope_local]) / slope_noise)

    tangent_end = np.nan
    if abs(slope) > np.finfo(float).eps and -polarity * slope > 0:
        tangent_end = slope_index + (baseline - float(t_trace[slope_index])) / slope
    minimum_end = t_peak + int(round(0.035 * fs_hz))
    tangent_valid = bool(np.isfinite(tangent_end) and minimum_end <= tangent_end <= end_cap)

    threshold = max(0.12 * amplitude, 2.5 * noise)
    hold = max(2, int(round(0.018 * fs_hz)))
    threshold_end = None
    threshold_start = t_peak + int(round(0.045 * fs_hz))
    for index in range(threshold_start, max(threshold_start, end_cap - hold)):
        if np.all(np.abs(t_trace[index : index + hold] - baseline) <= threshold):
            threshold_end = int(index)
            break

    if tangent_valid:
        t_end = int(round(float(tangent_end)))
        method = "terminal-limb tangent"
        slope_score = float(np.clip((slope_snr - 2.0) / 8.0, 0.0, 1.0))
        end_confidence = float(
            np.clip(0.70 * peak_confidence + 0.30 * slope_score, 0.0, 1.0)
        )
    elif threshold_end is not None:
        t_end = int(threshold_end)
        method = "sustained baseline return"
        end_confidence = float(0.65 * peak_confidence)
    else:
        # Never manufacture a T end at the edge of the allowed window.
        return None

    note = f"automatic {method} suggestion"
    if min(peak_confidence, end_confidence) < 0.45:
        note += "; low confidence — manual review required"
    return t_peak, t_end, peak_confidence, end_confidence, note


def _qrs_bounds(signal: np.ndarray, r: int, fs_hz: float) -> tuple[int, int, float]:
    """Estimate QRS bounds from a short-time derivative envelope."""

    n = len(signal)
    left = max(1, r - int(round(0.18 * fs_hz)))
    right = min(n - 2, r + int(round(0.20 * fs_hz)))
    derivative = np.abs(np.gradient(signal))
    envelope = _moving_average(derivative, max(1, int(round(0.010 * fs_hz))))
    local = envelope[left : right + 1]
    peak = float(np.max(local)) if len(local) else 0.0
    quiet_parts = np.r_[
        envelope[left : max(left, r - int(round(0.10 * fs_hz)))],
        envelope[min(right, r + int(round(0.12 * fs_hz))) : right + 1],
    ]
    quiet = float(np.median(quiet_parts)) if len(quiet_parts) else 0.0
    mad = float(np.median(np.abs(quiet_parts - quiet)) * 1.4826) if len(quiet_parts) else 0.0
    threshold = max(quiet + 2.5 * mad, 0.075 * peak)
    hold = max(2, int(round(0.012 * fs_hz)))

    onset = left
    for index in range(r - hold, left + hold, -1):
        if np.all(envelope[index - hold : index] <= threshold):
            onset = index
            break
    offset = right
    for index in range(r + hold, right - hold):
        if np.all(envelope[index : index + hold] <= threshold):
            offset = index
            break
    if offset - onset < int(round(0.045 * fs_hz)):
        onset = max(left, r - int(round(0.045 * fs_hz)))
        offset = min(right, r + int(round(0.055 * fs_hz)))
    confidence = float(np.clip((peak - quiet) / max(peak, np.finfo(float).eps), 0.0, 1.0))
    return int(onset), int(offset), confidence


def _dominant_deviation(signal: np.ndarray, start: int, stop: int) -> tuple[int, float]:
    start = max(0, int(start))
    stop = min(len(signal), int(stop))
    if stop - start < 3:
        return start, 0.0
    local = np.asarray(signal[start:stop], dtype=float)
    baseline = float(np.median(np.r_[local[: max(1, len(local) // 8)], local[-max(1, len(local) // 8) :]]))
    deviation = np.abs(local - baseline)
    peak_local = int(np.argmax(deviation))
    robust = float(np.median(np.abs(local - np.median(local))) * 1.4826)
    confidence = float(np.clip(deviation[peak_local] / max(6.0 * robust, np.finfo(float).eps), 0.0, 1.0))
    return start + peak_local, confidence


def _wave_onset(signal: np.ndarray, peak: int, start: int, fs_hz: float) -> int:
    start = max(0, int(start))
    peak = int(np.clip(peak, start, len(signal) - 1))
    baseline = float(np.median(signal[start : max(start + 1, peak - int(round(0.03 * fs_hz)))]))
    amplitude = abs(float(signal[peak]) - baseline)
    threshold = max(0.10 * amplitude, np.finfo(float).eps)
    hold = max(2, int(round(0.012 * fs_hz)))
    onset = start
    for index in range(peak - hold, start + hold, -1):
        if np.all(np.abs(signal[index - hold : index] - baseline) <= threshold):
            onset = index
            break
    # A single baseline excursion must not make one P wave consume most of the
    # preceding R-R interval. The limit remains deliberately generous.
    return int(max(onset, peak - int(round(0.14 * fs_hz))))


def _wave_end(signal: np.ndarray, peak: int, stop: int, fs_hz: float) -> int:
    stop = min(len(signal) - 1, int(stop))
    peak = int(np.clip(peak, 0, stop))
    tail_start = max(peak + 1, stop - max(2, int(round(0.06 * fs_hz))))
    baseline = float(np.median(signal[tail_start : stop + 1]))
    amplitude = abs(float(signal[peak]) - baseline)
    threshold = max(0.12 * amplitude, np.finfo(float).eps)
    hold = max(2, int(round(0.016 * fs_hz)))
    end = stop
    search_start = peak + max(hold, int(round(0.09 * fs_hz)))
    for index in range(search_start, stop - hold):
        if np.all(np.abs(signal[index : index + hold] - baseline) <= threshold):
            end = index
            break
    return int(end)


def build_median_template(
    filtered_signal: np.ndarray,
    r_peaks: Iterable[int],
    fs_hz: float,
    pre_r_s: float = 0.30,
    post_r_s: float = 0.45,
) -> ECGMedianTemplate:
    """Build a robust dominant R-aligned template and P/QRS suggestions.

    A sample-wise median is preferable to a simple average because a few
    ectopic or movement-contaminated complexes cannot pull the representative
    waveform toward themselves.  Morphology screening is intentionally based
    on the QRS neighbourhood; slower P-wave variation is preserved in the IQR
    envelope instead of being used to reject otherwise valid beats.
    """

    signal = np.asarray(filtered_signal, dtype=float)
    peaks = np.asarray(list(r_peaks), dtype=int)
    if len(signal) < 3 or len(peaks) < 1 or fs_hz <= 0:
        raise ValueError("A filtered ECG and at least one R marker are required.")
    pre = max(1, int(round(float(pre_r_s) * fs_hz)))
    post = max(1, int(round(float(post_r_s) * fs_hz)))
    offsets_s = np.arange(-pre, post + 1, dtype=float) / float(fs_hz)
    rows: list[np.ndarray] = []
    beat_indices: list[int] = []
    qrs_left = pre - int(round(0.12 * fs_hz))
    qrs_right = pre + int(round(0.16 * fs_hz)) + 1
    baseline_stop = max(2, int(round(0.055 * fs_hz)))

    for beat_index, r_peak in enumerate(peaks):
        start, stop = int(r_peak) - pre, int(r_peak) + post + 1
        if start < 0 or stop > len(signal):
            continue
        row = np.asarray(signal[start:stop], dtype=float).copy()
        if len(row) != len(offsets_s) or not np.all(np.isfinite(row)):
            continue
        row -= float(np.median(row[:baseline_stop]))
        qrs = row[max(0, qrs_left) : min(len(row), qrs_right)]
        scale = float(np.percentile(qrs, 99) - np.percentile(qrs, 1)) if len(qrs) else 0.0
        if not np.isfinite(scale) or scale <= np.finfo(float).eps:
            continue
        rows.append(row / scale)
        beat_indices.append(int(beat_index))

    if not rows:
        raise ValueError("No complete R-aligned complexes are available for a template.")
    matrix = np.vstack(rows)
    preliminary = np.median(matrix, axis=0)
    focus = slice(max(0, qrs_left), min(matrix.shape[1], qrs_right))
    reference = preliminary[focus] - float(np.mean(preliminary[focus]))
    reference_norm = float(np.linalg.norm(reference))
    correlations = np.ones(matrix.shape[0], dtype=float)
    if matrix.shape[0] >= 4 and reference_norm > np.finfo(float).eps:
        for index, row in enumerate(matrix):
            candidate = row[focus] - float(np.mean(row[focus]))
            denominator = float(np.linalg.norm(candidate) * reference_norm)
            correlations[index] = (
                float(np.dot(candidate, reference) / denominator)
                if denominator > np.finfo(float).eps
                else -1.0
            )
        centre = float(np.median(correlations))
        spread = _robust_mad(correlations)
        threshold = max(0.55, centre - max(0.08, 3.0 * spread))
        accepted = np.flatnonzero(correlations >= threshold)
        minimum = min(matrix.shape[0], max(3, int(np.ceil(0.60 * matrix.shape[0]))))
        if len(accepted) < minimum:
            accepted = np.argsort(correlations)[-minimum:]
    else:
        accepted = np.arange(matrix.shape[0], dtype=int)

    accepted = np.asarray(sorted(int(value) for value in accepted), dtype=int)
    included_rows = matrix[accepted]
    included = tuple(int(beat_indices[index]) for index in accepted)
    included_set = set(included)
    excluded = tuple(int(index) for index in range(len(peaks)) if int(index) not in included_set)
    median_signal = np.median(included_rows, axis=0)
    lower_signal = np.percentile(included_rows, 25.0, axis=0)
    upper_signal = np.percentile(included_rows, 75.0, axis=0)

    r_index = pre
    qrs_onset, qrs_offset, _confidence = _qrs_bounds(median_signal, r_index, fs_hz)
    landmark_offsets_s: dict[str, float] = {
        "qrs_onset": (qrs_onset - r_index) / float(fs_hz),
        "r_peak": 0.0,
        "qrs_offset": (qrs_offset - r_index) / float(fs_hz),
    }
    p_start = max(0, r_index - int(round(0.30 * fs_hz)))
    p_stop = qrs_onset - int(round(0.045 * fs_hz))
    if p_stop - p_start >= int(round(0.050 * fs_hz)):
        p_peak, _p_confidence = _dominant_deviation(median_signal, p_start, p_stop)
        p_onset = _wave_onset(median_signal, p_peak, p_start, fs_hz)
        landmark_offsets_s.update(
            {
                "p_onset": (p_onset - r_index) / float(fs_hz),
                "p_peak": (p_peak - r_index) / float(fs_hz),
            }
        )
    landmark_sources = {kind: "template_automatic" for kind in landmark_offsets_s}
    return ECGMedianTemplate(
        offsets_s=offsets_s,
        median_signal=np.asarray(median_signal, dtype=float),
        lower_signal=np.asarray(lower_signal, dtype=float),
        upper_signal=np.asarray(upper_signal, dtype=float),
        included_beat_indices=included,
        excluded_beat_indices=excluded,
        landmark_offsets_s=landmark_offsets_s,
        landmark_sources=landmark_sources,
    )


def project_template_landmarks(
    template: ECGMedianTemplate,
    r_peaks: Iterable[int],
    fs_hz: float,
    sample_count: int,
) -> list[ECGLandmark]:
    """Project reviewed template offsets onto every accepted R marker."""

    suggestions: list[ECGLandmark] = []
    for beat_index, r_peak in enumerate(np.asarray(list(r_peaks), dtype=int)):
        for kind in ELECTRICAL_KINDS:
            offset_s = template.offset(kind)
            if offset_s is None:
                continue
            sample = int(round(int(r_peak) + offset_s * fs_hz))
            if not 0 <= sample < int(sample_count):
                continue
            source = template.landmark_sources.get(kind, "template_automatic")
            suggestions.append(
                ECGLandmark(
                    kind=kind,
                    sample_index=sample,
                    beat_index=int(beat_index),
                    source=source,
                    confidence=1.0 if source == "template_reviewed" else 0.75,
                    note="R-aligned median-template projection; not independently measured on this beat",
                )
            )
    return sorted(suggestions, key=lambda item: (item.sample_index, item.kind))


def suggest_landmarks(
    filtered_signal: np.ndarray,
    r_peaks: Iterable[int],
    fs_hz: float,
    template: ECGMedianTemplate | None = None,
) -> list[ECGLandmark]:
    """Return median-template P/QRS projections; never delineate T waves."""

    signal = np.asarray(filtered_signal, dtype=float)
    peaks = np.asarray(list(r_peaks), dtype=int)
    if template is None:
        template = build_median_template(signal, peaks, fs_hz)
    return project_template_landmarks(template, peaks, fs_hz, len(signal))


def annotation_payload(
    source_sha256: str,
    fs_hz: float,
    channel_name: str,
    landmarks: Iterable[ECGLandmark],
    template: ECGMedianTemplate | None = None,
) -> dict:
    payload = {
        "schema": "open-4d-cardiac-anatomy-ecg-annotations-v1",
        "source_sha256": str(source_sha256),
        "sampling_rate_hz": float(fs_hz),
        "channel_name": str(channel_name),
        "landmarks": [asdict(item) for item in landmarks],
        "interpretation": (
            "P/QRS offsets are reviewed on an R-aligned median template and projected "
            "onto accepted R peaks. Mechanical markers are manual observations or "
            "rate-model estimates, not ECG measurements. T waves are not delineated."
        ),
    }
    if template is not None:
        payload["median_template"] = {
            "landmark_offsets_s": {
                kind: float(value)
                for kind, value in template.landmark_offsets_s.items()
                if kind in ELECTRICAL_KINDS
            },
            "landmark_sources": {
                kind: str(template.landmark_sources.get(kind, "template_automatic"))
                for kind in template.landmark_offsets_s
                if kind in ELECTRICAL_KINDS
            },
            "included_beat_indices": list(template.included_beat_indices),
            "excluded_beat_indices": list(template.excluded_beat_indices),
        }
    return payload


def save_annotation_sidecar(path: Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_annotation_sidecar(path: Path) -> tuple[dict, list[ECGLandmark]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != "open-4d-cardiac-anatomy-ecg-annotations-v1":
        raise ValueError("This is not a supported Open 4D ECG annotation sidecar.")
    landmarks = []
    for item in payload.get("landmarks", []):
        kind = str(item.get("kind", ""))
        if kind not in LANDMARK_SPECS:
            continue
        landmarks.append(
            ECGLandmark(
                kind=kind,
                sample_index=int(item["sample_index"]),
                beat_index=int(item.get("beat_index", 0)),
                source=str(item.get("source", "manual")),
                confidence=float(item.get("confidence", 0.0)),
                note=str(item.get("note", "")),
            )
        )
    return payload, landmarks
