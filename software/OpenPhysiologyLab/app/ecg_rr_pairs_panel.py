
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
        QComboBox, QGroupBox, QTextEdit, QSplitter, QShortcut, QTabWidget
    )
except Exception:  # pragma: no cover
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeySequence
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
        QComboBox, QGroupBox, QTextEdit, QSplitter, QShortcut, QTabWidget
    )

import pyqtgraph as pg
pg.setConfigOptions(antialias=True)

RR_RAW_COLOR = "#2ECC71"
RR_FILTERED_COLOR = "#E6C200"
RR_SELECTED_COLOR = "#E6C200"
RR_R_MARKER_COLOR = "#66D9EF"
RR_TEXT_COLOR = "#D8DEE9"
RR_PANEL_BG = "#0B0F14"
RR_PANEL_BORDER = "#243241"
RR_GOLD = "#E6C200"

try:
    from app.ecg_core.io import load_ecg_csv, choose_default_channel_name
    from app.ecg_core.filters import safe_sampling_rate
    from app.ecg_core.r_detection import detect_complete_ecg_complexes
    from app.ecg_core.complexes import (
        pair_count_from_complete_peaks,
        pair_indices,
        pair_time_window,
    )
except Exception:  # pragma: no cover
    from .ecg_core.io import load_ecg_csv, choose_default_channel_name
    from .ecg_core.filters import safe_sampling_rate
    from .ecg_core.r_detection import detect_complete_ecg_complexes
    from .ecg_core.complexes import (
        pair_count_from_complete_peaks,
        pair_indices,
        pair_time_window,
    )


class ECGRRPairsPanel(QWidget):
    """
    RR Pairs tab.

    Waveform-first design:
    - Load raw.csv.
    - Use the shared ECG review R-detection helper.
    - Reject partial first/last complexes.
    - Number complete complexes 1, 2, 3...
    - Show pairs 1+2, 2+3, 3+4...
    - Plot raw waveform with selectable reference:
        A R peak = 0
        B R peak = 0
        RR midpoint = 0
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

        self.raw_path: Optional[Path] = None
        self.time_s: Optional[np.ndarray] = None
        self.channels: Dict[str, np.ndarray] = {}
        self.channel_name: Optional[str] = None

        self.filtered: Optional[np.ndarray] = None
        self.r_peaks: np.ndarray = np.array([], dtype=int)
        self.complete_peaks: np.ndarray = np.array([], dtype=int)  # morphology-complete beats
        self.rr_peaks: np.ndarray = np.array([], dtype=int)        # HRV/RR timing source

        self.pair_index: int = 0

        # These should match the teaching/complete-beat logic:
        # enough before R for P wave and enough after R for ST-T.
        self.pre_r_s: float = 0.25
        self.post_r_s: float = 0.55

        # Fixed display scales for this recording.
        # This prevents the graph from visually jumping when moving pair-to-pair.
        self.axis_rr_s: float = 0.80
        self.fixed_y_range = (-500.0, 1500.0)
        self.fixed_y_ranges = {}

        # Arrow-key navigation starts on View:
        # Left/Right chooses Ch, View, Complex, Reference.
        # Up/Down changes the current target's option.
        self.keyboard_target_index: int = 1
        self.keyboard_target_names = ["Ch", "View", "Complex", "Reference"]

        # Ctrl-arrow keyboard navigation target:
        # Ctrl+Left/Right selects one of these targets.
        # Ctrl+Up/Down changes the selected target.
        self.keyboard_target_index: int = 0
        self.keyboard_target_names = ["App tab", "Ch", "View", "Complex", "Reference", "Pair"]

        self._build_ui()
        self._install_shortcuts()
        self.update_right_panels()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        title = QLabel("RR Pairs")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #E6C200;")
        root.addWidget(title)

        subtitle = QLabel(
            "Raw ECG pair view: complete complex 1+2, 2+3, 3+4... with selectable R/RR midpoint reference."
        )
        subtitle.setStyleSheet("color: #AAB3C0;")
        root.addWidget(subtitle)

        control_group = QGroupBox("Source and pair navigation")
        control_group.setStyleSheet("QGroupBox { color: #E6C200; font-weight: bold; }")
        controls = QHBoxLayout(control_group)
        controls.setContentsMargins(8, 8, 8, 8)
        controls.setSpacing(8)

        self.load_raw_btn = QPushButton("Load raw.csv")
        self.load_raw_btn.clicked.connect(self.load_raw_csv_clicked)
        controls.addWidget(self.load_raw_btn)

        controls.addWidget(QLabel("Ch"))
        self.channel_box = QComboBox()
        self.channel_box.currentIndexChanged.connect(self.channel_changed)
        controls.addWidget(self.channel_box)

        controls.addWidget(QLabel("View"))
        self.view_box = QComboBox()
        self.view_box.addItems([
            "Raw pair",
            "Filtered pair",
            "AB overlap",
            "Key AB complexes",
        ])
        self.view_box.currentIndexChanged.connect(self.refresh_plot)
        self.view_box.setMinimumWidth(135)
        controls.addWidget(self.view_box)

        controls.addWidget(QLabel("Complex"))
        self.complex_box = QComboBox()
        self.complex_box.setMinimumWidth(100)
        self.complex_box.addItems(["All complexes", "Mean / median / min / max"])
        self.complex_box.currentIndexChanged.connect(self.complex_selection_changed)
        controls.addWidget(self.complex_box)

        controls.addWidget(QLabel("Reference"))
        self.reference_box = QComboBox()
        self.reference_box.setMinimumWidth(135)
        self.reference_box.addItems([
            'RR midpoint = 0',
            'Complex A R = 0',
            'Complex B R = 0',
        ])
        self.reference_box.currentIndexChanged.connect(self.refresh_plot)
        controls.addWidget(self.reference_box)

        self.prev_btn = QPushButton("< Pair")
        self.prev_btn.clicked.connect(self.previous_pair)
        self.prev_btn.setVisible(False)

        self.next_btn = QPushButton("Pair >")
        self.next_btn.clicked.connect(self.next_pair)
        self.next_btn.setVisible(False)

        self.reset_view_btn = QPushButton("Reset")
        self.reset_view_btn.clicked.connect(self.reset_current_view)
        controls.addWidget(self.reset_view_btn)

        self.status_label = QLabel("Load raw.csv")
        self.status_label.setStyleSheet("color: #D8DEE9;")
        controls.addWidget(self.status_label, stretch=1)

        root.addWidget(control_group)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#05070A")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("bottom", "Time (s)")
        self.plot.setLabel("left", "Raw ECG")
        try:
            self.plot.getAxis("bottom").enableAutoSIPrefix(False)
            self.plot.getAxis("left").enableAutoSIPrefix(False)
        except Exception:
            pass
        try:
            self.plot.setMenuEnabled(False)
            self.plot.getViewBox().setMouseEnabled(x=False, y=False)
        except Exception:
            pass
        left_layout.addWidget(self.plot, stretch=1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(6)

        self.measurements_box = self._make_text_group(right_layout, "Pair Measurements", stretch=2, min_height=150)
        self.navigation_box = self._make_text_group(right_layout, "Navigation", stretch=1, min_height=120)
        self.method_box = self._make_text_group(right_layout, "Method", stretch=1, min_height=130)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

    def _make_text_group(self, parent_layout, title: str, stretch: int = 1, min_height: int = 120):
        group = QGroupBox(title)
        group.setStyleSheet("QGroupBox { color: #E6C200; font-weight: bold; }")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setMinimumHeight(min_height)
        box.setStyleSheet(
            "QTextEdit { color: #D8DEE9; background-color: #0B0F14; "
            "border: 1px solid #243241; border-radius: 4px; }"
        )
        layout.addWidget(box)
        parent_layout.addWidget(group, stretch=stretch)
        return box

    def qt_key(self, name: str):
        key_obj = getattr(Qt, name, None)
        if key_obj is not None:
            return key_obj
        return getattr(Qt.Key, name)

    def _install_shortcuts(self):
        # Plain arrows navigate controls inside RR Pairs.
        QShortcut(QKeySequence(self.qt_key("Key_Left")), self, activated=lambda: self.move_keyboard_target(-1))
        QShortcut(QKeySequence(self.qt_key("Key_Right")), self, activated=lambda: self.move_keyboard_target(+1))
        QShortcut(QKeySequence(self.qt_key("Key_Up")), self, activated=lambda: self.change_keyboard_target(-1))
        QShortcut(QKeySequence(self.qt_key("Key_Down")), self, activated=lambda: self.change_keyboard_target(+1))

        # Backup pair navigation.
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=self.previous_pair)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=self.next_pair)

        # Backup app-tab navigation.
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self.change_app_tab(-1))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self.change_app_tab(+1))

    def current_keyboard_target_name(self) -> str:
        try:
            names = getattr(self, "keyboard_target_names", ["Ch", "View", "Complex", "Reference"])
            i = int(getattr(self, "keyboard_target_index", 1)) % len(names)
            return names[i]
        except Exception:
            return "View"

    def move_keyboard_target(self, delta: int):
        try:
            names = getattr(self, "keyboard_target_names", ["Ch", "View", "Complex", "Reference"])
            self.keyboard_target_index = (int(getattr(self, "keyboard_target_index", 1)) + int(delta)) % len(names)
            self.focus_current_keyboard_target()
            self.update_keyboard_target_status()
            self.update_right_panels()
        except Exception:
            pass

    def change_keyboard_target(self, delta: int):
        try:
            target = self.current_keyboard_target_name()

            if target == "Ch":
                self.step_combo(self.channel_box, delta)
                return

            if target == "View":
                self.step_combo(self.view_box, delta)
                return

            if target == "Complex":
                view = self.current_view_name()
                if view in ("Raw pair", "Filtered pair"):
                    self.step_pair_by_delta(delta)
                elif hasattr(self, "complex_box"):
                    self.step_combo(self.complex_box, delta)
                return

            if target == "Reference":
                self.step_combo(self.reference_box, delta)
                return

            self.update_keyboard_target_status()
            self.update_right_panels()
        except Exception:
            pass

    def step_pair_by_delta(self, delta: int):
        try:
            n = self.pair_count()
            if n <= 0:
                return
            self.pair_index = max(0, min(n - 1, self.pair_index + int(delta)))
            self.set_complex_box_to_pair_index()
            self.refresh_plot()
            self.update_keyboard_target_status()
        except Exception:
            pass

    def set_complex_box_to_pair_index(self):
        try:
            if not hasattr(self, "complex_box"):
                return
            target = f"AB{self.pair_index + 1}"
            idx = self.complex_box.findText(target)
            if idx >= 0:
                self.complex_box.blockSignals(True)
                self.complex_box.setCurrentIndex(idx)
                self.complex_box.blockSignals(False)
        except Exception:
            try:
                self.complex_box.blockSignals(False)
            except Exception:
                pass

    def change_app_tab(self, delta: int):
        try:
            tabs = self.find_parent_tab_widget()
            if tabs is not None and tabs.count() > 0:
                tabs.setCurrentIndex((tabs.currentIndex() + int(delta)) % tabs.count())
        except Exception:
            pass

    def step_combo(self, combo, delta: int):
        try:
            n = combo.count()
            if n <= 0:
                return
            combo.setCurrentIndex((combo.currentIndex() + int(delta)) % n)
            combo.setFocus()
            self.update_keyboard_target_status()
            self.update_right_panels()
        except Exception:
            pass

    def focus_current_keyboard_target(self):
        try:
            target = self.current_keyboard_target_name()
            if target == "Ch":
                self.channel_box.setFocus()
            elif target == "View":
                self.view_box.setFocus()
            elif target == "Complex" and hasattr(self, "complex_box"):
                if self.current_view_name() in ("Raw pair", "Filtered pair"):
                    self.set_complex_box_to_pair_index()
                self.complex_box.setFocus()
            elif target == "Reference":
                self.reference_box.setFocus()
        except Exception:
            pass

    def find_parent_tab_widget(self):
        try:
            w = self.parent()
            while w is not None:
                if isinstance(w, QTabWidget):
                    return w
                w = w.parent()
        except Exception:
            pass
        return None

    def update_keyboard_target_status(self):
        try:
            target = self.current_keyboard_target_name()
            if target == "Ch":
                detail = "Up/Down changes channel"
            elif target == "View":
                detail = "Up/Down changes view"
            elif target == "Complex":
                if self.current_view_name() in ("Raw pair", "Filtered pair"):
                    detail = "Up/Down changes AB pair"
                else:
                    detail = "Up/Down changes complex selector"
            elif target == "Reference":
                detail = "Up/Down changes reference"
            else:
                detail = "Up/Down changes option"

            if hasattr(self, "status_label"):
                base = self.status_label.text()
                if " | keyboard:" in base:
                    base = base.split(" | keyboard:")[0]
                if " | reset" in base:
                    base = base.split(" | reset")[0]
                self.status_label.setText(f"{base} | keyboard: {target} ({detail})")
        except Exception:
            pass

    def set_keyboard_target(self, target_name: str):
        try:
            names = getattr(self, "keyboard_target_names", ["Ch", "View", "Complex", "Reference"])
            if target_name in names:
                self.keyboard_target_index = names.index(target_name)
                self.focus_current_keyboard_target()
                self.update_keyboard_target_status()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load_raw_csv_clicked(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select raw.csv",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if path:
            self.load_raw_csv(Path(path))

    def load_raw_csv(self, path: Path):
        try:
            self.raw_path = Path(path)

            # Shared ECG core loader:
            # - reads numeric CSV
            # - detects seconds/ms/us time units
            # - excludes time/segment/sample/index columns
            # - keeps only ECG-like signal channels
            self.time_s, self.channels, self.csv_headers, self.csv_columns, self.time_idx = load_ecg_csv(self.raw_path)

            self.channel_box.blockSignals(True)
            self.channel_box.clear()
            self.channel_box.addItems(list(self.channels.keys()))
            default_name = choose_default_channel_name(self.channels)
            if default_name:
                self.channel_box.setCurrentText(default_name)
            self.channel_box.blockSignals(False)

            self.channel_name = self.channel_box.currentText()
            self.pair_index = 0
            self.recompute()
        except Exception as exc:
            self.status_label.setText("Load failed")
            self.plot.clear()
            self.measurements_box.setPlainText(f"Could not load raw.csv:\n{exc}")

    def channel_changed(self):
        self.channel_name = self.channel_box.currentText()
        if self.time_s is not None and self.channel_name:
            self.pair_index = 0
            self.recompute()

    # ------------------------------------------------------------------
    # Shared R detection integration
    # ------------------------------------------------------------------
    def recompute(self):
        if self.time_s is None or not self.channel_name:
            return

        raw = self.channels[self.channel_name]
        self.filtered, self.r_peaks, self.complete_peaks = detect_complete_ecg_complexes(
            raw,
            self.time_s,
            pre_r_s=self.pre_r_s,
            post_r_s=self.post_r_s,
        )

        # Guideline-consistent split:
        # - r_peaks / rr_peaks are the RR timing source.
        # - complete_peaks are only the morphology/PQRST-complete subset.
        self.r_peaks = np.asarray(self.r_peaks, dtype=int)
        self.complete_peaks = np.asarray(self.complete_peaks, dtype=int)
        self.rr_peaks = np.asarray(self.r_peaks, dtype=int)

        self.update_fixed_plot_scales(raw)

        if self.pair_count() > 0:
            self.pair_index = int(max(0, min(self.pair_index, self.pair_count() - 1)))
        else:
            self.pair_index = 0

        self.update_complex_box_items()
        self.set_keyboard_target("View")

        morphology_edge = max(0, len(self.r_peaks) - len(self.complete_peaks))
        fs = safe_sampling_rate(self.time_s)

        rr_warning = ""
        try:
            peaks = self.rr_peak_array()
            if len(peaks) >= 2:
                rr0_ms = (float(self.time_s[int(peaks[1])]) - float(self.time_s[int(peaks[0])])) * 1000.0
                if rr0_ms > 3000.0:
                    rr_warning = " | check time units"
        except Exception:
            pass

        self.status_label.setText(
            f"fs {fs:.1f} Hz | R {len(self.r_peaks)} | morphology complete {len(self.complete_peaks)} | "
            f"RR pairs {self.pair_count()} | edge morphology {morphology_edge}{rr_warning}"
        )
        self.update_keyboard_target_status()
        self.refresh_plot()

    def pair_count(self) -> int:
        return max(0, len(self.rr_peak_array()) - 1)

    def rr_peak_array(self):
        # RR/HRV timing source. R peaks at the recording edges remain valid for
        # RR intervals even if the full P-QRS-T morphology window is incomplete.
        try:
            peaks = np.asarray(getattr(self, "rr_peaks", self.r_peaks), dtype=int)
            if len(peaks):
                return peaks
        except Exception:
            pass
        try:
            return np.asarray(self.r_peaks, dtype=int)
        except Exception:
            return np.asarray([], dtype=int)

    def rr_pair_indices(self, index: int):
        peaks = self.rr_peak_array()
        i = max(0, min(int(index), max(0, len(peaks) - 2)))
        return int(peaks[i]), int(peaks[i + 1])

    def morphology_complete_peak_set(self):
        try:
            return set(int(p) for p in np.asarray(self.complete_peaks, dtype=int))
        except Exception:
            return set()

    def reset_current_view(self):
        # Reset the currently selected RR Pairs view to its standard axes.
        try:
            self.refresh_plot()
            if hasattr(self, "status_label"):
                base = self.status_label.text()
                if " | reset" not in base:
                    self.status_label.setText(base + " | reset")
        except Exception:
            pass

    def sync_complex_box_to_pair_index(self):
        # If ABk mode is active, keep combo synced with left/right pair navigation.
        try:
            if not hasattr(self, "complex_box"):
                return
            label = self.current_complex_selection()
            if label.startswith("AB"):
                target = f"AB{self.pair_index + 1}"
                idx = self.complex_box.findText(target)
                if idx >= 0:
                    self.complex_box.blockSignals(True)
                    self.complex_box.setCurrentIndex(idx)
                    self.complex_box.blockSignals(False)
        except Exception:
            try:
                self.complex_box.blockSignals(False)
            except Exception:
                pass

    def previous_pair(self):
        try:
            if self.pair_count() <= 0:
                return
            self.pair_index = max(0, self.pair_index - 1)
            self.set_complex_box_to_pair_index()
            self.refresh_plot()
        except Exception:
            pass


    def next_pair(self):
        try:
            if self.pair_count() <= 0:
                return
            self.pair_index = min(self.pair_count() - 1, self.pair_index + 1)
            self.set_complex_box_to_pair_index()
            self.refresh_plot()
        except Exception:
            pass


    def refresh_plot(self):
        self.plot.clear()

        if self.time_s is None or not self.channel_name:
            self.plot.setTitle("Load raw.csv to begin")
            self.update_right_panels()
            return

        if self.pair_count() <= 0:
            self.plot.setTitle("Need at least two R peaks")
            self.update_right_panels()
            return

        view = self.current_view_name()
        if view == "Filtered pair":
            self.plot_filtered_pair()
        elif view == "AB overlap":
            self.plot_ab_overlap()
        elif view == "Key AB complexes":
            self.plot_key_ab_complexes()
        else:
            self.plot_raw_pair()
        self.update_right_panels()


    def robust_y_range_from_arrays(self, arrays, default=(-500.0, 1500.0)):
        # Calipers-like stable y range from one or more plotted arrays.
        try:
            chunks = []
            for arr in arrays:
                y = np.asarray(arr, dtype=float)
                y = y[np.isfinite(y)]
                if len(y):
                    chunks.append(y)
            if not chunks:
                return default
            yy = np.concatenate(chunks)
            lo = float(np.nanpercentile(yy, 0.1))
            hi = float(np.nanpercentile(yy, 99.9))
            if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
                lo, hi = float(np.nanmin(yy)), float(np.nanmax(yy))
            if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
                return default
            pad = max(40.0, 0.10 * (hi - lo))
            return (lo - pad, hi + pad)
        except Exception:
            return default

    def update_fixed_plot_scales(self, raw_signal):
        # Stable coordinate system for the loaded recording.
        # Y ranges are computed per view, like ECG Calipers, not per beat.
        try:
            if self.time_s is None or len(self.rr_peak_array()) < 2:
                self.axis_rr_s = 0.80
            else:
                r_times = self.time_s[np.asarray(self.rr_peak_array(), dtype=int)]
                rr_s = np.diff(r_times)
                rr_s = rr_s[np.isfinite(rr_s) & (rr_s > 0)]
                if len(rr_s):
                    med_rr = float(np.nanmedian(rr_s))
                    p95_rr = float(np.nanpercentile(rr_s, 95))
                    axis_rr = max(med_rr, p95_rr)
                    axis_rr = min(max(axis_rr, 0.45), 1.60)
                    self.axis_rr_s = axis_rr
                else:
                    self.axis_rr_s = 0.80
        except Exception:
            self.axis_rr_s = 0.80

        self.fixed_y_ranges = {}

        def collect_pair_chunks(signal):
            chunks = []
            try:
                t = self.time_s
                sig = np.asarray(signal, dtype=float)
                if t is not None and len(self.rr_peak_array()) >= 2:
                    for i in range(min(self.pair_count(), 250)):
                        r1, r2 = self.rr_pair_indices(i)
                        start_t, end_t = pair_time_window(t, r1, r2, self.pre_r_s, self.post_r_s)
                        mask = (t >= start_t) & (t <= end_t)
                        y = sig[mask]
                        if len(y) and np.isfinite(y).any():
                            y = y - np.nanmedian(y)
                            chunks.append(y)
                if not chunks:
                    finite = sig[np.isfinite(sig)]
                    if len(finite):
                        chunks.append(finite - np.nanmedian(finite))
            except Exception:
                pass
            return chunks

        raw_chunks = collect_pair_chunks(raw_signal)
        raw_range = self.robust_y_range_from_arrays(raw_chunks)
        self.fixed_y_ranges["Raw pair"] = raw_range
        self.fixed_y_range = raw_range

        try:
            if self.filtered is not None:
                filt_chunks = collect_pair_chunks(self.filtered)
                self.fixed_y_ranges["Filtered pair"] = self.robust_y_range_from_arrays(filt_chunks, default=raw_range)
        except Exception:
            self.fixed_y_ranges["Filtered pair"] = raw_range

    def current_plot_y_range(self):
        try:
            view = self.current_view_name()
            ranges = getattr(self, "fixed_y_ranges", {})
            if view in ranges:
                return ranges[view]
            if view == "Key AB complexes" and "AB overlap" in ranges:
                return ranges["AB overlap"]
            if view == "AB overlap" and "Key AB complexes" in ranges:
                return ranges["Key AB complexes"]
            return getattr(self, "fixed_y_range", (-500.0, 1500.0))
        except Exception:
            return (-500.0, 1500.0)

    def fixed_x_range_for_reference(self, r1_t: float, r2_t: float, ref_t: float, ref_label: str):
        # Stable X windows per reference mode. They depend on the loaded recording's
        # typical RR interval, not on the currently selected pair.
        rr_axis = float(getattr(self, "axis_rr_s", 0.80))
        if ref_label.startswith("RR midpoint"):
            xmin = -(rr_axis / 2.0) - self.pre_r_s
            xmax = +(rr_axis / 2.0) + self.post_r_s
        elif ref_label.startswith("Complex A"):
            xmin = -self.pre_r_s
            xmax = rr_axis + self.post_r_s
        elif ref_label.startswith("Complex B"):
            xmin = -(rr_axis + self.pre_r_s)
            xmax = self.post_r_s
        else:
            xmin = (r1_t - self.pre_r_s) - ref_t
            xmax = (r2_t + self.post_r_s) - ref_t
        return float(xmin), float(xmax)


    def current_reference_time(self, r1_t: float, r2_t: float) -> Tuple[float, str]:
        ref = self.reference_box.currentText() if hasattr(self, "reference_box") else "Complex A R = 0"
        if ref.startswith("Complex B"):
            return r2_t, "Complex B R = 0"
        if ref.startswith("RR midpoint"):
            return (r1_t + r2_t) / 2.0, "RR midpoint = 0"
        return r1_t, "Complex A R = 0"




    def update_complex_box_items(self):
        # Update AB complex selector: All, Rep/min/max, AB1...ABn.
        try:
            if not hasattr(self, "complex_box"):
                return

            current = self.complex_box.currentText()
            self.complex_box.blockSignals(True)
            self.complex_box.clear()
            self.complex_box.addItem("All complexes")
            self.complex_box.addItem("Mean / median / min / max")
            for i in range(self.pair_count()):
                self.complex_box.addItem(f"AB{i + 1}")
            if current:
                idx = self.complex_box.findText(current)
                if idx >= 0:
                    self.complex_box.setCurrentIndex(idx)
                else:
                    self.complex_box.setCurrentIndex(0)
            self.complex_box.blockSignals(False)
        except Exception:
            try:
                self.complex_box.blockSignals(False)
            except Exception:
                pass

    def current_complex_selection(self) -> str:
        try:
            if hasattr(self, "complex_box"):
                return self.complex_box.currentText()
        except Exception:
            pass
        return "All complexes"

    def selected_ab_index_from_complex_box(self):
        # Return zero-based AB index if ABk is selected, else None.
        try:
            label = self.current_complex_selection().strip()
            if label.startswith("AB"):
                return max(0, int(label[2:]) - 1)
        except Exception:
            pass
        return None

    def complex_selection_changed(self):
        try:
            selected = self.selected_ab_index_from_complex_box()
            if selected is not None:
                self.pair_index = max(0, min(selected, self.pair_count() - 1))
            self.refresh_plot()
        except Exception:
            pass

    def current_view_name(self) -> str:
        try:
            return self.view_box.currentText()
        except Exception:
            return "Raw pair"

    def plot_reference_lines_and_labels(self, r1_t: float, r2_t: float, ref_t: float, ref_label: str, ymax: float, a_label: str, b_label: str):
        a_x = r1_t - ref_t
        b_x = r2_t - ref_t
        midpoint_x = ((r1_t + r2_t) / 2.0) - ref_t

        self.plot.addItem(pg.InfiniteLine(a_x, angle=90, pen=pg.mkPen(RR_R_MARKER_COLOR, width=1.2)))
        self.plot.addItem(pg.InfiniteLine(b_x, angle=90, pen=pg.mkPen(RR_R_MARKER_COLOR, width=1.2)))
        self.plot.addItem(pg.InfiniteLine(midpoint_x, angle=90, pen=pg.mkPen("#888888", width=1, style=Qt.DashLine)))
        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen("#FFFFFF", width=1, style=Qt.DotLine)))

        try:
            txt1 = pg.TextItem(a_label, color="#D8DEE9", anchor=(0.5, 1.2))
            txt2 = pg.TextItem(b_label, color="#D8DEE9", anchor=(0.5, 1.2))
            txt1.setPos(a_x, ymax)
            txt2.setPos(b_x, ymax)
            self.plot.addItem(txt1)
            self.plot.addItem(txt2)
        except Exception:
            pass

    def plot_filtered_pair(self):
        if self.filtered is None:
            self.plot_raw_pair()
            return

        signal = np.asarray(self.filtered, dtype=float)
        t = self.time_s
        i = self.pair_index
        r1, r2 = self.rr_pair_indices(i)
        r1_t = float(t[r1])
        r2_t = float(t[r2])
        rr_s = r2_t - r1_t

        ref_t, ref_label = self.current_reference_time(r1_t, r2_t)
        start_t, end_t = pair_time_window(t, r1, r2, self.pre_r_s, self.post_r_s)

        mask = (t >= start_t) & (t <= end_t)
        x = t[mask] - ref_t
        y = np.asarray(signal[mask], dtype=float)
        if len(y) and np.isfinite(y).any():
            y = y - np.nanmedian(y)

        self.plot.plot(x, y, pen=pg.mkPen(RR_FILTERED_COLOR, width=1.5))

        ymax = float(np.nanmax(y)) if len(y) and np.isfinite(y).any() else 0.0
        self.plot_reference_lines_and_labels(
            r1_t, r2_t, ref_t, ref_label, ymax,
            f"Complex {i + 1}", f"Complex {i + 2}"
        )

        self.plot.setTitle(
            f"Filtered pair | AB {i + 1}/{self.pair_count()} | Complex {i + 1}+{i + 2} | RR = {rr_s * 1000.0:.1f} ms | {ref_label}"
        )
        self.plot.setLabel("bottom", f"Time relative to {ref_label} (s)")
        self.plot.setLabel("left", "Filtered ECG 0.5-40 Hz, local visual median removed")

        try:
            xmin, xmax = self.fixed_x_range_for_reference(r1_t, r2_t, ref_t, ref_label)
            self.plot.setXRange(xmin, xmax, padding=0)
            ymin, ymax = self.current_plot_y_range()
            self.plot.setYRange(float(ymin), float(ymax), padding=0)
        except Exception:
            self.plot.setXRange(start_t - ref_t, end_t - ref_t, padding=0)

    def ab_reference_mode(self):
        # Reference mode for AB overlap / Key AB complexes.
        try:
            label = self.reference_box.currentText().strip().lower()
            if 'complex a' in label or label.startswith('a') or 'a r' in label:
                return 'A'
            if 'complex b' in label or label.startswith('b') or 'b r' in label:
                return 'B'
        except Exception:
            pass
        return 'MID'

    def ab_reference_label(self):
        mode = self.ab_reference_mode()
        if mode == 'A':
            return 'Complex A R = 0'
        if mode == 'B':
            return 'Complex B R = 0'
        return 'RR midpoint = 0'

    def ab_reference_time_for_pair(self, r1_t: float, r2_t: float) -> float:
        mode = self.ab_reference_mode()
        if mode == 'A':
            return float(r1_t)
        if mode == 'B':
            return float(r2_t)
        return (float(r1_t) + float(r2_t)) / 2.0

    def ab_pair_grid(self):
        # Common x grid for AB-pair overlays using the selected Reference.
        try:
            r_times = self.time_s[np.asarray(self.rr_peak_array(), dtype=int)]
            rr_s = np.diff(r_times)
            rr_s = rr_s[np.isfinite(rr_s) & (rr_s > 0)]
            med_rr = float(np.nanmedian(rr_s)) if len(rr_s) else float(getattr(self, 'axis_rr_s', 0.80))
        except Exception:
            med_rr = float(getattr(self, 'axis_rr_s', 0.80))

        mode = self.ab_reference_mode()
        if mode == 'A':
            xmin = -self.pre_r_s
            xmax = med_rr + self.post_r_s
        elif mode == 'B':
            xmin = -med_rr - self.pre_r_s
            xmax = self.post_r_s
        else:
            xmin = -(med_rr / 2.0) - self.pre_r_s
            xmax = +(med_rr / 2.0) + self.post_r_s

        try:
            fs = safe_sampling_rate(self.time_s)
            dt = 1.0 / fs if fs > 0 else 0.002
        except Exception:
            dt = 0.002

        return np.arange(xmin, xmax + dt / 2.0, dt)

    def collect_filtered_ab_pair_traces(self):
        """
        Collect all filtered AB pair waveforms:
            AB1 = complex 1+2
            AB2 = complex 2+3
            AB3 = complex 3+4

        Each AB pair is aligned to its own RR midpoint = 0.
        Samples outside that specific pair's A-pre to B-post window are set
        to NaN, so neighbouring complexes are not plotted.
        """
        if self.time_s is None or len(self.rr_peak_array()) < 2:
            return None, []

        signal = np.asarray(self.filtered if self.filtered is not None else self.channels[self.channel_name], dtype=float)
        t = self.time_s
        x_grid = self.ab_pair_grid()
        traces = []

        for i in range(self.pair_count()):
            try:
                r1, r2 = self.rr_pair_indices(i)
                r1_t = float(t[r1])
                r2_t = float(t[r2])
                rr_s = r2_t - r1_t
                ref_t = self.ab_reference_time_for_pair(r1_t, r2_t)
                sample_t = ref_t + x_grid

                pair_start = r1_t - self.pre_r_s
                pair_end = r2_t + self.post_r_s
                valid = (
                    (sample_t >= pair_start)
                    & (sample_t <= pair_end)
                    & (sample_t >= float(t[0]))
                    & (sample_t <= float(t[-1]))
                )

                if not np.any(valid):
                    continue

                y = np.full_like(x_grid, np.nan, dtype=float)
                y_valid = np.interp(sample_t[valid], t, signal)
                if len(y_valid) and np.isfinite(y_valid).any():
                    y_valid = y_valid - np.nanmedian(y_valid)
                    y[valid] = y_valid
                    traces.append({
                        "index": i,
                        "label": f"AB{i + 1}",
                        "complex_a": i + 1,
                        "complex_b": i + 2,
                        "rr_s": rr_s,
                        "r1_x": r1_t - ref_t,
                        "r2_x": r2_t - ref_t,
                        "y": y,
                    })
            except Exception:
                continue

        return x_grid, traces

    def representative_ab_trace(self, traces):
        """
        Return the actual recorded AB pair closest to the group centre.

        This is a medoid-style representative, not a synthetic averaged wave.
        """
        if not traces:
            return None
        try:
            arr = np.vstack([tr["y"] for tr in traces])
            centre = np.nanmedian(arr, axis=0)
            distances = []
            for row in arr:
                good = np.isfinite(row) & np.isfinite(centre)
                if np.count_nonzero(good) < max(10, int(0.25 * len(row))):
                    distances.append(np.inf)
                else:
                    distances.append(float(np.nanmean((row[good] - centre[good]) ** 2)))
            best = int(np.nanargmin(np.asarray(distances, dtype=float)))
            return traces[best]
        except Exception:
            return traces[0]

    def shortest_longest_ab_traces(self, traces):
        if not traces:
            return None, None
        try:
            shortest = min(traces, key=lambda tr: tr.get("rr_s", np.inf))
            longest = max(traces, key=lambda tr: tr.get("rr_s", -np.inf))
            return shortest, longest
        except Exception:
            return traces[0], traces[-1]

    def trace_rr_ms(self, tr):
        try:
            rr = tr.get('rr_ms', None)
            if rr is not None and np.isfinite(float(rr)):
                return float(rr)
        except Exception:
            pass
        try:
            return abs(float(tr.get('r2_x')) - float(tr.get('r1_x'))) * 1000.0
        except Exception:
            return float('nan')

    def rr_key_ab_traces(self, traces):
        # Choose real recorded AB pairs by RR duration, not by waveform-shape centrality.
        valid = []
        for tr in traces:
            rr = self.trace_rr_ms(tr)
            if np.isfinite(rr):
                valid.append((rr, tr))
        if not valid:
            return {'shortest': None, 'longest': None, 'mean': None, 'median': None, 'mean_rr_ms': float('nan'), 'median_rr_ms': float('nan')}
        rr_values = np.asarray([v[0] for v in valid], dtype=float)
        mean_rr = float(np.nanmean(rr_values))
        median_rr = float(np.nanmedian(rr_values))
        shortest = min(valid, key=lambda item: item[0])[1]
        longest = max(valid, key=lambda item: item[0])[1]
        mean_trace = min(valid, key=lambda item: abs(item[0] - mean_rr))[1]
        median_trace = min(valid, key=lambda item: abs(item[0] - median_rr))[1]
        return {'shortest': shortest, 'longest': longest, 'mean': mean_trace, 'median': median_trace, 'mean_rr_ms': mean_rr, 'median_rr_ms': median_rr}

    def format_trace_label(self, tr):
        try:
            return tr.get('label', f"AB{int(tr.get('index', 0)) + 1}")
        except Exception:
            return '--'

    def current_ab_reference_label(self):
        try:
            return self.ab_reference_label()
        except Exception:
            try:
                return self.reference_box.currentText()
            except Exception:
                return 'RR midpoint = 0'

    def plot_ab_overlap(self):
        x_grid, traces = self.collect_filtered_ab_pair_traces()
        if x_grid is None or not traces:
            self.plot.setTitle('No RR-timing AB pairs available')
            return

        selection = self.current_complex_selection()
        current_i = int(self.pair_index)
        selected_i = self.selected_ab_index_from_complex_box()
        keys = self.rr_key_ab_traces(traces)
        shortest = keys.get('shortest')
        longest = keys.get('longest')
        mean_trace = keys.get('mean')
        median_trace = keys.get('median')
        mean_rr = keys.get('mean_rr_ms', float('nan'))
        median_rr = keys.get('median_rr_ms', float('nan'))
        ref_label = self.current_ab_reference_label()

        def draw_trace(tr, color, width):
            if tr is None:
                return
            try:
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=width))
            except Exception:
                pass

        key_selection_names = ('Mean / median / min / max', 'Rep / min / max', 'RR key intervals')

        if selection == 'All complexes':
            for tr in traces:
                color = pg.intColor(tr['index'], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(125)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=0.75))
            title_detail = f'all AB complexes equally weighted | n={len(traces)}'

        elif selection in key_selection_names:
            for tr in traces:
                color = pg.intColor(tr['index'], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(70)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=0.55))
            draw_trace(shortest, '#66D9EF', 2.0)
            draw_trace(longest, '#FF66CC', 2.0)
            draw_trace(median_trace, '#A78BFA', 2.2)
            draw_trace(mean_trace, '#FFFFFF', 2.5)
            title_detail = (
                f'meanRR {self.format_trace_label(mean_trace)} ({mean_rr:.0f} ms) | '
                f'medianRR {self.format_trace_label(median_trace)} ({median_rr:.0f} ms) | '
                f'shortest {self.format_trace_label(shortest)} | longest {self.format_trace_label(longest)}'
            )

        elif selected_i is not None:
            for tr in traces:
                color = pg.intColor(tr['index'], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(80)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=0.50))
            selected_trace = None
            for tr in traces:
                if tr['index'] == selected_i:
                    selected_trace = tr
                    break
            if selected_trace is not None:
                draw_trace(selected_trace, '#E6C200', 2.1)
                self.pair_index = max(0, min(selected_i, self.pair_count() - 1))
                title_detail = f'selected {selected_trace["label"]}'
            else:
                title_detail = f'selected AB{selected_i + 1} unavailable'

        else:
            for tr in traces:
                color = pg.intColor(tr['index'], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(125)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=0.75))
            title_detail = f'all AB complexes equally weighted | n={len(traces)}'

        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen('#FFFFFF', width=1.4, style=Qt.DotLine)))
        try:
            marker = mean_trace
            if selected_i is not None:
                for tr in traces:
                    if tr['index'] == selected_i:
                        marker = tr
                        break
            if marker is None and 0 <= current_i < len(traces):
                marker = traces[current_i]
            if marker is not None:
                self.plot.addItem(pg.InfiniteLine(marker['r1_x'], angle=90, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine)))
                self.plot.addItem(pg.InfiniteLine(marker['r2_x'], angle=90, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine)))
                if hasattr(self, 'add_reference_labels'):
                    self.add_reference_labels(ref_label, marker['r1_x'], marker['r2_x'])
        except Exception:
            pass

        self.plot.setTitle(f'Filtered AB overlap | reference: {ref_label} | {selection} | {title_detail}')
        self.plot.setLabel('bottom', f'Time relative to {ref_label} (s)')
        self.plot.setLabel('left', 'Filtered ECG 0.5-40 Hz, each AB pair local median removed')
        try:
            self.plot.setXRange(float(x_grid[0]), float(x_grid[-1]), padding=0)
            ymin, ymax = self.current_plot_y_range()
            self.plot.setYRange(float(ymin), float(ymax), padding=0)
        except Exception:
            pass

    def plot_key_ab_complexes(self):
        x_grid, traces = self.collect_filtered_ab_pair_traces()
        if x_grid is None or not traces:
            self.plot.setTitle('No RR-timing AB pairs available')
            return
        keys = self.rr_key_ab_traces(traces)
        shortest = keys.get('shortest')
        longest = keys.get('longest')
        mean_trace = keys.get('mean')
        median_trace = keys.get('median')
        mean_rr = keys.get('mean_rr_ms', float('nan'))
        median_rr = keys.get('median_rr_ms', float('nan'))
        ref_label = self.current_ab_reference_label()
        def draw_once(tr, color, width):
            if tr is None:
                return
            try:
                self.plot.plot(x_grid, tr['y'], pen=pg.mkPen(color, width=width))
            except Exception:
                pass
        draw_once(shortest, '#66D9EF', 2.0)
        draw_once(longest, '#FF66CC', 2.0)
        draw_once(median_trace, '#A78BFA', 2.2)
        draw_once(mean_trace, '#FFFFFF', 2.5)
        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen('#FFFFFF', width=1.4, style=Qt.DotLine)))
        try:
            marker = mean_trace or median_trace or shortest or longest
            if marker is not None:
                self.plot.addItem(pg.InfiniteLine(marker['r1_x'], angle=90, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine)))
                self.plot.addItem(pg.InfiniteLine(marker['r2_x'], angle=90, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine)))
                if hasattr(self, 'add_reference_labels'):
                    self.add_reference_labels(ref_label, marker['r1_x'], marker['r2_x'])
        except Exception:
            pass
        self.plot.setTitle(
            f'Key AB complexes | reference: {ref_label} | '
            f'meanRR {self.format_trace_label(mean_trace)} ({mean_rr:.0f} ms) | '
            f'medianRR {self.format_trace_label(median_trace)} ({median_rr:.0f} ms) | '
            f'shortest {self.format_trace_label(shortest)} | longest {self.format_trace_label(longest)}'
        )
        self.plot.setLabel('bottom', f'Time relative to {ref_label} (s)')
        self.plot.setLabel('left', 'Filtered ECG 0.5-40 Hz, each AB pair local median removed')
        try:
            self.plot.setXRange(float(x_grid[0]), float(x_grid[-1]), padding=0)
            ymin, ymax = self.current_plot_y_range()
            self.plot.setYRange(float(ymin), float(ymax), padding=0)
        except Exception:
            pass


    def plot_raw_pair(self):
        raw = self.channels[self.channel_name]
        t = self.time_s

        i = self.pair_index
        r1, r2 = self.rr_pair_indices(i)
        r1_t = float(t[r1])
        r2_t = float(t[r2])
        rr_s = r2_t - r1_t

        ref_t, ref_label = self.current_reference_time(r1_t, r2_t)

        # Include the full PQRST of both complexes:
        # complex A: R_A - pre to R_A + post
        # complex B: R_B - pre to R_B + post
        start_t, end_t = pair_time_window(t, r1, r2, self.pre_r_s, self.post_r_s)

        mask = (t >= start_t) & (t <= end_t)
        x = t[mask] - ref_t
        y = np.asarray(raw[mask], dtype=float)

        # Display-only visual baseline. R timing and raw shape remain unchanged.
        if len(y) and np.isfinite(y).any():
            y = y - np.nanmedian(y)

        self.plot.plot(x, y, pen=pg.mkPen(RR_RAW_COLOR, width=1.2))

        a_x = r1_t - ref_t
        b_x = r2_t - ref_t
        midpoint_x = ((r1_t + r2_t) / 2.0) - ref_t

        self.plot.addItem(pg.InfiniteLine(a_x, angle=90, pen=pg.mkPen(RR_R_MARKER_COLOR, width=1.2)))
        self.plot.addItem(pg.InfiniteLine(b_x, angle=90, pen=pg.mkPen(RR_R_MARKER_COLOR, width=1.2)))
        self.plot.addItem(pg.InfiniteLine(midpoint_x, angle=90, pen=pg.mkPen("#888888", width=1, style=Qt.DashLine)))
        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen("#FFFFFF", width=1, style=Qt.DotLine)))

        try:
            ymax = float(np.nanmax(y)) if len(y) and np.isfinite(y).any() else 0.0
            txt1 = pg.TextItem(f"Complex {i + 1}", color="#D8DEE9", anchor=(0.5, 1.2))
            txt2 = pg.TextItem(f"Complex {i + 2}", color="#D8DEE9", anchor=(0.5, 1.2))
            txt1.setPos(a_x, ymax)
            txt2.setPos(b_x, ymax)
            self.plot.addItem(txt1)
            self.plot.addItem(txt2)
        except Exception:
            pass

        self.plot.setTitle(
            f"Raw pair | Complex {i + 1} + {i + 2} | RR = {rr_s * 1000.0:.1f} ms | {ref_label}"
        )
        self.plot.setLabel("bottom", f"Time relative to {ref_label} (s)")
        self.plot.setLabel("left", "Raw ECG, local visual median removed")

        try:
            xmin, xmax = self.fixed_x_range_for_reference(r1_t, r2_t, ref_t, ref_label)
            self.plot.setXRange(xmin, xmax, padding=0)
            ymin, ymax = self.current_plot_y_range()
            self.plot.setYRange(float(ymin), float(ymax), padding=0)
        except Exception:
            self.plot.setXRange(start_t - ref_t, end_t - ref_t, padding=0)

    # ------------------------------------------------------------------
    # Right panel text
    # ------------------------------------------------------------------
    def update_right_panels(self):
        try:
            self.measurements_box.setPlainText(self.measurements_text())
            self.navigation_box.setPlainText(self.navigation_text())
            self.method_box.setPlainText(self.method_text())
        except Exception:
            pass

    def measurements_text(self) -> str:
        if self.time_s is None:
            return "Pair Measurements\n\nLoad raw.csv to begin."

        if self.pair_count() <= 0:
            return (
                "Pair Measurements\n\n"
                f"Detected R peaks: {len(self.r_peaks)}\n"
                f"Morphology-complete beats: {len(self.complete_peaks)}\n"
                "Need at least two R peaks for an RR interval."
            )

        i = self.pair_index
        r1, r2 = self.rr_pair_indices(i)
        r1_t = float(self.time_s[r1])
        r2_t = float(self.time_s[r2])
        rr_ms = (r2_t - r1_t) * 1000.0
        hr = 60000.0 / rr_ms if rr_ms > 0 else np.nan
        morphology_edge = max(0, len(self.r_peaks) - len(self.complete_peaks))
        ref_t, ref_label = self.current_reference_time(r1_t, r2_t)

        complete_set = self.morphology_complete_peak_set()
        edge_note = "no"
        if int(r1) not in complete_set or int(r2) not in complete_set:
            edge_note = "yes; RR timing usable, PQRST context incomplete"

        return "\n".join([
            "Pair Measurements",
            "",
            f"Selected RR pair: {i + 1}/{self.pair_count()}",
            f"R peaks shown: {i + 1} and {i + 2}",
            f"View: {self.current_view_name()}",
            f"Reference: {ref_label}",
            f"RR interval: {rr_ms:.1f} ms",
            f"Instant HR: {hr:.1f} bpm" if np.isfinite(hr) else "Instant HR: --",
            "",
            f"Detected R peaks: {len(self.r_peaks)}",
            f"Morphology-complete beats: {len(self.complete_peaks)}",
            f"Edge morphology incomplete: {morphology_edge}",
            f"Selected pair edge note: {edge_note}",
            "",
            f"R peak {i + 1} time: {r1_t:.3f} s",
            f"R peak {i + 2} time: {r2_t:.3f} s",
        ])

    def navigation_text(self) -> str:
        return "\n".join([
            "Navigation",
            "Arrow-key UI navigation:",
            "- Default target after loading is View.",
            "- Up / Down: change current target option.",
            "- Left / Right: move target: Ch, View, Complex, Reference.",
            "- In Raw pair / Filtered pair, Complex target Up/Down changes AB pair.",
            "- In AB overlap / Key AB complexes, Complex target Up/Down changes All / Mean-median-min-max / AB1...ABn.",
            "",
            "Pair navigation:",
            "- Ctrl+Left / Ctrl+Right: previous / next pair.",
            "- Reset View: restore the current view axes.",
            "",
            "App tab navigation:",
            "- Ctrl+Up / Ctrl+Down: switch Setup, Recorder, ECG Calipers, RR Pairs...",
            "- Pair 1 shows complete complex 1 and 2.",
            "- Pair 2 shows complete complex 2 and 3.",
            "- Pair 3 shows complete complex 3 and 4.",
            "- Reference selector changes the zero-time anchor.",
            "- White dotted line = selected zero reference.",
            "- Cyan lines = R peaks of complex A and B.",
            "- Grey dashed line = RR midpoint.",
        ])

    def method_text(self) -> str:
        return "\n".join([
            "Method",
            "- Keyboard model: default target after loading is View.",
            "- Left/Right changes keyboard target; Up/Down changes selected option.",
            "- R peaks are detected using the shared ECG review helper.",
            "- Detection is done on an internal filtered copy.",
            "- RR pairs are built from consecutive detected R peaks.",
            "- This follows the HRV rule: RR/NN timing depends on R-to-R intervals, not on full PQRST visibility.",
            "- Morphology-complete beats are still counted separately for PQRST/average-beat teaching.",
            f"- Morphology rule: {self.pre_r_s:.2f} s before R and {self.post_r_s:.2f} s after R.",
            "- A first/last R peak can be used for RR timing even if its full morphology window is incomplete.",
            "- Raw pair shows the selected RR interval without morphology filtering.",
            "- Filtered pair shows the same selected RR interval after the ECG review filter.",
            "- AB overlap shows filtered RR-pair waveforms: AB1, AB2, AB3...",
            "- Mean / median / min / max uses real recorded AB pairs selected by RR duration, not waveform-shape averaging.",
            "- White = nearest mean-RR AB pair; purple = nearest median-RR AB pair.",
            "- Reference selector changes AB overlap alignment: midpoint, A-R, or B-R.",
            "- Complex selector controls what is emphasized.",
            "- All complexes: all AB waveforms are drawn with equal intensity.",
            "- Mean / median / min / max: representative, shortest-RR and longest-RR real AB pairs are emphasized.",
            "- AB1...ABn: one selected AB pair is emphasized.",
            "- Key AB complexes shows nearest-mean-RR, nearest-median-RR, shortest-RR, and longest-RR AB pairs only.",
            "- The X and Y coordinate ranges are locked for the loaded recording.",
            "- This prevents the graph from jumping when moving pair-to-pair.",
            "- Reference modes:",
            "  1. RR midpoint = 0",
            "  2. Complex A R = 0",
            "  3. Complex B R = 0",
        ])

