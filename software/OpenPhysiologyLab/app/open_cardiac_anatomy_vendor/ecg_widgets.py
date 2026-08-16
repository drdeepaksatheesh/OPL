"""Native Qt ECG canvas and review dialog.

This module deliberately does not use pyqtgraph or OpenPhysiologyLab. The ECG
strip is painted directly with QPainter, avoiding ViewBox/GraphicsItem lifecycle
failures inside the 3-D application.
"""

from __future__ import annotations

import copy
import numpy as np

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .ecg import ECGGatingRecording
from .ecg_landmarks import (
    ELECTRICAL_KINDS,
    LANDMARK_SPECS,
    MECHANICAL_KINDS,
    TEMPLATE_EDITABLE_KINDS,
)


ECG_TRACE_COLOUR = "#1CA7EC"
ECG_CURSOR_COLOUR = "#F5C542"


_SHORT_LANDMARK_NAMES = {
    "p_onset": "P on",
    "p_peak": "P peak",
    "qrs_onset": "QRS on",
    "r_peak": "R peak",
    "qrs_offset": "QRS end",
    "av_close_s1": "AV close/S1",
    "semilunar_open": "SL open",
    "semilunar_close_s2": "SL close/S2",
    "av_open": "AV open",
    "early_filling_end": "Early-fill end",
    "atrial_mechanical_onset": "Atrial contraction",
}


def beat_landmark_summary_html(
    recording: ECGGatingRecording,
    beat_index: int,
    heading: str = "accepted markers",
) -> str:
    """Return a readable, colour-keyed summary for one reviewed beat."""

    if recording is None or recording.beat_count <= 0:
        return "No reviewed beat is available."
    beat = int(np.clip(beat_index, 0, recording.beat_count - 1))
    start_s = recording.beat_start_time_s(beat)
    ordered = [*ELECTRICAL_KINDS, *MECHANICAL_KINDS]
    markers = {
        kind: recording.landmark(kind, beat)
        for kind in ordered
    }
    electrical_parts = []
    mechanical_parts = []
    for kind in ordered:
        item = markers[kind]
        if item is None:
            continue
        delta_ms = (float(recording.time_s[item.sample_index]) - start_s) * 1000.0
        colour = LANDMARK_SPECS[kind][1]
        if item.source == "manual":
            source = " <b>[manual]</b>"
        elif item.source == "template_reviewed":
            source = " <b>[reviewed template]</b>"
        elif item.source == "template_automatic":
            source = " [template]"
        else:
            source = ""
        part = (
            f'<span style="color:{colour};"><b>{_SHORT_LANDMARK_NAMES[kind]}</b> '
            f'{delta_ms:+.0f} ms{source}</span>'
        )
        if item.group == "electrical":
            electrical_parts.append(part)
        elif item.source == "manual":
            mechanical_parts.append(part)
    electrical = " &nbsp;·&nbsp; ".join(electrical_parts) or "No electrical markers"
    mechanical = (
        " &nbsp;·&nbsp; ".join(mechanical_parts)
        if mechanical_parts
        else '<span style="color:#9AA6B6;">none — mechanical phases remain estimates</span>'
    )
    return (
        f'<b style="color:#D4AF37;">Beat {beat + 1} {heading}</b><br>'
        f'{electrical}<br><b>Measured mechanical observations:</b> {mechanical}'
    )


def template_landmark_summary_html(recording: ECGGatingRecording) -> str:
    template = recording.median_template
    if template is None:
        return "No complete complexes are available for a median template."
    parts = []
    for kind in ELECTRICAL_KINDS:
        offset = template.offset(kind)
        if offset is None:
            continue
        colour = LANDMARK_SPECS[kind][1]
        reviewed = (
            " <b>[reviewed]</b>"
            if template.landmark_sources.get(kind) == "template_reviewed"
            else " [suggested]"
        )
        parts.append(
            f'<span style="color:{colour};"><b>{_SHORT_LANDMARK_NAMES[kind]}</b> '
            f'{offset * 1000.0:+.0f} ms{reviewed}</span>'
        )
    return (
        '<b style="color:#D4AF37;">Dominant R-aligned median template</b><br>'
        + " &nbsp;·&nbsp; ".join(parts)
        + '<br><span style="color:#9AA6B6;">Offsets are projected onto accepted R triggers; '
        "they are not independently measured on each beat. T is not annotated.</span>"
    )


def _visible_signal_range(time_s, signal, start_s, stop_s) -> tuple[float, float]:
    times = np.asarray(time_s, dtype=float)
    values = np.asarray(signal, dtype=float)
    visible = values[(times >= start_s) & (times <= stop_s) & np.isfinite(values)]
    if not len(visible):
        visible = values[np.isfinite(values)]
    if not len(visible):
        return -1.0, 1.0
    low, high = np.percentile(visible, [0.5, 99.5])
    span = float(high - low)
    if not np.isfinite(span) or span <= np.finfo(float).eps:
        return float(low - 1.0), float(high + 1.0)
    return float(low - 0.14 * span), float(high + 0.14 * span)


class ECGCanvas(QWidget):
    """Zoomable native ECG strip with electrical/mechanical annotation lanes."""

    cursorMoved = pyqtSignal(float)

    def __init__(self, parent=None, editable: bool = False, compact: bool = False):
        super().__init__(parent)
        self.recording: ECGGatingRecording | None = None
        self.window_start_s = 0.0
        self.window_span_s = 5.0
        self.cursor_time_s = 0.0
        self.editable = bool(editable)
        self.compact = bool(compact)
        self.show_landmarks = True
        self.landmark_filter: set[str] | None = None
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_recording(self, recording: ECGGatingRecording | None) -> None:
        self.recording = recording
        if recording is not None:
            self.cursor_time_s = recording.beat_start_time_s(0)
            self.centre_on(self.cursor_time_s)
        self.update()

    def set_cursor_time(self, time_s: float, centre: bool = False) -> None:
        if self.recording is None:
            return
        self.cursor_time_s = float(np.clip(time_s, self.recording.time_s[0], self.recording.time_s[-1]))
        if centre or not (self.window_start_s <= self.cursor_time_s <= self.window_start_s + self.window_span_s):
            self.centre_on(self.cursor_time_s)
        self.update()

    def centre_on(self, time_s: float) -> None:
        if self.recording is None:
            return
        maximum = max(float(self.recording.time_s[0]), float(self.recording.time_s[-1]) - self.window_span_s)
        self.window_start_s = float(np.clip(time_s - 0.45 * self.window_span_s, self.recording.time_s[0], maximum))
        self.update()

    def shift_window(self, delta_s: float) -> None:
        if self.recording is None:
            return
        maximum = max(float(self.recording.time_s[0]), float(self.recording.time_s[-1]) - self.window_span_s)
        self.window_start_s = float(np.clip(self.window_start_s + delta_s, self.recording.time_s[0], maximum))
        self.update()

    def frame_beats(self, beat_index: int, count: int = 1) -> None:
        """Frame one or more complete QRS cycles with room for the preceding P wave."""

        if self.recording is None or self.recording.beat_count <= 0:
            return
        count = int(np.clip(count, 1, max(1, self.recording.beat_count)))
        beat = int(np.clip(beat_index, 0, self.recording.beat_count - 1))
        first = max(0, beat - count // 2)
        last = min(self.recording.beat_count, first + count)
        first = max(0, last - count)
        boundaries = self.recording.time_s[self.recording.beat_boundary_samples]
        start_s = float(boundaries[first] - 0.22)
        stop_s = float(boundaries[last] + 0.10)
        self.window_span_s = float(np.clip(stop_s - start_s, 0.75, self.recording.duration_s))
        maximum = max(float(self.recording.time_s[0]), float(self.recording.time_s[-1]) - self.window_span_s)
        self.window_start_s = float(np.clip(start_s, self.recording.time_s[0], maximum))
        self.update()

    def frame_overview(self, span_s: float = 10.0) -> None:
        if self.recording is None:
            return
        self.window_span_s = float(np.clip(span_s, 1.0, self.recording.duration_s))
        self.centre_on(self.cursor_time_s)

    def _plot_rect(self) -> QRectF:
        return QRectF(42.0, 25.0, max(10.0, self.width() - 54.0), max(20.0, self.height() - 50.0))

    def _x(self, time_s: float, rect: QRectF) -> float:
        return rect.left() + (time_s - self.window_start_s) / self.window_span_s * rect.width()

    def _time_at_x(self, x: float, rect: QRectF) -> float:
        return self.window_start_s + (x - rect.left()) / max(rect.width(), 1.0) * self.window_span_s

    def _y(self, value: float, low: float, high: float, rect: QRectF) -> float:
        return rect.bottom() - (value - low) / max(high - low, np.finfo(float).eps) * rect.height()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#030406"))
        rect = self._plot_rect()
        painter.fillRect(rect, QColor("#05080B"))
        if self.recording is None:
            painter.setPen(QColor("#8090A0"))
            painter.drawText(rect, Qt.AlignCenter, "No recorded ECG loaded")
            return
        stop_s = self.window_start_s + self.window_span_s
        low, high = _visible_signal_range(self.recording.time_s, self.recording.filtered_signal, self.window_start_s, stop_s)
        self._draw_grid(painter, rect)
        self._draw_active_beat(painter, rect)
        self._draw_trace(painter, rect, low, high, stop_s)
        if self.show_landmarks:
            self._draw_landmarks(painter, rect, low, high, stop_s)
        self._draw_cursor(painter, rect)

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        value = np.floor(self.window_start_s / 0.04) * 0.04
        label_stride = max(1, int(np.ceil(65.0 / max(1.0, rect.width() * 0.20 / self.window_span_s))))
        major_index = int(round(value / 0.20))
        while value <= self.window_start_s + self.window_span_s + 1e-9:
            major = abs(value / 0.20 - round(value / 0.20)) < 1e-5
            painter.setPen(QPen(QColor(55, 47, 30, 125 if major else 55), 1))
            x = self._x(float(value), rect)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            if major and major_index % label_stride == 0:
                painter.setPen(QColor("#738092"))
                painter.drawText(QRectF(x - 25, rect.bottom() + 2, 50, 14), Qt.AlignHCenter, f"{value:.1f}")
            if major:
                major_index += 1
            value += 0.04
        for row in range(1, 10):
            painter.setPen(QPen(QColor(55, 47, 30, 105 if row == 5 else 45), 1))
            y = rect.top() + row / 10.0 * rect.height()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#28313C"), 1))
        painter.drawRect(rect)

    def _draw_active_beat(self, painter: QPainter, rect: QRectF) -> None:
        boundaries = self.recording.time_s[self.recording.beat_boundary_samples]
        beat = int(np.searchsorted(boundaries, self.cursor_time_s, side="right") - 1)
        beat = int(np.clip(beat, 0, max(0, self.recording.beat_count - 1)))
        x1, x2 = self._x(float(boundaries[beat]), rect), self._x(float(boundaries[beat + 1]), rect)
        painter.fillRect(QRectF(x1, rect.top(), x2 - x1, rect.height()), QColor(212, 175, 55, 20))

    def _draw_trace(self, painter: QPainter, rect: QRectF, low: float, high: float, stop_s: float) -> None:
        mask = (self.recording.time_s >= self.window_start_s) & (self.recording.time_s <= stop_s)
        times, values = self.recording.time_s[mask], self.recording.filtered_signal[mask]
        if not len(times):
            return
        painter.setPen(QPen(QColor(ECG_TRACE_COLOUR), 1.35))
        width_px = max(1, int(rect.width()))
        if len(times) <= 3 * width_px:
            path = QPainterPath()
            path.moveTo(self._x(float(times[0]), rect), self._y(float(values[0]), low, high, rect))
            for time_value, signal_value in zip(times[1:], values[1:]):
                path.lineTo(self._x(float(time_value), rect), self._y(float(signal_value), low, high, rect))
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.drawPath(path)
            painter.setRenderHint(QPainter.Antialiasing, False)
            return
        columns = np.clip(((times - self.window_start_s) / self.window_span_s * width_px).astype(int), 0, width_px - 1)
        unique, starts = np.unique(columns, return_index=True)
        ends = np.r_[starts[1:], len(values)]
        for column, start, end in zip(unique, starts, ends):
            segment = values[start:end]
            x = rect.left() + float(column)
            painter.drawLine(QPointF(x, self._y(float(np.min(segment)), low, high, rect)), QPointF(x, self._y(float(np.max(segment)), low, high, rect)))

    def _draw_landmarks(self, painter: QPainter, rect: QRectF, low: float, high: float, stop_s: float) -> None:
        # A point-sized font inside a fixed 10 px rectangle was clipped on
        # high-DPI Windows displays.  Use a predictable pixel size and the
        # actual font metrics so every marker label has enough vertical room.
        label_font = QFont("Segoe UI")
        label_font.setPixelSize(10 if self.compact else 12)
        painter.setFont(label_font)
        metrics = painter.fontMetrics()
        label_height = float(metrics.height() + 4)
        boundaries = self.recording.time_s[self.recording.beat_boundary_samples]
        active_beat = int(np.searchsorted(boundaries, self.cursor_time_s, side="right") - 1)
        active_beat = int(np.clip(active_beat, 0, max(0, self.recording.beat_count - 1)))
        for item in self.recording.landmarks:
            if self.landmark_filter is not None and item.kind not in self.landmark_filter:
                continue
            if self.compact and item.group == "electrical" and item.kind not in {
                "p_peak", "qrs_onset", "r_peak", "qrs_offset"
            }:
                continue
            time_value = float(self.recording.time_s[item.sample_index])
            if not self.window_start_s <= time_value <= stop_s:
                continue
            label, colour, group = LANDMARK_SPECS[item.kind]
            x = self._x(time_value, rect)
            pen = QPen(QColor(colour), 1.1)
            if group == "mechanical":
                pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            if group == "electrical":
                y = self._y(float(self.recording.filtered_signal[item.sample_index]), low, high, rect)
                painter.drawLine(QPointF(x, rect.top() + 14), QPointF(x, y - 3))
                painter.setBrush(QColor(colour))
                painter.drawEllipse(QPointF(x, y), 3.2, 3.2)
            else:
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            if item.beat_index != active_beat:
                continue
            painter.setPen(QColor(colour))
            short = label.replace(" onset", " on").replace("Semilunar", "SL")
            electrical_offsets = {
                "p_onset": (-50, 0),
                "p_peak": (-32, 11),
                "qrs_onset": (-56, 22),
                "r_peak": (4, 33),
                "qrs_offset": (4, 44),
            }
            if group == "electrical":
                offset_x, _offset_y = electrical_offsets.get(item.kind, (4, 0))
                if self.compact:
                    lane_index = {
                        "p_peak": 0,
                        "qrs_onset": 1,
                        "r_peak": 2,
                        "qrs_offset": 3,
                    }.get(item.kind, 0)
                else:
                    lane_index = {
                        "p_onset": 0,
                        "p_peak": 1,
                        "qrs_onset": 2,
                        "r_peak": 3,
                        "qrs_offset": 4,
                    }.get(item.kind, 0)
                label_top = rect.top() + 3.0 + lane_index * label_height
            else:
                offset_x = 4
                lane_index = MECHANICAL_KINDS.index(item.kind) % 2
                label_top = rect.bottom() - 4.0 - (lane_index + 1) * label_height
            text_width = float(np.clip(metrics.horizontalAdvance(short) + 10, 55, 128))
            text_x = float(np.clip(x + offset_x, rect.left() + 2, rect.right() - text_width - 2))
            label_rect = QRectF(text_x, label_top, text_width, label_height)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(3, 6, 9, 205))
            painter.drawRoundedRect(label_rect, 2.0, 2.0)
            painter.setPen(QColor(colour))
            painter.drawText(
                label_rect.adjusted(4.0, 0.0, -2.0, 0.0),
                Qt.AlignLeft | Qt.AlignVCenter,
                short,
            )

    def _draw_cursor(self, painter: QPainter, rect: QRectF) -> None:
        if not self.window_start_s <= self.cursor_time_s <= self.window_start_s + self.window_span_s:
            return
        x = self._x(self.cursor_time_s, rect)
        painter.setPen(QPen(QColor(ECG_CURSOR_COLOUR), 1.5))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        painter.setBrush(QColor(ECG_CURSOR_COLOUR))
        painter.drawPolygon(QPolygonF([QPointF(x, rect.top()), QPointF(x - 4, rect.top() - 7), QPointF(x + 4, rect.top() - 7)]))

    def mousePressEvent(self, event) -> None:
        if self.recording is None or event.button() != Qt.LeftButton:
            return
        rect = self._plot_rect()
        self.cursor_time_s = float(np.clip(self._time_at_x(event.x(), rect), self.recording.time_s[0], self.recording.time_s[-1]))
        self.cursorMoved.emit(self.cursor_time_s)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.editable and event.buttons() & Qt.LeftButton:
            rect = self._plot_rect()
            self.cursor_time_s = float(np.clip(self._time_at_x(event.x(), rect), self.recording.time_s[0], self.recording.time_s[-1]))
            self.cursorMoved.emit(self.cursor_time_s)
            self.update()

    def wheelEvent(self, event) -> None:
        if self.recording is None:
            return
        old_span = self.window_span_s
        factor = 0.80 if event.angleDelta().y() > 0 else 1.25
        self.window_span_s = float(np.clip(old_span * factor, 1.0, min(30.0, self.recording.duration_s)))
        anchor = self._time_at_x(event.x(), self._plot_rect())
        ratio = (anchor - self.window_start_s) / max(old_span, 1e-9)
        self.window_start_s = anchor - ratio * self.window_span_s
        self.shift_window(0.0)


class ECGMedianTemplateCanvas(QWidget):
    """Editable median P/QRS template with an interquartile morphology band."""

    cursorMoved = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recording: ECGGatingRecording | None = None
        self.cursor_offset_s = 0.0
        self.setMinimumHeight(390)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_recording(self, recording: ECGGatingRecording | None) -> None:
        self.recording = recording
        self.cursor_offset_s = 0.0
        self.update()

    def set_cursor_offset(self, offset_s: float) -> None:
        template = None if self.recording is None else self.recording.median_template
        if template is None:
            return
        self.cursor_offset_s = float(
            np.clip(offset_s, template.offsets_s[0], template.offsets_s[-1])
        )
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(46.0, 26.0, max(10.0, self.width() - 58.0), max(20.0, self.height() - 54.0))

    def _x(self, offset_s: float, rect: QRectF) -> float:
        template = self.recording.median_template
        start, stop = float(template.offsets_s[0]), float(template.offsets_s[-1])
        return rect.left() + (float(offset_s) - start) / max(stop - start, 1e-9) * rect.width()

    def _offset_at_x(self, x: float, rect: QRectF) -> float:
        template = self.recording.median_template
        start, stop = float(template.offsets_s[0]), float(template.offsets_s[-1])
        return start + (x - rect.left()) / max(rect.width(), 1.0) * (stop - start)

    @staticmethod
    def _y(value: float, low: float, high: float, rect: QRectF) -> float:
        return rect.bottom() - (float(value) - low) / max(high - low, 1e-9) * rect.height()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#030406"))
        rect = self._plot_rect()
        painter.fillRect(rect, QColor("#05080B"))
        template = None if self.recording is None else self.recording.median_template
        if template is None:
            painter.setPen(QColor("#8090A0"))
            painter.drawText(rect, Qt.AlignCenter, "No complete complexes for a median template")
            return
        values = np.r_[template.lower_signal, template.upper_signal]
        low, high = np.percentile(values[np.isfinite(values)], [0.5, 99.5])
        span = max(float(high - low), np.finfo(float).eps)
        low, high = float(low - 0.16 * span), float(high + 0.16 * span)
        self._draw_grid(painter, rect)

        lower_points = [
            QPointF(self._x(offset, rect), self._y(value, low, high, rect))
            for offset, value in zip(template.offsets_s, template.lower_signal)
        ]
        upper_points = [
            QPointF(self._x(offset, rect), self._y(value, low, high, rect))
            for offset, value in zip(template.offsets_s[::-1], template.upper_signal[::-1])
        ]
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 167, 236, 50))
        painter.drawPolygon(QPolygonF(lower_points + upper_points))

        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(ECG_TRACE_COLOUR), 2.0))
        path = QPainterPath()
        path.moveTo(
            self._x(float(template.offsets_s[0]), rect),
            self._y(float(template.median_signal[0]), low, high, rect),
        )
        for offset, value in zip(template.offsets_s[1:], template.median_signal[1:]):
            path.lineTo(self._x(float(offset), rect), self._y(float(value), low, high, rect))
        painter.drawPath(path)
        painter.setRenderHint(QPainter.Antialiasing, False)
        self._draw_markers(painter, rect, low, high)

        cursor_x = self._x(self.cursor_offset_s, rect)
        painter.setPen(QPen(QColor(ECG_CURSOR_COLOUR), 1.5))
        painter.drawLine(QPointF(cursor_x, rect.top()), QPointF(cursor_x, rect.bottom()))
        painter.setBrush(QColor(ECG_CURSOR_COLOUR))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(cursor_x, rect.top()),
                    QPointF(cursor_x - 4, rect.top() - 7),
                    QPointF(cursor_x + 4, rect.top() - 7),
                ]
            )
        )

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        template = self.recording.median_template
        start, stop = float(template.offsets_s[0]), float(template.offsets_s[-1])
        tick = np.ceil(start / 0.04) * 0.04
        while tick <= stop + 1e-9:
            major = abs(tick / 0.20 - round(tick / 0.20)) < 1e-5
            painter.setPen(QPen(QColor(55, 47, 30, 125 if major else 55), 1))
            x = self._x(float(tick), rect)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            if major:
                painter.setPen(QColor("#738092"))
                painter.drawText(
                    QRectF(x - 35, rect.bottom() + 2, 70, 16),
                    Qt.AlignHCenter,
                    f"{tick * 1000.0:+.0f} ms",
                )
            tick += 0.04
        for row in range(1, 8):
            painter.setPen(QPen(QColor(55, 47, 30, 45), 1))
            y = rect.top() + row / 8.0 * rect.height()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#28313C"), 1))
        painter.drawRect(rect)

    def _draw_markers(self, painter: QPainter, rect: QRectF, low: float, high: float) -> None:
        template = self.recording.median_template
        label_font = QFont("Segoe UI")
        label_font.setPixelSize(12)
        painter.setFont(label_font)
        metrics = painter.fontMetrics()
        lane = {
            "p_onset": 0,
            "p_peak": 1,
            "qrs_onset": 2,
            "r_peak": 3,
            "qrs_offset": 4,
        }
        for kind in ELECTRICAL_KINDS:
            offset = template.offset(kind)
            if offset is None:
                continue
            colour = LANDMARK_SPECS[kind][1]
            x = self._x(offset, rect)
            index = int(np.argmin(np.abs(template.offsets_s - offset)))
            y = self._y(float(template.median_signal[index]), low, high, rect)
            painter.setPen(QPen(QColor(colour), 1.15))
            painter.drawLine(QPointF(x, rect.top() + 16), QPointF(x, y - 3))
            painter.setBrush(QColor(colour))
            painter.drawEllipse(QPointF(x, y), 3.5, 3.5)
            reviewed = template.landmark_sources.get(kind) == "template_reviewed"
            short = _SHORT_LANDMARK_NAMES[kind] + (" ✓" if reviewed else "")
            width = float(np.clip(metrics.horizontalAdvance(short) + 12, 58, 130))
            label_x = float(np.clip(x + 5, rect.left() + 2, rect.right() - width - 2))
            label_y = rect.top() + 3 + lane.get(kind, 0) * float(metrics.height() + 4)
            box = QRectF(label_x, label_y, width, float(metrics.height() + 4))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(3, 6, 9, 215))
            painter.drawRoundedRect(box, 2.0, 2.0)
            painter.setPen(QColor(colour))
            painter.drawText(box.adjusted(4, 0, -2, 0), Qt.AlignLeft | Qt.AlignVCenter, short)

    def mousePressEvent(self, event) -> None:
        if self.recording is None or self.recording.median_template is None:
            return
        if event.button() != Qt.LeftButton:
            return
        self.set_cursor_offset(self._offset_at_x(event.x(), self._plot_rect()))
        self.cursorMoved.emit(self.cursor_offset_s)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            if self.recording is None or self.recording.median_template is None:
                return
            self.set_cursor_offset(self._offset_at_x(event.x(), self._plot_rect()))
            self.cursorMoved.emit(self.cursor_offset_s)


class ECGTraceWidget(QWidget):
    """Compact synchronized ECG canvas used by the main viewer."""

    timeSelected = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.recording: ECGGatingRecording | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.canvas = ECGCanvas(editable=False, compact=True)
        self.canvas.window_span_s = 2.6
        self.canvas.cursorMoved.connect(self.timeSelected.emit)
        self.canvas.setMinimumHeight(180)
        self.canvas.setMaximumHeight(220)
        layout.addWidget(self.canvas)
        self.marker_summary = QLabel()
        self.marker_summary.setWordWrap(True)
        self.marker_summary.setTextFormat(Qt.RichText)
        self.marker_summary.setStyleSheet(
            "background:#080C11; border:1px solid #202A35; padding:4px; color:#C7D0DC;"
        )
        layout.addWidget(self.marker_summary)
        self._summary_beat = None
        self.setMinimumHeight(245)

    def set_recording(self, recording: ECGGatingRecording | None) -> None:
        self.recording = recording
        self.canvas.set_recording(recording)
        self.setVisible(recording is not None)
        self._update_summary(force=True)

    def refresh_markers(self) -> None:
        self.canvas.update()
        self._update_summary(force=True)

    def set_cursor_time(self, time_s: float, force_window: bool = False) -> None:
        self.canvas.set_cursor_time(time_s, centre=force_window)
        self._update_summary()

    def _update_summary(self, force: bool = False) -> None:
        if self.recording is None:
            self.marker_summary.clear()
            self._summary_beat = None
            return
        beat = self.recording.beat_index_at_time(self.canvas.cursor_time_s)
        if force or beat != self._summary_beat:
            self.marker_summary.setText(beat_landmark_summary_html(self.recording, beat))
            self._summary_beat = beat


class ECGPeakReviewDialog(QDialog):
    """Review one median P/QRS template, R triggers and mechanical marks."""

    def __init__(self, recording: ECGGatingRecording, parent=None):
        super().__init__(parent)
        self.recording = recording
        self._original_peaks = recording.r_peaks.copy()
        self._original_landmarks = copy.deepcopy(recording.landmarks)
        self._original_template = copy.deepcopy(recording.median_template)
        # Start away from the clipped left edge when a second beat is available.
        self._cursor_time = recording.beat_start_time_s(1 if recording.beat_count > 1 else 0)
        self.setWindowTitle("Review ECG landmarks and synchronization")
        self.setMinimumSize(1100, 700)
        self.resize(1500, 900)
        self._view_beat_count: int | None = None
        self._mode = "template"
        layout = QVBoxLayout(self)
        title = QLabel(
            "Review P and QRS once on the dominant R-aligned median template. The shaded band is "
            "the interquartile beat-to-beat spread. Accepted offsets are projected onto each R "
            "trigger; T is not annotated. Mechanical observations may still be added separately "
            "from PCG/echo. The raw ECG is never rewritten."
        )
        title.setWordWrap(True)
        layout.addWidget(title)
        self.canvas_stack = QStackedWidget()
        self.template_canvas = ECGMedianTemplateCanvas()
        self.template_canvas.set_recording(recording)
        self.template_canvas.cursorMoved.connect(self._template_cursor_moved)
        self.canvas = ECGCanvas(editable=True)
        self.canvas.setMinimumHeight(390)
        self.canvas.set_recording(recording)
        self.canvas.set_cursor_time(self._cursor_time, centre=True)
        self.canvas.frame_beats(recording.beat_index_at_time(self._cursor_time), 3)
        self.canvas.landmark_filter = {"r_peak", *MECHANICAL_KINDS}
        self.canvas.cursorMoved.connect(self._cursor_moved)
        self.canvas_stack.addWidget(self.template_canvas)
        self.canvas_stack.addWidget(self.canvas)
        self.canvas_stack.setCurrentWidget(self.template_canvas)
        layout.addWidget(self.canvas_stack, 1)

        self.active_markers = QLabel()
        self.active_markers.setWordWrap(True)
        self.active_markers.setTextFormat(Qt.RichText)
        self.active_markers.setStyleSheet(
            "background:#080C11; border:1px solid #202A35; padding:6px; color:#C7D0DC;"
        )
        layout.addWidget(self.active_markers)

        navigation = QHBoxLayout()
        for label, action in (
            ("Median P–QRS template", self._set_template_view),
            ("◀ Beat", lambda: self._move_beat(-1)),
            ("Beat ▶", lambda: self._move_beat(1)),
            ("3-beat timing strip", lambda: self._set_beat_view(3)),
            ("10 s R review", self._set_overview),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            navigation.addWidget(button)
        navigation.addStretch(1)
        layout.addLayout(navigation)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Annotation type"))
        self.kind_combo = QComboBox()
        self._populate_kind_combo()
        controls.addWidget(self.kind_combo, 1)
        for label, action in (
            ("Set / move at cursor", self._set_marker),
            ("Reset / delete selected", self._delete_marker),
        ):
            button = QPushButton(label)
            button.clicked.connect(action)
            controls.addWidget(button)
        layout.addLayout(controls)

        file_controls = QHBoxLayout()
        redetect = QPushButton("Rebuild median template")
        redetect.clicked.connect(self._redetect)
        self.add_r_button = QPushButton("Add R beat")
        self.add_r_button.clicked.connect(self._add_r)
        self.remove_r_button = QPushButton("Remove nearest R beat")
        self.remove_r_button.clicked.connect(self._remove_r)
        save_sidecar = QPushButton("Save annotations…")
        save_sidecar.clicked.connect(self._save_sidecar)
        load_sidecar = QPushButton("Load annotations…")
        load_sidecar.clicked.connect(self._load_sidecar)
        file_controls.addWidget(redetect)
        file_controls.addWidget(self.add_r_button)
        file_controls.addWidget(self.remove_r_button)
        file_controls.addStretch(1)
        file_controls.addWidget(load_sidecar)
        file_controls.addWidget(save_sidecar)
        layout.addLayout(file_controls)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Use template + reviewed R triggers")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_mode_controls()
        self._refresh()

    def exec_(self) -> int:
        # Landmark review is visual work; do not open it as a cramped child dialog.
        self.showMaximized()
        return super().exec_()

    def reject(self) -> None:
        self.recording.r_peaks = self._original_peaks.copy()
        self.recording.landmarks = copy.deepcopy(self._original_landmarks)
        self.recording.median_template = copy.deepcopy(self._original_template)
        super().reject()

    def _populate_kind_combo(self) -> None:
        self.kind_combo.clear()
        if self._mode == "template":
            for kind in TEMPLATE_EDITABLE_KINDS:
                self.kind_combo.addItem(f"Template: {LANDMARK_SPECS[kind][0]}", kind)
        else:
            for kind in MECHANICAL_KINDS:
                self.kind_combo.addItem(f"Mechanical observation: {LANDMARK_SPECS[kind][0]}", kind)

    def _update_mode_controls(self) -> None:
        rhythm_mode = self._mode == "rhythm"
        self.add_r_button.setEnabled(rhythm_mode)
        self.remove_r_button.setEnabled(rhythm_mode)

    def _set_template_view(self) -> None:
        self._mode = "template"
        self.canvas_stack.setCurrentWidget(self.template_canvas)
        self._populate_kind_combo()
        self._update_mode_controls()
        self._refresh()

    def _template_cursor_moved(self, offset_s: float) -> None:
        self.template_canvas.cursor_offset_s = float(offset_s)
        self._refresh()

    def _cursor_moved(self, time_s: float) -> None:
        self._cursor_time = float(time_s)
        self._refresh()

    def _move_beat(self, delta: int) -> None:
        if self._mode != "rhythm":
            self._set_beat_view(3)
        beat = self.recording.beat_index_at_time(self._cursor_time)
        beat = int(np.clip(beat + delta, 0, max(0, self.recording.beat_count - 1)))
        self._cursor_time = self.recording.beat_start_time_s(beat) + min(
            0.08, self.recording.beat_duration_ms(beat) / 4000.0
        )
        self.canvas.set_cursor_time(self._cursor_time, centre=False)
        if self._view_beat_count is None:
            self.canvas.frame_overview(10.0)
        else:
            self.canvas.frame_beats(beat, self._view_beat_count)
        self._refresh()

    def _set_beat_view(self, count: int) -> None:
        self._mode = "rhythm"
        self._view_beat_count = int(count)
        beat = self.recording.beat_index_at_time(self._cursor_time)
        self.canvas.frame_beats(beat, self._view_beat_count)
        self.canvas_stack.setCurrentWidget(self.canvas)
        self._populate_kind_combo()
        self._update_mode_controls()
        self._refresh()

    def _set_overview(self) -> None:
        self._mode = "rhythm"
        self._view_beat_count = None
        self.canvas.frame_overview(10.0)
        self.canvas_stack.setCurrentWidget(self.canvas)
        self._populate_kind_combo()
        self._update_mode_controls()
        self._refresh()

    def _set_marker(self) -> None:
        try:
            kind = str(self.kind_combo.currentData())
            if self._mode == "template":
                self.recording.set_template_landmark_offset(
                    kind, self.template_canvas.cursor_offset_s
                )
            else:
                self.recording.set_landmark_at_time(kind, self._cursor_time)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not set annotation", str(exc))

    def _delete_marker(self) -> None:
        try:
            kind = str(self.kind_combo.currentData())
            if self._mode == "template":
                self.recording.reset_template_landmark(kind)
            else:
                self.recording.remove_landmark_near_time(self._cursor_time, kind)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not delete annotation", str(exc))

    def _add_r(self) -> None:
        try:
            peak = self.recording.add_peak_at_time(self._cursor_time)
            self._cursor_time = float(self.recording.time_s[peak])
            self.canvas.set_cursor_time(self._cursor_time)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not add R beat", str(exc))

    def _remove_r(self) -> None:
        try:
            self.recording.remove_peak_near_time(self._cursor_time)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not remove R beat", str(exc))

    def _redetect(self) -> None:
        self.recording.redetect_landmarks(preserve_manual=True)
        self.template_canvas.set_recording(self.recording)
        self._refresh()

    def _save_sidecar(self) -> None:
        suggested = str(self.recording.source_path.with_suffix(".ecg_annotations.json"))
        path, _ = QFileDialog.getSaveFileName(self, "Save ECG annotations", suggested, "JSON (*.json)")
        if not path:
            return
        try:
            self.recording.save_annotations(path)
        except Exception as exc:
            QMessageBox.warning(self, "Could not save annotations", str(exc))

    def _load_sidecar(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load ECG annotations", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.recording.load_annotations(path)
            self.template_canvas.set_recording(self.recording)
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Could not load annotations", str(exc))

    def _refresh(self) -> None:
        rr = self.recording.rr_s
        template = self.recording.median_template
        electrical = 0 if template is None else len(template.landmark_offsets_s)
        mechanical = sum(
            item.group == "mechanical" and item.source == "manual"
            for item in self.recording.landmarks
        )
        beat = self.recording.beat_index_at_time(self._cursor_time) + 1
        if self._mode == "template":
            self.active_markers.setText(template_landmark_summary_html(self.recording))
        else:
            self.active_markers.setText(
                beat_landmark_summary_html(self.recording, beat - 1, "projected markers")
            )
        included = 0 if template is None else len(template.included_beat_indices)
        excluded = 0 if template is None else len(template.excluded_beat_indices)
        cursor_text = (
            f"template cursor {self.template_canvas.cursor_offset_s * 1000.0:+.0f} ms"
            if self._mode == "template"
            else f"cursor {self._cursor_time:.3f} s • beat {beat}/{self.recording.beat_count}"
        )
        self.summary.setText(
            f"{cursor_text} • {len(self.recording.r_peaks)} accepted R triggers • "
            f"median template {included} included / {excluded} morphology outliers • "
            f"{electrical} template offsets • "
            f"{mechanical} manual mechanical observations • mean {self.recording.mean_heart_rate_bpm:.1f} bpm • "
            f"cycle {np.min(rr) * 1000.0:.0f}–{np.max(rr) * 1000.0:.0f} ms. "
            "T is not delineated; valve timings remain estimates unless a dashed manual mechanical marker is present."
        )
        self.canvas.update()
        self.template_canvas.update()
