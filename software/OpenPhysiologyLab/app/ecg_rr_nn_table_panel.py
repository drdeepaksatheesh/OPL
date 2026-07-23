
from pathlib import Path
import csv
import numpy as np

from PyQt5.QtCore import Qt, QEvent, QItemSelectionModel
from PyQt5.QtGui import QKeySequence, QColor
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QComboBox,
    QSplitter,
    QGroupBox,
    QPlainTextEdit,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
    QSlider,
    QTableWidgetSelectionRange,
    QSizePolicy,
    QFrame,
    QCheckBox,
    QShortcut,
)

import pyqtgraph as pg
pg.setConfigOptions(antialias=True)

NN_TEXT_COLOR = "#D8DEE9"
NN_PANEL_BG = "#0B0F14"
NN_PANEL_BORDER = "#243241"
NN_GOLD = "#E6C200"
NN_FILTERED_COLOR = "#E6C200"
NN_SELECTED_COLOR = "#66D9EF"
NN_REJECTED_COLOR = "#FF6B6B"
NN_SUBTLE_R_COLOR = "#52606D"

try:
    from .ecg_core.filters import safe_sampling_rate
    from .ecg_core.r_detection import detect_complete_ecg_complexes
except Exception:
    try:
        from app.ecg_core.filters import safe_sampling_rate
        from app.ecg_core.r_detection import detect_complete_ecg_complexes
    except Exception:
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
        [float(x) for x in header[: min(3, len(header))]]
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
                vals.append(float(str(x).strip()))
                ok_any = True
            except Exception:
                vals.append(np.nan)
        if ok_any:
            numeric_rows.append(vals)

    arr = np.asarray(numeric_rows, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 5:
        raise ValueError("CSV has too few numeric rows")

    # Canonical OPL time selection.
    #
    # Important bug fixed here:
    # Older RR/NN and Triplets loaders treated a column named "sample" as a
    # generic time column. Since sample increments by 1, _normalize_time_column()
    # interpreted it as milliseconds and produced fs ~1000 Hz for a 500 Hz file.
    #
    # Correct priority:
    # 1. sample_time_s / device seconds
    # 2. time_us / device microseconds
    # 3. time_ms / device milliseconds
    # 4. sample number converted using default_fs = 500 Hz
    # 5. row index / 500 Hz fallback
    lowered = [str(h).strip().lower() for h in header]
    time_idx = None
    time_s = None

    def finite_good(col):
        try:
            finite = np.isfinite(col)
            if int(np.sum(finite)) <= 5:
                return False
            dif = np.diff(col[finite])
            return len(dif) > 0 and float(np.nanmedian(dif)) > 0
        except Exception:
            return False

    for want in ["sample_time_s", "time_s", "device_time_s", "t_s"]:
        if want in lowered:
            idx = lowered.index(want)
            col = arr[:, idx].astype(float)
            if finite_good(col):
                time_idx = idx
                time_s = col - np.nanmin(col[np.isfinite(col)])
                break

    if time_s is None:
        for want in ["time_us", "device_time_us", "t_us"]:
            if want in lowered:
                idx = lowered.index(want)
                col = arr[:, idx].astype(float)
                if finite_good(col):
                    time_idx = idx
                    time_s = (col - np.nanmin(col[np.isfinite(col)])) / 1_000_000.0
                    break

    if time_s is None:
        for want in ["time_ms", "device_time_ms", "t_ms"]:
            if want in lowered:
                idx = lowered.index(want)
                col = arr[:, idx].astype(float)
                if finite_good(col):
                    time_idx = idx
                    time_s = (col - np.nanmin(col[np.isfinite(col)])) / 1000.0
                    break

    if time_s is None:
        for want in ["sample", "sample_index", "sample_number"]:
            if want in lowered:
                idx = lowered.index(want)
                col = arr[:, idx].astype(float)
                if finite_good(col):
                    time_idx = idx
                    first = np.nanmin(col[np.isfinite(col)])
                    time_s = (col - first) / 500.0
                    break

    if time_s is None:
        time_s = np.arange(arr.shape[0], dtype=float) / 500.0

    non_signal_names = {
        "segment_id",
        "segment",
        "sample",
        "sample_index",
        "sample_number",
        "time",
        "timestamp",
        "sample_time_s",
        "time_s",
        "device_time_s",
        "t_s",
        "time_us",
        "device_time_us",
        "t_us",
        "time_ms",
        "device_time_ms",
        "t_ms",
        "pc_time_s",
        "pc_time",
    }

    channels = {}
    for i, h in enumerate(header):
        if i == time_idx or str(h).strip().lower() in non_signal_names or _looks_like_time_name(h):
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


class ECGRRNNTablePanel(QWidget):
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
        self.complete_peaks = np.asarray([], dtype=int)  # morphology-complete beats
        self.rr_peaks = np.asarray([], dtype=int)        # HRV/RR timing source
        self.interval_rows = []
        self._updating_tables = False
        self.selected_interval_index = 0
        self.monitor_center_s = None
        self._syncing_scrub = False
        self.pre_r_s = 0.25
        self.post_r_s = 0.55
        self.default_nn_min_ms = 300.0
        self.default_nn_max_ms = 2000.0

        self._build_ui()
        self._install_shortcuts()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(6, 4, 6, 4)
        main.setSpacing(4)

        title = QLabel("RR / NN Table")
        title.setStyleSheet("color: #E6C200; font-weight: bold;")
        main.addWidget(title)

        subtitle = QLabel("Auditable interval layer: R-peak times → RR intervals → accepted NN intervals → HRV metrics.")
        subtitle.setStyleSheet("color: #D8DEE9;")
        main.addWidget(subtitle)

        group = QGroupBox("Source, screening window and NN decisions")
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

        controls.addWidget(QLabel("Window"))
        self.window_box = QComboBox()
        self.window_box.setMinimumWidth(105)
        self.window_box.addItems(["Selected RR", "5 s", "10 s", "30 s", "60 s", "Full"])
        self.window_box.setCurrentText("60 s")
        self.window_box.currentIndexChanged.connect(self.window_mode_changed)
        controls.addWidget(self.window_box)

        self.prev_window_btn = QPushButton("◀")
        self.prev_window_btn.setToolTip("Move monitor window backward")
        self.prev_window_btn.setFixedWidth(28)
        self.prev_window_btn.clicked.connect(lambda: self.step_monitor_window(-1))
        controls.addWidget(self.prev_window_btn)

        self.next_window_btn = QPushButton("▶")
        self.next_window_btn.setToolTip("Move monitor window forward")
        self.next_window_btn.setFixedWidth(28)
        self.next_window_btn.clicked.connect(lambda: self.step_monitor_window(+1))
        controls.addWidget(self.next_window_btn)

        controls.addWidget(QLabel("Columns"))
        self.column_mode_box = QComboBox()
        self.column_mode_box.setMinimumWidth(95)
        self.column_mode_box.addItems(["Essential", "Full audit"])
        self.column_mode_box.currentIndexChanged.connect(self.rebuild_tables)
        controls.addWidget(self.column_mode_box)

        self.accept_all_btn = QPushButton("Reset auto NN")
        self.accept_all_btn.clicked.connect(self.accept_all_basic)
        controls.addWidget(self.accept_all_btn)

        self.reject_selected_btn = QPushButton("Use / reject selected")
        self.reject_selected_btn.clicked.connect(self.toggle_selected_interval)
        controls.addWidget(self.reject_selected_btn)

        self.export_btn = QPushButton("Export table")
        self.export_btn.clicked.connect(self.export_table_dialog)
        controls.addWidget(self.export_btn)

        self.status_label = QLabel("Load raw.csv")
        self.status_label.setMinimumWidth(230)
        controls.addWidget(self.status_label, stretch=1)
        main.addWidget(group)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#05080D")
        self.plot.showGrid(x=True, y=True, alpha=0.20)
        try:
            self.plot.getPlotItem().layout.setContentsMargins(8, 8, 8, 6)
        except Exception:
            pass
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.getAxis("bottom").enableAutoSIPrefix(False)
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        try:
            self.plot.setDownsampling(auto=True, mode="peak")
            self.plot.setClipToView(True)
        except Exception:
            pass
        self.plot.setMinimumHeight(330)
        try:
            self.plot.setFocusPolicy(Qt.StrongFocus)
            self.plot.scene().sigMouseClicked.connect(self.plot_mouse_clicked)
            self.interval_region = pg.LinearRegionItem(values=[0.0, 1.0], orientation='vertical', brush=pg.mkBrush(102, 217, 239, 35), movable=False)
            self.interval_region.setZValue(-5)
            self.interval_region.sigRegionChangeFinished.connect(self.plot_region_changed_by_user)
            self._setting_plot_region = False
            self._original_vb_mouse_drag_event = self.plot.plotItem.vb.mouseDragEvent
            self.plot.plotItem.vb.mouseDragEvent = self.monitor_mouse_drag_event
        except Exception:
            pass
        left_layout.addWidget(self.plot, stretch=2)

        scrub_row = QHBoxLayout()
        scrub_row.setContentsMargins(2, 0, 2, 0)
        scrub_row.setSpacing(6)
        self.scrub_back_btn = QPushButton("◀◀")
        self.scrub_back_btn.setToolTip("Move back by one monitor window")
        self.scrub_back_btn.setFixedWidth(42)
        self.scrub_back_btn.clicked.connect(lambda: self.step_monitor_window(-1))
        scrub_row.addWidget(self.scrub_back_btn)
        self.monitor_scrub = QSlider(Qt.Horizontal)
        self.monitor_scrub.setMinimum(0)
        self.monitor_scrub.setMaximum(10000)
        self.monitor_scrub.setSingleStep(50)
        self.monitor_scrub.setPageStep(500)
        self.monitor_scrub.setToolTip("Scrub through recording time")
        self.monitor_scrub.valueChanged.connect(self.scrub_changed)
        scrub_row.addWidget(self.monitor_scrub, stretch=1)
        self.scrub_forward_btn = QPushButton("▶▶")
        self.scrub_forward_btn.setToolTip("Move forward by one monitor window")
        self.scrub_forward_btn.setFixedWidth(42)
        self.scrub_forward_btn.clicked.connect(lambda: self.step_monitor_window(+1))
        scrub_row.addWidget(self.scrub_forward_btn)
        self.scrub_label = QLabel("0.000 s")
        self.scrub_label.setMinimumWidth(90)
        scrub_row.addWidget(self.scrub_label)
        left_layout.addLayout(scrub_row)

        self.source_summary_label = QLabel("Load raw.csv to build the auditable RR / NN table.")
        self.source_summary_label.setStyleSheet("color: #D8DEE9; background-color: #0B0F14; border: 1px solid #243241; padding: 4px;")
        left_layout.addWidget(self.source_summary_label)

        table_splitter = QSplitter(Qt.Horizontal)

        self.interval_group = QGroupBox("RR / NN intervals")
        interval_layout = QVBoxLayout(self.interval_group)
        interval_layout.setContentsMargins(4, 4, 4, 4)
        self.interval_table = QTableWidget()
        self.interval_table.setAlternatingRowColors(False)
        self.interval_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.interval_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.interval_table.itemChanged.connect(self.interval_item_changed)
        self.interval_table.itemSelectionChanged.connect(self.interval_selection_changed)
        self.interval_table.verticalHeader().setVisible(False)
        self.apply_table_style(self.interval_table)
        interval_layout.addWidget(self.interval_table)
        table_splitter.addWidget(self.interval_group)

        self.diff_group = QGroupBox("Successive ΔNN / Poincaré source")
        diff_layout = QVBoxLayout(self.diff_group)
        diff_layout.setContentsMargins(4, 4, 4, 4)
        self.diff_table = QTableWidget()
        self.diff_table.setAlternatingRowColors(False)
        self.diff_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.diff_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.diff_table.itemSelectionChanged.connect(self.diff_selection_changed)
        self.diff_table.verticalHeader().setVisible(False)
        self.apply_table_style(self.diff_table)
        diff_layout.addWidget(self.diff_table)
        table_splitter.addWidget(self.diff_group)

        self.table_splitter = table_splitter
        table_splitter.setSizes([1040, 960])
        table_splitter.setCollapsible(0, False)
        table_splitter.setCollapsible(1, False)
        table_splitter.setStretchFactor(0, 1)
        table_splitter.setStretchFactor(1, 1)
        left_layout.addWidget(table_splitter, stretch=2)

        splitter.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(330)
        right.setMaximumWidth(500)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self.summary_group = QGroupBox("Screening Summary")
        sg = QVBoxLayout(self.summary_group)
        self.summary_box = QTextEdit()
        self.summary_box.setReadOnly(True)
        self.apply_text_style(self.summary_box)
        sg.addWidget(self.summary_box)

        self.interval_info_group = QGroupBox("Selected Interval")
        ig = QVBoxLayout(self.interval_info_group)
        self.interval_box = QTextEdit()
        self.interval_box.setReadOnly(True)
        self.apply_text_style(self.interval_box)
        ig.addWidget(self.interval_box)

        self.method_group = QGroupBox("Method")
        mg = QVBoxLayout(self.method_group)
        self.method_box = QTextEdit()
        self.method_box.setReadOnly(True)
        self.apply_text_style(self.method_box)
        mg.addWidget(self.method_box)

        right_layout.addWidget(self.summary_group, stretch=2)
        right_layout.addWidget(self.interval_info_group, stretch=1)
        right_layout.addWidget(self.method_group, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([980, 360])
        main.addWidget(splitter, stretch=1)

        self.setStyleSheet("QGroupBox { color: #E6C200; font-weight: bold; } QLabel { color: #D8DEE9; }")
        self.polish_interval_tables()
        self.polish_lower_tables()
        self.fix_group_title_padding()
        self.install_monitor_trackpad_scrub()
        self.update_method_box()
        self.update_summary()
        self.update_selected_interval_box()
        self.install_clear_selection_filters()

    def apply_table_style(self, table):
        table.setStyleSheet(
            "QTableWidget { color: #D8DEE9; background-color: #071018; gridline-color: #243241; selection-background-color: #174A7C; selection-color: #FFFFFF; }"
            "QTableWidget::item { padding: 3px; }"
            "QHeaderView::section { color: #E6C200; background-color: #111821; border: 1px solid #243241; padding: 4px; }"
            "QCheckBox { color: #D8DEE9; }"
        )

    def apply_text_style(self, box):
        box.setStyleSheet(f"QTextEdit {{ color: {NN_TEXT_COLOR}; background-color: {NN_PANEL_BG}; border: 1px solid {NN_PANEL_BORDER}; border-radius: 4px; }}")

    def _install_shortcuts(self):
        try:
            shortcuts = [
                (Qt.Key_Up, lambda: self.step_selected_row(-1)),
                (Qt.Key_Left, lambda: self.step_selected_row(-1)),
                (Qt.Key_Down, lambda: self.step_selected_row(+1)),
                (Qt.Key_Right, lambda: self.step_selected_row(+1)),
                (Qt.Key_Space, self.toggle_selected_interval),
            ]
            self._rrnn_shortcuts = []
            for key, callback in shortcuts:
                sc = QShortcut(QKeySequence(key), self)
                sc.setContext(Qt.WidgetWithChildrenShortcut)
                sc.activated.connect(callback)
                self._rrnn_shortcuts.append(sc)
        except Exception:
            pass

    def keyPressEvent(self, event):
        try:
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_Left):
                self.step_selected_row(-1)
                event.accept()
                return
            if key in (Qt.Key_Down, Qt.Key_Right):
                self.step_selected_row(+1)
                event.accept()
                return
            if key == Qt.Key_Space:
                self.toggle_selected_interval()
                event.accept()
                return
        except Exception:
            pass
        try:
            super().keyPressEvent(event)
        except Exception:
            pass

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
        self.rr_peaks = np.asarray(self.r_peaks, dtype=int)  # HRV/RR timing source
        self.selected_interval_index = 0
        self.monitor_center_s = None
        self.build_interval_rows()
        self.rebuild_tables()
        fs = safe_sampling_rate(self.time_s)
        self.status_label.setText(f"fs {fs:.1f} Hz | R {len(self.r_peaks)} | morphology complete {len(self.complete_peaks)} | RR {len(self.interval_rows)}")

    def build_interval_rows(self):
        self.interval_rows = []
        peaks = np.asarray(getattr(self, "rr_peaks", self.r_peaks), dtype=int)
        if self.time_s is None or len(peaks) < 2:
            return

        complete_set = set(int(p) for p in np.asarray(self.complete_peaks, dtype=int))
        r_times = self.time_s[peaks]
        for i in range(len(r_times) - 1):
            a_peak = int(peaks[i])
            b_peak = int(peaks[i + 1])
            a_time = float(r_times[i])
            b_time = float(r_times[i + 1])
            rr_ms = (b_time - a_time) * 1000.0
            hr_bpm = 60000.0 / rr_ms if rr_ms > 0 else float("nan")
            basic_accept = bool(np.isfinite(rr_ms) and self.default_nn_min_ms <= rr_ms <= self.default_nn_max_ms)

            edge_note = ""
            if a_peak not in complete_set or b_peak not in complete_set:
                edge_note = "; edge morphology incomplete"

            reason = ("basic accepted" if basic_accept else "outside 300-2000 ms") + edge_note

            self.interval_rows.append({
                "id": i + 1,
                "a_complex": i + 1,
                "b_complex": i + 2,
                "a_peak": a_peak,
                "b_peak": b_peak,
                "a_morphology_complete": a_peak in complete_set,
                "b_morphology_complete": b_peak in complete_set,
                "a_time_s": a_time,
                "b_time_s": b_time,
                "rr_ms": rr_ms,
                "hr_bpm": hr_bpm,
                "accepted": basic_accept,
                "basic_accept": basic_accept,
                "reason": reason,
                "manual": False,
            })

    def accepted_rows(self):
        return [row for row in self.interval_rows if row.get("accepted") and np.isfinite(row.get("rr_ms", np.nan))]

    def accepted_rr_ms(self):
        return np.asarray([row["rr_ms"] for row in self.accepted_rows()], dtype=float)

    def full_audit_columns_enabled(self):
        try:
            return self.column_mode_box.currentText() == "Full audit"
        except Exception:
            return False

    def window_seconds(self):
        label = self.window_box.currentText()
        if label == "Selected RR":
            return None
        if label == "Full":
            return "full"
        try:
            return float(label.replace("s", "").strip())
        except Exception:
            return 5.0

    def make_item(self, text, editable=False, checkable=False, checked=False):
        item = QTableWidgetItem(str(text))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if editable:
            flags |= Qt.ItemIsEditable
        if checkable:
            flags |= Qt.ItemIsUserCheckable
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        item.setFlags(flags)
        return item

    def interval_row_color(self, row):
        try:
            if row.get("manual") and row.get("accepted"):
                return QColor("#102A1D"), QColor("#D8F3DC")
            if row.get("manual") and not row.get("accepted"):
                return QColor("#2A1515"), QColor("#FFD6D6")
            if row.get("accepted"):
                return QColor("#071018"), QColor("#D8DEE9")
            return QColor("#241316"), QColor("#FFB4B4")
        except Exception:
            return QColor("#071018"), QColor("#D8DEE9")

    def apply_row_style(self, table, table_row, source_row):
        try:
            bg, fg = self.interval_row_color(source_row)
            for c in range(table.columnCount()):
                it = table.item(table_row, c)
                if it is not None:
                    it.setBackground(bg)
                    it.setForeground(fg)
        except Exception:
            pass

    def apply_monitor_selection_style(self):
        # Persistent cyan highlight for intervals selected from the ECG monitor.
        # Only changed rows are repainted, to keep arrow/click navigation responsive.
        old_updating = getattr(self, '_updating_tables', False)
        old_block = False
        try:
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
            except Exception:
                old_block = False

            selected = set(getattr(self, 'monitor_selected_indices', set()))
            previous = set(getattr(self, '_last_monitor_selected_indices', set()))
            rows_to_touch = selected | previous

            for r in rows_to_touch:
                r = int(r)
                if 0 <= r < self.interval_table.rowCount() and r < len(self.interval_rows):
                    row = self.interval_rows[r]
                    try:
                        self.apply_row_style(self.interval_table, r, row)
                    except TypeError:
                        self.apply_row_style(r, row)

            if selected:
                # Same family as the transparent cyan plot selection band, but solid enough for a table.
                bg = QColor('#123D4A')
                fg = QColor('#E8FAFF')
                for r in selected:
                    r = int(r)
                    if 0 <= r < self.interval_table.rowCount():
                        for c in range(self.interval_table.columnCount()):
                            it = self.interval_table.item(r, c)
                            if it is not None:
                                it.setBackground(bg)
                                it.setForeground(fg)

            self._last_monitor_selected_indices = set(selected)
        except Exception:
            pass
        finally:
            try:
                self.interval_table.blockSignals(old_block)
            except Exception:
                pass
            self._updating_tables = old_updating

    def apply_difference_row_style(self, table_row, abs_delta_ms):
        try:
            if abs_delta_ms > 50.0:
                bg, fg = QColor("#2A2110"), QColor("#FFE8A3")
            else:
                bg, fg = QColor("#071018"), QColor("#D8DEE9")
            for c in range(self.diff_table.columnCount()):
                it = self.diff_table.item(table_row, c)
                if it is not None:
                    it.setBackground(bg)
                    it.setForeground(fg)
        except Exception:
            pass

    def rebuild_tables(self):
        self.populate_interval_table()
        self.populate_difference_table()
        self.update_summary()
        self.update_source_summary_label()
        self.update_selected_interval_box()
        self.update_plot_for_selected()

    def fix_group_title_padding(self):
        try:
            style = (
                'QGroupBox {'
                ' margin-top: 18px;'
                ' padding-top: 10px;'
                ' border: 1px solid #243746;'
                ' border-radius: 4px;'
                '}'
                'QGroupBox::title {'
                ' subcontrol-origin: margin;'
                ' subcontrol-position: top left;'
                ' left: 8px;'
                ' top: 2px;'
                ' padding: 0 4px;'
                ' color: #E6C200;'
                ' font-weight: bold;'
                '}'
            )
            for g in self.findChildren(QGroupBox):
                try:
                    title = g.title()
                    if title in ('RR / NN intervals', 'Successive ΔNN / Poincaré source', 'Screening Summary', 'Selected Interval', 'Method', 'Source, screening window and NN decisions'):
                        g.setStyleSheet(style)
                except Exception:
                    pass
        except Exception:
            pass

    def polish_lower_tables(self):
        try:
            for t in [getattr(self, 'interval_table', None), getattr(self, 'diff_table', None)]:
                if t is None:
                    continue
                try:
                    t.verticalHeader().setVisible(False)
                    t.verticalHeader().setDefaultSectionSize(26)
                    t.setShowGrid(True)
                    t.setWordWrap(False)
                    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                    t.setAlternatingRowColors(False)
                except Exception:
                    pass
                t.setStyleSheet(
                    'QTableWidget {'
                    ' background-color: #071018;'
                    ' color: #D8DEE9;'
                    ' gridline-color: #263746;'
                    ' selection-background-color: #123D4A;'
                    ' selection-color: #E8FAFF;'
                    ' border: 1px solid #243746;'
                    '}'
                    'QTableWidget::item { padding: 3px; }'
                    'QHeaderView::section {'
                    ' background-color: #101A24;'
                    ' color: #E6C200;'
                    ' border: 1px solid #34495A;'
                    ' padding: 4px;'
                    ' font-weight: bold;'
                    '}'
                )
        except Exception:
            pass

    def populate_interval_table(self):
        self._updating_tables = True
        t = self.interval_table
        old_block = False
        try:
            old_block = t.blockSignals(True)

            full = self.full_audit_columns_enabled()
            if full:
                headers = ['Use', '#', 'A', 'B', 'A s', 'B s', 'RR', 'HR', 'Reason', 'Man']
            else:
                headers = ['Use', '#', 'A->B', 'RR', 'HR', 'Reason']

            t.clear()
            t.setColumnCount(len(headers))
            t.setHorizontalHeaderLabels(headers)
            t.setRowCount(len(self.interval_rows))

            for r, row in enumerate(self.interval_rows):
                t.setItem(r, 0, self.make_item('', checkable=True, checked=row['accepted']))
                t.setItem(r, 1, self.make_item(row['id']))

                if full:
                    t.setItem(r, 2, self.make_item(row['a_complex']))
                    t.setItem(r, 3, self.make_item(row['b_complex']))
                    t.setItem(r, 4, self.make_item(f"{row['a_time_s']:.3f}"))
                    t.setItem(r, 5, self.make_item(f"{row['b_time_s']:.3f}"))
                    t.setItem(r, 6, self.make_item(f"{row['rr_ms']:.1f}"))
                    t.setItem(r, 7, self.make_item(f"{row['hr_bpm']:.1f}"))
                    t.setItem(r, 8, self.make_item(row['reason'], editable=True))
                    t.setItem(r, 9, self.make_item('yes' if row['manual'] else 'no'))
                else:
                    t.setItem(r, 2, self.make_item(f"{row['a_complex']}->{row['b_complex']}"))
                    t.setItem(r, 3, self.make_item(f"{row['rr_ms']:.1f}"))
                    t.setItem(r, 4, self.make_item(f"{row['hr_bpm']:.1f}"))
                    t.setItem(r, 5, self.make_item(row['reason'], editable=True))

                try:
                    self.apply_row_style(t, r, row)
                except TypeError:
                    self.apply_row_style(r, row)

            self.polish_lower_tables()
            self.tune_interval_columns()
            if self.interval_rows:
                focus = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
                t.setSelectionMode(QAbstractItemView.SingleSelection)
                t.setCurrentCell(focus, 0)
                t.selectRow(focus)

        finally:
            try:
                t.blockSignals(old_block)
            except Exception:
                pass
            self._updating_tables = False

        try:
            self.apply_monitor_selection_style()
        except Exception:
            pass

    def successive_nn_pairs(self):
        """
        Return only truly adjacent accepted NN interval pairs.

        If interval 10 is accepted, interval 11 is rejected, and interval 12 is accepted,
        this method does NOT bridge 10 -> 12. The sequence is broken at 11.
        """
        pairs = []
        try:
            rows = self.interval_rows
            for i in range(len(rows) - 1):
                a = rows[i]
                b = rows[i + 1]
                if not (a.get("accepted") and b.get("accepted")):
                    continue
                if int(b.get("id", -999)) != int(a.get("id", -999)) + 1:
                    continue
                if not (np.isfinite(a.get("rr_ms", np.nan)) and np.isfinite(b.get("rr_ms", np.nan))):
                    continue
                d = float(b["rr_ms"] - a["rr_ms"])
                pairs.append((a, b, d, abs(d)))
        except Exception:
            pass
        return pairs

    def accepted_successive_differences_ms(self):
        try:
            return np.asarray([p[2] for p in self.successive_nn_pairs()], dtype=float)
        except Exception:
            return np.asarray([], dtype=float)

    def interval_consequence_lines(self, row):
        try:
            interval_id = int(row.get("id", 0))
            accepted = bool(row.get("accepted"))
            prev_exists = interval_id > 1
            next_exists = interval_id < len(self.interval_rows)

            if accepted:
                lines = [
                    "Consequence",
                    "- Included in mean NN, mean HR and SDNN.",
                    "- Can contribute to RMSSD/pNN50 only if the neighbouring interval is also accepted.",
                ]
                if prev_exists:
                    prev_row = self.interval_rows[interval_id - 2]
                    lines.append(f"- Previous link: {'active' if prev_row.get('accepted') else 'broken'} for interval {interval_id - 1}->{interval_id}.")
                if next_exists:
                    next_row = self.interval_rows[interval_id]
                    lines.append(f"- Next link: {'active' if next_row.get('accepted') else 'broken'} for interval {interval_id}->{interval_id + 1}.")
                return lines

            lines = [
                "Consequence",
                "- Excluded from mean NN, mean HR and SDNN.",
                "- Breaks successive-difference calculations at this point.",
            ]
            if prev_exists:
                lines.append(f"- No RMSSD/pNN50/Poincare link from interval {interval_id - 1}->{interval_id}.")
            if next_exists:
                lines.append(f"- No RMSSD/pNN50/Poincare link from interval {interval_id}->{interval_id + 1}.")
            return lines
        except Exception:
            return ["Consequence", "- Could not calculate consequence text."]

    def populate_difference_table(self):
        self._updating_tables = True
        pairs = self.successive_nn_pairs()
        headers = ['#', 'RRn', 'RRn+1', 'NNn', 'NNn+1', 'Δ', '|Δ|', '>50', 'Δ²']
        t = self.diff_table
        old_block = False
        try:
            old_block = t.blockSignals(True)
            t.clear()
            t.setColumnCount(len(headers))
            t.setHorizontalHeaderLabels(headers)
            t.setRowCount(len(pairs))

            for i, (a, b, d, ad) in enumerate(pairs):
                t.setItem(i, 0, self.make_item(i + 1))
                t.setItem(i, 1, self.make_item(a['id']))
                t.setItem(i, 2, self.make_item(b['id']))
                t.setItem(i, 3, self.make_item(f"{a['rr_ms']:.1f}"))
                t.setItem(i, 4, self.make_item(f"{b['rr_ms']:.1f}"))
                t.setItem(i, 5, self.make_item(f"{d:+.1f}"))
                t.setItem(i, 6, self.make_item(f"{ad:.1f}"))
                t.setItem(i, 7, self.make_item('yes' if ad > 50.0 else 'no'))
                t.setItem(i, 8, self.make_item(f"{d*d:.1f}"))
                self.apply_difference_row_style(i, ad)
        finally:
            try:
                t.blockSignals(old_block)
            except Exception:
                pass
            self._updating_tables = False

        self.polish_lower_tables()
        self.tune_difference_columns()

    def set_weighted_table_columns(self, table, weights, min_widths=None):
        try:
            if table is None or table.columnCount() <= 0:
                return
            h = table.horizontalHeader()
            h.setStretchLastSection(False)
            for c in range(table.columnCount()):
                h.setSectionResizeMode(c, QHeaderView.Fixed)
            n = min(table.columnCount(), len(weights))
            weights = [float(w) for w in weights[:n]]
            if min_widths is None:
                min_widths = [34] * n
            min_widths = [int(w) for w in min_widths[:n]]
            available = max(120, int(table.viewport().width()) - 6)
            total_weight = sum(weights) if sum(weights) > 0 else float(n)
            widths = [max(min_widths[i], int(available * weights[i] / total_weight)) for i in range(n)]
            total = sum(widths)
            if total > available and total > 0:
                scale = available / float(total)
                widths = [max(30, int(w * scale)) for w in widths]
            diff = available - sum(widths)
            if n and diff:
                target = max(range(n), key=lambda i: weights[i])
                widths[target] = max(30, widths[target] + diff)
            for c, w in enumerate(widths):
                table.setColumnWidth(c, int(w))
        except Exception:
            pass

    def polish_interval_tables(self):
        # Make the two lower tables visually important without wasting space.
        try:
            tables = [getattr(self, 'interval_table', None), getattr(self, 'diff_table', None)]
            for t in tables:
                if t is None:
                    continue
                try:
                    t.verticalHeader().setVisible(False)
                    t.verticalHeader().setDefaultSectionSize(24)
                    t.setAlternatingRowColors(False)
                    t.setShowGrid(True)
                    t.setWordWrap(False)
                    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                except Exception:
                    pass
                t.setStyleSheet(
                    'QTableWidget {'
                    ' color: #D8DEE9;'
                    ' background-color: #071018;'
                    ' alternate-background-color: #09121A;'
                    ' gridline-color: #263746;'
                    ' selection-background-color: #1E5A91;'
                    ' selection-color: #FFFFFF;'
                    ' border: 1px solid #2D4050;'
                    '}'
                    'QTableWidget::item { padding: 4px; border-bottom: 1px solid #13202A; }'
                    'QHeaderView::section {'
                    ' color: #E6C200;'
                    ' background-color: #101A24;'
                    ' border: 1px solid #34495A;'
                    ' padding: 5px;'
                    ' font-weight: bold;'
                    '}'
                    'QTableCornerButton::section { background-color: #101A24; border: 1px solid #34495A; }'
                )
            try:
                self.interval_group.setStyleSheet(
                    'QGroupBox { color: #E6C200; font-weight: bold; border: 1px solid #304354; margin-top: 8px; }'
                    'QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }'
                )
                self.diff_group.setStyleSheet(
                    'QGroupBox { color: #E6C200; font-weight: bold; border: 1px solid #304354; margin-top: 8px; }'
                    'QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }'
                )
            except Exception:
                pass
        except Exception:
            pass

    def tune_interval_columns(self):
        try:
            t = self.interval_table
            h = t.horizontalHeader()
            h.setStretchLastSection(False)
            for c in range(t.columnCount()):
                h.setSectionResizeMode(c, QHeaderView.Stretch)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            t.setWordWrap(False)
            for r in range(t.rowCount()):
                t.setRowHeight(r, 26)
        except Exception:
            pass

    def tune_difference_columns(self):
        try:
            t = self.diff_table
            h = t.horizontalHeader()
            h.setStretchLastSection(False)
            for c in range(t.columnCount()):
                h.setSectionResizeMode(c, QHeaderView.Stretch)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            t.setWordWrap(False)
            for r in range(t.rowCount()):
                t.setRowHeight(r, 26)
        except Exception:
            pass

    def reason_column_index(self):
        return 8 if self.full_audit_columns_enabled() else 5

    def interval_item_changed(self, item):
        if self._updating_tables or getattr(self, '_handling_interval_item_changed', False):
            return
        self._handling_interval_item_changed = True
        try:
            row_idx = item.row()
            col = item.column()
            if row_idx < 0 or row_idx >= len(self.interval_rows):
                return

            row = self.interval_rows[row_idx]
            if col == 0:
                row['accepted'] = item.checkState() == Qt.Checked
                row['manual'] = True
                row['reason'] = 'manual accepted' if row['accepted'] else 'manual rejected'
                # Checkbox change is intentionally single-row only.
            elif col == self.reason_column_index():
                row['reason'] = item.text()
                row['manual'] = True
            else:
                return

            self.selected_interval_index = row_idx
            if not getattr(self, 'monitor_selected_indices', set()):
                self.monitor_selected_indices = set([row_idx])
            self.rebuild_tables()
        finally:
            self._handling_interval_item_changed = False

    def interval_selection_changed(self):
        if self._updating_tables or getattr(self, '_handling_interval_selection_changed', False):
            return
        self._handling_interval_selection_changed = True
        try:
            row_idx = self.interval_table.currentRow()
            if row_idx < 0 or row_idx >= len(self.interval_rows):
                rows = self.interval_table.selectionModel().selectedRows() if self.interval_table.selectionModel() else []
                if rows:
                    row_idx = rows[0].row()
            if 0 <= row_idx < len(self.interval_rows):
                self.select_interval_index(row_idx, update_plot=True)
        finally:
            self._handling_interval_selection_changed = False

    def diff_selection_changed(self):
        if self._updating_tables:
            return
        rows = self.diff_table.selectionModel().selectedRows() if self.diff_table.selectionModel() else []
        if not rows:
            return
        idx = rows[0].row()
        acc = self.accepted_rows()
        if 0 <= idx < len(acc) - 1:
            first_interval_id = int(acc[idx]["id"])
            self.selected_interval_index = max(0, min(first_interval_id - 1, len(self.interval_rows) - 1))
            self.interval_table.selectRow(self.selected_interval_index)
            self.update_selected_interval_box()
            self.update_plot_for_selected()

    def step_selected_row(self, delta):
        try:
            if not self.interval_rows:
                return
            i = max(0, min(self.selected_interval_index + int(delta), len(self.interval_rows) - 1))
            self.select_interval_index(i, update_plot=True)
        except Exception:
            pass

    def toggle_selected_interval(self):
        indices = self.selected_interval_row_indices()
        if not indices:
            return
        all_accepted = all(bool(self.interval_rows[i].get('accepted')) for i in indices)
        new_state = not all_accepted
        for r in indices:
            row = self.interval_rows[r]
            row['accepted'] = new_state
            row['manual'] = True
            row['reason'] = 'manual accepted' if new_state else 'manual rejected'
        self.selected_interval_index = indices[0]
        self.rebuild_tables()
        self.select_interval_rows(indices, focus_first=True, update_plot=True)

    def accept_all_basic(self):
        for row in self.interval_rows:
            row["accepted"] = row["basic_accept"]
            row["manual"] = False
            row["reason"] = "basic accepted" if row["basic_accept"] else "outside 300-2000 ms"
        self.rebuild_tables()

    def update_source_summary_label(self):
        try:
            total = len(self.interval_rows)
            accepted = len([r for r in self.interval_rows if r.get("accepted")])
            rejected = total - accepted
            name = self.raw_path.name if self.raw_path else "raw.csv"
            self.source_summary_label.setText(
                f"Source: {name} | Channel: {self.current_channel or '--'} | "
                f"R peaks: {len(self.r_peaks)} | Morphology complete: {len(self.complete_peaks)} | "
                f"RR {total} | NN {accepted} | Rejected {rejected} | "
                f"Window {self.window_box.currentText()} | {'Full audit' if self.full_audit_columns_enabled() else 'Essential'}"
            )
        except Exception:
            pass

    def current_group_indices(self):
        try:
            group = sorted({int(i) for i in getattr(self, 'monitor_selected_indices', set()) if 0 <= int(i) < len(self.interval_rows)})
            if group:
                return group
        except Exception:
            pass
        if self.interval_rows:
            return [max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))]
        return []

    def current_group_rows(self):
        try:
            return [self.interval_rows[i] for i in self.current_group_indices()]
        except Exception:
            return []

    def current_group_time_bounds(self):
        rows = self.current_group_rows()
        if not rows:
            return None, None
        try:
            return min(float(r['a_time_s']) for r in rows), max(float(r['b_time_s']) for r in rows)
        except Exception:
            return None, None

    def selected_interval_row_indices(self):
        return self.current_group_indices()

    def apply_monitor_selection_style(self):
        # Paint persistent group highlight without triggering itemChanged recursion.
        old_updating = getattr(self, '_updating_tables', False)
        old_block = False
        try:
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
            except Exception:
                old_block = False
            selected = set(getattr(self, 'monitor_selected_indices', set()))
            for r, row in enumerate(self.interval_rows):
                if r < self.interval_table.rowCount():
                    try:
                        self.apply_row_style(self.interval_table, r, row)
                    except TypeError:
                        self.apply_row_style(r, row)
            if selected:
                bg = QColor('#12324A')
                fg = QColor('#FFFFFF')
                for r in selected:
                    r = int(r)
                    if 0 <= r < self.interval_table.rowCount():
                        for c in range(self.interval_table.columnCount()):
                            it = self.interval_table.item(r, c)
                            if it is not None:
                                it.setBackground(bg)
                                it.setForeground(fg)
        except Exception:
            pass
        finally:
            try:
                self.interval_table.blockSignals(old_block)
            except Exception:
                pass
            self._updating_tables = old_updating

    def select_interval_rows(self, indices, focus_first=True, update_plot=True):
        try:
            valid = sorted({int(i) for i in indices if 0 <= int(i) < len(self.interval_rows)})
            if not valid:
                return

            previous_group = set(getattr(self, 'monitor_selected_indices', set()))
            self.monitor_selected_indices = set(valid)
            focus = valid[0] if focus_first else valid[-1]
            self.selected_interval_index = focus

            # Decide before changing plot whether the target is already visible.
            rows = [self.interval_rows[i] for i in valid]
            sel_start = min(float(r['a_time_s']) for r in rows)
            sel_end = max(float(r['b_time_s']) for r in rows)
            already_visible = self.time_range_visible_in_monitor(sel_start, sel_end)

            old_updating = getattr(self, '_updating_tables', False)
            old_block = False
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
                self.interval_table.setSelectionMode(QAbstractItemView.SingleSelection)
                self.interval_table.clearSelection()
                self.interval_table.setCurrentCell(int(focus), 0)
                self.interval_table.selectRow(int(focus))
                item = self.interval_table.item(int(focus), 0)
                if item is not None:
                    self.interval_table.scrollToItem(item, QAbstractItemView.EnsureVisible)
            finally:
                try:
                    self.interval_table.blockSignals(old_block)
                except Exception:
                    pass
                self._updating_tables = old_updating

            self.apply_monitor_selection_style()
            self.update_selected_interval_box()
            self.update_summary()

            if update_plot:
                if not already_visible:
                    try:
                        self.monitor_center_s = self.selected_or_group_center_s()
                    except Exception:
                        pass
                self.update_plot_for_selected()
        except Exception as exc:
            try:
                self.status_label.setText(f'Selection failed: {exc}')
            except Exception:
                pass

    def select_interval_index(self, index, update_plot=True):
        try:
            if index is None or not self.interval_rows:
                return
            i = max(0, min(int(index), len(self.interval_rows) - 1))
            self.select_interval_rows([i], focus_first=True, update_plot=update_plot)
        except Exception:
            pass

    def current_group_rows(self):
        try:
            return [self.interval_rows[i] for i in self.current_group_indices()]
        except Exception:
            return []

    def current_group_time_bounds(self):
        rows = self.current_group_rows()
        if not rows:
            return None, None
        try:
            return min(float(r['a_time_s']) for r in rows), max(float(r['b_time_s']) for r in rows)
        except Exception:
            return None, None

    def install_clear_selection_filters(self):
        # Clicking non-editing/non-plot information areas should clear a monitor group.
        try:
            for w in [
                getattr(self, 'source_summary_label', None),
                getattr(self, 'summary_box', None),
                getattr(self, 'interval_box', None),
                getattr(self, 'method_box', None),
            ]:
                if w is not None:
                    w.installEventFilter(self)
        except Exception:
            pass

    def clear_monitor_selection(self, update_plot=True):
        # Clear the persistent blue group while keeping the current focused interval.
        try:
            self.monitor_selected_indices = set()
            self.apply_monitor_selection_style()
            self.update_selected_interval_box()
            self.update_summary()
            self.status_label.setText('Cleared monitor group selection')
            if update_plot:
                self.update_plot_for_selected()
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.MouseButtonPress:
                # These are non-specific information areas, not the ECG monitor/table.
                if obj in [
                    getattr(self, 'source_summary_label', None),
                    getattr(self, 'summary_box', None),
                    getattr(self, 'interval_box', None),
                    getattr(self, 'method_box', None),
                ]:
                    if len(getattr(self, 'monitor_selected_indices', set())) > 1:
                        self.clear_monitor_selection(update_plot=True)
        except Exception:
            pass
        try:
            return super().eventFilter(obj, event)
        except Exception:
            return False

    def mousePressEvent(self, event):
        # Clicks on bare panel background clear the group selection.
        try:
            if len(getattr(self, 'monitor_selected_indices', set())) > 1:
                self.clear_monitor_selection(update_plot=True)
        except Exception:
            pass
        try:
            return super().mousePressEvent(event)
        except Exception:
            pass

    def current_group_rows(self):
        try:
            return [self.interval_rows[i] for i in self.current_group_indices()]
        except Exception:
            return []

    def current_group_time_bounds(self):
        rows = self.current_group_rows()
        if not rows:
            return None, None
        try:
            start = min(float(r['a_time_s']) for r in rows)
            end = max(float(r['b_time_s']) for r in rows)
            return start, end
        except Exception:
            return None, None

    def current_group_interval_label(self):
        idx = self.current_group_indices()
        if not idx:
            return 'no interval selected'
        if len(idx) == 1:
            row = self.interval_rows[idx[0]]
            return f"interval {row['id']} ({row['a_complex']}->{row['b_complex']})"
        first = self.interval_rows[idx[0]]
        last = self.interval_rows[idx[-1]]
        return f"{len(idx)} intervals: #{first['id']}-#{last['id']} ({first['a_complex']}->{last['b_complex']})"

    def update_summary(self):
        self.update_source_summary_label()
        total = len(self.interval_rows)
        accepted_total = len([r for r in self.interval_rows if r.get('accepted')])
        rejected_total = total - accepted_total
        group = self.current_group_indices()
        rows = [self.interval_rows[i] for i in group] if group else []
        lines = [
            'Screening Summary',
            '',
            'This tab screens RR intervals from consecutive detected R peaks and decides which intervals become NN.',
            'Full HRV statistics will be built in the Analysis/HRV tab.',
            '',
            'Recording source',
            f'R peaks: {len(self.r_peaks)} | morphology complete: {len(self.complete_peaks)}',
            f'RR intervals: {total} | NN accepted: {accepted_total} | rejected: {rejected_total}',
        ]
        if rows:
            start = min(float(r['a_time_s']) for r in rows)
            end = max(float(r['b_time_s']) for r in rows)
            nn_used = len([r for r in rows if r.get('accepted')])
            rr_vals = np.asarray([r.get('rr_ms', np.nan) for r in rows], dtype=float)
            rr_vals = rr_vals[np.isfinite(rr_vals)]
            lines += ['', 'Current selection']
            lines += [f'{len(rows)} interval(s) | {start:.3f}-{end:.3f} s | Use NN {nn_used}/{len(rows)}']
            if len(rr_vals):
                lines += [f'RR range {float(np.nanmin(rr_vals)):.1f}-{float(np.nanmax(rr_vals)):.1f} ms']
        self.summary_box.setPlainText(chr(10).join(lines))

    def update_selected_interval_box(self):
        if not self.interval_rows:
            self.interval_box.setPlainText('No interval selected.')
            return
        group = self.current_group_indices()
        rows = [self.interval_rows[i] for i in group] if group else []
        if len(rows) > 1:
            start = min(float(r['a_time_s']) for r in rows)
            end = max(float(r['b_time_s']) for r in rows)
            nn_used = len([r for r in rows if r.get('accepted')])
            lines = [
                'Selected group',
                '',
                f'{len(rows)} RR intervals',
                f'Interval range: #{rows[0]["id"]}-#{rows[-1]["id"]}',
                f'Complex range: {rows[0]["a_complex"]}->{rows[-1]["b_complex"]}',
                f'Recording time: {start:.3f}-{end:.3f} s',
                f'Use as NN: {nn_used}/{len(rows)} checked',
                '',
                'Click one checkbox = one row only.',
                'Space/button = whole selected group.',
            ]
        else:
            i = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
            row = self.interval_rows[i]
            lines = [
                'Selected Interval',
                '',
                f'Interval: {row["id"]}',
                f'Source complexes: {row["a_complex"]} -> {row["b_complex"]}',
                f'R_A time: {row["a_time_s"]:.3f} s',
                f'R_B time: {row["b_time_s"]:.3f} s',
                f'RR / NN: {row["rr_ms"]:.1f} ms',
                f'Instant HR: {row["hr_bpm"]:.1f} bpm',
                f'Used as NN: {"yes" if row["accepted"] else "no"}',
                f'Reason: {row["reason"]}',
            ]
        self.interval_box.setPlainText(chr(10).join(lines))

    def decimate_for_screening_plot(self, x, y, max_points=9000):
        # Return a lighter trace for fast screening-window redraws.
        try:
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            n = len(x)
            if n <= int(max_points):
                return x, y
            step = int(np.ceil(n / float(max_points)))
            return x[::step], y[::step]
        except Exception:
            return x, y

    def should_draw_context_r_markers(self, start, end):
        # Context R lines are useful in short windows but clutter and slow long windows.
        try:
            return float(end - start) <= 15.0
        except Exception:
            return False

    def decimate_for_screening_plot(self, x, y, max_points=9000):
        # Return a lighter trace for fast screening-window redraws.
        try:
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            n = len(x)
            if n <= int(max_points):
                return x, y
            step = int(np.ceil(n / float(max_points)))
            return x[::step], y[::step]
        except Exception:
            return x, y

    def should_draw_context_r_markers(self, start, end):
        # Context R lines are useful in short windows but clutter and slow long windows.
        try:
            return float(end - start) <= 15.0
        except Exception:
            return False

    def selected_row_a_time(self):
        try:
            if not self.interval_rows:
                return 0.0
            i = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
            return float(self.interval_rows[i].get('a_time_s', 0.0))
        except Exception:
            return 0.0

    def plot_x_to_absolute_time(self, x_value):
        # The monitor x-axis is time from selected A R peak.
        return self.selected_row_a_time() + float(x_value)

    def interval_index_for_absolute_time(self, abs_time):
        if not self.interval_rows:
            return None
        try:
            t = float(abs_time)
            for i, row in enumerate(self.interval_rows):
                if float(row['a_time_s']) <= t <= float(row['b_time_s']):
                    return i
            mids = np.asarray([(float(r['a_time_s']) + float(r['b_time_s'])) / 2.0 for r in self.interval_rows], dtype=float)
            if len(mids):
                return int(np.nanargmin(np.abs(mids - t)))
        except Exception:
            return None
        return None

    def select_interval_index(self, index, update_plot=True):
        try:
            if index is None or not self.interval_rows:
                return
            i = max(0, min(int(index), len(self.interval_rows) - 1))
            self.select_interval_rows([i], focus_first=True, update_plot=update_plot)
        except Exception:
            pass

    def install_monitor_trackpad_scrub(self):
        try:
            vb = self.plot.plotItem.vb
            if not hasattr(self, '_original_monitor_wheel_event'):
                self._original_monitor_wheel_event = vb.wheelEvent
            vb.wheelEvent = self.monitor_wheel_scrub
        except Exception:
            pass

    def monitor_window_seconds(self):
        try:
            txt = self.window_box.currentText().strip().lower()
            if 'full' in txt or 'all' in txt:
                if len(self.time_s):
                    return max(0.001, float(self.time_s[-1]) - float(self.time_s[0]))
            cleaned = txt.replace('seconds', ' ').replace('second', ' ').replace('sec', ' ').replace('s', ' ')
            for part in cleaned.split():
                try:
                    return max(0.001, float(part))
                except Exception:
                    pass
        except Exception:
            pass
        return 60.0

    def move_monitor_window_by(self, delta_s):
        try:
            if not hasattr(self, 'time_s') or self.time_s is None or len(self.time_s) < 2:
                return
            t0 = float(self.time_s[0])
            t1 = float(self.time_s[-1])
            duration = max(0.001, t1 - t0)
            win = min(self.monitor_window_seconds(), duration)
            half = win / 2.0
            center = float(getattr(self, 'monitor_center_s', (t0 + t1) / 2.0)) + float(delta_s)
            if duration <= win:
                center = (t0 + t1) / 2.0
            else:
                center = max(t0 + half, min(t1 - half, center))
            self.monitor_center_s = center
            self.update_plot_for_selected()
        except Exception as exc:
            try:
                self.status_label.setText(f'Scrub failed: {exc}')
            except Exception:
                pass

    def monitor_wheel_scrub(self, event, *args, **kwargs):
        try:
            if not hasattr(self, 'time_s') or self.time_s is None or len(self.time_s) < 2:
                original = getattr(self, '_original_monitor_wheel_event', None)
                if original is not None:
                    return original(event)
                return

            dx = 0.0
            dy = 0.0
            used_pixels = False

            try:
                pd = event.pixelDelta()
                if not pd.isNull():
                    dx = float(pd.x())
                    dy = float(pd.y())
                    used_pixels = True
            except Exception:
                pass

            if not used_pixels:
                try:
                    ad = event.angleDelta()
                    dx = float(ad.x())
                    dy = float(ad.y())
                except Exception:
                    try:
                        dy = float(event.delta())
                    except Exception:
                        dy = 0.0

            dominant = dx if abs(dx) > abs(dy) else dy
            if abs(dominant) < 1e-9:
                return

            win = self.monitor_window_seconds()
            if used_pixels:
                delta_s = -dominant * win / 900.0
            else:
                delta_s = -(dominant / 120.0) * win * 0.12

            if abs(delta_s) < 0.002:
                try:
                    event.accept()
                except Exception:
                    pass
                return

            self.move_monitor_window_by(delta_s)
            try:
                event.accept()
            except Exception:
                pass
        except Exception:
            try:
                event.accept()
            except Exception:
                pass

    def plot_mouse_clicked(self, event):
        try:
            if event.button() != Qt.LeftButton:
                return
            vb = self.plot.plotItem.vb
            pos = vb.mapSceneToView(event.scenePos())
            idx = self.interval_index_for_absolute_time(float(pos.x()))
            if idx is not None:
                self.select_interval_index(idx, update_plot=True)
                event.accept()
        except Exception:
            pass

    def monitor_mouse_drag_event(self, event):
        try:
            if event.button() != Qt.LeftButton:
                original = getattr(self, '_original_vb_mouse_drag_event', None)
                if original is not None:
                    return original(event)
                return

            vb = self.plot.plotItem.vb
            p0 = vb.mapToView(event.buttonDownPos())
            p1 = vb.mapToView(event.pos())
            lo = min(float(p0.x()), float(p1.x()))
            hi = max(float(p0.x()), float(p1.x()))
            if abs(hi - lo) < 1e-6:
                event.accept()
                return

            # During live drag, update the cyan region only occasionally.
            # This avoids the heavy feeling from redrawing the region on every mouse event.
            import time
            now = time.perf_counter()
            last = float(getattr(self, '_last_drag_region_update_s', 0.0))
            if event.isFinish() or (now - last) > 0.08:
                self._last_drag_region_update_s = now
                self.add_or_update_interval_region(lo, hi)

            if event.isFinish():
                indices = self.interval_indices_for_recording_time_range(lo, hi)
                # Do not redraw the full monitor here. The cyan band is already visible;
                # just update the table highlight/details. This is much faster.
                self.select_interval_rows(indices, focus_first=True, update_plot=False)
                self.status_label.setText(f'Selected {len(indices)} RR interval(s) from recording-time selection {lo:.3f}-{hi:.3f} s')

            event.accept()
        except Exception:
            try:
                event.accept()
            except Exception:
                pass

    def plot_region_changed_by_user(self):
        # Selection is handled by monitor_mouse_drag_event on mouse release.
        # Keeping this no-op avoids duplicate table/plot work and reduces drag lag.
        return

    def add_or_update_interval_region(self, a_x, b_x):
        try:
            if not hasattr(self, 'interval_region'):
                return
            self._setting_plot_region = True
            try:
                self.interval_region.setRegion([float(a_x), float(b_x)])
                self.plot.addItem(self.interval_region)
            finally:
                self._setting_plot_region = False
        except Exception:
            try:
                self._setting_plot_region = False
            except Exception:
                pass

    # RRNN_MONITOR_ABSOLUTE_HELPERS_V1
    def decimate_for_screening_plot(self, x, y, max_points=9000):
        # Return a lighter trace for fast screening-window redraws.
        try:
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            n = len(x)
            if n <= int(max_points):
                return x, y
            step = int(np.ceil(n / float(max_points)))
            return x[::step], y[::step]
        except Exception:
            return x, y

    def should_draw_context_r_markers(self, start, end):
        # Context R lines are useful in short windows but clutter and slow long windows.
        try:
            return float(end - start) <= 15.0
        except Exception:
            return False

    def selected_row_a_time(self):
        try:
            if not self.interval_rows:
                return 0.0
            i = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
            return float(self.interval_rows[i].get('a_time_s', 0.0))
        except Exception:
            return 0.0

    def plot_x_to_absolute_time(self, x_value):
        # The monitor x-axis is now recording time, not selected-beat-relative time.
        try:
            return float(x_value)
        except Exception:
            return 0.0

    def interval_index_for_absolute_time(self, abs_time):
        if not self.interval_rows:
            return None
        try:
            t = float(abs_time)
            for i, row in enumerate(self.interval_rows):
                if float(row['a_time_s']) <= t <= float(row['b_time_s']):
                    return i
            mids = np.asarray([(float(r['a_time_s']) + float(r['b_time_s'])) / 2.0 for r in self.interval_rows], dtype=float)
            if len(mids):
                return int(np.nanargmin(np.abs(mids - t)))
        except Exception:
            return None
        return None

    def interval_indices_for_recording_time_range(self, t0, t1):
        # Inclusive overlap rule: every RR interval touched by the rectangle is selected.
        out = []
        try:
            lo = min(float(t0), float(t1))
            hi = max(float(t0), float(t1))
            for i, row in enumerate(self.interval_rows):
                a = float(row['a_time_s'])
                b = float(row['b_time_s'])
                if b >= lo and a <= hi:
                    out.append(i)
        except Exception:
            pass
        return out

    def selected_interval_row_indices(self):
        try:
            group = sorted({int(i) for i in getattr(self, 'monitor_selected_indices', set()) if 0 <= int(i) < len(self.interval_rows)})
            if group:
                return group
        except Exception:
            pass
        try:
            r = self.interval_table.currentRow()
            if 0 <= r < len(self.interval_rows):
                return [int(r)]
        except Exception:
            pass
        if self.interval_rows:
            return [max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))]
        return []

    def select_interval_rows(self, indices, focus_first=True, update_plot=True):
        # Store a monitor-selected group and paint it persistently.
        # Only the focus row is Qt-selected; all group rows are blue-highlighted manually.
        try:
            valid = sorted({int(i) for i in indices if 0 <= int(i) < len(self.interval_rows)})
            if not valid:
                return

            self.monitor_selected_indices = set(valid)
            focus = valid[0] if focus_first else valid[-1]
            self.selected_interval_index = focus

            old_updating = getattr(self, '_updating_tables', False)
            old_block = False
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
                self.interval_table.setSelectionMode(QAbstractItemView.SingleSelection)
                self.interval_table.clearSelection()
                self.interval_table.setCurrentCell(int(focus), 0)
                self.interval_table.selectRow(int(focus))
                item = self.interval_table.item(int(focus), 0)
                if item is not None:
                    self.interval_table.scrollToItem(item, QAbstractItemView.EnsureVisible)
            finally:
                try:
                    self.interval_table.blockSignals(old_block)
                except Exception:
                    pass
                self._updating_tables = old_updating

            self.apply_monitor_selection_style()
            self.update_selected_interval_box()
            if update_plot:
                self.monitor_center_s = self.selected_or_group_center_s()
                self.update_plot_for_selected()
        except Exception as exc:
            try:
                self.status_label.setText(f'Selection failed: {exc}')
            except Exception:
                pass

    def select_interval_index(self, index, update_plot=True):
        try:
            if index is None or not self.interval_rows:
                return
            self.select_interval_rows([index], focus_first=True, update_plot=update_plot)
        except Exception:
            pass

    def plot_mouse_clicked(self, event):
        # Left-click the ECG monitor to select the RR interval under the cursor.
        try:
            if event.button() != Qt.LeftButton:
                return
            vb = self.plot.plotItem.vb
            pos = vb.mapSceneToView(event.scenePos())
            abs_t = self.plot_x_to_absolute_time(pos.x())
            idx = self.interval_index_for_absolute_time(abs_t)
            if idx is not None:
                self.select_interval_index(idx, update_plot=True)
                event.accept()
        except Exception:
            pass

    def monitor_mouse_drag_event(self, event):
        # Drag across the ECG monitor to select all RR intervals touched by the dragged time range.
        try:
            if event.button() != Qt.LeftButton:
                original = getattr(self, "_original_vb_mouse_drag_event", None)
                if original is not None:
                    return original(event)
                return

            vb = self.plot.plotItem.vb
            p0 = vb.mapToView(event.buttonDownPos())
            p1 = vb.mapToView(event.pos())
            x0 = float(p0.x())
            x1 = float(p1.x())
            lo = min(x0, x1)
            hi = max(x0, x1)

            if abs(hi - lo) < 1e-6:
                event.accept()
                return

            self.add_or_update_interval_region(lo, hi)

            if event.isFinish():
                if hasattr(self, "interval_indices_for_recording_time_range"):
                    indices = self.interval_indices_for_recording_time_range(lo, hi)
                else:
                    indices = []
                    for i, row in enumerate(self.interval_rows):
                        a = float(row["a_time_s"])
                        b = float(row["b_time_s"])
                        if b >= lo and a <= hi:
                            indices.append(i)

                self.select_interval_rows(indices, focus_first=True, update_plot=True)
                self.status_label.setText(
                    f"Selected {len(indices)} RR interval(s) from recording-time selection {lo:.3f}-{hi:.3f} s"
                )

            event.accept()
        except Exception:
            try:
                event.accept()
            except Exception:
                pass

    def plot_region_changed_by_user(self):
        # Region handles are kept for visibility; selection uses recording-time x values.
        try:
            if getattr(self, '_setting_plot_region', False):
                return
            if not self.interval_rows:
                return
            r0, r1 = self.interval_region.getRegion()
            indices = self.interval_indices_for_recording_time_range(float(r0), float(r1))
            if not indices:
                return
            self.select_interval_rows(indices, focus_first=True, update_plot=True)
            self.update_selected_interval_box()
            self.status_label.setText(f'Selected {len(indices)} RR interval(s) from monitor region')
        except Exception:
            pass

    def add_or_update_interval_region(self, a_x, b_x):
        try:
            if not hasattr(self, 'interval_region'):
                return
            self._setting_plot_region = True
            try:
                self.interval_region.setRegion([float(a_x), float(b_x)])
                if self.interval_region.scene() is None:
                    self.plot.addItem(self.interval_region)
            finally:
                self._setting_plot_region = False
        except Exception:
            try:
                self._setting_plot_region = False
            except Exception:
                pass

    def recording_time_bounds(self):
        try:
            if self.time_s is None or len(self.time_s) == 0:
                return 0.0, 0.0
            return float(self.time_s[0]), float(self.time_s[-1])
        except Exception:
            return 0.0, 0.0

    def current_group_indices(self):
        try:
            group = sorted({int(i) for i in getattr(self, 'monitor_selected_indices', set()) if 0 <= int(i) < len(self.interval_rows)})
            if group:
                return group
        except Exception:
            pass
        if self.interval_rows:
            return [max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))]
        return []

    def current_group_rows(self):
        try:
            return [self.interval_rows[i] for i in self.current_group_indices()]
        except Exception:
            return []

    def current_group_time_bounds(self):
        rows = self.current_group_rows()
        if not rows:
            return None, None
        try:
            return min(float(r['a_time_s']) for r in rows), max(float(r['b_time_s']) for r in rows)
        except Exception:
            return None, None

    def current_plot_x_range(self):
        try:
            xr = self.plot.plotItem.vb.viewRange()[0]
            return float(xr[0]), float(xr[1])
        except Exception:
            return None, None

    def time_range_visible_in_monitor(self, start_s, end_s, margin_s=0.25):
        try:
            x0, x1 = self.current_plot_x_range()
            if x0 is None or x1 is None:
                return False
            return float(start_s) >= x0 + margin_s and float(end_s) <= x1 - margin_s
        except Exception:
            return False

    def selected_or_group_center_s(self):
        try:
            a, b = self.current_group_time_bounds()
            if a is not None and b is not None:
                return (float(a) + float(b)) / 2.0
        except Exception:
            pass
        start, end = self.recording_time_bounds()
        return (start + end) / 2.0

    def current_window_span_s(self):
        mode = self.window_seconds()
        start, end = self.recording_time_bounds()
        duration = max(0.0, end - start)
        if mode == 'full':
            return duration if duration > 0 else 60.0
        if mode is None:
            return 5.0
        try:
            return max(0.5, float(mode))
        except Exception:
            return 60.0

    def clamp_monitor_center(self, center):
        start, end = self.recording_time_bounds()
        span = self.current_window_span_s()
        if end <= start:
            return 0.0
        if span >= (end - start):
            return (start + end) / 2.0
        half = span / 2.0
        return max(start + half, min(float(center), end - half))

    def window_mode_changed(self):
        try:
            self.monitor_center_s = self.clamp_monitor_center(self.selected_or_group_center_s())
            self.update_plot_for_selected()
        except Exception:
            self.update_plot_for_selected()

    def update_scrub_from_center(self):
        try:
            if not hasattr(self, 'monitor_scrub') or self.time_s is None:
                return
            start, end = self.recording_time_bounds()
            if end <= start:
                return
            center = self.monitor_center_s
            if center is None:
                center = self.selected_or_group_center_s()
            center = self.clamp_monitor_center(center)
            frac = (center - start) / max(1e-9, end - start)
            value = int(max(0, min(10000, round(frac * 10000))))
            self._syncing_scrub = True
            self.monitor_scrub.setValue(value)
            if hasattr(self, 'scrub_label'):
                self.scrub_label.setText(f'{center:.3f} s')
        except Exception:
            pass
        finally:
            try:
                self._syncing_scrub = False
            except Exception:
                pass

    def scrub_changed(self, value):
        try:
            if getattr(self, '_syncing_scrub', False):
                return
            start, end = self.recording_time_bounds()
            if end <= start:
                return
            frac = float(value) / 10000.0
            self.monitor_center_s = self.clamp_monitor_center(start + frac * (end - start))
            if hasattr(self, 'scrub_label'):
                self.scrub_label.setText(f'{self.monitor_center_s:.3f} s')
            self.update_plot_for_selected()
        except Exception:
            pass

    def step_monitor_window(self, direction):
        try:
            if self.time_s is None:
                return
            span = self.current_window_span_s()
            if self.monitor_center_s is None:
                self.monitor_center_s = self.selected_or_group_center_s()
            self.monitor_center_s = self.clamp_monitor_center(float(self.monitor_center_s) + float(direction) * span * 0.80)
            self.update_plot_for_selected()
        except Exception:
            pass

    def interval_indices_for_recording_time_range(self, t0, t1):
        out = []
        try:
            lo = min(float(t0), float(t1))
            hi = max(float(t0), float(t1))
            for i, row in enumerate(self.interval_rows):
                a = float(row['a_time_s'])
                b = float(row['b_time_s'])
                if b >= lo and a <= hi:
                    out.append(i)
        except Exception:
            pass
        return out

    def selected_interval_row_indices(self):
        group = self.current_group_indices()
        if group:
            return group
        return []

    def apply_monitor_selection_style(self):
        old_updating = getattr(self, '_updating_tables', False)
        old_block = False
        try:
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
            except Exception:
                old_block = False
            selected = set(getattr(self, 'monitor_selected_indices', set()))
            for r, row in enumerate(self.interval_rows):
                if r < self.interval_table.rowCount():
                    try:
                        self.apply_row_style(self.interval_table, r, row)
                    except TypeError:
                        self.apply_row_style(r, row)
            if selected:
                bg = QColor('#12324A')
                fg = QColor('#FFFFFF')
                for r in selected:
                    if 0 <= int(r) < self.interval_table.rowCount():
                        for c in range(self.interval_table.columnCount()):
                            it = self.interval_table.item(int(r), c)
                            if it is not None:
                                it.setBackground(bg)
                                it.setForeground(fg)
        except Exception:
            pass
        finally:
            try:
                self.interval_table.blockSignals(old_block)
            except Exception:
                pass
            self._updating_tables = old_updating

    def select_interval_rows(self, indices, focus_first=True, update_plot=True):
        try:
            valid = sorted({int(i) for i in indices if 0 <= int(i) < len(self.interval_rows)})
            if not valid:
                return
            self.monitor_selected_indices = set(valid)
            focus = valid[0] if focus_first else valid[-1]
            self.selected_interval_index = focus
            old_updating = getattr(self, '_updating_tables', False)
            old_block = False
            self._updating_tables = True
            try:
                old_block = self.interval_table.blockSignals(True)
                self.interval_table.setSelectionMode(QAbstractItemView.SingleSelection)
                self.interval_table.clearSelection()
                self.interval_table.setCurrentCell(int(focus), 0)
                self.interval_table.selectRow(int(focus))
                item = self.interval_table.item(int(focus), 0)
                if item is not None:
                    self.interval_table.scrollToItem(item, QAbstractItemView.EnsureVisible)
            finally:
                try:
                    self.interval_table.blockSignals(old_block)
                except Exception:
                    pass
                self._updating_tables = old_updating
            self.apply_monitor_selection_style()
            self.update_selected_interval_box()
            self.update_summary()
            if update_plot:
                self.monitor_center_s = self.selected_or_group_center_s()
                self.update_plot_for_selected()
        except Exception as exc:
            try:
                self.status_label.setText(f'Selection failed: {exc}')
            except Exception:
                pass

    def select_interval_index(self, index, update_plot=True):
        try:
            if index is None or not self.interval_rows:
                return
            i = max(0, min(int(index), len(self.interval_rows) - 1))
            self.select_interval_rows([i], focus_first=True, update_plot=update_plot)
        except Exception:
            pass

    def plot_x_to_absolute_time(self, x_value):
        try:
            return float(x_value)
        except Exception:
            return 0.0

    def interval_index_for_absolute_time(self, abs_time):
        if not self.interval_rows:
            return None
        try:
            t = float(abs_time)
            for i, row in enumerate(self.interval_rows):
                if float(row['a_time_s']) <= t <= float(row['b_time_s']):
                    return i
            mids = np.asarray([(float(r['a_time_s']) + float(r['b_time_s'])) / 2.0 for r in self.interval_rows], dtype=float)
            if len(mids):
                return int(np.nanargmin(np.abs(mids - t)))
        except Exception:
            return None
        return None

    def plot_mouse_clicked(self, event):
        try:
            if event.button() != Qt.LeftButton:
                return
            vb = self.plot.plotItem.vb
            pos = vb.mapSceneToView(event.scenePos())
            idx = self.interval_index_for_absolute_time(pos.x())
            if idx is not None:
                self.select_interval_index(idx, update_plot=True)
                event.accept()
        except Exception:
            pass

    def monitor_mouse_drag_event(self, event):
        try:
            if event.button() != Qt.LeftButton:
                original = getattr(self, '_original_vb_mouse_drag_event', None)
                if original is not None:
                    return original(event)
                return
            vb = self.plot.plotItem.vb
            p0 = vb.mapToView(event.buttonDownPos())
            p1 = vb.mapToView(event.pos())
            x0 = float(p0.x())
            x1 = float(p1.x())
            lo = min(x0, x1)
            hi = max(x0, x1)
            if abs(hi - lo) < 1e-6:
                event.accept()
                return
            self.add_or_update_interval_region(lo, hi)
            if event.isFinish():
                indices = self.interval_indices_for_recording_time_range(lo, hi)
                self.select_interval_rows(indices, focus_first=True, update_plot=True)
                self.status_label.setText(f'Selected {len(indices)} RR interval(s) from recording-time selection {lo:.3f}-{hi:.3f} s')
            event.accept()
        except Exception:
            try:
                event.accept()
            except Exception:
                pass

    def plot_region_changed_by_user(self):
        try:
            if getattr(self, '_setting_plot_region', False):
                return
            if not self.interval_rows:
                return
            r0, r1 = self.interval_region.getRegion()
            lo = min(float(r0), float(r1))
            hi = max(float(r0), float(r1))
            indices = self.interval_indices_for_recording_time_range(lo, hi)
            if indices:
                self.select_interval_rows(indices, focus_first=True, update_plot=True)
                self.status_label.setText(f'Selected {len(indices)} RR interval(s) from monitor region')
        except Exception:
            pass

    def add_or_update_interval_region(self, a_x, b_x):
        try:
            if not hasattr(self, 'interval_region'):
                return
            self._setting_plot_region = True
            try:
                self.interval_region.setRegion([float(a_x), float(b_x)])
                if self.interval_region.scene() is None:
                    self.plot.addItem(self.interval_region)
            finally:
                self._setting_plot_region = False
        except Exception:
            try:
                self._setting_plot_region = False
            except Exception:
                pass

    def selected_or_group_center_s(self):
        try:
            g0, g1 = self.current_group_time_bounds()
            if g0 is not None and g1 is not None:
                return (float(g0) + float(g1)) / 2.0
        except Exception:
            pass
        try:
            if self.interval_rows:
                i = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
                row = self.interval_rows[i]
                return (float(row['a_time_s']) + float(row['b_time_s'])) / 2.0
        except Exception:
            pass
        start, end = self.recording_time_bounds()
        return (start + end) / 2.0

    def current_window_span_s(self):
        mode = self.window_seconds()
        start, end = self.recording_time_bounds()
        duration = max(0.0, end - start)
        if mode == 'full':
            return duration if duration > 0 else 60.0
        if mode is None:
            return 5.0
        try:
            return max(0.5, float(mode))
        except Exception:
            return 60.0

    def clamp_monitor_center(self, center):
        start, end = self.recording_time_bounds()
        span = self.current_window_span_s()
        if end <= start:
            return 0.0
        if span >= (end - start):
            return (start + end) / 2.0
        half = span / 2.0
        return max(start + half, min(float(center), end - half))

    def window_mode_changed(self):
        try:
            self.monitor_center_s = self.clamp_monitor_center(self.selected_or_group_center_s())
            pass  # scrub disabled in classic look
            self.update_plot_for_selected()
        except Exception:
            self.update_plot_for_selected()

    def update_scrub_from_center(self):
        try:
            if not hasattr(self, 'monitor_scrub') or self.time_s is None:
                return
            start, end = self.recording_time_bounds()
            if end <= start:
                return
            center = self.monitor_center_s
            if center is None:
                center = self.selected_or_group_center_s()
            center = self.clamp_monitor_center(center)
            frac = (center - start) / max(1e-9, end - start)
            value = int(max(0, min(10000, round(frac * 10000))))
            self._syncing_scrub = True
            self.monitor_scrub.setValue(value)
            if hasattr(self, 'scrub_label'):
                self.scrub_label.setText(f'{center:.3f} s')
        except Exception:
            pass
        finally:
            try:
                self._syncing_scrub = False
            except Exception:
                pass

    def scrub_changed(self, value):
        try:
            if getattr(self, '_syncing_scrub', False):
                return
            start, end = self.recording_time_bounds()
            if end <= start:
                return
            frac = float(value) / 10000.0
            self.monitor_center_s = self.clamp_monitor_center(start + frac * (end - start))
            if hasattr(self, 'scrub_label'):
                self.scrub_label.setText(f'{self.monitor_center_s:.3f} s')
            self.update_plot_for_selected()
        except Exception:
            pass

    def step_monitor_window(self, direction):
        try:
            if self.time_s is None:
                return
            span = self.current_window_span_s()
            if self.monitor_center_s is None:
                self.monitor_center_s = self.selected_or_group_center_s()
            # Move by 80% of the visible window; fast but with overlap.
            self.monitor_center_s = self.clamp_monitor_center(float(self.monitor_center_s) + float(direction) * span * 0.80)
            pass  # scrub disabled in classic look
            self.update_plot_for_selected()
        except Exception:
            pass

    def update_plot_for_selected(self):
        self.plot.clear()
        if self.time_s is None or self.filtered_signal is None or not self.interval_rows:
            self.plot.setTitle('Load raw.csv')
            return
        self.update_source_summary_label()
        i = max(0, min(self.selected_interval_index, len(self.interval_rows) - 1))
        row = self.interval_rows[i]
        group = sorted({int(x) for x in getattr(self, 'monitor_selected_indices', set()) if 0 <= int(x) < len(self.interval_rows)})
        group_mode = len(group) > 1
        if group_mode:
            rows = [self.interval_rows[g] for g in group]
            group_start = min(float(r['a_time_s']) for r in rows)
            group_end = max(float(r['b_time_s']) for r in rows)
        else:
            group_start = float(row['a_time_s'])
            group_end = float(row['b_time_s'])
        rec_start, rec_end = self.recording_time_bounds()
        mode = self.window_seconds()
        if mode == 'full':
            start = rec_start
            end = rec_end
            self.monitor_center_s = (rec_start + rec_end) / 2.0
        elif mode is None:
            start = max(rec_start, group_start - self.pre_r_s)
            end = min(rec_end, group_end + self.post_r_s)
            self.monitor_center_s = (start + end) / 2.0
        else:
            span = max(0.5, float(mode))
            if self.monitor_center_s is None:
                self.monitor_center_s = self.selected_or_group_center_s()
            center = self.clamp_monitor_center(self.monitor_center_s)
            self.monitor_center_s = center
            half = span / 2.0
            start = max(rec_start, center - half)
            end = min(rec_end, center + half)
        mask = (self.time_s >= start) & (self.time_s <= end)
        x = self.time_s[mask]
        y = self.filtered_signal[mask]
        try:
            y = y - np.nanmedian(y)
        except Exception:
            pass
        try:
            px, py = self.decimate_for_screening_plot(x, y, max_points=6000)
        except Exception:
            px, py = x, y
        self.plot.plot(px, py, pen=pg.mkPen(NN_FILTERED_COLOR, width=1.05))
        if self.should_draw_context_r_markers(start, end):
            try:
                r_times = self.time_s[np.asarray(getattr(self, 'rr_peaks', self.r_peaks), dtype=int)]
                for rt in r_times:
                    if start <= rt <= end:
                        self.plot.addItem(pg.InfiniteLine(float(rt), angle=90, pen=pg.mkPen(NN_SUBTLE_R_COLOR, width=0.6, style=Qt.DotLine)))
            except Exception:
                pass
        try:
            finite = y[np.isfinite(y)]
            y_top = float(np.nanpercentile(finite, 95)) if len(finite) else 0.0
        except Exception:
            y_top = 0.0
        self.add_or_update_interval_region(float(group_start), float(group_end))
        if start <= group_start <= end:
            self.plot.addItem(pg.InfiniteLine(float(group_start), angle=90, pen=pg.mkPen(NN_SELECTED_COLOR, width=1.5, style=Qt.DashLine)))
        if start <= group_end <= end:
            self.plot.addItem(pg.InfiniteLine(float(group_end), angle=90, pen=pg.mkPen(NN_SELECTED_COLOR, width=1.5, style=Qt.DashLine)))
        try:
            if start <= group_start <= end:
                label1 = 'selection start' if group_mode else 'A R'
                txt1 = pg.TextItem(label1, color=NN_TEXT_COLOR, anchor=(0.5, 1.2))
                txt1.setPos(float(group_start), y_top)
                self.plot.addItem(txt1)
            if start <= group_end <= end:
                label2 = 'selection end' if group_mode else 'B R'
                txt2 = pg.TextItem(label2, color=NN_TEXT_COLOR, anchor=(0.5, 1.2))
                txt2.setPos(float(group_end), y_top)
                self.plot.addItem(txt2)
        except Exception:
            pass
        if group_mode:
            marker_note = f'Group {len(group)} RR intervals | {group_start:.3f}-{group_end:.3f} s'
        else:
            marker_note = f'Interval {row["id"]} | {row["a_complex"]}->{row["b_complex"]} | RR {row["rr_ms"]:.1f} ms | NN {"yes" if row["accepted"] else "no"}'
        speed_note = '' if self.should_draw_context_r_markers(start, end) else ' | fast view'
        self.plot.setTitle(f'Window {self.window_box.currentText()}{speed_note} | Recording time {start:.3f}-{end:.3f} s | {marker_note}')
        self.plot.setLabel('bottom', 'Recording time (s)')
        self.plot.setLabel('left', 'Filtered ECG 0.5-40 Hz')
        try:
            self.plot.setXRange(float(start), float(end), padding=0)
            finite = y[np.isfinite(y)]
            if len(finite):
                lo, hi = np.nanpercentile(finite, [1, 99])
                pad = max(40.0, 0.20 * (hi - lo))
                self.plot.setYRange(float(lo - pad), float(hi + pad), padding=0)
        except Exception:
            pass
        self.update_scrub_from_center()

    def update_method_box(self):
        lines = [
            'Method',
            '',
            'This tab is the source-of-truth interval screening layer.',
            'It decides which RR intervals become NN.',
            '',
            'Navigation:',
            '- Arrow keys: previous/next interval.',
            '- Space: use/reject selected interval or selected group.',
            '- Click monitor: select interval under cursor.',
            '- Two-finger trackpad scroll on monitor: scrub through recording.',
            '- Drag monitor: select a group of intervals.',
            '',
            'Reject when:',
            '- false extra R peak, missed R peak, noise, motion artefact, or ectopic/non-sinus beat.',
            '- Rejected intervals break delta-NN links; OPL does not bridge gaps.',
        ]
        self.method_box.setPlainText(chr(10).join(lines))

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self.polish_lower_tables()
            self.tune_interval_columns()
            self.tune_difference_columns()
        except Exception:
            pass

    def export_table_dialog(self):
        if not self.interval_rows:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export RR NN table", "rr_nn_table.csv", "CSV files (*.csv)")
        if not path:
            return
        self.export_table(path)

    def export_table(self, path):
        path = Path(path)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "interval_id", "a_complex", "b_complex", "r_a_time_s", "r_b_time_s",
                "rr_ms", "hr_bpm", "accepted_nn", "reason", "manual_override"
            ])
            for row in self.interval_rows:
                writer.writerow([
                    row["id"], row["a_complex"], row["b_complex"],
                    f"{row['a_time_s']:.6f}", f"{row['b_time_s']:.6f}",
                    f"{row['rr_ms']:.3f}", f"{row['hr_bpm']:.3f}",
                    "1" if row["accepted"] else "0",
                    row["reason"], "1" if row["manual"] else "0",
                ])
        self.status_label.setText(f"Exported {path.name}")
