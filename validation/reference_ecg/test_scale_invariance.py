"""Regression test: ECG peak detection must not depend on arbitrary amplitude units.

The same waveform expressed in V, mV, microvolt-like units or ADC-like counts
should yield the same R-peak indices.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOFTWARE = ROOT / "software" / "OpenPhysiologyLab"
sys.path.insert(0, str(SOFTWARE))

from analysis.peak_detection import detect_ecg_r_peaks  # noqa: E402


class TestECGScaleInvariance(unittest.TestCase):
    def test_r_peaks_are_scale_invariant(self):
        fs = 500.0
        duration_s = 10.0
        t = np.arange(int(fs * duration_s)) / fs

        # A deterministic ECG-like test trace: low baseline wander plus
        # narrow R-like Gaussian peaks at 1-second intervals.
        y = 0.02 * np.sin(2 * np.pi * 0.33 * t)
        expected_centers = []

        for beat_s in np.arange(0.8, 9.0, 1.0):
            center = int(round(beat_s * fs))
            expected_centers.append(center)
            width = 0.012
            y += 1.0 * np.exp(-0.5 * ((t - beat_s) / width) ** 2)

        outputs = []
        for scale in (0.001, 1.0, 1000.0, 2048.0):
            result = detect_ecg_r_peaks(t, y * scale, fs)
            outputs.append(np.asarray(result["peaks"], dtype=int))

        for peaks in outputs:
            self.assertEqual(len(peaks), len(expected_centers))

        reference = outputs[0]
        for peaks in outputs[1:]:
            np.testing.assert_array_equal(peaks, reference)

        np.testing.assert_allclose(reference, expected_centers, atol=2)


if __name__ == "__main__":
    unittest.main()
