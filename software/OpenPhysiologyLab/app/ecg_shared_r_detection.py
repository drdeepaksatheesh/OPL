
from __future__ import annotations

# Compatibility wrapper. New code should import from app.ecg_core directly.
try:
    from app.ecg_core.filters import safe_sampling_rate, ecg_review_filter
    from app.ecg_core.r_detection import (
        detect_r_peaks_calipers_style,
        complete_complex_peaks,
        detect_complete_ecg_complexes,
    )
except Exception:  # pragma: no cover
    from .ecg_core.filters import safe_sampling_rate, ecg_review_filter
    from .ecg_core.r_detection import (
        detect_r_peaks_calipers_style,
        complete_complex_peaks,
        detect_complete_ecg_complexes,
    )
