
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
        self.complete_peaks: np.ndarray = np.array([], dtype=int)

        self.pair_index: int = 0

        # These should match the teaching/complete-beat logic:
        # enough before R for P wave and enough after R for ST-T.
        self.pre_r_s: float = 0.25
        self.post_r_s: float = 0.55

        # Fixed display scales for this recording.
        # This prevents the graph from visually jumping when moving pair-to-pair.
        self.axis_rr_s: float = 0.80
        self.fixed_y_range = (-500.0, 1500.0)

        # Ctrl-arrow keyboard navigation target:
        # Ctrl+Left/Right selects one of these targets.
        # Ctrl+Up/Down changes the selected target.
        self.keyboard_target_index: int = 0
        self.keyboard_target_names = ["App tab", "Ch", "View", "Reference", "Pair"]

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
        self.view_box.addItems(["Raw pair"])
        controls.addWidget(self.view_box)

        controls.addWidget(QLabel("Reference"))
        self.reference_box = QComboBox()
        self.reference_box.addItems([
            "RR midpoint = 0",
            "Complex A R = 0",
            "Complex B R = 0",
        ])
        self.reference_box.currentIndexChanged.connect(self.refresh_plot)
        controls.addWidget(self.reference_box)

        self.prev_btn = QPushButton("< Pair")
        self.prev_btn.clicked.connect(self.previous_pair)
        controls.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Pair >")
        self.next_btn.clicked.connect(self.next_pair)
        controls.addWidget(self.next_btn)

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
        # Plain arrows are reserved for the core RR-pair workflow.
        QShortcut(QKeySequence(self.qt_key("Key_Left")), self, activated=self.previous_pair)
        QShortcut(QKeySequence(self.qt_key("Key_Right")), self, activated=self.next_pair)

        # Ctrl arrows navigate the UI controls without disturbing pair navigation.
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self.move_keyboard_target(-1))
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self.move_keyboard_target(+1))
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self.change_keyboard_target(-1))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self.change_keyboard_target(+1))

    def current_keyboard_target_name(self) -> str:
        try:
            names = getattr(self, "keyboard_target_names", ["App tab", "Ch", "View", "Reference", "Pair"])
            i = int(getattr(self, "keyboard_target_index", 0)) % len(names)
            return names[i]
        except Exception:
            return "App tab"

    def move_keyboard_target(self, delta: int):
        try:
            names = getattr(self, "keyboard_target_names", ["App tab", "Ch", "View", "Reference", "Pair"])
            self.keyboard_target_index = (int(getattr(self, "keyboard_target_index", 0)) + int(delta)) % len(names)
            self.focus_current_keyboard_target()
            self.update_keyboard_target_status()
            self.update_right_panels()
        except Exception:
            pass

    def change_keyboard_target(self, delta: int):
        try:
            target = self.current_keyboard_target_name()

            if target == "App tab":
                tabs = self.find_parent_tab_widget()
                if tabs is not None and tabs.count() > 0:
                    tabs.setCurrentIndex((tabs.currentIndex() + int(delta)) % tabs.count())
                    return

            elif target == "Ch":
                self.step_combo(self.channel_box, delta)
                return

            elif target == "View":
                self.step_combo(self.view_box, delta)
                return

            elif target == "Reference":
                self.step_combo(self.reference_box, delta)
                return

            elif target == "Pair":
                if int(delta) > 0:
                    self.next_pair()
                else:
                    self.previous_pair()
                return

            self.update_keyboard_target_status()
            self.update_right_panels()
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
            elif target == "Reference":
                self.reference_box.setFocus()
            elif target == "Pair":
                self.next_btn.setFocus()
            elif target == "App tab":
                tabs = self.find_parent_tab_widget()
                if tabs is not None:
                    tabs.setFocus()
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
            if target == "App tab":
                detail = "Ctrl+Up/Down switches Setup, Recorder, ECG Calipers, RR Pairs..."
            elif target == "Ch":
                detail = "Ctrl+Up/Down changes channel"
            elif target == "View":
                detail = "Ctrl+Up/Down changes view"
            elif target == "Reference":
                detail = "Ctrl+Up/Down changes reference"
            else:
                detail = "Ctrl+Up/Down changes pair"
            if hasattr(self, "status_label"):
                base = self.status_label.text()
                if " | keyboard:" in base:
                    base = base.split(" | keyboard:")[0]
                self.status_label.setText(f"{base} | keyboard: {target} ({detail})")
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

        self.update_fixed_plot_scales(raw)

        if self.pair_count() > 0:
            self.pair_index = int(max(0, min(self.pair_index, self.pair_count() - 1)))
        else:
            self.pair_index = 0

        rejected = len(self.r_peaks) - len(self.complete_peaks)
        fs = safe_sampling_rate(self.time_s)

        rr_warning = ""
        try:
            if len(self.complete_peaks) >= 2:
                rr0_ms = (float(self.time_s[int(self.complete_peaks[1])]) - float(self.time_s[int(self.complete_peaks[0])])) * 1000.0
                if rr0_ms > 3000.0:
                    rr_warning = " | check time units"
        except Exception:
            pass

        self.status_label.setText(
            f"{self.raw_path.name if self.raw_path else 'raw.csv'} | "
            f"fs {fs:.1f} Hz | R {len(self.r_peaks)} | complete {len(self.complete_peaks)} | rejected partial {rejected}{rr_warning}"
        )
        self.update_keyboard_target_status()
        self.refresh_plot()

    def pair_count(self) -> int:
        return pair_count_from_complete_peaks(self.complete_peaks)

    # ------------------------------------------------------------------
    # Navigation and plotting
    # ------------------------------------------------------------------
    def previous_pair(self):
        if self.pair_count() <= 0:
            return
        self.pair_index = max(0, self.pair_index - 1)
        self.refresh_plot()

    def next_pair(self):
        if self.pair_count() <= 0:
            return
        self.pair_index = min(self.pair_count() - 1, self.pair_index + 1)
        self.refresh_plot()

    def refresh_plot(self):
        self.plot.clear()

        if self.time_s is None or not self.channel_name:
            self.plot.setTitle("Load raw.csv to begin")
            self.update_right_panels()
            return

        if self.pair_count() <= 0:
            self.plot.setTitle("Need at least two complete ECG complexes")
            self.update_right_panels()
            return

        self.plot_raw_pair()
        self.update_right_panels()


    def update_fixed_plot_scales(self, raw_signal):
        # Compute a stable coordinate system for this loaded recording.
        # X scale is based on the typical RR interval, not the currently selected pair.
        # Y scale is based on all complete pair windows with local visual medians removed.
        try:
            if self.time_s is None or len(self.complete_peaks) < 2:
                self.axis_rr_s = 0.80
            else:
                r_times = self.time_s[np.asarray(self.complete_peaks, dtype=int)]
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

        try:
            y_chunks = []
            t = self.time_s
            raw = np.asarray(raw_signal, dtype=float)
            if t is not None and len(self.complete_peaks) >= 2:
                for i in range(min(self.pair_count(), 200)):
                    r1 = int(self.complete_peaks[i])
                    r2 = int(self.complete_peaks[i + 1])
                    start_t = max(float(t[0]), float(t[r1]) - self.pre_r_s)
                    end_t = min(float(t[-1]), float(t[r2]) + self.post_r_s)
                    mask = (t >= start_t) & (t <= end_t)
                    y = raw[mask]
                    if len(y) and np.isfinite(y).any():
                        y = y - np.nanmedian(y)
                        y_chunks.append(y[np.isfinite(y)])
            if y_chunks:
                yy = np.concatenate(y_chunks)
            else:
                finite = raw[np.isfinite(raw)]
                yy = finite - np.nanmedian(finite)
            lo = float(np.nanpercentile(yy, 0.5))
            hi = float(np.nanpercentile(yy, 99.5))
            if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
                lo, hi = -500.0, 1500.0
            pad = max(50.0, 0.08 * (hi - lo))
            self.fixed_y_range = (lo - pad, hi + pad)
        except Exception:
            self.fixed_y_range = (-500.0, 1500.0)

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

    def plot_raw_pair(self):
        raw = self.channels[self.channel_name]
        t = self.time_s

        i = self.pair_index
        r1, r2 = pair_indices(i, self.complete_peaks)
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

        self.plot.plot(x, y, pen=pg.mkPen("#E6C200", width=1.5))

        a_x = r1_t - ref_t
        b_x = r2_t - ref_t
        midpoint_x = ((r1_t + r2_t) / 2.0) - ref_t

        self.plot.addItem(pg.InfiniteLine(a_x, angle=90, pen=pg.mkPen("#66D9EF", width=1.2)))
        self.plot.addItem(pg.InfiniteLine(b_x, angle=90, pen=pg.mkPen("#66D9EF", width=1.2)))
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
            ymin, ymax = self.fixed_y_range
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
                f"Complete complexes: {len(self.complete_peaks)}\n"
                "Need at least two complete complexes."
            )

        i = self.pair_index
        r1, r2 = pair_indices(i, self.complete_peaks)
        r1_t = float(self.time_s[r1])
        r2_t = float(self.time_s[r2])
        rr_ms = (r2_t - r1_t) * 1000.0
        hr = 60000.0 / rr_ms if rr_ms > 0 else np.nan
        rejected = len(self.r_peaks) - len(self.complete_peaks)
        ref_t, ref_label = self.current_reference_time(r1_t, r2_t)

        return "\n".join([
            "Pair Measurements",
            "",
            f"Selected pair: {i + 1}/{self.pair_count()}",
            f"Complexes shown: {i + 1} and {i + 2}",
            f"Reference: {ref_label}",
            f"RR interval: {rr_ms:.1f} ms",
            f"Instant HR: {hr:.1f} bpm" if np.isfinite(hr) else "Instant HR: --",
            "",
            f"Detected R peaks: {len(self.r_peaks)}",
            f"Complete complexes: {len(self.complete_peaks)}",
            f"Rejected partial/edge complexes: {rejected}",
            "",
            f"Complex {i + 1} R time: {r1_t:.3f} s",
            f"Complex {i + 2} R time: {r2_t:.3f} s",
        ])

    def navigation_text(self) -> str:
        return "\n".join([
            "Navigation",
            "- Right arrow / Pair >: show next pair.",
            "- Left arrow / < Pair: show previous pair.",
            "",
            "Ctrl-arrow UI navigation:",
            "- Ctrl+Left / Ctrl+Right: choose target.",
            "- Ctrl+Up / Ctrl+Down: change selected target.",
            "- Targets: App tab, Ch, View, Reference, Pair.",
            "- App tab target switches Setup, Recorder, ECG Calipers, RR Pairs, etc.",
            "",
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
            "- R peaks are detected using the shared ECG review helper.",
            "- Detection is done on an internal filtered copy.",
            "- The plotted waveform is raw ECG.",
            "- A complex is accepted only if full PQRST context exists.",
            f"- Complete-complex rule: {self.pre_r_s:.2f} s before R and {self.post_r_s:.2f} s after R.",
            "- Partial first/last complexes are rejected before numbering.",
            "- Consecutive accepted complexes create the pairs.",
            "- The X and Y coordinate ranges are locked for the loaded recording.",
            "- This prevents the graph from jumping when moving pair-to-pair.",
            "- Reference modes:",
            "  1. RR midpoint = 0",
            "  2. Complex A R = 0",
            "  3. Complex B R = 0",
        ])
