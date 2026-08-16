from __future__ import annotations

"""OPL-native 4D Cardiac Anatomy panel.

This panel intentionally does NOT embed the standalone Open 4D Cardiac Anatomy
application UI. It reuses the rendering and cardiac-motion engine underneath,
while presenting a compact OpenPhysiologyLab-native interface.
"""

from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QSpinBox, QSlider, QFrame, QSizePolicy,
)

from app.open_cardiac_anatomy_vendor.viewer import CardiacAnatomyViewer


GOLD = "#D4AF37"
TEXT = "#F2F2F4"
SECONDARY = "#C6CBD5"
MUTED = "#8F96A6"
EMERALD = "#50C878"
CYAN = "#25D8FF"

PHASE_COLOURS = {
    "isovolumetric_contraction": "#8A6A1F",
    "rapid_ejection": "#B84747",
    "reduced_ejection": "#8F353D",
    "protodiastole": "#72507D",
    "isovolumetric_relaxation": "#52679A",
    "rapid_filling": "#247D89",
    "diastasis": "#2F6B55",
    "atrial_systole": "#885A91",
}

PHASE_SHORT = {
    "isovolumetric_contraction": "IVC",
    "rapid_ejection": "Rapid ejection",
    "reduced_ejection": "Reduced ejection",
    "protodiastole": "Proto-D",
    "isovolumetric_relaxation": "IVR",
    "rapid_filling": "Rapid filling",
    "diastasis": "Diastasis",
    "atrial_systole": "Atrial systole",
}


class OPLPhaseRibbon(QWidget):
    """Small OPL-styled cardiac-cycle phase ribbon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timing = None
        self.fraction = 0.0
        # OPL_4D_VERTICAL_FIT_V02
        # OPL_4D_SYNC_DECK_V03
        # The ribbon is now purely a phase map/playhead. Time belongs to
        # the future ECG scrubber rather than being repeated below it.
        self.setMinimumHeight(23)
        self.setMaximumHeight(25)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, timing, fraction: float):
        self.timing = timing
        self.fraction = float(fraction) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#030406"))

        if self.timing is None:
            painter.setPen(QColor(MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter, "Cardiac phases load with the model")
            return

        left = 2.0
        top = 1.0
        width = max(1.0, float(self.width()) - 4.0)
        height = 21.0

        for phase in self.timing.phases:
            x0 = left + width * (phase.start_ms / self.timing.cycle_ms)
            x1 = left + width * (phase.end_ms / self.timing.cycle_ms)
            rect = QRectF(x0, top, max(1.0, x1 - x0), height)
            painter.fillRect(rect, QColor(PHASE_COLOURS.get(phase.key, "#303744")))
            painter.setPen(QColor("#F2F2F4"))
            name = PHASE_SHORT.get(phase.key, phase.name)
            if painter.fontMetrics().horizontalAdvance(name) + 8 <= rect.width():
                painter.drawText(rect, Qt.AlignCenter | Qt.TextSingleLine, name)

        marker_x = left + width * self.fraction
        painter.setPen(QColor(GOLD))
        painter.drawLine(int(marker_x), 0, int(marker_x), int(self.height()))


class OPL4DCardiacAnatomyPanel(QWidget):
    """4D cardiac anatomy presented entirely through OPL-facing controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._syncing_slider = False

        # The standalone viewer is used only as a rendering/motion engine.
        # Its application shell remains hidden and is never embedded in OPL.
        self.engine = CardiacAnatomyViewer(self)
        self.engine.hide()

        self._build_ui()
        self._detach_gl_view_into_opl()
        self._detach_ecg_trace_into_opl()

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(100)
        self.ui_timer.timeout.connect(self._sync_from_engine)
        self.ui_timer.start()

        QTimer.singleShot(0, self._initialise_engine_state)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)
        self.setMinimumSize(0, 0)

        title = QLabel("OpenPhysiologyLab 4D Cardiac Anatomy")
        title.setStyleSheet(f"font-size:13px; font-weight:700; color:{GOLD};")
        root.addWidget(title)

        self.subtitle = QLabel(
            "Registered open-data teaching composite • statistical cardiac-motion cycle • not patient-specific mechanics"
        )
        self.subtitle.setWordWrap(False)
        self.subtitle.setStyleSheet(f"color:{SECONDARY};")
        self.subtitle.setToolTip(
            "Explore a detailed open-data heart through the cardiac cycle. "
            "The anatomy is a registered teaching composite and the motion is "
            "a statistical source cycle — not patient-specific mechanics."
        )
        root.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(7)

        playback_box = QGroupBox("Playback")
        playback = QHBoxLayout(playback_box)
        playback.setContentsMargins(6, 3, 6, 3)
        playback.setSpacing(6)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setObjectName("primaryButton")
        self.play_btn.clicked.connect(self._toggle_play)
        playback.addWidget(self.play_btn)

        playback.addWidget(QLabel("Heart rate"))
        self.hr_spin = QSpinBox()
        self.hr_spin.setRange(40, 140)
        self.hr_spin.setValue(72)
        self.hr_spin.setSuffix(" bpm")
        self.hr_spin.valueChanged.connect(self._heart_rate_changed)
        playback.addWidget(self.hr_spin)

        playback.addWidget(QLabel("Speed"))
        self.speed_box = QComboBox()
        self.speed_box.addItem("1×", 1.0)
        self.speed_box.addItem("0.5×", 0.5)
        self.speed_box.addItem("0.25×", 0.25)
        self.speed_box.addItem("0.1×", 0.10)
        self.speed_box.setCurrentIndex(0)
        self.speed_box.currentIndexChanged.connect(self._speed_changed)
        playback.addWidget(self.speed_box)

        # OPL_4D_RECORDED_ECG_V05
        self.load_ecg_btn = QPushButton("ECG…")
        self.load_ecg_btn.setToolTip(
            "Load an OPL/NPG Lite raw.csv, review accepted R triggers and "
            "median P/QRS landmarks, then drive the 4-D heart from the recorded RR cycles."
        )
        self.load_ecg_btn.clicked.connect(self._load_ecg_clicked)
        playback.addWidget(self.load_ecg_btn)

        controls.addWidget(playback_box, 0)

        view_box = QGroupBox("View")
        view = QHBoxLayout(view_box)
        view.setContentsMargins(6, 3, 6, 3)
        view.setSpacing(6)

        self.view_box = QComboBox()
        self.view_box.addItems([
            "External anatomy + coronaries",
            "Ventricular walls + myocardium",
            "Four chambers",
            "Valve orifices",
            "Coronary circulation",
            "Source-motion surfaces",
            "Registered atlas overview",
        ])
        self.view_box.currentIndexChanged.connect(self._view_changed)
        view.addWidget(self.view_box, 1)

        self.camera_box = QComboBox()
        self.camera_box.addItems([
            "Free rotation",
            "Anterior",
            "Posterior",
            "Left lateral",
            "Right lateral",
            "Superior",
            "Inferior",
        ])
        self.camera_box.currentTextChanged.connect(self._camera_changed)
        view.addWidget(self.camera_box)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self._fit)
        view.addWidget(fit_btn)
        controls.addWidget(view_box, 1)

        step_box = QGroupBox("Phase")
        step = QHBoxLayout(step_box)
        step.setContentsMargins(6, 3, 6, 3)
        step.setSpacing(5)

        prev_btn = QPushButton("◀ Phase")
        prev_btn.clicked.connect(lambda: self._jump_phase(-1))
        step.addWidget(prev_btn)
        next_btn = QPushButton("Phase ▶")
        next_btn.clicked.connect(lambda: self._jump_phase(+1))
        step.addWidget(next_btn)
        back_btn = QPushButton("−20 ms")
        back_btn.clicked.connect(lambda: self._step_ms(-20.0))
        step.addWidget(back_btn)
        fwd_btn = QPushButton("+20 ms")
        fwd_btn.clicked.connect(lambda: self._step_ms(+20.0))
        step.addWidget(fwd_btn)
        controls.addWidget(step_box, 0)

        root.addLayout(controls)

        self.viewport_frame = QFrame()
        self.viewport_frame.setObjectName("contentFrame")
        self.viewport_frame.setMinimumSize(0, 0)
        self.viewport_frame.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        viewport_layout = QVBoxLayout(self.viewport_frame)
        viewport_layout.setContentsMargins(5, 5, 5, 5)
        viewport_layout.setSpacing(4)
        self.viewport_layout = viewport_layout

        self.missing_view_label = QLabel("Preparing 3D cardiac anatomy…")
        self.missing_view_label.setAlignment(Qt.AlignCenter)
        self.missing_view_label.setStyleSheet(f"color:{MUTED};")
        viewport_layout.addWidget(self.missing_view_label, 1)

        root.addWidget(self.viewport_frame, 1)

        # OPL-native synchronized ECG strip. The actual canvas is detached
        # from the hidden OCA engine so there is only ONE recording, ONE set
        # of reviewed R triggers and ONE playback clock.
        self.ecg_frame = QFrame()
        self.ecg_frame.setObjectName("cardiacEcgDeck")
        self.ecg_frame.setStyleSheet(
            "QFrame#cardiacEcgDeck { background:#05070A; "
            "border-top:1px solid #242A34; }"
        )
        ecg_layout = QVBoxLayout(self.ecg_frame)
        ecg_layout.setContentsMargins(4, 2, 4, 2)
        ecg_layout.setSpacing(2)

        ecg_header = QHBoxLayout()
        ecg_header.setSpacing(6)
        self.ecg_source_label = QLabel("Recorded ECG")
        self.ecg_source_label.setStyleSheet(
            f"font-weight:700; color:{GOLD};"
        )
        ecg_header.addWidget(self.ecg_source_label)

        self.ecg_status_label = QLabel("No ECG loaded")
        self.ecg_status_label.setStyleSheet(f"color:{SECONDARY};")
        ecg_header.addWidget(self.ecg_status_label, 1)

        self.review_ecg_btn = QPushButton("Review")
        self.review_ecg_btn.setToolTip(
            "Review the median P/QRS template and accepted R triggers. "
            "T-wave delineation is intentionally not required for synchronization."
        )
        self.review_ecg_btn.clicked.connect(self._review_ecg_clicked)
        ecg_header.addWidget(self.review_ecg_btn)

        self.clear_ecg_btn = QPushButton("Model clock")
        self.clear_ecg_btn.setToolTip(
            "Detach the recording and return the 4-D heart to the selected model heart rate."
        )
        self.clear_ecg_btn.clicked.connect(self._clear_ecg_clicked)
        ecg_header.addWidget(self.clear_ecg_btn)

        ecg_layout.addLayout(ecg_header)

        self.ecg_trace_host = QVBoxLayout()
        self.ecg_trace_host.setContentsMargins(0, 0, 0, 0)
        self.ecg_trace_host.setSpacing(0)
        ecg_layout.addLayout(self.ecg_trace_host)

        self.ecg_frame.setVisible(False)
        root.addWidget(self.ecg_frame, 0)

        # OPL_4D_OCA_TIMING_BAR_V04
        # Restore the useful timing hierarchy from standalone OCA while
        # keeping the entire presentation OPL-native.
        phase_frame = QFrame()
        phase_frame.setObjectName("cardiacTimingDeck")
        phase_frame.setStyleSheet(
            "QFrame#cardiacTimingDeck { background:#05070A; "
            "border-top:1px solid #242A34; }"
        )
        phase_layout = QVBoxLayout(phase_frame)
        phase_layout.setContentsMargins(4, 2, 4, 2)
        phase_layout.setSpacing(1)

        timeline_header = QHBoxLayout()
        timeline_header.setSpacing(8)

        self.cycle_time_label = QLabel(
            "Beat 1/5 • 0 ms/833 ms • total 0/4,167 ms"
        )
        self.cycle_time_label.setStyleSheet(
            f"font-weight:700; color:{GOLD};"
        )
        timeline_header.addWidget(self.cycle_time_label, 0)
        timeline_header.addStretch(1)

        self.cycle_phase_label = QLabel(
            "Estimated: End-diastole • IVC begins • 0.0%"
        )
        self.cycle_phase_label.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )
        self.cycle_phase_label.setStyleSheet(f"color:{SECONDARY};")
        timeline_header.addWidget(self.cycle_phase_label, 0)
        phase_layout.addLayout(timeline_header)

        self.phase_ribbon = OPLPhaseRibbon()
        phase_layout.addWidget(self.phase_ribbon)

        # OCA-style visible scrub line. Later the ECG cursor and this
        # control will move together.
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.setValue(0)
        self.timeline.setSingleStep(1)
        self.timeline.setPageStep(10)
        self.timeline.setMaximumHeight(14)
        self.timeline.valueChanged.connect(self._timeline_changed)
        phase_layout.addWidget(self.timeline)

        marker_row = QHBoxLayout()
        marker_row.setContentsMargins(0, 0, 0, 0)
        marker_row.setSpacing(4)
        self.timeline_markers_layout = marker_row

        self.ed_marker_label = QLabel("ED • 0 ms")
        self.es_marker_label = QLabel("ES • -- ms")
        self.es_marker_label.setAlignment(Qt.AlignCenter)
        self.next_ed_marker_label = QLabel("next ED • -- ms")
        self.next_ed_marker_label.setAlignment(
            Qt.AlignRight | Qt.AlignVCenter
        )

        self.valve_label = QLabel("AV: -- • Semilunar: --")
        self.valve_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.valve_label.setStyleSheet(
            f"color:{CYAN}; font-size:9pt;"
        )

        for marker in (
            self.ed_marker_label,
            self.es_marker_label,
            self.next_ed_marker_label,
        ):
            marker.setStyleSheet(
                f"color:{MUTED}; font-size:9pt;"
            )

        marker_row.addWidget(self.ed_marker_label)
        marker_row.addStretch(4)
        marker_row.addWidget(self.es_marker_label)
        marker_row.addStretch(6)
        marker_row.addWidget(self.next_ed_marker_label)
        marker_row.addSpacing(18)
        marker_row.addWidget(self.valve_label)
        phase_layout.addLayout(marker_row)

        root.addWidget(phase_frame, 0)

        self.viewport_frame.setToolTip(
            "Mouse: left-drag rotate • right/middle-drag pan • wheel zoom • "
            "double-click fit.\n"
            "Scientific boundary: registered open anatomy + one normalized "
            "statistical cardiac-motion cycle."
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Scientific viewport and phase controls get priority over explanatory
        # prose when vertical space is limited.
        if hasattr(self, "subtitle"):
            ecg_active = False
            try:
                ecg_active = bool(self.engine._ecg_gating_active())
            except Exception:
                pass
            self.subtitle.setVisible(
                self.height() >= (860 if ecg_active else 760)
            )

    def _detach_gl_view_into_opl(self):
        gl_view = getattr(self.engine, "gl_view", None)
        if gl_view is None:
            self.missing_view_label.setText(
                "3D view unavailable. PyOpenGL / pyqtgraph.opengl could not initialise."
            )
            return

        self.viewport_layout.removeWidget(self.missing_view_label)
        self.missing_view_label.deleteLater()
        self.missing_view_label = None

        gl_view.setParent(self.viewport_frame)
        gl_view.setMinimumSize(0, 0)
        gl_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewport_layout.addWidget(gl_view, 1)
        gl_view.show()

    def _detach_ecg_trace_into_opl(self):
        trace = getattr(self.engine, "ecg_trace", None)
        if trace is None:
            self.ecg_status_label.setText("ECG canvas unavailable")
            self.load_ecg_btn.setEnabled(False)
            return

        trace.setParent(self.ecg_frame)
        trace.setMinimumHeight(118)
        trace.setMaximumHeight(158)
        try:
            trace.canvas.setMinimumHeight(108)
            trace.canvas.setMaximumHeight(145)
            trace.canvas.window_span_s = 2.6
        except Exception:
            pass
        try:
            # Marker details remain available in the full Review window; the
            # synchronized strip itself should remain a compact physiology view.
            trace.marker_summary.setVisible(False)
        except Exception:
            pass
        self.ecg_trace_host.addWidget(trace)
        self.ecg_trace = trace
        trace.setVisible(False)

    def _initialise_engine_state(self):
        try:
            self.engine.heart_rate_spin.setValue(72)
            self.engine.view_mode_combo.setCurrentIndex(0)
            self.engine.orientation_combo.setCurrentText("Anterior")
            self.engine.reset_view()
            self._speed_changed()
        except Exception:
            pass

    def _load_ecg_clicked(self):
        try:
            self.engine.load_ecg()
        except Exception:
            return
        self._sync_ecg_panel_state()
        self._sync_from_engine()

    def _review_ecg_clicked(self):
        try:
            self.engine.review_ecg_peaks()
        except Exception:
            return
        self._sync_ecg_panel_state()
        self._sync_from_engine()

    def _clear_ecg_clicked(self):
        try:
            self.engine.clear_ecg_gating()
        except Exception:
            return
        self._sync_ecg_panel_state()
        self._sync_from_engine()

    def _sync_ecg_panel_state(self):
        recording = getattr(self.engine, "ecg_recording", None)
        active = recording is not None

        self.ecg_frame.setVisible(active)
        self.review_ecg_btn.setEnabled(active)
        self.clear_ecg_btn.setEnabled(active)
        self.hr_spin.setEnabled(not active)

        if not active:
            self.load_ecg_btn.setText("ECG…")
            self.load_ecg_btn.setToolTip(
                "Load an OPL/NPG Lite raw.csv and synchronize the 4-D heart "
                "to reviewed R-trigger cycles."
            )
            self.ecg_source_label.setText("Recorded ECG")
            self.ecg_status_label.setText("No ECG loaded")
            return

        try:
            source_name = recording.source_path.name
        except Exception:
            source_name = "recorded ECG"

        try:
            mean_hr = recording.mean_heart_rate_bpm
        except Exception:
            mean_hr = float("nan")

        try:
            status = (
                f"{recording.channel_name} • {recording.fs_hz:.0f} Hz • "
                f"{recording.beat_count} reviewed RR cycles • full reviewed sequence"
            )
            if mean_hr == mean_hr:
                status += f" • mean {mean_hr:.1f} bpm"
            if recording.quality_flags:
                status += f" • {len(recording.quality_flags)} quality flag"
                if len(recording.quality_flags) != 1:
                    status += "s"
        except Exception:
            status = "Recorded ECG drives cycle timing"

        self.load_ecg_btn.setText("ECG ✓")
        self.load_ecg_btn.setToolTip(
            f"Loaded: {source_name}. Click to choose a different recording."
        )
        self.ecg_source_label.setText(f"Recorded ECG • {source_name}")
        self.ecg_status_label.setText(status)
        self.ecg_status_label.setToolTip(
            "Raw ECG samples remain unchanged. Accepted R triggers define each "
            "electrical cycle. Median P/QRS landmarks inform the synchronization "
            "review; mechanical subphases and valve events remain model estimates "
            "unless separately annotated from PCG/echo."
        )

    def _toggle_play(self):
        try:
            self.engine.toggle_playback()
        except Exception:
            pass
        self._sync_from_engine()

    def _heart_rate_changed(self, value):
        try:
            self.engine.heart_rate_spin.setValue(int(value))
            self.engine._playback_rate_changed()
        except Exception:
            pass

    def _speed_changed(self):
        speed = float(self.speed_box.currentData() or 1.0)
        try:
            combo = self.engine.playback_speed_combo
            best = min(
                range(combo.count()),
                key=lambda i: abs(float(combo.itemData(i)) - speed),
            )
            combo.setCurrentIndex(best)
        except Exception:
            pass

    def _view_changed(self, index):
        # OPL-facing names map directly to the proven OCA rendering presets.
        engine_index = max(0, min(int(index), self.engine.view_mode_combo.count() - 1))
        try:
            self.engine.view_mode_combo.setCurrentIndex(engine_index)
        except Exception:
            pass

    def _camera_changed(self, text):
        try:
            self.engine.orientation_combo.setCurrentText(str(text))
        except Exception:
            pass

    def _fit(self):
        try:
            self.engine.reset_view()
        except Exception:
            pass

    def _jump_phase(self, direction):
        try:
            self.engine._jump_relative_phase(int(direction))
        except Exception:
            pass
        self._sync_from_engine()

    def _step_ms(self, delta_ms):
        try:
            self.engine._step_time_ms(float(delta_ms))
        except Exception:
            pass
        self._sync_from_engine()

    def _timeline_changed(self, value):
        if self._syncing_slider:
            return
        try:
            self.engine._timeline_changed(int(value))
        except Exception:
            pass
        self._sync_from_engine()

    # OPL_FULL_RECORDING_TIMING_V06
    @staticmethod
    def _format_ecg_clock(seconds):
        """Format recording time as MM:SS.mmm (or H:MM:SS.mmm)."""
        try:
            total_ms = max(0, int(round(float(seconds) * 1000.0)))
        except Exception:
            return "--:--.---"

        hours, rem_ms = divmod(total_ms, 3_600_000)
        minutes, rem_ms = divmod(rem_ms, 60_000)
        secs, millis = divmod(rem_ms, 1000)

        if hours:
            return f"{hours:d}:{minutes:02d}:{secs:02d}.{millis:03d}"
        return f"{minutes:02d}:{secs:02d}.{millis:03d}"

    def _sync_from_engine(self):
        try:
            self._sync_ecg_panel_state()
            active = bool(self.engine._timer.isActive())
            self.play_btn.setText("❚❚ Pause" if active else "▶ Play")

            phase = float(getattr(self.engine, "_playback_phase", 0.0)) % 1.0
            timing = self.engine._current_timing()
            phase_record, _ = timing.phase_at_fraction(phase)

            elapsed_ms = phase * timing.cycle_ms
            durations = self.engine._sequence_durations_ms()
            beat_index = int(
                getattr(self.engine, "_playback_beat_index", 0)
            )
            beat_count = int(self.engine._beat_sequence_count())

            sequence_elapsed_ms = (
                float(sum(durations[:beat_index])) + elapsed_ms
            )
            sequence_total_ms = float(sum(durations))

            try:
                ecg_gated = bool(self.engine._ecg_gating_active())
            except Exception:
                ecg_gated = False

            beat_prefix = "ECG beat" if ecg_gated else "Beat"

            if ecg_gated:
                recording = self.engine.ecg_recording
                beat_start_s = recording.beat_start_time_s(beat_index)
                beat_end_s = beat_start_s + timing.cycle_ms / 1000.0
                cursor_s = beat_start_s + elapsed_ms / 1000.0
                recording_duration_s = float(
                    getattr(recording, "duration_s", 0.0)
                )

                self.cycle_time_label.setText(
                    f"{beat_prefix} {beat_index + 1}/{beat_count}  •  "
                    f"R {self._format_ecg_clock(beat_start_s)} → "
                    f"{self._format_ecg_clock(beat_end_s)}  •  "
                    f"RR {timing.cycle_ms:,.0f} ms  •  "
                    f"now {self._format_ecg_clock(cursor_s)}"
                )
                self.cycle_time_label.setToolTip(
                    f"All {beat_count} complete reviewed R–R cycles are in the "
                    f"playback sequence.\nCurrent recording position: "
                    f"{self._format_ecg_clock(cursor_s)} / "
                    f"{self._format_ecg_clock(recording_duration_s)}.\n"
                    "Signal before the first reviewed R peak and after the final "
                    "reviewed R peak is not a complete R–R cycle and is therefore "
                    "not assigned a full mechanical-cycle animation."
                )
            else:
                self.cycle_time_label.setText(
                    f"{beat_prefix} {beat_index + 1}/{beat_count}  •  "
                    f"{elapsed_ms:,.0f} ms/{timing.cycle_ms:,.0f} ms  •  "
                    f"total {sequence_elapsed_ms:,.0f}/"
                    f"{sequence_total_ms:,.0f} ms"
                )

            display_phase_name = phase_record.name
            if elapsed_ms <= 0.5:
                display_phase_name = "End-diastole • IVC begins"
            elif abs(elapsed_ms - timing.systole_ms) <= 0.5:
                display_phase_name = "End-systole • IVR begins"

            estimate_prefix = (
                "ECG-gated estimate" if ecg_gated else "Estimated"
            )

            phase_elapsed_ms = max(
                0.0, elapsed_ms - phase_record.start_ms
            )
            phase_duration_ms = max(
                0.0, phase_record.end_ms - phase_record.start_ms
            )

            if ecg_gated:
                phase_start_s = beat_start_s + phase_record.start_ms / 1000.0
                phase_end_s = beat_start_s + phase_record.end_ms / 1000.0
                self.cycle_phase_label.setText(
                    f"{estimate_prefix}: {display_phase_name}  •  "
                    f"phase {phase_elapsed_ms:,.0f}/{phase_duration_ms:,.0f} ms  •  "
                    f"{self._format_ecg_clock(phase_start_s)} → "
                    f"{self._format_ecg_clock(phase_end_s)}"
                )
            else:
                self.cycle_phase_label.setText(
                    f"{estimate_prefix}: {display_phase_name}  •  "
                    f"{phase * 100.0:.1f}%"
                )

            self.valve_label.setText(
                f"AV: {phase_record.av_valves}  •  "
                f"Semilunar: {phase_record.semilunar_valves}"
            )

            self.phase_ribbon.set_state(timing, phase)
            self.phase_ribbon.setToolTip(
                f"{phase_record.name}\n"
                f"{phase_record.start_ms:.0f}–"
                f"{phase_record.end_ms:.0f} ms\n"
                f"AV valves: {phase_record.av_valves} • "
                f"Semilunar valves: {phase_record.semilunar_valves}"
            )

            self.ed_marker_label.setText("ED • 0 ms")
            self.es_marker_label.setText(
                f"ES • {timing.systole_ms:,.0f} ms"
            )
            self.next_ed_marker_label.setText(
                f"next ED • {timing.cycle_ms:,.0f} ms"
            )

            # Keep ES physically aligned with the systole/diastole
            # boundary underneath the phase ribbon.
            self.timeline_markers_layout.setStretch(
                1,
                max(
                    1,
                    int(round(timing.systolic_fraction * 100.0)),
                ),
            )
            self.timeline_markers_layout.setStretch(
                3,
                max(
                    1,
                    int(round(timing.diastolic_fraction * 100.0)),
                ),
            )

            self._syncing_slider = True
            try:
                self.timeline.setValue(int(round(phase * 1000.0)))
            finally:
                self._syncing_slider = False
        except Exception:
            pass

    def set_external_theme(self, light_mode=False):
        # The panel is intentionally designed for OPL's black-opal theme.
        # Global stylesheet changes are inherited automatically.
        pass
