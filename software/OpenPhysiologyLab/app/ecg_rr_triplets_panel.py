
from pathlib import Path
import csv
import math
import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel,
    QFileDialog, QSplitter, QGroupBox, QTextEdit, QShortcut, QTabWidget
)

import pyqtgraph as pg
pg.setConfigOptions(antialias=True)

TRIPLET_RAW_COLOR = "#2ECC71"
TRIPLET_FILTERED_COLOR = "#E6C200"
TRIPLET_SELECTED_COLOR = "#E6C200"
TRIPLET_R_MARKER_COLOR = "#66D9EF"
TRIPLET_TEXT_COLOR = "#D8DEE9"
TRIPLET_PANEL_BG = "#0B0F14"
TRIPLET_PANEL_BORDER = "#243241"
TRIPLET_GOLD = "#E6C200"

try:
    from .ecg_core.filters import ecg_review_filter, safe_sampling_rate
    from .ecg_core.r_detection import detect_complete_ecg_complexes
except Exception:
    try:
        from app.ecg_core.filters import ecg_review_filter, safe_sampling_rate
        from app.ecg_core.r_detection import detect_complete_ecg_complexes
    except Exception:
        ecg_review_filter = None
        detect_complete_ecg_complexes = None

        def safe_sampling_rate(time_s, default=500.0):
            try:
                t = np.asarray(time_s, dtype=float)
                dt = np.diff(t)
                dt = dt[np.isfinite(dt) & (dt > 0)]
                if len(dt):
                    return float(1.0 / np.nanmedian(dt))
            except Exception:
                pass
            return float(default)


def _looks_like_time_name(name):
    n = str(name).strip().lower()
    return any(k in n for k in ["time", "timestamp", "sample", "index", "ms", "sec"])


def _normalize_time_column(raw):
    t = np.asarray(raw, dtype=float)
    t = t - np.nanmin(t)
    dt = np.diff(t)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if len(dt) == 0:
        return np.arange(len(t), dtype=float) / 500.0
    med = float(np.nanmedian(dt))
    if med > 100:
        return t / 1_000_000.0
    if med > 0.02:
        return t / 1000.0
    return t


def _read_numeric_csv(path):
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        rows = list(csv.reader(f, dialect))

    if not rows:
        raise ValueError("CSV is empty")

    header = rows[0]
    body = rows[1:]
    try:
        test_vals = [float(x) for x in header[: min(3, len(header))]]
        has_header = False
    except Exception:
        has_header = True

    if not has_header:
        body = rows
        header = [f"col{i+1}" for i in range(len(rows[0]))]

    numeric_rows = []
    width = len(header)
    for row in body:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        vals = []
        ok_any = False
        for x in row[:width]:
            try:
                v = float(str(x).strip())
                vals.append(v)
                ok_any = True
            except Exception:
                vals.append(np.nan)
        if ok_any:
            numeric_rows.append(vals)

    arr = np.asarray(numeric_rows, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 5:
        raise ValueError("CSV has too few numeric rows")

    time_idx = None
    for i, h in enumerate(header):
        if _looks_like_time_name(h):
            col = arr[:, i]
            finite = np.isfinite(col)
            if np.sum(finite) > 5:
                dif = np.diff(col[finite])
                if np.nanmedian(dif) > 0:
                    time_idx = i
                    break

    if time_idx is None:
        col = arr[:, 0]
        finite = np.isfinite(col)
        if np.sum(finite) > 5:
            dif = np.diff(col[finite])
            if len(dif) and np.nanmedian(dif) > 0:
                if np.nanmax(col) - np.nanmin(col) > arr.shape[0] * 0.2:
                    time_idx = 0

    if time_idx is not None:
        time_s = _normalize_time_column(arr[:, time_idx])
    else:
        time_s = np.arange(arr.shape[0], dtype=float) / 500.0

    channels = {}
    for i, h in enumerate(header):
        if i == time_idx:
            continue
        if _looks_like_time_name(h):
            continue
        col = arr[:, i].astype(float)
        finite = np.isfinite(col)
        if np.sum(finite) < 10:
            continue
        if np.nanmax(col) - np.nanmin(col) <= 1e-9:
            continue
        name = str(h).strip() or f"ch{i+1}"
        channels[name] = col

    if not channels:
        raise ValueError("No usable signal columns found")

    return time_s, channels


def _review_filter_local(signal, time_s):
    y = np.asarray(signal, dtype=float)
    fs = safe_sampling_rate(time_s)
    try:
        from scipy.signal import butter, filtfilt
        nyq = fs / 2.0
        low = max(0.001, 0.5 / nyq)
        high = min(0.99, 40.0 / nyq)
        if high > low:
            b, a = butter(4, [low, high], btype="band")
            return filtfilt(b, a, y)
    except Exception:
        pass

    try:
        win = max(5, int(fs * 0.75))
        if win % 2 == 0:
            win += 1
        kernel = np.ones(win) / float(win)
        baseline = np.convolve(y, kernel, mode="same")
        return y - baseline
    except Exception:
        return y - np.nanmedian(y)


def _simple_r_detect(filtered, time_s):
    y = np.asarray(filtered, dtype=float)
    fs = safe_sampling_rate(time_s)
    z = y - np.nanmedian(y)
    if abs(np.nanmin(z)) > abs(np.nanmax(z)):
        z = -z
    try:
        from scipy.signal import find_peaks
        distance = max(1, int(0.45 * fs))
        prom = max(1e-9, 0.35 * (np.nanpercentile(z, 99) - np.nanpercentile(z, 50)))
        peaks, _ = find_peaks(z, distance=distance, prominence=prom)
        return np.asarray(peaks, dtype=int)
    except Exception:
        threshold = np.nanpercentile(z, 98)
        candidates = np.where(z >= threshold)[0]
        if len(candidates) == 0:
            return np.asarray([], dtype=int)
        groups = np.split(candidates, np.where(np.diff(candidates) > int(0.12 * fs))[0] + 1)
        peaks = []
        last = -10**9
        refractory = int(0.45 * fs)
        for g in groups:
            if len(g) == 0:
                continue
            p = int(g[np.nanargmax(z[g])])
            if p - last >= refractory:
                peaks.append(p)
                last = p
        return np.asarray(peaks, dtype=int)


class ECGRRTripletsPanel(QWidget):
    def __init__(self, *args, **kwargs):
        parent = kwargs.get("parent", None)
        if args and isinstance(args[0], QWidget):
            parent = args[0]
        super().__init__(parent)

        self.raw_path = None
        self.time_s = None
        self.channels = {}
        self.current_channel = None
        self.raw_signal = None
        self.filtered_signal = None
        self.r_peaks = np.asarray([], dtype=int)
        self.complete_peaks = np.asarray([], dtype=int)
        self.triplet_index = 0
        self.pre_r_s = 0.25
        self.post_r_s = 0.55
        self.fixed_y_range = (-500.0, 1500.0)
        self.keyboard_target_index = 1
        self.keyboard_target_names = ["Ch", "View", "Triplet", "Reference"]

        self._build_ui()
        self._install_shortcuts()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 4, 6, 4)
        main.setSpacing(4)

        title = QLabel("RR Triplets")
        title.setStyleSheet("color: #E6C200; font-weight: bold;")
        main.addWidget(title)

        subtitle = QLabel("Successive ECG triplet view: complex 1+2+3, 2+3+4, 3+4+5... showing RR-pre and RR-post.")
        subtitle.setStyleSheet("color: #D8DEE9;")
        main.addWidget(subtitle)

        group = QGroupBox("Source and triplet navigation")
        controls = QHBoxLayout(group)
        controls.setContentsMargins(6, 4, 6, 4)
        controls.setSpacing(5)

        self.load_btn = QPushButton("Load raw.csv")
        self.load_btn.clicked.connect(self.load_csv_dialog)
        controls.addWidget(self.load_btn)

        controls.addWidget(QLabel("Ch"))
        self.channel_box = QComboBox()
        self.channel_box.setFixedWidth(70)
        self.channel_box.currentIndexChanged.connect(self.channel_changed)
        controls.addWidget(self.channel_box)

        controls.addWidget(QLabel("View"))
        self.view_box = QComboBox()
        self.view_box.setMinimumWidth(135)
        self.view_box.addItems(["Raw triplet", "Filtered triplet", "Triplet overlap", "Key triplets"])
        self.view_box.currentIndexChanged.connect(self.refresh_plot)
        controls.addWidget(self.view_box)

        controls.addWidget(QLabel("Triplet"))
        self.triplet_box = QComboBox()
        self.triplet_box.setMinimumWidth(130)
        self.triplet_box.addItems(["All triplets", "Mean / median / min / max"])
        self.triplet_box.currentIndexChanged.connect(self.triplet_selection_changed)
        controls.addWidget(self.triplet_box)

        controls.addWidget(QLabel("Reference"))
        self.reference_box = QComboBox()
        self.reference_box.setMinimumWidth(135)
        self.reference_box.addItems(["Complex B R = 0", "Complex A R = 0", "Complex C R = 0", "Triplet midpoint = 0"])
        self.reference_box.currentIndexChanged.connect(self.refresh_plot)
        controls.addWidget(self.reference_box)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.refresh_plot)
        controls.addWidget(self.reset_btn)

        self.status_label = QLabel("Load raw.csv")
        self.status_label.setMinimumWidth(240)
        controls.addWidget(self.status_label, stretch=1)

        main.addWidget(group)

        splitter = QSplitter(Qt.Horizontal)
        self.plot = pg.PlotWidget()
        self.plot.setBackground("#05080D")
        self.plot.showGrid(x=True, y=True, alpha=0.20)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        splitter.addWidget(self.plot)

        right = QWidget()
        right.setMinimumWidth(310)
        right.setMaximumWidth(460)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self.measure_group = QGroupBox("Triplet Measurements")
        mg = QVBoxLayout(self.measure_group)
        self.measurements_box = QTextEdit()
        self.measurements_box.setReadOnly(True)
        self.measurements_box.setStyleSheet(f"QTextEdit {{ color: {TRIPLET_TEXT_COLOR}; background-color: {TRIPLET_PANEL_BG}; border: 1px solid {TRIPLET_PANEL_BORDER}; border-radius: 4px; }}")
        mg.addWidget(self.measurements_box)

        self.navigation_group = QGroupBox("Navigation")
        ng = QVBoxLayout(self.navigation_group)
        self.navigation_box = QTextEdit()
        self.navigation_box.setReadOnly(True)
        self.navigation_box.setStyleSheet(f"QTextEdit {{ color: {TRIPLET_TEXT_COLOR}; background-color: {TRIPLET_PANEL_BG}; border: 1px solid {TRIPLET_PANEL_BORDER}; border-radius: 4px; }}")
        ng.addWidget(self.navigation_box)

        self.method_group = QGroupBox("Method")
        mtg = QVBoxLayout(self.method_group)
        self.method_box = QTextEdit()
        self.method_box.setReadOnly(True)
        self.method_box.setStyleSheet(f"QTextEdit {{ color: {TRIPLET_TEXT_COLOR}; background-color: {TRIPLET_PANEL_BG}; border: 1px solid {TRIPLET_PANEL_BORDER}; border-radius: 4px; }}")
        mtg.addWidget(self.method_box)

        right_layout.addWidget(self.measure_group, stretch=2)
        right_layout.addWidget(self.navigation_group, stretch=1)
        right_layout.addWidget(self.method_group, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([900, 340])
        main.addWidget(splitter, stretch=1)

        self.setStyleSheet("QGroupBox { color: #E6C200; font-weight: bold; } QLabel { color: #D8DEE9; }")

        self.update_right_panels()

    def _install_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self.move_keyboard_target(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.move_keyboard_target(+1))
        QShortcut(QKeySequence(Qt.Key_Up), self, activated=lambda: self.change_keyboard_target(-1))
        QShortcut(QKeySequence(Qt.Key_Down), self, activated=lambda: self.change_keyboard_target(+1))
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self.step_triplet(-1))
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self.step_triplet(+1))
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self.change_app_tab(-1))
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self.change_app_tab(+1))

    def current_view_name(self):
        return self.view_box.currentText()

    def current_reference_mode(self):
        label = self.reference_box.currentText().lower()
        if "complex a" in label:
            return "A"
        if "complex c" in label:
            return "C"
        if "midpoint" in label:
            return "MID"
        return "B"

    def current_reference_label(self):
        return self.reference_box.currentText()

    def reference_time(self, r1_t, r2_t, r3_t):
        mode = self.current_reference_mode()
        if mode == "A":
            return float(r1_t)
        if mode == "C":
            return float(r3_t)
        if mode == "MID":
            return (float(r1_t) + float(r3_t)) / 2.0
        return float(r2_t)

    def triplet_count(self):
        return max(0, len(self.complete_peaks) - 2)

    def load_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load raw ECG CSV", "", "CSV files (*.csv);;All files (*.*)")
        if path:
            self.load_csv(path)

    def load_csv(self, path):
        try:
            self.raw_path = Path(path)
            self.time_s, self.channels = _read_numeric_csv(path)
            self.channel_box.blockSignals(True)
            self.channel_box.clear()
            for name in self.channels.keys():
                self.channel_box.addItem(name)
            preferred = 0
            for i, name in enumerate(self.channels.keys()):
                if str(name).lower() in ("ch1", "channel1", "a0", "ecg", "lead ii", "lead2"):
                    preferred = i
                    break
            self.channel_box.setCurrentIndex(preferred)
            self.channel_box.blockSignals(False)
            self.current_channel = self.channel_box.currentText()
            self.recompute()
        except Exception as exc:
            self.status_label.setText(f"Could not load CSV: {exc}")

    def channel_changed(self):
        if not self.channels:
            return
        self.current_channel = self.channel_box.currentText()
        self.recompute()

    def recompute(self):
        if not self.current_channel or self.current_channel not in self.channels:
            return
        self.raw_signal = np.asarray(self.channels[self.current_channel], dtype=float)
        try:
            if detect_complete_ecg_complexes is not None:
                out = detect_complete_ecg_complexes(self.raw_signal, self.time_s, pre_r_s=self.pre_r_s, post_r_s=self.post_r_s)
                self.filtered_signal, self.r_peaks, self.complete_peaks = out
            else:
                raise RuntimeError("core detector unavailable")
        except Exception:
            self.filtered_signal = _review_filter_local(self.raw_signal, self.time_s)
            self.r_peaks = _simple_r_detect(self.filtered_signal, self.time_s)
            self.complete_peaks = np.asarray([
                p for p in self.r_peaks
                if self.time_s[p] - self.time_s[0] >= self.pre_r_s and self.time_s[-1] - self.time_s[p] >= self.post_r_s
            ], dtype=int)

        self.r_peaks = np.asarray(self.r_peaks, dtype=int)
        self.complete_peaks = np.asarray(self.complete_peaks, dtype=int)
        self.triplet_index = max(0, min(self.triplet_index, self.triplet_count() - 1))
        self.update_triplet_box_items()
        self.set_keyboard_target("View")
        self.update_y_range()
        fs = safe_sampling_rate(self.time_s)
        self.status_label.setText(f"fs {fs:.1f} Hz | R {len(self.r_peaks)} | complete {len(self.complete_peaks)} | triplets {self.triplet_count()}")
        self.refresh_plot()

    def robust_y_range_from_arrays(self, arrays, min_span=250.0):
        # Return a robust y-range for local-median removed plotted arrays.
        try:
            vals = []
            for arr in arrays:
                a = np.asarray(arr, dtype=float).ravel()
                a = a[np.isfinite(a)]
                if len(a):
                    vals.append(a)
            if not vals:
                return (-500.0, 500.0)
            v = np.concatenate(vals)
            if len(v) < 2:
                return (-500.0, 500.0)
            lo, hi = np.nanpercentile(v, [1, 99])
            if not np.isfinite(lo) or not np.isfinite(hi):
                return (-500.0, 500.0)
            span = float(hi - lo)
            if span < float(min_span):
                centre = float(np.nanmedian(v))
                span = float(min_span)
                return (centre - span / 2.0, centre + span / 2.0)
            pad = max(40.0, 0.20 * span)
            return (float(lo - pad), float(hi + pad))
        except Exception:
            return (-500.0, 500.0)

    def update_y_range(self):
        try:
            vals = np.asarray(self.raw_signal, dtype=float)
            lo, hi = np.nanpercentile(vals, [1, 99])
            pad = max(50.0, 0.20 * (hi - lo))
            self.fixed_y_range = (float(lo - pad), float(hi + pad))
        except Exception:
            self.fixed_y_range = (-500.0, 1500.0)

    def update_triplet_box_items(self):
        current = self.triplet_box.currentText()
        self.triplet_box.blockSignals(True)
        self.triplet_box.clear()
        self.triplet_box.addItem("All triplets")
        self.triplet_box.addItem("Mean / median / min / max")
        for i in range(self.triplet_count()):
            self.triplet_box.addItem(f"Triplet {i + 1}")
        if current:
            idx = self.triplet_box.findText(current)
            self.triplet_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.triplet_box.blockSignals(False)

    def selected_triplet_index_from_box(self):
        try:
            label = self.triplet_box.currentText()
            if label.startswith("Triplet "):
                return max(0, int(label.split()[-1]) - 1)
        except Exception:
            pass
        return None

    def triplet_selection_changed(self):
        idx = self.selected_triplet_index_from_box()
        if idx is not None:
            self.triplet_index = max(0, min(idx, self.triplet_count() - 1))
        self.refresh_plot()

    def set_triplet_box_to_index(self):
        target = f"Triplet {self.triplet_index + 1}"
        idx = self.triplet_box.findText(target)
        if idx >= 0:
            self.triplet_box.blockSignals(True)
            self.triplet_box.setCurrentIndex(idx)
            self.triplet_box.blockSignals(False)

    def step_triplet(self, delta):
        n = self.triplet_count()
        if n <= 0:
            return
        self.triplet_index = max(0, min(n - 1, self.triplet_index + int(delta)))
        self.set_triplet_box_to_index()
        self.refresh_plot()

    def current_keyboard_target_name(self):
        return self.keyboard_target_names[self.keyboard_target_index % len(self.keyboard_target_names)]

    def move_keyboard_target(self, delta):
        self.keyboard_target_index = (self.keyboard_target_index + int(delta)) % len(self.keyboard_target_names)
        self.focus_current_keyboard_target()
        self.update_keyboard_target_status()

    def change_keyboard_target(self, delta):
        target = self.current_keyboard_target_name()
        if target == "Ch":
            self.step_combo(self.channel_box, delta)
        elif target == "View":
            self.step_combo(self.view_box, delta)
        elif target == "Triplet":
            if self.current_view_name() in ("Raw triplet", "Filtered triplet"):
                self.step_triplet(delta)
            else:
                self.step_combo(self.triplet_box, delta)
        elif target == "Reference":
            self.step_combo(self.reference_box, delta)

    def step_combo(self, combo, delta):
        n = combo.count()
        if n <= 0:
            return
        combo.setCurrentIndex((combo.currentIndex() + int(delta)) % n)
        combo.setFocus()
        self.update_keyboard_target_status()

    def focus_current_keyboard_target(self):
        target = self.current_keyboard_target_name()
        if target == "Ch":
            self.channel_box.setFocus()
        elif target == "View":
            self.view_box.setFocus()
        elif target == "Triplet":
            self.triplet_box.setFocus()
        elif target == "Reference":
            self.reference_box.setFocus()

    def set_keyboard_target(self, target):
        if target in self.keyboard_target_names:
            self.keyboard_target_index = self.keyboard_target_names.index(target)
            self.focus_current_keyboard_target()
            self.update_keyboard_target_status()

    def find_parent_tab_widget(self):
        w = self.parent()
        while w is not None:
            if isinstance(w, QTabWidget):
                return w
            w = w.parent()
        return None

    def change_app_tab(self, delta):
        tabs = self.find_parent_tab_widget()
        if tabs is not None and tabs.count() > 0:
            tabs.setCurrentIndex((tabs.currentIndex() + int(delta)) % tabs.count())

    def update_keyboard_target_status(self):
        target = self.current_keyboard_target_name()
        detail = {
            "Ch": "Up/Down changes channel",
            "View": "Up/Down changes view",
            "Triplet": "Up/Down changes triplet selector",
            "Reference": "Up/Down changes reference",
        }.get(target, "Up/Down changes option")
        base = self.status_label.text().split(" | keyboard:")[0]
        self.status_label.setText(f"{base} | keyboard: {target} ({detail})")

    def triplet_times(self, index):
        peaks = self.complete_peaks
        a, b, c = int(peaks[index]), int(peaks[index + 1]), int(peaks[index + 2])
        return a, b, c, float(self.time_s[a]), float(self.time_s[b]), float(self.time_s[c])

    def triplet_grid(self):
        try:
            r_times = self.time_s[np.asarray(self.complete_peaks, dtype=int)]
            rr = np.diff(r_times)
            rr = rr[np.isfinite(rr) & (rr > 0)]
            med = float(np.nanmedian(rr)) if len(rr) else 0.75
        except Exception:
            med = 0.75
        mode = self.current_reference_mode()
        if mode == "A":
            xmin, xmax = -self.pre_r_s, 2 * med + self.post_r_s
        elif mode == "C":
            xmin, xmax = -2 * med - self.pre_r_s, self.post_r_s
        elif mode == "MID":
            xmin, xmax = -med - self.pre_r_s, med + self.post_r_s
        else:
            xmin, xmax = -med - self.pre_r_s, med + self.post_r_s
        fs = safe_sampling_rate(self.time_s)
        dt = 1.0 / fs if fs > 0 else 0.002
        return np.arange(xmin, xmax + dt / 2.0, dt)

    def collect_triplet_traces(self):
        if self.triplet_count() <= 0:
            return None, []
        x_grid = self.triplet_grid()
        traces = []
        for i in range(self.triplet_count()):
            try:
                a, b, c, t1, t2, t3 = self.triplet_times(i)
                ref_t = self.reference_time(t1, t2, t3)
                sample_t = ref_t + x_grid
                start = t1 - self.pre_r_s
                end = t3 + self.post_r_s
                y = np.interp(sample_t, self.time_s, self.filtered_signal, left=np.nan, right=np.nan)
                y[(sample_t < start) | (sample_t > end)] = np.nan
                y = y - np.nanmedian(y)
                rr_pre = (t2 - t1) * 1000.0
                rr_post = (t3 - t2) * 1000.0
                traces.append({
                    "index": i,
                    "label": f"T{i + 1}",
                    "y": y,
                    "r1_x": t1 - ref_t,
                    "r2_x": t2 - ref_t,
                    "r3_x": t3 - ref_t,
                    "rr_pre_ms": rr_pre,
                    "rr_post_ms": rr_post,
                    "delta_ms": rr_post - rr_pre,
                    "abs_delta_ms": abs(rr_post - rr_pre),
                })
            except Exception:
                pass
        return x_grid, traces

    def key_triplets(self, traces):
        valid = [tr for tr in traces if np.isfinite(tr["rr_pre_ms"]) and np.isfinite(tr["rr_post_ms"])]
        if not valid:
            return {}
        pre = np.asarray([tr["rr_pre_ms"] for tr in valid], dtype=float)
        post = np.asarray([tr["rr_post_ms"] for tr in valid], dtype=float)
        mean_pre, mean_post = float(np.nanmean(pre)), float(np.nanmean(post))
        med_pre, med_post = float(np.nanmedian(pre)), float(np.nanmedian(post))

        def dist_to(tr, x, y):
            return (tr["rr_pre_ms"] - x) ** 2 + (tr["rr_post_ms"] - y) ** 2

        return {
            "mean": min(valid, key=lambda tr: dist_to(tr, mean_pre, mean_post)),
            "median": min(valid, key=lambda tr: dist_to(tr, med_pre, med_post)),
            "min_delta": min(valid, key=lambda tr: tr["abs_delta_ms"]),
            "max_delta": max(valid, key=lambda tr: tr["abs_delta_ms"]),
            "mean_pre": mean_pre,
            "mean_post": mean_post,
            "median_pre": med_pre,
            "median_post": med_post,
        }

    def refresh_plot(self):
        self.plot.clear()
        if self.time_s is None or self.filtered_signal is None or self.triplet_count() <= 0:
            self.plot.setTitle("Load ECG raw.csv")
            self.update_right_panels()
            return
        view = self.current_view_name()
        if view == "Raw triplet":
            self.plot_single_triplet(raw=True)
        elif view == "Filtered triplet":
            self.plot_single_triplet(raw=False)
        elif view == "Triplet overlap":
            self.plot_triplet_overlap()
        else:
            self.plot_key_triplets()
        self.update_right_panels()

    def plot_single_triplet(self, raw=True):
        i = max(0, min(self.triplet_index, self.triplet_count() - 1))
        a, b, c, t1, t2, t3 = self.triplet_times(i)
        ref_t = self.reference_time(t1, t2, t3)
        start, end = t1 - self.pre_r_s, t3 + self.post_r_s
        mask = (self.time_s >= start) & (self.time_s <= end)
        x = self.time_s[mask] - ref_t
        y = (self.raw_signal if raw else self.filtered_signal)[mask]
        y = y - np.nanmedian(y)
        rr_pre = (t2 - t1) * 1000.0
        rr_post = (t3 - t2) * 1000.0
        delta = rr_post - rr_pre
        color = TRIPLET_RAW_COLOR if raw else TRIPLET_FILTERED_COLOR
        self.plot.plot(x, y, pen=pg.mkPen(color, width=1.35 if raw else 1.55))
        self.add_r_lines(t1 - ref_t, t2 - ref_t, t3 - ref_t)
        self.plot.setTitle(f"{'Raw' if raw else 'Filtered'} triplet | Triplet {i + 1}/{self.triplet_count()} | RR-pre {rr_pre:.1f} ms | RR-post {rr_post:.1f} ms | ΔRR {delta:+.1f} ms")
        self.plot.setLabel("bottom", f"Time relative to {self.current_reference_label()} (s)")
        self.plot.setLabel("left", "Raw ECG, local median removed" if raw else "Filtered ECG 0.5-40 Hz, local median removed")
        self.plot.setXRange(float(np.nanmin(x)), float(np.nanmax(x)), padding=0)
        ymin, ymax = self.robust_y_range_from_arrays([y])
        self.plot.setYRange(float(ymin), float(ymax), padding=0)

    def add_r_lines(self, x1, x2, x3):
        for x, label in [(x1, "A R"), (x2, "B R"), (x3, "C R")]:
            self.plot.addItem(pg.InfiniteLine(float(x), angle=90, pen=pg.mkPen(TRIPLET_R_MARKER_COLOR, width=1, style=Qt.DashLine)))
            try:
                ymin, ymax = self.fixed_y_range
                txt = pg.TextItem(label, color=TRIPLET_TEXT_COLOR, anchor=(0.5, 1.2))
                txt.setPos(float(x), float(ymax) - 0.07 * (float(ymax) - float(ymin)))
                self.plot.addItem(txt)
            except Exception:
                pass
        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen("#FFFFFF", width=1.3, style=Qt.DotLine)))

    def draw_trace(self, x_grid, tr, color, width, alpha=None):
        if tr is None:
            return
        pen_color = color
        if alpha is not None:
            try:
                pen_color = pg.mkColor(color)
                pen_color.setAlpha(int(alpha))
            except Exception:
                pen_color = color
        self.plot.plot(x_grid, tr["y"], pen=pg.mkPen(pen_color, width=width))

    def mean_median_triplet_title_part(self, keys):
        try:
            mean_tr = keys.get("mean")
            med_tr = keys.get("median")
            mean_label = mean_tr.get("label", "--") if mean_tr is not None else "--"
            med_label = med_tr.get("label", "--") if med_tr is not None else "--"
            if mean_label == med_label and mean_label != "--":
                return f"mean=median {mean_label}"
            return f"meanTriplet {mean_label} | medianTriplet {med_label}"
        except Exception:
            return "meanTriplet -- | medianTriplet --"

    def plot_triplet_overlap(self):
        x_grid, traces = self.collect_triplet_traces()
        if x_grid is None or not traces:
            self.plot.setTitle("No complete triplets")
            return
        selection = self.triplet_box.currentText()
        selected_i = self.selected_triplet_index_from_box()
        keys = self.key_triplets(traces)

        if selection == "All triplets":
            for tr in traces:
                color = pg.intColor(tr["index"], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(120)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr["y"], pen=pg.mkPen(color, width=0.70))
            detail = f"all triplets equally weighted | n={len(traces)}"
        elif selection.startswith("Mean / median"):
            for tr in traces:
                color = pg.intColor(tr["index"], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(60)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr["y"], pen=pg.mkPen(color, width=0.45))
            self.draw_trace(x_grid, keys.get("min_delta"), "#66D9EF", 2.0)
            self.draw_trace(x_grid, keys.get("max_delta"), "#FF66CC", 2.0)
            # Median is drawn wide first; mean is drawn narrower on top.
            # If mean and median are the same real triplet, this creates a purple halo.
            self.draw_trace(x_grid, keys.get("median"), "#A78BFA", 4.0)
            self.draw_trace(x_grid, keys.get("mean"), "#FFFFFF", 2.0)
            detail = f"mean {keys.get('mean', {}).get('label', '--')} | median {keys.get('median', {}).get('label', '--')} | minΔ {keys.get('min_delta', {}).get('label', '--')} | maxΔ {keys.get('max_delta', {}).get('label', '--')}"
        elif selected_i is not None:
            for tr in traces:
                color = pg.intColor(tr["index"], hues=max(8, len(traces)), values=1.0, maxValue=255)
                try:
                    color.setAlpha(70)
                except Exception:
                    pass
                self.plot.plot(x_grid, tr["y"], pen=pg.mkPen(color, width=0.45))
            selected = next((tr for tr in traces if tr["index"] == selected_i), None)
            self.draw_trace(x_grid, selected, TRIPLET_SELECTED_COLOR, 2.2)
            detail = f"selected {selected['label']}" if selected else "selected unavailable"
        else:
            detail = ""

        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen("#FFFFFF", width=1.3, style=Qt.DotLine)))
        self.plot.setTitle(f"Triplet overlap | reference: {self.current_reference_label()} | {selection} | {detail}")
        self.plot.setLabel("bottom", f"Time relative to {self.current_reference_label()} (s)")
        self.plot.setLabel("left", "Filtered ECG 0.5-40 Hz, local median removed")
        self.plot.setXRange(float(x_grid[0]), float(x_grid[-1]), padding=0)
        visible_arrays = [tr.get("y") for tr in traces if isinstance(tr, dict) and tr.get("y") is not None]
        ymin, ymax = self.robust_y_range_from_arrays(visible_arrays)
        self.plot.setYRange(float(ymin), float(ymax), padding=0)

    def plot_key_triplets(self):
        x_grid, traces = self.collect_triplet_traces()
        if x_grid is None or not traces:
            self.plot.setTitle("No complete triplets")
            return
        keys = self.key_triplets(traces)
        self.draw_trace(x_grid, keys.get("min_delta"), "#66D9EF", 2.0)
        self.draw_trace(x_grid, keys.get("max_delta"), "#FF66CC", 2.0)
        # Median is drawn wide first; mean is drawn narrower on top.
        # If mean and median are the same real triplet, this creates a purple halo.
        self.draw_trace(x_grid, keys.get("median"), "#A78BFA", 4.0)
        self.draw_trace(x_grid, keys.get("mean"), "#FFFFFF", 2.0)
        self.plot.addItem(pg.InfiniteLine(0.0, angle=90, pen=pg.mkPen("#FFFFFF", width=1.3, style=Qt.DotLine)))
        self.plot.setTitle(
            f"Key triplets | reference: {self.current_reference_label()} | "
            f"{self.mean_median_triplet_title_part(keys)} | "
            f"minΔ {keys.get('min_delta', {}).get('label', '--')} | "
            f"maxΔ {keys.get('max_delta', {}).get('label', '--')}"
        )
        self.plot.setLabel("bottom", f"Time relative to {self.current_reference_label()} (s)")
        self.plot.setLabel("left", "Filtered ECG 0.5-40 Hz, local median removed")
        self.plot.setXRange(float(x_grid[0]), float(x_grid[-1]), padding=0)
        visible_arrays = [tr.get("y") for tr in traces if isinstance(tr, dict) and tr.get("y") is not None]
        ymin, ymax = self.robust_y_range_from_arrays(visible_arrays)
        self.plot.setYRange(float(ymin), float(ymax), padding=0)

    def key_triplet_summary_text(self):
        try:
            _x_grid, traces = self.collect_triplet_traces()
            if not traces:
                return []
            keys = self.key_triplets(traces)
            def line(name, tr):
                if tr is None:
                    return f"{name}: --"
                return (
                    f"{name}: {tr.get('label', '--')} | "
                    f"RR-pre {tr.get('rr_pre_ms', float('nan')):.1f} ms | "
                    f"RR-post {tr.get('rr_post_ms', float('nan')):.1f} ms | "
                    f"ΔRR {tr.get('delta_ms', float('nan')):+.1f} ms"
                )
            return [
                "",
                "Key triplets in current recording",
                line("White nearest mean", keys.get("mean")),
                line("Purple nearest median", keys.get("median")),
                line("Cyan smallest |ΔRR|", keys.get("min_delta")),
                line("Pink largest |ΔRR|", keys.get("max_delta")),
            ]
        except Exception:
            return []

    def update_right_panels(self):
        self.update_measurements_box()
        self.navigation_box.setPlainText("\n".join([
            "Navigation",
            "",
            "Arrow-key UI navigation:",
            "- Default target after loading is View.",
            "- Left / Right: move target: Ch, View, Triplet, Reference.",
            "- Up / Down: change current target option.",
            "- In Raw / Filtered triplet, Triplet target Up/Down changes triplet.",
            "",
            "Triplet meaning:",
            "- Triplet 1 = complexes 1, 2, 3.",
            "- RR-pre = A→B.",
            "- RR-post = B→C.",
            "- ΔRR = RR-post - RR-pre.",
            "",
            "Backup:",
            "- Ctrl+Left / Ctrl+Right: previous / next triplet.",
        ]))
        self.method_box.setPlainText("\n".join([
            "Method",
            "",
            "- R peaks are detected from the shared ECG review-style filtered signal.",
            "- Complete complexes are used to build triplets.",
            "- Triplet n contains complexes n, n+1 and n+2.",
            "- This is the visual bridge to RMSSD, pNN50 and Poincaré.",
            "- Mean / median examples are real recorded triplets nearest to the mean or median RR-pre/RR-post point.",
            "- Cyan = smallest |ΔRR| triplet.",
            "- Pink = largest |ΔRR| triplet.",
            "- Purple = nearest median triplet.",
            "- White = nearest mean triplet.",
        ]))

    def update_measurements_box(self):
        if self.time_s is None or self.triplet_count() <= 0:
            self.measurements_box.setPlainText("Load raw.csv to inspect RR triplets.")
            return
        i = max(0, min(self.triplet_index, self.triplet_count() - 1))
        a, b, c, t1, t2, t3 = self.triplet_times(i)
        rr_pre = (t2 - t1) * 1000.0
        rr_post = (t3 - t2) * 1000.0
        delta = rr_post - rr_pre
        abs_delta = abs(delta)
        pnn50 = "yes" if abs_delta > 50.0 else "no"
        rmssd_contrib = delta * delta
        txt = [
            "Triplet Measurements",
            "",
            f"Selected triplet: {i + 1}/{self.triplet_count()}",
            f"Complexes shown: {i + 1}, {i + 2}, {i + 3}",
            f"View: {self.current_view_name()}",
            f"Reference: {self.current_reference_label()}",
            "",
            f"Complex A R time: {t1:.3f} s",
            f"Complex B R time: {t2:.3f} s",
            f"Complex C R time: {t3:.3f} s",
            "",
            f"RR-pre  A→B: {rr_pre:.1f} ms",
            f"RR-post B→C: {rr_post:.1f} ms",
            f"ΔRR: {delta:+.1f} ms",
            f"|ΔRR|: {abs_delta:.1f} ms",
            f"pNN50 contribution: {pnn50}",
            f"RMSSD contribution: ΔRR² = {rmssd_contrib:.1f} ms²",
            f"Poincaré point: ({rr_pre:.1f}, {rr_post:.1f})",
            *self.key_triplet_summary_text(),
            "",
            f"Detected R peaks: {len(self.r_peaks)}",
            f"Complete complexes: {len(self.complete_peaks)}",
        ]
        self.measurements_box.setPlainText("\n".join(txt))
