
from __future__ import annotations

# Shared ECG defaults for OpenPhysiologyLab.
# Keep the numbers here so future ECG tabs do not silently diverge.

# General fallback when a file has no explicit time column.
# This does not upsample data; it only labels samples correctly when timing is absent.
DEFAULT_SAMPLE_RATE_HZ = 500.0

# ECG Calipers should prefer maximum detail for morphology/measurement work.
ECG_CALIPERS_DEFAULT_SAMPLE_RATE_HZ = 1000.0

# RR/HRV visual tabs can remain lighter for now.
ECG_RR_PAIRS_DEFAULT_SAMPLE_RATE_HZ = 500.0
ECG_HRV_DEFAULT_SAMPLE_RATE_HZ = 500.0

# Display/review filter: preserve P-QRS-T morphology for teaching.
DISPLAY_FILTER_LOW_HZ = 0.5
DISPLAY_FILTER_HIGH_HZ = 40.0
DISPLAY_FILTER_ORDER = 4

# Current detector is still review-filter based. Later we can add a separate
# QRS-focused detection filter and R-refinement step here without changing
# each visual tab separately.
DETECTION_REFRACTORY_S = 0.45

# Complete PQRST context around each R peak.
COMPLETE_COMPLEX_PRE_R_S = 0.25
COMPLETE_COMPLEX_POST_R_S = 0.55

# Transparent first-pass NN interval acceptance.
NN_MIN_RR_MS = 300.0
NN_MAX_RR_MS = 2000.0

# ECG paper/grid target constants for later voltage calibration.
# For now y remains in raw units unless a calibrated scale is available.
ECG_SMALL_SQUARE_S = 0.04
ECG_LARGE_SQUARE_S = 0.20
ECG_SMALL_SQUARE_MV = 0.1
ECG_LARGE_SQUARE_MV = 0.5

# OPL dark ECG colors.
ECG_BG = "#05070A"
ECG_GRID_ALPHA = 0.25
ECG_TRACE = "#E6C200"
ECG_R_MARKER = "#66D9EF"
ECG_REFERENCE = "#FFFFFF"
ECG_MIDPOINT = "#888888"
ECG_TEXT = "#D8DEE9"
ECG_PANEL_BG = "#0B0F14"
ECG_PANEL_BORDER = "#243241"
