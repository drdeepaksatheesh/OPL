# -*- coding: utf-8 -*-
"""
Visual HRV / HRV Derivation Studio for OpenPhysiologyLab.

Teaching goal:
    ECG waveform -> R peaks -> RR intervals -> accepted NN intervals
    -> table rows -> mathematical derivation -> visual geometry -> result.

This panel is intentionally visual and auditable. It currently loads a CSV
independently and applies a transparent basic NN mask. Later it should consume
the accepted/rejected NN decisions directly from the RR / NN Table tab.
"""

from __future__ import annotations

import csv
import io
import math
import json
import zipfile
from pathlib import Path

import numpy as np

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QGroupBox,
    QPushButton,
    QLabel,
    QFileDialog,
    QComboBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
)

import pyqtgraph as pg


class ECGVisualHRVPanel(QWidget):
    """Metric-by-metric HRV derivation studio."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.csv_path = None
        self.recording_metadata = {}
        self.time_s = np.asarray([], dtype=float)
        self.channels = {}
        self.channel_name = ""
        self.raw = np.asarray([], dtype=float)
        self.filtered = np.asarray([], dtype=float)
        self.fs = 500.0

        self.r_peaks = np.asarray([], dtype=int)
        self.complete_peaks = np.asarray([], dtype=int)
        self.interval_rows = []
        self.nn_rows = []
        self.successive_pairs_cache = []

        self.selected_source_index = 0
        self.anim_timer = QTimer(self)
        self.anim_timer.setInterval(650)
        self.anim_timer.timeout.connect(self.animation_tick)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        title = QLabel("Visual HRV Derivation Studio")
        title.setStyleSheet("font-weight: bold; color: #E6C200;")
        root.addWidget(title)

        subtitle = QLabel(
            "Every HRV value is shown as: RR/NN source rows → formula → visual geometry → result."
        )
        root.addWidget(subtitle)

        controls_group = QGroupBox("Source and metric")
        controls = QHBoxLayout(controls_group)
        controls.setContentsMargins(8, 8, 8, 8)

        self.load_button = QPushButton("Load ECG file")
        self.load_button.clicked.connect(self.load_csv_dialog)
        controls.addWidget(self.load_button)

        controls.addWidget(QLabel("Ch"))
        self.channel_box = QComboBox()
        self.channel_box.setMinimumWidth(90)
        self.channel_box.currentTextChanged.connect(self.change_channel)
        controls.addWidget(self.channel_box)

        controls.addWidget(QLabel("Metric"))
        self.metric_box = QComboBox()
        self.metric_box.addItems([
            "NN tachogram source",
            "Mean NN / Mean HR",
            "SDNN derivation",
            "RMSSD derivation",
            "SDSD derivation",
            "pNN50 derivation",
            "Poincaré source",
            "Instant HR trend",
        ])
        self.metric_box.setMinimumWidth(220)
        self.metric_box.currentTextChanged.connect(self.metric_changed)
        controls.addWidget(self.metric_box)

        self.prev_button = QPushButton("◀")
        self.prev_button.clicked.connect(lambda: self.step_source(-1))
        controls.addWidget(self.prev_button)

        self.next_button = QPushButton("▶")
        self.next_button.clicked.connect(lambda: self.step_source(1))
        controls.addWidget(self.next_button)

        self.animate_button = QPushButton("Animate source")
        self.animate_button.clicked.connect(self.toggle_animation)
        controls.addWidget(self.animate_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_view)
        controls.addWidget(self.reset_button)

        self.status_label = QLabel("Load an ECG CSV to begin.")
        controls.addWidget(self.status_label, stretch=1)

        root.addWidget(controls_group)

        main_split = QSplitter(Qt.Horizontal)
        root.addWidget(main_split, stretch=1)

        # Left: ECG source + visual derivation
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        plot_split = QSplitter(Qt.Vertical)
        self.ecg_plot = pg.PlotWidget()
        self.visual_plot = pg.PlotWidget()

        for plot in (self.ecg_plot, self.visual_plot):
            plot.setBackground("#05080D")
            plot.showGrid(x=True, y=True, alpha=0.22)
            plot.setMenuEnabled(False)
            plot.plotItem.vb.setMouseEnabled(x=False, y=False)
            plot.getAxis("bottom").setPen(pg.mkPen("#AAB2BD"))
            plot.getAxis("left").setPen(pg.mkPen("#AAB2BD"))
            plot.getAxis("bottom").setTextPen(pg.mkPen("#D8DEE9"))
            plot.getAxis("left").setTextPen(pg.mkPen("#D8DEE9"))

        self.ecg_plot.setMinimumHeight(240)
        self.visual_plot.setMinimumHeight(420)

        plot_split.addWidget(self.ecg_plot)
        plot_split.addWidget(self.visual_plot)
        plot_split.setSizes([300, 600])
        plot_split.setCollapsible(0, False)
        plot_split.setCollapsible(1, False)
        left_layout.addWidget(plot_split)
        main_split.addWidget(left)

        # Right: source table + formula + interpretation
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(6)

        source_group = QGroupBox("1. Source rows from RR / NN table")
        source_layout = QVBoxLayout(source_group)
        self.source_table = QTableWidget()
        self.source_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.source_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.source_table.cellClicked.connect(self.source_row_clicked)
        self.source_table.verticalHeader().setVisible(False)
        self.source_table.setAlternatingRowColors(True)
        source_layout.addWidget(self.source_table)
        right_layout.addWidget(source_group, stretch=3)

        formula_group = QGroupBox("2. Mathematical derivation")
        formula_layout = QVBoxLayout(formula_group)
        self.formula_box = QPlainTextEdit()
        self.formula_box.setReadOnly(True)
        formula_layout.addWidget(self.formula_box)
        right_layout.addWidget(formula_group, stretch=2)

        meaning_group = QGroupBox("3. Visual meaning / result")
        meaning_layout = QVBoxLayout(meaning_group)
        self.meaning_box = QPlainTextEdit()
        self.meaning_box.setReadOnly(True)
        meaning_layout.addWidget(self.meaning_box)
        right_layout.addWidget(meaning_group, stretch=2)

        main_split.addWidget(right)
        main_split.setSizes([1360, 520])

        self._style_text_boxes()
        self._fix_group_title_padding()
        self.update_all()

    def _style_text_boxes(self):
        style = (
            "QPlainTextEdit {"
            " background-color: #050A10;"
            " color: #D8DEE9;"
            " border: 1px solid #243746;"
            " font-size: 10pt;"
            "}"
            "QTableWidget {"
            " background-color: #050A10;"
            " alternate-background-color: #07111A;"
            " color: #D8DEE9;"
            " gridline-color: #243746;"
            " selection-background-color: #123D4A;"
            " selection-color: #E8FAFF;"
            "}"
            "QHeaderView::section {"
            " background-color: #0B1520;"
            " color: #E6C200;"
            " border: 1px solid #243746;"
            " padding: 3px;"
            "}"
        )
        self.formula_box.setStyleSheet(style)
        self.meaning_box.setStyleSheet(style)
        self.source_table.setStyleSheet(style)

    def _fix_group_title_padding(self):
        style = (
            "QGroupBox {"
            " margin-top: 18px;"
            " padding-top: 10px;"
            " border: 1px solid #243746;"
            " border-radius: 4px;"
            "}"
            "QGroupBox::title {"
            " subcontrol-origin: margin;"
            " subcontrol-position: top left;"
            " left: 8px;"
            " top: 2px;"
            " padding: 0 4px;"
            " color: #E6C200;"
            " font-weight: bold;"
            "}"
        )
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(style)

    # ------------------------------------------------------------------
    # Loading and signal processing
    # ------------------------------------------------------------------

    def load_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load ECG recording",
            "",
            "ECG recordings (*.csv *.zip);;CSV files (*.csv);;OPL recording packages (*.zip);;All files (*.*)",
        )
        if path:
            self.load_csv(path)


    def load_csv(self, path):
        self.csv_path = str(path)
        time_s, channels, metadata = self.read_numeric_recording(path)
        self.recording_metadata = metadata or {}
        if not channels:
            self.status_label.setText("No usable signal channel found. Check raw.csv columns.")
            return

        self.time_s = time_s
        self.channels = channels

        self.channel_box.blockSignals(True)
        self.channel_box.clear()
        for name in channels.keys():
            self.channel_box.addItem(name)
        default_ch = self.choose_default_channel(channels)
        self.channel_box.setCurrentText(default_ch)
        self.channel_box.blockSignals(False)

        self.channel_name = default_ch
        self.prepare_channel(default_ch)
        self.status_label.setText(self.status_text())
        self.update_all()

    def change_channel(self, name):
        if not name or name not in self.channels:
            return
        self.channel_name = name
        self.prepare_channel(name)
        self.status_label.setText(self.status_text())
        self.update_all()

    def prepare_channel(self, name):
        self.raw = np.asarray(self.channels[name], dtype=float)
        self.fs = self.safe_fs(self.time_s)
        self.filtered = self.ecg_review_filter(self.raw, self.fs)
        self.r_peaks = self.detect_r_peaks(self.filtered, self.fs)
        self.complete_peaks = self.complete_complex_peaks(self.r_peaks)
        self.interval_rows = self.build_interval_rows()
        self.nn_rows = [r for r in self.interval_rows if r["accepted"]]
        self.successive_pairs_cache = self.successive_nn_pairs()
        self.selected_source_index = 0


    def read_numeric_recording(self, path):
        # Read CSV, OPL recording folder, or OPL recording zip.
        # Prefer device time_us/time_s over pc_time_s for HRV.
        path = Path(path)
        metadata = {}

        if path.is_dir():
            raw_path = path / "raw.csv"
            meta_path = path / "metadata.json"
            if not raw_path.exists():
                matches = list(path.rglob("raw.csv"))
                if matches:
                    raw_path = matches[0]
            if meta_path.exists():
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    metadata = {}
            if not raw_path.exists():
                return np.asarray([], dtype=float), {}, metadata
            return self.read_numeric_csv_text(raw_path.read_text(encoding="utf-8-sig", errors="replace"), source_name=str(raw_path), metadata=metadata)

        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                    raw_names = [n for n in names if n.lower().endswith("/raw.csv") or n.lower() == "raw.csv"]
                    if not raw_names:
                        raw_names = [n for n in names if n.lower().endswith(".csv")]
                    if not raw_names:
                        return np.asarray([], dtype=float), {}, metadata
                    raw_name = raw_names[0]

                    meta_names = [n for n in names if n.lower().endswith("/metadata.json") or n.lower() == "metadata.json"]
                    if meta_names:
                        try:
                            metadata = json.loads(zf.read(meta_names[0]).decode("utf-8", errors="replace"))
                        except Exception:
                            metadata = {}

                    raw_text = zf.read(raw_name).decode("utf-8-sig", errors="replace")
                    metadata["_opl_package_path"] = str(path)
                    metadata["_opl_raw_member"] = raw_name
                    return self.read_numeric_csv_text(raw_text, source_name=f"{path.name}:{raw_name}", metadata=metadata)
            except Exception:
                return np.asarray([], dtype=float), {}, metadata

        return self.read_numeric_csv_text(path.read_text(encoding="utf-8-sig", errors="replace"), source_name=str(path), metadata=metadata)

    def read_numeric_csv(self, path):
        # Backward-compatible wrapper used by older code paths.
        time_s, channels, _metadata = self.read_numeric_recording(path)
        return time_s, channels

    def read_numeric_csv_text(self, text, source_name="", metadata=None):
        metadata = metadata or {}
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return np.asarray([], dtype=float), {}, metadata

        headers = [h.strip() if h.strip() else f"col{i+1}" for i, h in enumerate(rows[0])]
        numeric = []
        for row in rows[1:]:
            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            vals = []
            ok = False
            for item in row[:len(headers)]:
                try:
                    item_s = str(item).strip()
                    if item_s == "":
                        val = np.nan
                    else:
                        val = float(item_s)
                        ok = True
                except Exception:
                    val = np.nan
                vals.append(val)
            if ok:
                numeric.append(vals)
        if not numeric:
            return np.asarray([], dtype=float), {}, metadata

        arr = np.asarray(numeric, dtype=float)
        time_idx = self.find_time_column(headers, arr)
        if time_idx is None:
            fs = float(metadata.get("sample_rate_target_hz") or metadata.get("measured_sample_rate_from_device_time_hz") or 500.0)
            if not np.isfinite(fs) or fs <= 0:
                fs = 500.0
            time_s = np.arange(arr.shape[0], dtype=float) / fs
        else:
            time_s = self.normalize_time(arr[:, time_idx])

        channels = {}
        blocked_exact = {"segment_id", "sample", "time_us", "time_ms", "time_s", "pc_time_s", "timestamp", "counter", "packet"}
        blocked_contains = ["time", "timestamp", "sample", "index", "packet", "counter", "marker", "event", "segment"]

        for i, name in enumerate(headers):
            if i == time_idx:
                continue
            lname = name.lower().strip()
            lname_compact = lname.replace(" ", "").replace("-", "_")
            if lname_compact in blocked_exact:
                continue
            if any(k in lname_compact for k in blocked_contains):
                continue

            col = arr[:, i].astype(float)
            good = np.isfinite(col)
            if np.count_nonzero(good) < 5:
                continue
            if np.nanmax(col) - np.nanmin(col) <= 1e-12:
                continue
            channels[name] = col

        return time_s, channels, metadata


    def find_time_column(self, headers, arr):
        # Prefer device time over PC time. pc_time_s is fallback only.
        lowered = [h.lower().strip() for h in headers]

        priority_exact = [
            "time_us",
            "device_time_us",
            "time_s",
            "device_time_s",
            "time_ms",
            "device_time_ms",
        ]
        for want in priority_exact:
            for i, lname in enumerate(lowered):
                if lname == want:
                    col = arr[:, i]
                    if np.count_nonzero(np.isfinite(col)) > 5:
                        return i

        for i, lname in enumerate(lowered):
            if "time_us" in lname or "device_time" in lname:
                col = arr[:, i]
                if np.count_nonzero(np.isfinite(col)) > 5:
                    return i

        for i, lname in enumerate(lowered):
            if "pc_time" in lname:
                continue
            if any(k == lname or k in lname for k in ["time", "timestamp", "seconds", "sec", "ms"]):
                col = arr[:, i]
                if np.count_nonzero(np.isfinite(col)) > 5:
                    return i

        for i, lname in enumerate(lowered):
            if "pc_time" in lname:
                col = arr[:, i]
                if np.count_nonzero(np.isfinite(col)) > 5:
                    return i

        return None

    def normalize_time(self, raw):
        t = np.asarray(raw, dtype=float)
        good = np.isfinite(t)
        if np.count_nonzero(good) < 3:
            return np.arange(len(t), dtype=float) / 500.0
        t = t.copy()
        if not np.all(good):
            idx = np.arange(len(t))
            t[~good] = np.interp(idx[~good], idx[good], t[good])
        t = t - t[0]
        d = np.diff(t)
        d = d[np.isfinite(d) & (d > 0)]
        if len(d) == 0:
            return np.arange(len(t), dtype=float) / 500.0
        med = float(np.median(d))
        if med > 100.0:
            t = t / 1_000_000.0
        elif med > 0.02:
            t = t / 1000.0
        return t

    def choose_default_channel(self, channels):
        keys = list(channels.keys())
        for want in ["ch1", "channel1", "a0", "ecg", "lead"]:
            for k in keys:
                if want in k.lower().replace(" ", ""):
                    return k
        ranges = [(np.nanmax(v) - np.nanmin(v), k) for k, v in channels.items()]
        ranges.sort(reverse=True)
        return ranges[0][1]

    def safe_fs(self, time_s):
        try:
            d = np.diff(np.asarray(time_s, dtype=float))
            d = d[np.isfinite(d) & (d > 0)]
            if len(d):
                fs = 1.0 / float(np.median(d))
                if 1.0 <= fs <= 100000.0:
                    return fs
        except Exception:
            pass
        return 500.0

    def ecg_review_filter(self, signal, fs):
        x = np.asarray(signal, dtype=float).copy()
        if not np.all(np.isfinite(x)):
            idx = np.arange(len(x))
            good = np.isfinite(x)
            if np.count_nonzero(good) >= 2:
                x[~good] = np.interp(idx[~good], idx[good], x[good])
            else:
                x[~good] = 0.0
        try:
            from scipy.signal import butter, filtfilt
            nyq = fs / 2.0
            low = max(0.001, 0.5 / nyq)
            high = min(0.999, 40.0 / nyq)
            if 0 < low < high < 1:
                b, a = butter(4, [low, high], btype="band")
                return filtfilt(b, a, x)
        except Exception:
            pass
        n = max(5, int(fs * 0.6))
        if n % 2 == 0:
            n += 1
        kernel = np.ones(n, dtype=float) / float(n)
        baseline = np.convolve(x, kernel, mode="same")
        return x - baseline

    def detect_r_peaks(self, signal, fs):
        x = np.asarray(signal, dtype=float)
        if len(x) < 10:
            return np.asarray([], dtype=int)
        pos = np.nanpercentile(x, 99) - np.nanmedian(x)
        neg = np.nanmedian(x) - np.nanpercentile(x, 1)
        y = x if pos >= neg else -x

        distance = max(1, int(0.45 * fs))
        prominence = max(1e-9, 0.25 * (np.nanpercentile(y, 98) - np.nanpercentile(y, 50)))
        height = np.nanpercentile(y, 85)
        try:
            from scipy.signal import find_peaks
            peaks, _ = find_peaks(y, distance=distance, prominence=prominence, height=height)
            return peaks.astype(int)
        except Exception:
            pass

        thr = np.nanpercentile(y, 92)
        candidates = []
        for i in range(1, len(y) - 1):
            if y[i] > thr and y[i] >= y[i - 1] and y[i] >= y[i + 1]:
                candidates.append(i)
        selected = []
        last = -10**9
        for i in candidates:
            if i - last >= distance:
                selected.append(i)
                last = i
            elif selected and y[i] > y[selected[-1]]:
                selected[-1] = i
                last = i
        return np.asarray(selected, dtype=int)

    def complete_complex_peaks(self, peaks):
        if len(peaks) == 0 or len(self.time_s) == 0:
            return np.asarray([], dtype=int)
        t0 = float(self.time_s[0])
        t1 = float(self.time_s[-1])
        keep = []
        for p in peaks:
            tp = float(self.time_s[int(p)])
            if tp - 0.25 >= t0 and tp + 0.55 <= t1:
                keep.append(int(p))
        return np.asarray(keep, dtype=int)

    def build_interval_rows(self):
        rows = []
        peaks = np.asarray(self.r_peaks, dtype=int)
        complete_set = set(int(p) for p in np.asarray(self.complete_peaks, dtype=int))
        for i in range(len(peaks) - 1):
            a = int(peaks[i])
            b = int(peaks[i + 1])
            ta = float(self.time_s[a])
            tb = float(self.time_s[b])
            rr = (tb - ta) * 1000.0
            hr = 60000.0 / rr if rr > 0 else np.nan
            accepted = bool(np.isfinite(rr) and 300.0 <= rr <= 2000.0)

            edge_note = ""
            if a not in complete_set or b not in complete_set:
                edge_note = "; edge morphology incomplete"

            rows.append({
                "id": i + 1,
                "a_peak": a,
                "b_peak": b,
                "a_morphology_complete": a in complete_set,
                "b_morphology_complete": b in complete_set,
                "a_time_s": ta,
                "b_time_s": tb,
                "mid_time_s": (ta + tb) / 2.0,
                "rr_ms": rr,
                "hr_bpm": hr,
                "accepted": accepted,
                "reason": ("basic accepted" if accepted else "outside basic NN range") + edge_note,
            })
        return rows

    def successive_nn_pairs(self):
        pairs = []
        nn = self.nn_rows
        for i in range(len(nn) - 1):
            a = nn[i]
            b = nn[i + 1]
            if int(b["id"]) != int(a["id"]) + 1:
                continue
            d = float(b["rr_ms"]) - float(a["rr_ms"])
            pairs.append((a, b, d, abs(d)))
        return pairs

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def nn_values(self):
        return np.asarray([r["rr_ms"] for r in self.nn_rows], dtype=float)

    def nn_times(self):
        return np.asarray([r["mid_time_s"] for r in self.nn_rows], dtype=float)

    def delta_values(self):
        return np.asarray([p[2] for p in self.successive_pairs_cache], dtype=float)

    def metrics(self):
        nn = self.nn_values()
        d = self.delta_values()
        out = {}
        if len(nn):
            hr = 60000.0 / nn
            out["n_nn"] = len(nn)
            out["mean_nn"] = float(np.nanmean(nn))
            out["mean_hr"] = float(np.nanmean(hr))
            out["min_hr"] = float(np.nanmin(hr))
            out["max_hr"] = float(np.nanmax(hr))
            out["sdnn"] = float(np.nanstd(nn, ddof=1)) if len(nn) > 1 else np.nan
        if len(d):
            ad = np.abs(d)
            out["n_pairs"] = len(d)
            out["rmssd"] = math.sqrt(float(np.nanmean(d * d)))
            out["sdsd"] = float(np.nanstd(d, ddof=1)) if len(d) > 1 else np.nan
            out["pnn50"] = 100.0 * float(np.count_nonzero(ad > 50.0)) / float(len(ad))
            x = np.asarray([p[0]["rr_ms"] for p in self.successive_pairs_cache], dtype=float)
            y = np.asarray([p[1]["rr_ms"] for p in self.successive_pairs_cache], dtype=float)
            diff = y - x
            summ = y + x
            out["sd1"] = math.sqrt(0.5) * float(np.nanstd(diff, ddof=1)) if len(diff) > 1 else np.nan
            out["sd2"] = math.sqrt(0.5) * float(np.nanstd(summ, ddof=1)) if len(summ) > 1 else np.nan
            out["sd1_sd2"] = out["sd1"] / out["sd2"] if out.get("sd2") and np.isfinite(out["sd2"]) else np.nan
        return out

    # ------------------------------------------------------------------
    # Source selection and animation
    # ------------------------------------------------------------------

    def status_text(self):
        if not self.csv_path:
            return "Load an ECG recording to begin."
        source = Path(self.csv_path).name
        if isinstance(getattr(self, "recording_metadata", None), dict):
            raw_member = self.recording_metadata.get("_opl_raw_member")
            if raw_member:
                source = f"{source} / {raw_member}"
        return (
            f"{source} | {self.channel_name} | fs {self.fs:.1f} Hz | "
            f"R {len(self.r_peaks)} | morphology complete {len(self.complete_peaks)} | "
            f"RR {len(self.interval_rows)} | NN {len(self.nn_rows)}"
        )

    def metric_changed(self, _text):
        self.selected_source_index = 0
        if self.anim_timer.isActive():
            self.anim_timer.stop()
            self.animate_button.setText("Animate source")
        self.update_all()

    def reset_view(self):
        self.selected_source_index = 0
        if self.anim_timer.isActive():
            self.anim_timer.stop()
            self.animate_button.setText("Animate source")
        self.update_all()

    def source_count(self):
        metric = self.metric_box.currentText()
        if metric in ("RMSSD derivation", "SDSD derivation", "pNN50 derivation", "Poincaré source"):
            return len(self.successive_pairs_cache)
        return len(self.nn_rows)

    def clamp_selected_index(self):
        count = self.source_count()
        if count <= 0:
            self.selected_source_index = 0
        else:
            self.selected_source_index = max(0, min(int(self.selected_source_index), count - 1))

    def step_source(self, step):
        count = self.source_count()
        if count <= 0:
            return
        self.selected_source_index = (int(self.selected_source_index) + int(step)) % count
        self.update_all()

    def toggle_animation(self):
        if self.anim_timer.isActive():
            self.anim_timer.stop()
            self.animate_button.setText("Animate source")
            return
        if self.source_count() <= 0:
            return
        self.animate_button.setText("Stop")
        self.anim_timer.start()

    def animation_tick(self):
        self.step_source(1)

    def source_row_clicked(self, row, _col):
        self.selected_source_index = int(row)
        self.update_all(select_table=False)

    # ------------------------------------------------------------------
    # Plot helpers
    # ------------------------------------------------------------------
    def finite_range(self, values, pad_fraction=0.08, min_pad=1.0):
        arr = np.asarray(values, dtype=float)
        arr = arr[np.isfinite(arr)]
        if len(arr) == 0:
            return -1.0, 1.0
        lo = float(np.nanmin(arr))
        hi = float(np.nanmax(arr))
        span = hi - lo
        if span <= 1e-12:
            pad = max(min_pad, abs(lo) * 0.05)
        else:
            pad = max(min_pad, span * pad_fraction)
        return lo - pad, hi + pad

    def decimate_xy(self, x, y, max_points=8000):
        x = np.asarray(x)
        y = np.asarray(y)
        n = len(x)
        if n <= max_points:
            return x, y
        step = int(math.ceil(n / float(max_points)))
        return x[::step], y[::step]

    def selected_interval_rows_for_metric(self):
        metric = self.metric_box.currentText()
        self.clamp_selected_index()

        if metric in ("RMSSD derivation", "SDSD derivation", "pNN50 derivation", "Poincaré source"):
            if not self.successive_pairs_cache:
                return []
            a, b, _d, _ad = self.successive_pairs_cache[self.selected_source_index]
            return [a, b]

        if not self.nn_rows:
            return []
        return [self.nn_rows[self.selected_source_index]]

    def current_ecg_window(self):
        if not len(self.time_s):
            return 0.0, 1.0
        t0 = float(self.time_s[0])
        t1 = float(self.time_s[-1])
        rows = self.selected_interval_rows_for_metric()
        if not rows:
            return t0, min(t1, t0 + 10.0)

        lo = min(float(r["a_time_s"]) for r in rows)
        hi = max(float(r["b_time_s"]) for r in rows)
        center = (lo + hi) / 2.0
        width = max(6.0, (hi - lo) + 4.0)
        return max(t0, center - width / 2.0), min(t1, center + width / 2.0)

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------
    def update_all(self, select_table=True):
        self.clamp_selected_index()
        self.populate_source_table(select_table=select_table)
        self.update_plots()
        self.update_formula_and_meaning()
        self.status_label.setText(self.status_text())

    def update_plots(self):
        self.ecg_plot.clear()
        self.visual_plot.clear()

        if len(self.time_s) == 0 or len(self.filtered) == 0:
            self.ecg_plot.setTitle("Load an ECG CSV")
            self.visual_plot.setTitle("HRV derivation will appear here")
            return

        self.plot_ecg_source()
        metric = self.metric_box.currentText()

        if metric == "NN tachogram source":
            self.plot_nn_tachogram()
        elif metric == "Mean NN / Mean HR":
            self.plot_mean_nn_hr()
        elif metric == "SDNN derivation":
            self.plot_sdnn()
        elif metric == "RMSSD derivation":
            self.plot_rmssd()
        elif metric == "SDSD derivation":
            self.plot_sdsd()
        elif metric == "pNN50 derivation":
            self.plot_pnn50()
        elif metric == "Poincaré source":
            self.plot_poincare()
        elif metric == "Instant HR trend":
            self.plot_instant_hr()

    # ------------------------------------------------------------------
    # ECG source plot
    # ------------------------------------------------------------------
    def plot_ecg_source(self):
        x0, x1 = self.current_ecg_window()
        mask = (self.time_s >= x0) & (self.time_s <= x1)
        tx, sy = self.decimate_xy(self.time_s[mask], self.filtered[mask], max_points=6000)

        self.ecg_plot.plot(tx, sy, pen=pg.mkPen("#E6C200", width=1))
        self.ecg_plot.setLabel("bottom", "Recording time", units="s")
        self.ecg_plot.setLabel("left", "Filtered ECG", units="raw")
        self.ecg_plot.setTitle("ECG source: highlighted R-to-R interval(s) feed the selected HRV calculation")

        # visible R peaks
        for p in self.r_peaks:
            t = float(self.time_s[int(p)])
            if x0 <= t <= x1:
                self.ecg_plot.addItem(pg.InfiniteLine(pos=t, angle=90, pen=pg.mkPen((60, 160, 180, 75), width=1)))

        rows = self.selected_interval_rows_for_metric()
        ymax = float(np.nanmax(sy)) if len(sy) else 0.0
        for i, row in enumerate(rows):
            a_t = float(row["a_time_s"])
            b_t = float(row["b_time_s"])
            if b_t < x0 or a_t > x1:
                continue
            brush = pg.mkBrush(0, 229, 255, 32 if i == 0 else 22)
            region = pg.LinearRegionItem(
                values=[a_t, b_t],
                orientation="vertical",
                movable=False,
                brush=brush,
                pen=pg.mkPen("#00E5FF", width=1),
            )
            self.ecg_plot.addItem(region)
            for label, t in [("A R", a_t), ("B R", b_t)]:
                self.ecg_plot.addItem(pg.InfiniteLine(pos=t, angle=90, pen=pg.mkPen("#00E5FF", width=2)))
                txt = pg.TextItem(label, color="#E8FAFF", anchor=(0.5, 1.0))
                txt.setPos(t, ymax)
                self.ecg_plot.addItem(txt)

        self.ecg_plot.setXRange(float(x0), float(x1), padding=0.0)
        y0, y1 = self.finite_range(sy, pad_fraction=0.08, min_pad=0.05)
        self.ecg_plot.setYRange(y0, y1, padding=0.0)

    # ------------------------------------------------------------------
    # Visual plots
    # ------------------------------------------------------------------
    def plot_nn_tachogram(self):
        x = self.nn_times()
        y = self.nn_values()
        if len(y) == 0:
            self.visual_plot.setTitle("No accepted NN intervals")
            return
        self.visual_plot.plot(x, y, pen=pg.mkPen("#00BFFF", width=2))
        self.visual_plot.addItem(pg.ScatterPlotItem(x=x, y=y, size=6, brush=pg.mkBrush("#00BFFF"), pen=pg.mkPen("#BFEFFF")))

        mean = float(np.nanmean(y))
        sd = float(np.nanstd(y, ddof=1)) if len(y) > 1 else np.nan
        self.visual_plot.addItem(pg.InfiniteLine(pos=mean, angle=0, pen=pg.mkPen("#FFFFFF", style=Qt.DashLine)))
        if np.isfinite(sd):
            self.visual_plot.addItem(pg.InfiniteLine(pos=mean + sd, angle=0, pen=pg.mkPen((255, 255, 255, 110), style=Qt.DotLine)))
            self.visual_plot.addItem(pg.InfiniteLine(pos=mean - sd, angle=0, pen=pg.mkPen((255, 255, 255, 110), style=Qt.DotLine)))

        if self.nn_rows:
            idx = max(0, min(self.selected_source_index, len(self.nn_rows) - 1))
            row = self.nn_rows[idx]
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[row["mid_time_s"]], y=[row["rr_ms"]],
                size=14, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))

        self.visual_plot.setTitle(f"NN tachogram source | mean NN {mean:.1f} ms | SDNN {sd:.1f} ms")
        self.visual_plot.setLabel("bottom", "Recording time", units="s")
        self.visual_plot.setLabel("left", "NN interval", units="ms")
        self.set_visual_range(x, y, y_min_pad=25.0)

    def plot_mean_nn_hr(self):
        x = self.nn_times()
        y = self.nn_values()
        if len(y) == 0:
            self.visual_plot.setTitle("No accepted NN intervals")
            return
        mean = float(np.nanmean(y))
        mean_hr = float(np.nanmean(60000.0 / y))

        self.visual_plot.plot(x, y, pen=pg.mkPen("#00BFFF", width=2), symbol="o", symbolSize=6, symbolBrush="#00BFFF")
        self.visual_plot.addItem(pg.InfiniteLine(pos=mean, angle=0, pen=pg.mkPen("#FFFFFF", width=2, style=Qt.DashLine)))

        self.visual_plot.setTitle(f"Mean NN / Mean HR | mean NN {mean:.1f} ms | mean HR {mean_hr:.1f} bpm")
        self.visual_plot.setLabel("bottom", "Recording time", units="s")
        self.visual_plot.setLabel("left", "NN interval", units="ms")
        self.set_visual_range(x, y, y_min_pad=25.0)

    def plot_sdnn(self):
        x = self.nn_times()
        y = self.nn_values()
        if len(y) == 0:
            self.visual_plot.setTitle("No accepted NN intervals")
            return
        mean = float(np.nanmean(y))
        sdnn = float(np.nanstd(y, ddof=1)) if len(y) > 1 else np.nan

        self.visual_plot.plot(x, y, pen=pg.mkPen("#00BFFF", width=1), symbol="o", symbolSize=6, symbolBrush="#00BFFF")
        self.visual_plot.addItem(pg.InfiniteLine(pos=mean, angle=0, pen=pg.mkPen("#FFFFFF", width=2, style=Qt.DashLine)))

        step = max(1, int(math.ceil(len(x) / 90)))
        for xi, yi in zip(x[::step], y[::step]):
            self.visual_plot.plot([xi, xi], [mean, yi], pen=pg.mkPen((255, 255, 255, 75), width=1))

        if self.nn_rows:
            idx = max(0, min(self.selected_source_index, len(self.nn_rows) - 1))
            row = self.nn_rows[idx]
            self.visual_plot.plot(
                [row["mid_time_s"], row["mid_time_s"]],
                [mean, row["rr_ms"]],
                pen=pg.mkPen("#FF00FF", width=3),
            )
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[row["mid_time_s"]], y=[row["rr_ms"]],
                size=14, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))

        self.visual_plot.setTitle(f"SDNN derivation | vertical deviations from mean NN | SDNN {sdnn:.1f} ms")
        self.visual_plot.setLabel("bottom", "Recording time", units="s")
        self.visual_plot.setLabel("left", "NN interval", units="ms")
        self.set_visual_range(x, y, y_min_pad=25.0)

    def plot_rmssd(self):
        pairs = self.successive_pairs_cache
        if not pairs:
            self.visual_plot.setTitle("No successive NN pairs")
            return
        idx = np.arange(1, len(pairs) + 1)
        d = np.asarray([p[2] for p in pairs], dtype=float)
        absd = np.abs(d)
        rmssd = math.sqrt(float(np.nanmean(d * d)))

        self.visual_plot.plot(idx, absd, pen=pg.mkPen("#FFB000", width=2), symbol="o", symbolSize=6, symbolBrush="#FFB000")
        if len(pairs):
            si = max(0, min(self.selected_source_index, len(pairs) - 1))
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[idx[si]], y=[absd[si]], size=15, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))
        self.visual_plot.setTitle(f"RMSSD derivation | |ΔNN| then square, mean, square-root | RMSSD {rmssd:.1f} ms")
        self.visual_plot.setLabel("bottom", "Successive NN pair number")
        self.visual_plot.setLabel("left", "|ΔNN|", units="ms")
        self.set_index_range(idx, absd, y_min_pad=5.0)

    def plot_sdsd(self):
        pairs = self.successive_pairs_cache
        if not pairs:
            self.visual_plot.setTitle("No successive NN pairs")
            return
        idx = np.arange(1, len(pairs) + 1)
        d = np.asarray([p[2] for p in pairs], dtype=float)
        mean_d = float(np.nanmean(d))
        sdsd = float(np.nanstd(d, ddof=1)) if len(d) > 1 else np.nan

        self.visual_plot.plot(idx, d, pen=pg.mkPen("#AAFFAA", width=2), symbol="o", symbolSize=6, symbolBrush="#AAFFAA")
        self.visual_plot.addItem(pg.InfiniteLine(pos=mean_d, angle=0, pen=pg.mkPen("#FFFFFF", style=Qt.DashLine)))
        if len(pairs):
            si = max(0, min(self.selected_source_index, len(pairs) - 1))
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[idx[si]], y=[d[si]], size=15, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))
        self.visual_plot.setTitle(f"SDSD derivation | spread of ΔNN values | SDSD {sdsd:.1f} ms")
        self.visual_plot.setLabel("bottom", "Successive NN pair number")
        self.visual_plot.setLabel("left", "ΔNN", units="ms")
        self.set_index_range(idx, d, y_min_pad=10.0)

    def plot_pnn50(self):
        pairs = self.successive_pairs_cache
        if not pairs:
            self.visual_plot.setTitle("No successive NN pairs")
            return
        idx = np.arange(1, len(pairs) + 1)
        absd = np.asarray([p[3] for p in pairs], dtype=float)
        over = absd > 50.0
        pnn50 = 100.0 * float(np.count_nonzero(over)) / float(len(absd))

        brushes = [pg.mkBrush("#FF5555") if v else pg.mkBrush("#00BFFF") for v in over]
        self.visual_plot.addItem(pg.ScatterPlotItem(x=idx, y=absd, size=8, brush=brushes, pen=pg.mkPen("#D8DEE9")))
        self.visual_plot.plot(idx, absd, pen=pg.mkPen((180, 180, 180, 95), width=1))
        self.visual_plot.addItem(pg.InfiniteLine(pos=50.0, angle=0, pen=pg.mkPen("#FF5555", width=2, style=Qt.DashLine)))
        if len(pairs):
            si = max(0, min(self.selected_source_index, len(pairs) - 1))
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[idx[si]], y=[absd[si]], size=15, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))

        self.visual_plot.setTitle(f"pNN50 derivation | red = |ΔNN| > 50 ms | pNN50 {pnn50:.1f}%")
        self.visual_plot.setLabel("bottom", "Successive NN pair number")
        self.visual_plot.setLabel("left", "|ΔNN|", units="ms")
        self.set_index_range(idx, np.concatenate([absd, np.asarray([50.0])]), y_min_pad=5.0)

    def plot_poincare(self):
        pairs = self.successive_pairs_cache
        if not pairs:
            self.visual_plot.setTitle("No successive NN pairs")
            return
        x = np.asarray([p[0]["rr_ms"] for p in pairs], dtype=float)
        y = np.asarray([p[1]["rr_ms"] for p in pairs], dtype=float)

        self.visual_plot.addItem(pg.ScatterPlotItem(x=x, y=y, size=8, brush=pg.mkBrush(0, 191, 255, 135), pen=pg.mkPen("#BFEFFF")))

        lo = float(np.nanmin([np.nanmin(x), np.nanmin(y)]))
        hi = float(np.nanmax([np.nanmax(x), np.nanmax(y)]))
        pad = max(20.0, 0.10 * (hi - lo))
        lo -= pad
        hi += pad
        self.visual_plot.plot([lo, hi], [lo, hi], pen=pg.mkPen("#888888", style=Qt.DashLine))

        si = max(0, min(self.selected_source_index, len(pairs) - 1))
        self.visual_plot.addItem(pg.ScatterPlotItem(
            x=[x[si]], y=[y[si]], size=15, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
        ))

        sd1, sd2 = self.poincare_sd1_sd2(x, y)
        self.visual_plot.setTitle(f"Poincaré source | each point = (NNn, NNn+1) | SD1 {sd1:.1f} ms | SD2 {sd2:.1f} ms")
        self.visual_plot.setLabel("bottom", "NNn", units="ms")
        self.visual_plot.setLabel("left", "NNn+1", units="ms")
        self.visual_plot.setXRange(lo, hi, padding=0.0)
        self.visual_plot.setYRange(lo, hi, padding=0.0)

    def plot_instant_hr(self):
        x = self.nn_times()
        nn = self.nn_values()
        if len(nn) == 0:
            self.visual_plot.setTitle("No accepted NN intervals")
            return
        hr = 60000.0 / nn
        self.visual_plot.plot(x, hr, pen=pg.mkPen("#7CFC00", width=2), symbol="o", symbolSize=6, symbolBrush="#7CFC00")
        mean_hr = float(np.nanmean(hr))
        self.visual_plot.addItem(pg.InfiniteLine(pos=mean_hr, angle=0, pen=pg.mkPen("#FFFFFF", style=Qt.DashLine)))
        if self.nn_rows:
            idx = max(0, min(self.selected_source_index, len(self.nn_rows) - 1))
            row = self.nn_rows[idx]
            self.visual_plot.addItem(pg.ScatterPlotItem(
                x=[row["mid_time_s"]], y=[row["hr_bpm"]],
                size=14, brush=pg.mkBrush("#FF00FF"), pen=pg.mkPen("#FFFFFF", width=2)
            ))
        self.visual_plot.setTitle(f"Instant HR trend | HR = 60000 / NN | mean HR {mean_hr:.1f} bpm")
        self.visual_plot.setLabel("bottom", "Recording time", units="s")
        self.visual_plot.setLabel("left", "Instant HR", units="bpm")
        self.set_visual_range(x, hr, y_min_pad=3.0)

    def set_visual_range(self, x, y, y_min_pad=1.0):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        x = x[np.isfinite(x)]
        if len(x) == 0:
            return
        x0 = float(np.nanmin(x))
        x1 = float(np.nanmax(x))
        if x1 <= x0:
            x1 = x0 + 1.0
        xpad = max(0.25, 0.02 * (x1 - x0))
        y0, y1 = self.finite_range(y, pad_fraction=0.10, min_pad=y_min_pad)
        self.visual_plot.setXRange(x0 - xpad, x1 + xpad, padding=0.0)
        self.visual_plot.setYRange(y0, y1, padding=0.0)

    def set_index_range(self, x, y, y_min_pad=1.0):
        x = np.asarray(x, dtype=float)
        if len(x) == 0:
            return
        x0 = float(np.nanmin(x)) - 1.0
        x1 = float(np.nanmax(x)) + 1.0
        y0, y1 = self.finite_range(y, pad_fraction=0.12, min_pad=y_min_pad)
        self.visual_plot.setXRange(x0, x1, padding=0.0)
        self.visual_plot.setYRange(y0, y1, padding=0.0)

    def poincare_sd1_sd2(self, x, y):
        if len(x) < 2:
            return np.nan, np.nan
        diff = y - x
        summ = y + x
        sd1 = math.sqrt(0.5) * float(np.nanstd(diff, ddof=1))
        sd2 = math.sqrt(0.5) * float(np.nanstd(summ, ddof=1))
        return sd1, sd2

    # ------------------------------------------------------------------
    # Source table and derivation text
    # ------------------------------------------------------------------
    def populate_source_table(self, select_table=True):
        metric = self.metric_box.currentText()
        self.source_table.blockSignals(True)
        self.source_table.clear()

        if metric in ("RMSSD derivation", "SDSD derivation", "pNN50 derivation", "Poincaré source"):
            rows = self.successive_pairs_cache
            headers = ["#", "NNn", "NNn+1", "Δ", "|Δ|", "Δ²", ">50"]
            self.source_table.setColumnCount(len(headers))
            self.source_table.setHorizontalHeaderLabels(headers)
            self.source_table.setRowCount(len(rows))
            for r, (a, b, d, ad) in enumerate(rows):
                vals = [
                    str(r + 1),
                    f"{a['rr_ms']:.1f}",
                    f"{b['rr_ms']:.1f}",
                    f"{d:+.1f}",
                    f"{ad:.1f}",
                    f"{d*d:.1f}",
                    "yes" if ad > 50.0 else "no",
                ]
                for c, val in enumerate(vals):
                    self.source_table.setItem(r, c, QTableWidgetItem(val))
        else:
            rows = self.nn_rows
            headers = ["#", "A→B", "A s", "B s", "NN ms", "HR bpm", "Reason"]
            self.source_table.setColumnCount(len(headers))
            self.source_table.setHorizontalHeaderLabels(headers)
            self.source_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                vals = [
                    str(row["id"]),
                    f"{row['id']}→{row['id']+1}",
                    f"{row['a_time_s']:.3f}",
                    f"{row['b_time_s']:.3f}",
                    f"{row['rr_ms']:.1f}",
                    f"{row['hr_bpm']:.1f}",
                    row["reason"],
                ]
                for c, val in enumerate(vals):
                    self.source_table.setItem(r, c, QTableWidgetItem(val))

        self.source_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.source_table.resizeRowsToContents()
        self.source_table.blockSignals(False)

        if select_table and self.source_table.rowCount() > 0:
            self.clamp_selected_index()
            self.source_table.selectRow(self.selected_source_index)
            item = self.source_table.item(self.selected_source_index, 0)
            if item is not None:
                self.source_table.scrollToItem(item, QAbstractItemView.EnsureVisible)

    def update_formula_and_meaning(self):
        metric = self.metric_box.currentText()
        m = self.metrics()
        formula = ""
        meaning = ""

        if not self.nn_rows:
            self.formula_box.setPlainText("Load ECG data and create accepted NN intervals.")
            self.meaning_box.setPlainText("No accepted NN intervals yet.")
            return

        if metric == "NN tachogram source":
            row = self.nn_rows[max(0, min(self.selected_source_index, len(self.nn_rows)-1))]
            formula = "\n".join([
                "One tachogram point comes from two R peaks:",
                "",
                "NN_i = time(B R) - time(A R)",
                "",
                f"Selected:",
                f"A R = {row['a_time_s']:.3f} s",
                f"B R = {row['b_time_s']:.3f} s",
                f"NN = {row['rr_ms']:.1f} ms",
                f"HR = 60000 / NN = {row['hr_bpm']:.1f} bpm",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "The upper ECG panel shows the source A R → B R interval.",
                "The lower tachogram shows that interval as one point.",
                "",
                "Longer NN = slower heart rate.",
                "Shorter NN = faster heart rate.",
                "",
                "This is the safest ECG-to-tachogram teaching view.",
            ])

        elif metric == "Mean NN / Mean HR":
            formula = "\n".join([
                "Mean NN:",
                "mean(NN_i) = sum(NN_i) / N",
                "",
                "Mean HR in this panel:",
                "HR_i = 60000 / NN_i",
                "mean HR = average(HR_i)",
                "",
                f"N = {m.get('n_nn', 0)}",
                f"Mean NN = {m.get('mean_nn', np.nan):.1f} ms",
                f"Mean HR = {m.get('mean_hr', np.nan):.1f} bpm",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "The dashed horizontal line is mean NN.",
                "All accepted NN rows contribute equally.",
                "",
                "Mean NN is the average heart period.",
                "Mean HR is the average of interval-derived heart rates.",
            ])

        elif metric == "SDNN derivation":
            nn = self.nn_values()
            row = self.nn_rows[max(0, min(self.selected_source_index, len(self.nn_rows)-1))]
            mean = float(np.nanmean(nn))
            dev = float(row["rr_ms"]) - mean
            formula = "\n".join([
                "SDNN = standard deviation of accepted NN intervals",
                "",
                "For each NN row:",
                "deviation_i = NN_i - mean(NN)",
                "square deviation_i",
                "combine deviations as standard deviation",
                "",
                f"Selected NN = {row['rr_ms']:.1f} ms",
                f"Mean NN = {mean:.1f} ms",
                f"Deviation = {dev:+.1f} ms",
                f"Deviation² = {dev*dev:.1f} ms²",
                "",
                f"SDNN = {m.get('sdnn', np.nan):.1f} ms",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "The mean line is the centre.",
                "Vertical deviation lines show spread.",
                "Large deviations increase SDNN.",
                "",
                "SDNN = overall spread of accepted NN intervals.",
            ])

        elif metric == "RMSSD derivation":
            pairs = self.successive_pairs_cache
            a, b, d, ad = pairs[max(0, min(self.selected_source_index, len(pairs)-1))]
            formula = "\n".join([
                "RMSSD uses successive NN pairs:",
                "",
                "ΔNN_i = NN_(i+1) - NN_i",
                "square each ΔNN_i",
                "mean the squared ΔNN values",
                "take square root",
                "",
                f"Selected pair:",
                f"NNn = {a['rr_ms']:.1f} ms",
                f"NNn+1 = {b['rr_ms']:.1f} ms",
                f"ΔNN = {d:+.1f} ms",
                f"ΔNN² = {d*d:.1f} ms²",
                "",
                f"RMSSD = {m.get('rmssd', np.nan):.1f} ms",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "Each point below is |ΔNN| from two neighboring NN rows.",
                "Large beat-to-beat jumps strongly affect RMSSD because ΔNN is squared.",
                "",
                "RMSSD = short-term beat-to-beat variability.",
            ])

        elif metric == "SDSD derivation":
            pairs = self.successive_pairs_cache
            a, b, d, ad = pairs[max(0, min(self.selected_source_index, len(pairs)-1))]
            formula = "\n".join([
                "SDSD uses the ΔNN series:",
                "",
                "ΔNN_i = NN_(i+1) - NN_i",
                "SDSD = standard deviation of ΔNN_i values",
                "",
                f"Selected pair:",
                f"NNn = {a['rr_ms']:.1f} ms",
                f"NNn+1 = {b['rr_ms']:.1f} ms",
                f"ΔNN = {d:+.1f} ms",
                "",
                f"SDSD = {m.get('sdsd', np.nan):.1f} ms",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "The lower plot is the signed ΔNN series.",
                "SDSD is the spread of those ΔNN values.",
                "",
                "It is related to beat-to-beat variability, like RMSSD, but uses SD of differences.",
            ])

        elif metric == "pNN50 derivation":
            pairs = self.successive_pairs_cache
            a, b, d, ad = pairs[max(0, min(self.selected_source_index, len(pairs)-1))]
            yes = ad > 50.0
            formula = "\n".join([
                "pNN50 counts large successive NN changes:",
                "",
                "|ΔNN_i| = |NN_(i+1) - NN_i|",
                "count yes if |ΔNN_i| > 50 ms",
                "pNN50 = yes count / total successive NN pairs × 100",
                "",
                f"Selected pair:",
                f"|ΔNN| = {ad:.1f} ms",
                f"> 50 ms? {'yes' if yes else 'no'}",
                "",
                f"pNN50 = {m.get('pnn50', np.nan):.1f} %",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "The red dashed line is 50 ms.",
                "Points above the line count toward pNN50.",
                "",
                "pNN50 = fraction of large beat-to-beat interval shifts.",
            ])

        elif metric == "Poincaré source":
            pairs = self.successive_pairs_cache
            a, b, d, ad = pairs[max(0, min(self.selected_source_index, len(pairs)-1))]
            formula = "\n".join([
                "Poincaré plot transforms successive NN pairs:",
                "",
                "x = NNn",
                "y = NNn+1",
                "",
                f"Selected point:",
                f"x = {a['rr_ms']:.1f} ms",
                f"y = {b['rr_ms']:.1f} ms",
                f"ΔNN = y - x = {d:+.1f} ms",
                "",
                f"SD1 = {m.get('sd1', np.nan):.1f} ms",
                f"SD2 = {m.get('sd2', np.nan):.1f} ms",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "Each point is two neighboring rows from the NN table.",
                "The diagonal line means NNn = NNn+1.",
                "",
                "Spread perpendicular to diagonal relates to short-term variability.",
                "Spread along diagonal relates to longer-term spread.",
            ])

        elif metric == "Instant HR trend":
            row = self.nn_rows[max(0, min(self.selected_source_index, len(self.nn_rows)-1))]
            formula = "\n".join([
                "Instant HR from each NN interval:",
                "",
                "HR_i = 60000 / NN_i",
                "",
                f"Selected NN = {row['rr_ms']:.1f} ms",
                f"HR = 60000 / {row['rr_ms']:.1f}",
                f"HR = {row['hr_bpm']:.1f} bpm",
                "",
                f"Mean HR = {m.get('mean_hr', np.nan):.1f} bpm",
            ])
            meaning = "\n".join([
                "Visual meaning",
                "",
                "Same NN intervals, converted to bpm.",
                "This is clinically familiar, but NN remains the HRV source.",
            ])

        self.formula_box.setPlainText(formula)
        self.meaning_box.setPlainText(meaning)
