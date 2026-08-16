"""Interactive standalone 4D cardiac anatomy viewer."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PyQt5.QtCore import QElapsedTimer, QRectF, QSettings, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap, QQuaternion, QVector3D
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .core import (
    ANATOMY,
    CHAMBERS,
    CardiacCineStudy,
    MissingImagingDependency,
    parse_anatomy_mapping,
)
from .atlas import OpenHeartAtlasStudy
from .ecg import ECGGatingRecording
from .ecg_sync import ecg_informed_cycle_timing
from .ecg_widgets import ECGPeakReviewDialog, ECGTraceWidget
from .timing import (
    MAX_SUPPORTED_HEART_RATE,
    MIN_SUPPORTED_HEART_RATE,
    TIMING_MODEL_DOIS,
    TIMING_MODEL_NAME,
    healthy_adult_cycle_timing,
    motion_phase_from_timing,
    motion_phase_from_time_phase,
    time_phase_from_timing,
    time_phase_from_motion_phase,
    valve_open_fraction,
    valve_state_summary,
)

try:
    import pyqtgraph
    import pyqtgraph.opengl as gl
    from pyqtgraph.opengl import shaders as gl_shaders
    from pyqtgraph.opengl.items.GLMeshItem import DirtyFlag as MeshDirtyFlag
    from OpenGL import GL
except Exception:
    pyqtgraph = None
    gl = None
    gl_shaders = None
    MeshDirtyFlag = None
    GL = None

try:
    import imageio.v2 as imageio
except Exception:
    imageio = None


ATLAS_CAMERA_EULER = {
    # Calibrated against the visually confirmed anterior view of the bundled
    # atlas: upright apex and anterior interventricular vessels, pulmonary
    # trunk superiorly, and aortic arch behind.
    "Anterior": (30.0, -45.0),
    "Posterior": (30.0, 135.0),
    "Left lateral": (30.0, 45.0),
    "Right lateral": (30.0, -135.0),
    "Superior": (90.0, -45.0),
    "Inferior": (-90.0, -45.0),
}
OPENING_ROTATION_SETTING = "atlas/opening_rotation_wxyz"
DEFAULT_HEART_RATE_BPM = 72
CAMERA_HEADLIGHT_SHADER = "cameraHeadlight"
CAMERA_DEPTH_GLASS_SHADER = "cameraDepthGlass"


def _register_camera_headlight_shader() -> str:
    """Register a camera-centred light for pyqtgraph 0.13 and 0.14.

    Pyqtgraph's built-in ``shaded`` light is camera-relative but offset toward
    the lower-right of the viewport.  This shader places the principal light
    on the viewing axis, keeps a modest ambient term, and uses two-sided
    normals so mixed-winding open-data meshes remain legible.
    """

    if gl_shaders is None or pyqtgraph is None:
        return "shaded"
    if CAMERA_HEADLIGHT_SHADER in gl_shaders.ShaderProgram.names:
        return CAMERA_HEADLIGHT_SHADER
    modern_shader_api = tuple(
        int(part) for part in pyqtgraph.__version__.split(".")[:2]
    ) >= (0, 14)
    if modern_shader_api:
        vertex_source = """
            uniform mat4 u_mvp;
            uniform mat3 u_normal;
            attribute vec4 a_position;
            attribute vec3 a_normal;
            attribute vec4 a_color;
            varying vec4 v_color;
            varying vec3 v_normal;
            void main() {
                v_normal = normalize(u_normal * a_normal);
                v_color = a_color;
                gl_Position = u_mvp * a_position;
            }
        """
        fragment_source = """
            #ifdef GL_ES
            precision mediump float;
            #endif
            varying vec4 v_color;
            varying vec3 v_normal;
            void main() {
                float facing = abs(normalize(v_normal).z);
                float diffuse = 0.34 + 0.66 * pow(facing, 0.70);
                float rim = 0.05 * pow(1.0 - facing, 2.0);
                vec3 rgb = min(v_color.rgb * diffuse + vec3(rim), vec3(1.0));
                gl_FragColor = vec4(rgb, v_color.a);
            }
        """
    else:
        vertex_source = """
            varying vec3 normal;
            void main() {
                normal = normalize(gl_NormalMatrix * gl_Normal);
                gl_FrontColor = gl_Color;
                gl_BackColor = gl_Color;
                gl_Position = ftransform();
            }
        """
        fragment_source = """
            varying vec3 normal;
            void main() {
                float facing = abs(normalize(normal).z);
                float diffuse = 0.34 + 0.66 * pow(facing, 0.70);
                float rim = 0.05 * pow(1.0 - facing, 2.0);
                vec4 color = gl_Color;
                color.rgb = min(color.rgb * diffuse + vec3(rim), vec3(1.0));
                gl_FragColor = color;
            }
        """
    gl_shaders.ShaderProgram(
        CAMERA_HEADLIGHT_SHADER,
        [
            gl_shaders.VertexShader(vertex_source),
            gl_shaders.FragmentShader(fragment_source),
        ],
    )
    return CAMERA_HEADLIGHT_SHADER


MESH_SHADER = _register_camera_headlight_shader()


def _register_camera_depth_glass_shader() -> str:
    """Register a two-sided translucent shader with an explicit depth cue.

    The normal transparent blend makes a closed chamber look like evenly
    coloured stained glass: its near and far walls contribute almost equally.
    This shader keeps the shell transparent but makes the camera-facing outer
    wall brighter and more present, while rear-facing wall fragments are
    quieter and less opaque. The result is a readable front-to-back order
    without hiding the anatomy inside the shell.
    """

    if gl_shaders is None or pyqtgraph is None:
        return "shaded"
    if CAMERA_DEPTH_GLASS_SHADER in gl_shaders.ShaderProgram.names:
        return CAMERA_DEPTH_GLASS_SHADER
    modern_shader_api = tuple(
        int(part) for part in pyqtgraph.__version__.split(".")[:2]
    ) >= (0, 14)
    if modern_shader_api:
        vertex_source = """
            uniform mat4 u_mvp;
            uniform mat3 u_normal;
            attribute vec4 a_position;
            attribute vec3 a_normal;
            attribute vec4 a_color;
            varying vec4 v_color;
            varying vec3 v_normal;
            void main() {
                v_normal = normalize(u_normal * a_normal);
                v_color = a_color;
                gl_Position = u_mvp * a_position;
            }
        """
        fragment_source = """
            #ifdef GL_ES
            precision mediump float;
            #endif
            varying vec4 v_color;
            varying vec3 v_normal;
            void main() {
                float facing = abs(normalize(v_normal).z);
                float front = gl_FrontFacing ? 1.0 : 0.0;
                float near_light = 0.46 + 0.54 * pow(facing, 0.72);
                float rear_light = 0.18 + 0.24 * pow(facing, 0.85);
                float rim = mix(0.025, 0.115, front)
                    * pow(1.0 - facing, 1.55);
                float luminance = dot(v_color.rgb, vec3(0.299, 0.587, 0.114));
                vec3 rear_colour = mix(
                    v_color.rgb,
                    vec3(luminance * 0.72),
                    0.42
                );
                vec3 rgb = mix(
                    rear_colour * rear_light,
                    v_color.rgb * near_light,
                    front
                ) + vec3(rim);
                float alpha_scale = mix(0.24, 0.86, front);
                gl_FragColor = vec4(
                    min(rgb, vec3(1.0)),
                    clamp(v_color.a * alpha_scale, 0.012, 0.95)
                );
            }
        """
    else:
        vertex_source = """
            varying vec3 normal;
            void main() {
                normal = normalize(gl_NormalMatrix * gl_Normal);
                gl_FrontColor = gl_Color;
                gl_BackColor = gl_Color;
                gl_Position = ftransform();
            }
        """
        fragment_source = """
            varying vec3 normal;
            void main() {
                float facing = abs(normalize(normal).z);
                float front = gl_FrontFacing ? 1.0 : 0.0;
                float near_light = 0.46 + 0.54 * pow(facing, 0.72);
                float rear_light = 0.18 + 0.24 * pow(facing, 0.85);
                float rim = mix(0.025, 0.115, front)
                    * pow(1.0 - facing, 1.55);
                vec4 color = gl_Color;
                float luminance = dot(color.rgb, vec3(0.299, 0.587, 0.114));
                vec3 rear_colour = mix(
                    color.rgb,
                    vec3(luminance * 0.72),
                    0.42
                );
                color.rgb = mix(
                    rear_colour * rear_light,
                    color.rgb * near_light,
                    front
                ) + vec3(rim);
                color.rgb = min(color.rgb, vec3(1.0));
                color.a = clamp(color.a * mix(0.24, 0.86, front), 0.012, 0.95);
                gl_FragColor = color;
            }
        """
    gl_shaders.ShaderProgram(
        CAMERA_DEPTH_GLASS_SHADER,
        [
            gl_shaders.VertexShader(vertex_source),
            gl_shaders.FragmentShader(fragment_source),
        ],
    )
    return CAMERA_DEPTH_GLASS_SHADER


DEPTH_GLASS_SHADER = _register_camera_depth_glass_shader()


def atlas_camera_rotation(name: str) -> QQuaternion:
    """Return a quaternion with the same rendered matrix as legacy GL angles."""

    elevation, azimuth = ATLAS_CAMERA_EULER[str(name)]
    elevation_rotation = QQuaternion.fromAxisAndAngle(
        QVector3D(1.0, 0.0, 0.0), elevation - 90.0
    )
    azimuth_rotation = QQuaternion.fromAxisAndAngle(
        QVector3D(0.0, 0.0, -1.0), azimuth + 90.0
    )
    return elevation_rotation * azimuth_rotation


if gl is not None:
    class AnatomicalGLViewWidget(gl.GLViewWidget):
        """Two-button camera navigation with explicit interaction signals."""

        cameraInteracted = pyqtSignal()
        fitRequested = pyqtSignal()

        def __init__(self, *args, **kwargs):
            # GLViewWidget.reset() creates either Euler keys or the quaternion
            # key according to rotationMethod. Changing opts after construction
            # leaves the widget without opts["rotation"], and an early Windows
            # paint event then fails before the atlas preset can repair it.
            kwargs.pop("rotationMethod", None)
            super().__init__(*args, rotationMethod="quaternion", **kwargs)

        def mouseMoveEvent(self, event):
            position = (
                event.position() if hasattr(event, "position") else event.localPos()
            )
            if not hasattr(self, "mousePos"):
                self.mousePos = position
            difference = position - self.mousePos
            self.mousePos = position
            buttons = event.buttons()
            if buttons & Qt.LeftButton:
                self.orbit(-difference.x(), difference.y())
                self.cameraInteracted.emit()
                event.accept()
                return
            if buttons & (Qt.RightButton | Qt.MiddleButton):
                self.pan(
                    difference.x(), difference.y(), 0.0, relative="view"
                )
                self.cameraInteracted.emit()
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseDoubleClickEvent(self, event):
            if event.button() == Qt.LeftButton:
                self.fitRequested.emit()
                event.accept()
                return
            super().mouseDoubleClickEvent(event)


    class DynamicMeshItem(gl.GLMeshItem):
        """GL mesh whose constant topology can receive position-only updates."""

        def __init__(self, *args, **kwargs):
            self._position_dirty = False
            super().__init__(*args, **kwargs)

        def set_vertexes_fast(self, vertices):
            """Change geometry positions without re-uploading faces or normals."""

            self.vertexes = np.ascontiguousarray(vertices, dtype=np.float32)
            self._position_dirty = True
            self.update()

        def parseMeshData(self):
            dirty = super().parseMeshData()
            if self._position_dirty:
                dirty |= MeshDirtyFlag.POSITION
                self._position_dirty = False
            return dirty
else:
    AnatomicalGLViewWidget = None
    DynamicMeshItem = None


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
PHASE_TIMELINE_LABELS = {
    "isovolumetric_contraction": ("Isovolumetric contraction", "IVC"),
    "rapid_ejection": ("Rapid ejection", "Rapid eject."),
    "reduced_ejection": ("Reduced ejection", "Reduced eject."),
    "protodiastole": ("Protodiastole", "Proto-D"),
    "isovolumetric_relaxation": ("Isovolumetric relaxation", "IVR"),
    "rapid_filling": ("Rapid ventricular filling", "Rapid filling"),
    "diastasis": ("Diastasis (slow filling)", "Diastasis"),
    "atrial_systole": ("Atrial systole (atrial kick)", "Atrial kick"),
}


# The user-validated v0.6.3 exterior palette is intentionally kept as a named
# rendering contract. External-heart presets use these colours with only a
# small luminance lift; internal teaching presets retain their v0.7.2 styling.
V063_EXTERNAL_PALETTE = {
    1: (0.58, 0.15, 0.18),
    2: (0.55, 0.13, 0.16),
    3: (0.50, 0.12, 0.16),
    4: (0.48, 0.11, 0.15),
    5: (0.55, 0.12, 0.15),
    6: (0.76, 0.20, 0.18),
    7: (0.22, 0.39, 0.63),
    8: (0.18, 0.33, 0.57),
    9: (0.18, 0.33, 0.57),
    10: (0.43, 0.55, 0.72),
    11: (0.98, 0.65, 0.12),
    17: (0.25, 0.43, 0.72),
}
V063_EXTERNAL_BRIGHTNESS = 1.08


class PhaseTimelineWidget(QWidget):
    """Compact phase map with an exact moving time marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timing = None
        self.cycle_fraction = 0.0
        self.setMinimumHeight(58)
        self.setMaximumHeight(64)

    def set_cycle(self, timing, cycle_fraction: float):
        self.timing = timing
        self.cycle_fraction = float(cycle_fraction) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor("#070A0E"))
        if self.timing is None:
            painter.setPen(QColor("#8F96A6"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Phase map loads with the heart")
            return
        left = 2.0
        width = max(1.0, float(self.width()) - 4.0)
        bar = QRectF(left, 4.0, width, 32.0)
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for phase in self.timing.phases:
            x0 = left + width * phase.start_ms / self.timing.cycle_ms
            x1 = left + width * phase.end_ms / self.timing.cycle_ms
            phase_rect = QRectF(x0, bar.top(), max(1.0, x1 - x0), bar.height())
            painter.fillRect(phase_rect, QColor(PHASE_COLOURS[phase.key]))
            painter.setPen(QColor("#D9DEE8"))
            full_name, compact_name = PHASE_TIMELINE_LABELS[phase.key]
            available = max(0.0, phase_rect.width() - 6.0)
            if painter.fontMetrics().horizontalAdvance(full_name) <= available:
                display_name = full_name
            elif painter.fontMetrics().horizontalAdvance(compact_name) <= available:
                display_name = compact_name
            else:
                display_name = ""
            if display_name:
                painter.drawText(
                    phase_rect.adjusted(3.0, 0.0, -3.0, 0.0),
                    Qt.AlignCenter | Qt.TextSingleLine,
                    display_name,
                )
        marker_x = left + width * self.cycle_fraction
        painter.setPen(QColor("#FFFFFF"))
        painter.drawLine(int(marker_x), 1, int(marker_x), 43)
        painter.setPen(QColor("#D4AF37"))
        painter.drawText(
            QRectF(max(left, marker_x - 34.0), 36.0, 68.0, 18.0),
            Qt.AlignCenter,
            f"{self.cycle_fraction * self.timing.cycle_ms:.0f} ms",
        )


class CollapsibleSection(QWidget):
    """Compact sidebar section with an explicit, accessible disclosure button."""

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self._title = str(title)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(3)
        self.toggle_button = QPushButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(bool(expanded))
        self.toggle_button.setObjectName("sectionDisclosure")
        self.toggle_button.setStyleSheet(
            "QPushButton { text-align: left; font-weight: 700; color: #D4AF37; "
            "padding: 5px 7px; }"
        )
        self.toggle_button.toggled.connect(self._set_expanded)
        outer.addWidget(self.toggle_button)
        self.body = QFrame()
        self.body.setObjectName("contentFrame")
        self.content_layout = QVBoxLayout(self.body)
        self.content_layout.setContentsMargins(8, 7, 8, 8)
        self.content_layout.setSpacing(6)
        outer.addWidget(self.body)
        self._set_expanded(bool(expanded))

    def _set_expanded(self, expanded: bool):
        self.body.setVisible(bool(expanded))
        icon = "▼" if expanded else "▶"
        self.toggle_button.setText(f"{icon}  {self._title}")

    def isExpanded(self) -> bool:
        return self.toggle_button.isChecked()


class CorrectionCanvas(QWidget):
    """A small slice editor that paints directly into the study label array."""

    mask_edited = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.study = None
        self.frame_index = 0
        self.slice_index = 0
        self.active_label = 1
        self.brush_radius = 4
        self.erase = False
        self._painting = False
        self._pixmap = QPixmap()
        self._draw_rect = None
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)

    def set_study(self, study):
        self.study = study
        self.frame_index = 0
        self.slice_index = getattr(study, "n_slices", 1) // 2 if study else 0
        self.update()

    def set_position(self, frame_index, slice_index):
        self.frame_index = int(frame_index)
        self.slice_index = int(slice_index)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#030406"))
        if self.study is None:
            painter.setPen(QColor("#8F96A6"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Load cine MRI or open the demo")
            return

        if not getattr(self.study, "has_image_data", True):
            painter.setPen(QColor("#D4AF37"))
            painter.drawText(
                self.rect().adjusted(28, 28, -28, -28),
                Qt.AlignCenter | Qt.TextWordWrap,
                "OPEN-DATA COMPOSITE MODE\n\n"
                "There is no patient MRI behind this atlas view.\n\n"
                "Detailed structures: Z-Anatomy / BodyParts3D\n"
                "Cardiac motion: FAU 3D+t CT-derived statistical model\n\n"
                "Switch to FAU source-motion surfaces to see only anatomy directly "
                "present in the motion model.",
            )
            return

        image = self.study.cine[self.frame_index, self.slice_index]
        mask = self.study.labels[self.frame_index, self.slice_index]
        finite = image[np.isfinite(image)]
        if finite.size:
            low, high = np.percentile(finite, (1.0, 99.0))
        else:
            low, high = 0.0, 1.0
        if high <= low:
            high = low + 1.0
        grey = (255.0 * np.clip((image - low) / (high - low), 0.0, 1.0)).astype(np.uint8)
        rgba = np.empty((*grey.shape, 4), dtype=np.uint8)
        rgba[..., :3] = grey[..., None]
        rgba[..., 3] = 255
        for label, definition in ANATOMY.items():
            selected = mask == label
            if not np.any(selected):
                continue
            colour = np.asarray(definition.colour_rgb, dtype=np.float32)
            rgba[selected, :3] = (
                0.48 * rgba[selected, :3].astype(np.float32) + 0.52 * colour
            ).astype(np.uint8)

        qimage = QImage(
            rgba.data,
            rgba.shape[1],
            rgba.shape[0],
            rgba.strides[0],
            QImage.Format_RGBA8888,
        ).copy()
        self._pixmap = QPixmap.fromImage(qimage)
        scaled = self._pixmap.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        left = (self.width() - scaled.width()) // 2
        top = (self.height() - scaled.height()) // 2
        self._draw_rect = (left, top, scaled.width(), scaled.height())
        painter.drawPixmap(left, top, scaled)
        painter.setPen(QColor("#D4AF37"))
        painter.drawText(10, 20, f"Frame {self.frame_index + 1}  •  Slice {self.slice_index + 1}")

    def _paint_at(self, position):
        if (
            self.study is None
            or not getattr(self.study, "has_image_data", True)
            or self._draw_rect is None
        ):
            return
        left, top, width, height = self._draw_rect
        if width <= 0 or height <= 0:
            return
        px = position.x() - left
        py = position.y() - top
        if px < 0 or py < 0 or px >= width or py >= height:
            return
        rows, cols = self.study.cine.shape[2:]
        x = int(np.clip(px / width * cols, 0, cols - 1))
        y = int(np.clip(py / height * rows, 0, rows - 1))
        yy, xx = np.ogrid[:rows, :cols]
        circle = (xx - x) ** 2 + (yy - y) ** 2 <= self.brush_radius ** 2
        target = self.study.labels[self.frame_index, self.slice_index]
        target[circle] = 0 if self.erase else self.active_label
        self.mask_edited.emit(self.frame_index, self.active_label)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._painting = True
            self._paint_at(event.pos())

    def mouseMoveEvent(self, event):
        if self._painting and event.buttons() & Qt.LeftButton:
            self._paint_at(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._painting = False


class CardiacAnatomyViewer(QWidget):
    """Load, correct, reconstruct, rotate, play and export chamber surfaces."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.study = None
        self._mesh_items = {}
        self._mesh_topology_keys = {}
        self._mesh_centres = {}
        self._mesh_cache = {}
        self._normal_cache = {}
        self._study_revision = 0
        self._playback_phase = 0.0
        self._playback_start_phase = 0.0
        self._playback_beat_index = 0
        self._playback_start_sequence_position = 0.0
        self._playback_start_sequence_ms = 0.0
        self.ecg_recording = None
        self._playback_clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance_frame)
        self._mesh_refresh_timer = QTimer(self)
        self._mesh_refresh_timer.setSingleShot(True)
        self._mesh_refresh_timer.setInterval(140)
        self._mesh_refresh_timer.timeout.connect(self._refresh_after_edit)
        self._build_ui()
        self._update_enabled_state()
        QTimer.singleShot(0, self.open_atlas)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        hero = QFrame()
        hero.setObjectName("heroFrame")
        hero_layout = QVBoxLayout(hero)
        title = QLabel("Open 4D Cardiac Anatomy")
        title.setStyleSheet("font-size: 19pt; font-weight: 700; color: #D4AF37;")
        subtitle = QLabel(
            "Explore a detailed open-data heart through systole and diastole, or load "
            "time-resolved MRI/CT and segmentation masks. Every view distinguishes "
            "source motion from registered anatomy. Teaching/research — not diagnostic."
        )
        subtitle.setWordWrap(True)
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        root.addWidget(hero)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self._build_controls())
        self.main_splitter.addWidget(self._build_viewer())
        self.main_splitter.addWidget(self._build_correction_panel())
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([400, 900, 400])
        root.addWidget(self.main_splitter, 1)

        self.status_label = QLabel(
            "Loading the bundled open-data heart: detailed atlas anatomy with CT-derived statistical cardiac motion."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #C6CBD5; padding: 4px;")
        root.addWidget(self.status_label)

    def _build_controls(self):
        scroll = QScrollArea()
        self.controls_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(385)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.NoFocus)
        content = QWidget()
        layout = QVBoxLayout(content)

        data_group = CollapsibleSection("1. Data workflow", expanded=False)
        data_layout = data_group.content_layout
        self.atlas_button = QPushButton("Open detailed beating heart")
        self.atlas_button.setObjectName("primaryButton")
        self.atlas_button.clicked.connect(self.open_atlas)
        self.load_cine_button = QPushButton("Load cine NIfTI (.nii / .nii.gz)")
        self.load_cine_button.clicked.connect(self.load_cine)
        self.load_mask_button = QPushButton("Load anatomy mask NIfTI")
        self.load_mask_button.clicked.connect(self.load_masks)
        self.load_ecg_button = QPushButton("Load NPG Lite ECG (.csv)")
        # QPushButton.clicked(bool) emits a checked-state Boolean even for a
        # non-checkable button. Do not let that hidden value become ``path``.
        self.load_ecg_button.clicked.connect(lambda _checked=False: self.load_ecg())
        self.dataset_help_button = QPushButton("Open dataset guide")
        self.dataset_help_button.clicked.connect(self.show_dataset_help)
        self.save_mask_button = QPushButton("Save corrected masks")
        self.save_mask_button.clicked.connect(self.save_masks)
        for button in (
            self.atlas_button,
            self.load_cine_button,
            self.load_mask_button,
            self.load_ecg_button,
            self.dataset_help_button,
            self.save_mask_button,
        ):
            data_layout.addWidget(button)
        data_note = QLabel(
            "The included model combines redistributable detailed atlas anatomy with "
            "a ten-phase CT-derived statistical cardiac-motion model. It is explicitly "
            "labelled composite. Real cine/CT plus same-subject masks can still be loaded "
            "below; nothing missing is silently invented."
        )
        data_note.setWordWrap(True)
        data_layout.addWidget(data_note)
        layout.addWidget(data_group)

        playback_group = CollapsibleSection("2. Cardiac-cycle playback", expanded=True)
        playback_layout = playback_group.content_layout
        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)
        self.reset_view_button = QPushButton("Fit view")
        self.reset_view_button.clicked.connect(self.reset_view)
        controls.addWidget(self.play_button)
        controls.addWidget(self.reset_view_button)
        playback_layout.addLayout(controls)
        advanced_playback = CollapsibleSection(
            "Phase stepping and model detail", expanded=False
        )
        self.advanced_playback_section = advanced_playback
        advanced_playback_layout = advanced_playback.content_layout
        phase_navigation = QHBoxLayout()
        self.previous_phase_button = QPushButton("◀ Phase")
        self.previous_phase_button.clicked.connect(lambda: self._jump_relative_phase(-1))
        self.next_phase_button = QPushButton("Phase ▶")
        self.next_phase_button.clicked.connect(lambda: self._jump_relative_phase(1))
        phase_navigation.addWidget(self.previous_phase_button)
        phase_navigation.addWidget(self.next_phase_button)
        advanced_playback_layout.addLayout(phase_navigation)
        phase_controls = QHBoxLayout()
        self.ed_button = QPushButton("End-diastole")
        self.ed_button.clicked.connect(self.jump_to_end_diastole)
        self.es_button = QPushButton("End-systole")
        self.es_button.clicked.connect(self.jump_to_end_systole)
        phase_controls.addWidget(self.ed_button)
        phase_controls.addWidget(self.es_button)
        advanced_playback_layout.addLayout(phase_controls)
        step_controls = QHBoxLayout()
        self.step_back_button = QPushButton("−10 ms")
        self.step_back_button.clicked.connect(lambda: self._step_time_ms(-10.0))
        self.step_forward_button = QPushButton("+10 ms")
        self.step_forward_button.clicked.connect(lambda: self._step_time_ms(10.0))
        step_controls.addWidget(self.step_back_button)
        step_controls.addWidget(self.step_forward_button)
        advanced_playback_layout.addLayout(step_controls)
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.valueChanged.connect(self.set_frame)
        playback_form = QFormLayout()
        playback_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        advanced_playback_form = QFormLayout()
        advanced_playback_form.setFieldGrowthPolicy(
            QFormLayout.AllNonFixedFieldsGrow
        )
        advanced_playback_form.addRow("Source frame", self.frame_slider)
        self.phase_selector = QComboBox()
        for phase in healthy_adult_cycle_timing(DEFAULT_HEART_RATE_BPM).phases:
            self.phase_selector.addItem(phase.name, phase.key)
        self.phase_selector.currentIndexChanged.connect(self._phase_selector_changed)
        self.phase_selector.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.phase_selector.setMinimumContentsLength(12)
        self.phase_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        playback_form.addRow("Estimated phase", self.phase_selector)
        self.playback_speed_combo = QComboBox()
        for label, speed in (
            ("Real time (1×)", 1.0),
            ("Slow (½×)", 0.5),
            ("Slower (¼×)", 0.25),
            ("Teaching (⅒×)", 0.10),
            ("Very slow (1/20×)", 0.05),
        ):
            self.playback_speed_combo.addItem(label, speed)
        self.playback_speed_combo.setCurrentIndex(3)
        self.playback_speed_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.playback_speed_combo.setMinimumContentsLength(12)
        self.playback_speed_combo.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Fixed
        )
        self.playback_speed_combo.currentIndexChanged.connect(
            self._playback_speed_changed
        )
        playback_form.addRow("Playback speed", self.playback_speed_combo)
        self.beat_sequence_combo = QComboBox()
        for label, count in (
            ("1 beat", 1),
            ("5 beats (same source cycle)", 5),
            ("10 beats (same source cycle)", 10),
        ):
            self.beat_sequence_combo.addItem(label, count)
        self.beat_sequence_combo.setCurrentIndex(1)
        self.beat_sequence_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.beat_sequence_combo.setMinimumContentsLength(12)
        self.beat_sequence_combo.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Fixed
        )
        self.beat_sequence_combo.currentIndexChanged.connect(
            self._beat_sequence_changed
        )
        self.beat_sequence_combo.setToolTip(
            "The FAU/CONRAD source contains one normalized statistical cardiac "
            "cycle. Five- and ten-beat modes repeat that same cycle and add a "
            "beat counter; they do not invent measured beat-to-beat variation."
        )
        advanced_playback_form.addRow("Sequence", self.beat_sequence_combo)
        self.heart_rate_spin = QSpinBox()
        self.heart_rate_spin.setRange(
            MIN_SUPPORTED_HEART_RATE, MAX_SUPPORTED_HEART_RATE
        )
        self.heart_rate_spin.setValue(DEFAULT_HEART_RATE_BPM)
        self.heart_rate_spin.setSuffix(" bpm")
        self.heart_rate_spin.valueChanged.connect(self._playback_rate_changed)
        self.heart_rate_spin.setToolTip(
            "Supported normal-adult empirical range. Increasing rate shortens "
            "diastole disproportionately rather than uniformly speeding the loop."
        )
        playback_form.addRow("Heart rate", self.heart_rate_spin)
        self.timing_source_label = QLabel("Model clock • 72 bpm")
        self.timing_source_label.setWordWrap(True)
        self.timing_source_label.setStyleSheet("color: #D4AF37;")
        playback_form.addRow("Timing source", self.timing_source_label)
        playback_layout.addLayout(playback_form)
        playback_layout.addWidget(advanced_playback)
        advanced_playback_layout.addLayout(advanced_playback_form)
        self.timing_summary = QLabel("Normal-adult mechanical timing")
        self.timing_summary.setWordWrap(True)
        self.timing_summary.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.timing_summary.setFixedHeight(78)
        self.timing_summary.setStyleSheet("color: #C6CBD5;")
        advanced_playback_layout.addWidget(self.timing_summary)
        self.frame_summary = QLabel("No study loaded")
        self.frame_summary.setWordWrap(True)
        self.frame_summary.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.frame_summary.setFixedHeight(40)
        advanced_playback_layout.addWidget(self.frame_summary)
        self.phase_detail = QLabel(
            "Phase boundaries and valve motion are estimated teaching overlays."
        )
        self.phase_detail.setWordWrap(True)
        self.phase_detail.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.phase_detail.setFixedHeight(82)
        self.phase_detail.setStyleSheet("color: #D4AF37;")
        advanced_playback_layout.addWidget(self.phase_detail)
        layout.addWidget(playback_group)

        chamber_group = CollapsibleSection("3. Anatomy and view", expanded=True)
        chamber_layout = chamber_group.content_layout
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems([
            "External anatomy + coronaries",
            "Ventricular walls + myocardium",
            "Four chambers (ventricles emphasized)",
            "Valve orifices (registration audit)",
            "Coronary circulation",
            "FAU source-motion surfaces (layered)",
            "Registered atlas overview (unfitted valves hidden)",
        ])
        self.view_mode_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.view_mode_combo.setMinimumContentsLength(20)
        self.view_mode_combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.view_mode_combo.currentIndexChanged.connect(self._apply_view_preset)
        chamber_layout.addWidget(self.view_mode_combo)
        manual_structures = CollapsibleSection(
            "Manual structure visibility", expanded=False
        )
        self.manual_structures_section = manual_structures
        manual_structures_layout = manual_structures.content_layout
        self.chamber_checks = {}
        for label, definition in ANATOMY.items():
            check = QCheckBox(definition.display_name)
            check.setChecked(True)
            check.stateChanged.connect(self._update_mesh_visibility)
            colour = definition.colour_rgb
            check.setStyleSheet(
                f"QCheckBox {{ color: rgb({colour[0]}, {colour[1]}, {colour[2]}); }}"
            )
            self.chamber_checks[label] = check
            manual_structures_layout.addWidget(check)
        opacity_form = QFormLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._rebuild_current_meshes)
        opacity_form.addRow("Opacity balance", self.opacity_slider)
        self.cutaway_slider = QSlider(Qt.Horizontal)
        self.cutaway_slider.setRange(0, 0)
        self.cutaway_slider.setValue(0)
        manual_structures_layout.addLayout(opacity_form)
        self.volume_label = QLabel("Chamber volumes appear after masks are loaded")
        self.volume_label.setWordWrap(True)
        manual_structures_layout.addWidget(self.volume_label)
        chamber_layout.addWidget(manual_structures)
        layout.addWidget(chamber_group)

        auto_group = CollapsibleSection(
            "4. Automatic help + verification", expanded=False
        )
        auto_layout = auto_group.content_layout
        self.propagate_button = QPushButton("Auto-propagate corrected frame")
        self.propagate_button.clicked.connect(self.propagate_masks)
        auto_layout.addWidget(self.propagate_button)
        auto_note = QLabel(
            "Temporal propagation helps carry a trusted mask through a cycle. It is not "
            "one-click anatomical truth. Inspect every plane and every frame, especially "
            "atria, valves, basal slices and small coronary vessels."
        )
        auto_note.setWordWrap(True)
        auto_layout.addWidget(auto_note)
        layout.addWidget(auto_group)

        export_group = CollapsibleSection("5. Validate and export", expanded=False)
        export_layout = export_group.content_layout
        self.qc_button = QPushButton("Run accuracy and completeness checks")
        self.qc_button.clicked.connect(self.show_quality_report)
        export_layout.addWidget(self.qc_button)
        self.export_button = QPushButton("Export rotating GIF / MP4")
        self.export_button.clicked.connect(self.export_movie)
        export_layout.addWidget(self.export_button)
        export_note = QLabel(
            "The live view remains freely rotatable while it beats. Export adds a provenance JSON sidecar."
        )
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)
        layout.addWidget(export_group)

        provenance_group = CollapsibleSection("Dataset provenance", expanded=False)
        provenance_form = QFormLayout()
        self.dataset_edit = QLineEdit()
        self.source_edit = QLineEdit()
        self.license_edit = QLineEdit()
        self.citation_edit = QLineEdit()
        provenance_form.addRow("Dataset", self.dataset_edit)
        provenance_form.addRow("Source URL", self.source_edit)
        provenance_form.addRow("Licence", self.license_edit)
        provenance_form.addRow("Citation", self.citation_edit)
        provenance_note = QLabel(
            "For a fused heart, cite every contributing dataset. A registered coronary "
            "atlas remains a composite even when it moves convincingly."
        )
        provenance_note.setWordWrap(True)
        provenance_form.addRow(provenance_note)
        provenance_group.content_layout.addLayout(provenance_form)
        layout.addWidget(provenance_group)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def show_dataset_help(self):
        QMessageBox.information(
            self,
            "Accuracy-first dataset guide",
            "Included teaching heart: detailed Z-Anatomy/BodyParts3D geometry is "
            "registered to the FAU CT-derived statistical motion model. Use External "
            "anatomy for detail and FAU source-motion surfaces to audit the unfused source.\n\n"
            "Easiest patient-data start: Sunnybrook cine MRI (CC0). It is excellent "
            "for LV motion, but it cannot provide a complete four-chamber or coronary heart.\n\n"
            "Better motion coverage: Cardiac Atlas 2011 Motion Tracking Challenge. "
            "It includes cine 2-chamber, 4-chamber and short-axis views, whole-heart "
            "end-diastolic MRI and temporal MRI. It is open-access by attribution; "
            "do not redistribute its raw scans without confirming permission.\n\n"
            "External coronary detail: use coronary CTA only as a "
            "separately attributed component. If it is from another subject, mark it "
            "registered/composite.\n\n"
            "Best eventual target: same-subject multiphase gated cardiac CTA with "
            "whole-heart and coronary labels. That is harder to obtain, but it is the "
            "cleanest route to a detailed subject-specific beating external heart."
        )

    def _restore_control_origin(self):
        """Keep the opening screen at the start of the workflow."""

        if hasattr(self, "controls_scroll"):
            self.controls_scroll.verticalScrollBar().setValue(0)
        if self.gl_view is not None:
            self.gl_view.setFocus(Qt.OtherFocusReason)

    def _build_viewer(self):
        frame = QFrame()
        frame.setObjectName("contentFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        orientation_row = QHBoxLayout()
        orientation_label = QLabel("Anatomical camera")
        orientation_label.setStyleSheet("color: #C6CBD5;")
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(
            [
                "Free rotation",
                "Anterior",
                "Posterior",
                "Left lateral",
                "Right lateral",
                "Superior",
                "Inferior",
            ]
        )
        self.orientation_combo.currentTextChanged.connect(self._orientation_changed)
        self.save_opening_view_button = QPushButton("Save current as opening")
        self.save_opening_view_button.setToolTip(
            "After rotating the atlas to a preferred view, save that exact camera "
            "orientation for future launches."
        )
        self.save_opening_view_button.clicked.connect(
            self.save_current_as_opening_view
        )
        self.restore_opening_view_button = QPushButton("Restore built-in")
        self.restore_opening_view_button.setToolTip(
            "Remove the personal opening view and restore the calibrated built-in anterior view."
        )
        self.restore_opening_view_button.clicked.connect(
            self.restore_builtin_opening_view
        )
        orientation_row.addWidget(orientation_label)
        orientation_row.addWidget(self.orientation_combo)
        orientation_row.addWidget(self.save_opening_view_button)
        orientation_row.addWidget(self.restore_opening_view_button)
        orientation_row.addStretch(1)
        layout.addLayout(orientation_row)
        if gl is None:
            self.gl_view = None
            missing = QLabel(
                "3D view unavailable. Close the app, then run Install_or_Repair.bat."
            )
            missing.setAlignment(Qt.AlignCenter)
            missing.setWordWrap(True)
            layout.addWidget(missing, 1)
        else:
            try:
                self.gl_view = AnatomicalGLViewWidget()
                self.gl_view.setBackgroundColor("#030406")
                self.gl_view.opts["distance"] = 260
                self.gl_view.cameraInteracted.connect(self._camera_interacted)
                self.gl_view.fitRequested.connect(self.reset_view)
                # Without this explicit stretch Qt gives the small instruction
                # label below roughly half of the available height and traps the
                # actual 3D canvas in the top strip of a maximized window.
                layout.addWidget(self.gl_view, 1)
            except Exception as exc:
                self.gl_view = None
                missing = QLabel(f"Could not initialise OpenGL view:\n{exc}")
                missing.setAlignment(Qt.AlignCenter)
                missing.setWordWrap(True)
                layout.addWidget(missing, 1)

        self.ecg_panel = QFrame()
        self.ecg_panel.setObjectName("timelineFrame")
        ecg_layout = QVBoxLayout(self.ecg_panel)
        ecg_layout.setContentsMargins(10, 5, 10, 5)
        ecg_layout.setSpacing(3)
        ecg_header = QHBoxLayout()
        self.ecg_trace_label = QLabel(
            "Recorded ECG — reviewed median P/QRS template projected to accepted R triggers"
        )
        self.ecg_trace_label.setStyleSheet("font-weight: 700; color: #D4AF37;")
        self.review_ecg_button = QPushButton("Review annotations")
        self.review_ecg_button.clicked.connect(self.review_ecg_peaks)
        self.clear_ecg_button = QPushButton("Return to model clock")
        self.clear_ecg_button.clicked.connect(self.clear_ecg_gating)
        ecg_header.addWidget(self.ecg_trace_label)
        ecg_header.addStretch(1)
        ecg_header.addWidget(self.review_ecg_button)
        ecg_header.addWidget(self.clear_ecg_button)
        ecg_layout.addLayout(ecg_header)
        self.ecg_trace = ECGTraceWidget()
        self.ecg_trace.timeSelected.connect(self._ecg_trace_scrubbed)
        ecg_layout.addWidget(self.ecg_trace)
        self.ecg_panel.setVisible(False)
        layout.addWidget(self.ecg_panel, 0)

        timeline = QFrame()
        timeline.setObjectName("timelineFrame")
        timeline_layout = QVBoxLayout(timeline)
        timeline_layout.setContentsMargins(10, 5, 10, 5)
        timeline_layout.setSpacing(2)

        timeline_header = QHBoxLayout()
        self.cycle_time_label = QLabel("Cycle time  0 ms / 1000 ms")
        self.cycle_time_label.setStyleSheet("font-weight: 700; color: #D4AF37;")
        self.cycle_phase_label = QLabel("End-diastole • 0%")
        self.cycle_phase_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cycle_phase_label.setStyleSheet("color: #C6CBD5;")
        timeline_header.addWidget(self.cycle_time_label)
        timeline_header.addStretch(1)
        timeline_header.addWidget(self.cycle_phase_label)
        timeline_layout.addLayout(timeline_header)

        self.phase_timeline = PhaseTimelineWidget()
        timeline_layout.addWidget(self.phase_timeline)

        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.setSingleStep(1)
        self.timeline_slider.setPageStep(10)
        self.timeline_slider.setTickPosition(QSlider.TicksBelow)
        self.timeline_slider.setTickInterval(50)
        self.timeline_slider.valueChanged.connect(self._timeline_changed)
        timeline_layout.addWidget(self.timeline_slider)

        timeline_markers = QHBoxLayout()
        self.timeline_markers_layout = timeline_markers
        self.ed_marker_label = QLabel("ED • 0 ms")
        self.es_marker_label = QLabel("ES")
        self.es_marker_label.setAlignment(Qt.AlignCenter)
        self.next_ed_marker_label = QLabel("next ED • 1000 ms")
        self.next_ed_marker_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for marker in (
            self.ed_marker_label,
            self.es_marker_label,
            self.next_ed_marker_label,
        ):
            marker.setStyleSheet("color: #8F96A6; font-size: 9pt;")
        timeline_markers.addWidget(self.ed_marker_label)
        timeline_markers.addStretch(4)
        timeline_markers.addWidget(self.es_marker_label)
        timeline_markers.addStretch(6)
        timeline_markers.addWidget(self.next_ed_marker_label)
        timeline_layout.addLayout(timeline_markers)
        layout.addWidget(timeline, 0)

        hint = QLabel(
            "Left-drag rotate • right/middle-drag pan • wheel zoom • double-click fit"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #8F96A6;")
        hint.setMaximumHeight(22)
        layout.addWidget(hint, 0)
        return frame

    def _build_correction_panel(self):
        frame = QFrame()
        frame.setObjectName("contentFrame")
        frame.setMinimumWidth(380)
        layout = QVBoxLayout(frame)
        self.correction_heading = QLabel("Source-faithful correction view")
        self.correction_heading.setStyleSheet("font-weight: 700; color: #D4AF37;")
        layout.addWidget(self.correction_heading)
        self.correction_note = QLabel(
            "Paint labels on the actual MRI slice. The 3D surface is regenerated from the edited mask; the source MRI is never overwritten."
        )
        self.correction_note.setWordWrap(True)
        layout.addWidget(self.correction_note)
        self.atlas_evidence_panel = QLabel()
        self.atlas_evidence_panel.setTextFormat(Qt.RichText)
        self.atlas_evidence_panel.setWordWrap(True)
        self.atlas_evidence_panel.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.atlas_evidence_panel.setStyleSheet(
            "QLabel { color: #D9DEE8; background: #070A0E; border: 1px solid #252B35; "
            "padding: 12px; }"
        )
        self.atlas_evidence_panel.setVisible(False)
        layout.addWidget(self.atlas_evidence_panel, 1)
        self.canvas = CorrectionCanvas()
        self.canvas.mask_edited.connect(self._mask_was_edited)
        layout.addWidget(self.canvas, 1)

        self.slice_form = QFormLayout()
        self.slice_slider = QSlider(Qt.Horizontal)
        self.slice_slider.valueChanged.connect(self.set_slice)
        self.slice_form.addRow("Slice", self.slice_slider)
        self.label_combo = QComboBox()
        for label, definition in ANATOMY.items():
            self.label_combo.addItem(definition.display_name, label)
        self.label_combo.currentIndexChanged.connect(self._update_brush)
        self.slice_form.addRow("Paint", self.label_combo)
        self.brush_spin = QSpinBox()
        self.brush_spin.setRange(1, 30)
        self.brush_spin.setValue(4)
        self.brush_spin.valueChanged.connect(self._update_brush)
        self.slice_form.addRow("Brush radius", self.brush_spin)
        self.erase_check = QCheckBox("Erase instead of paint")
        self.erase_check.stateChanged.connect(self._update_brush)
        self.slice_form.addRow("", self.erase_check)
        layout.addLayout(self.slice_form)
        return frame

    def _update_enabled_state(self):
        loaded = self.study is not None
        image_data = loaded and getattr(self.study, "has_image_data", True)
        for widget in (
            self.play_button,
            self.frame_slider,
            self.export_button,
            self.reset_view_button,
            self.qc_button,
            self.ed_button,
            self.es_button,
            self.timeline_slider,
            self.previous_phase_button,
            self.next_phase_button,
            self.step_back_button,
            self.step_forward_button,
            self.phase_selector,
            self.playback_speed_combo,
            self.beat_sequence_combo,
        ):
            widget.setEnabled(loaded)
        for widget in (
            self.load_mask_button,
            self.save_mask_button,
            self.slice_slider,
            self.propagate_button,
            self.label_combo,
            self.brush_spin,
            self.erase_check,
        ):
            widget.setEnabled(image_data)
        if self.export_button:
            self.export_button.setEnabled(loaded and self.gl_view is not None and imageio is not None)

    def open_atlas(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.set_study(OpenHeartAtlasStudy())
            self.view_mode_combo.setCurrentText(
                "External anatomy + coronaries"
            )
            self._apply_view_preset()
            if self.gl_view is None:
                self.status_label.setText(
                    "The open-data heart loaded, but the 3D OpenGL view is unavailable. "
                    "Run Install_or_Repair.bat, then restart the app."
                )
            else:
                self.status_label.setText(
                    "OPEN-DATA COMPOSITE — detailed Z-Anatomy/BodyParts3D structures "
                    "registered to FAU CT-derived statistical cardiac motion. Not one patient."
                )
            QTimer.singleShot(0, self._restore_control_origin)
        except Exception as exc:
            QMessageBox.critical(self, "Could not open the bundled heart", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def load_ecg(self, path=None):
        """Load an NPG Lite-style CSV for reviewed electrical synchronization."""

        # Defensive compatibility for direct Qt signal connections or plugins
        # that still forward QPushButton.clicked(bool) into this method.
        if isinstance(path, (bool, np.bool_)):
            path = None
        if path is None:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Load recorded ECG for timing",
                "",
                "CSV recordings (*.csv);;All files (*)",
            )
            if not selected:
                return
            path = selected
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            recording = ECGGatingRecording.from_csv(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Could not load ECG", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        review = ECGPeakReviewDialog(recording, self)
        if review.exec_() != QDialog.Accepted:
            return
        self._activate_ecg_recording(recording)

    def _activate_ecg_recording(self, recording: ECGGatingRecording):
        self._pause_playback()
        self.ecg_recording = recording
        self._playback_phase = 0.0
        self._playback_beat_index = 0
        self._playback_start_sequence_ms = 0.0
        self.ecg_trace.set_recording(recording)
        self.ecg_panel.setVisible(True)
        # OPL_PLAY_ALL_REVIEWED_ECG_V06
        # OPL treats a loaded ECG as a physiology recording, not a ten-beat
        # demonstration window. Use every complete reviewed R-R cycle.
        self._set_ecg_sequence_options(
            default_count=recording.beat_count
        )
        self.heart_rate_spin.setEnabled(False)
        self._update_ecg_timing_source()
        if self.study is not None:
            self._set_phase(0.0, restart_clock=False, beat_index=0)
        flags = " " + " ".join(recording.quality_flags) if recording.quality_flags else ""
        self.status_label.setText(
            f"ECG-GATED MODEL — {recording.source_path.name}: {recording.beat_count} "
            f"{recording.cycle_reference_name} cycles at {recording.fs_hz:.0f} Hz. "
            "Raw samples are unchanged; the reviewed median P/QRS template and accepted R "
            "triggers anchor the shared clock. T waves are not delineated. "
            "Mechanical subphases and valve events remain estimates unless manually annotated "
            f"from PCG/echo.{flags}"
        )
        self._update_atlas_evidence_panel()

    def _ecg_trace_scrubbed(self, time_s: float):
        """Move the 3-D heart and phase ribbon to a clicked ECG position."""

        if not self._ecg_gating_active():
            return
        self._pause_playback()
        beat = self.ecg_recording.beat_index_at_time(float(time_s))
        start_s = self.ecg_recording.beat_start_time_s(beat)
        duration_s = self.ecg_recording.beat_duration_ms(beat) / 1000.0
        phase = float(np.clip((float(time_s) - start_s) / max(duration_s, 1e-9), 0.0, 0.999999))
        self._set_phase(phase, restart_clock=False, beat_index=beat)

    def review_ecg_peaks(self):
        if self.ecg_recording is None:
            return
        self._pause_playback()
        previous_count = self._beat_sequence_count()
        review = ECGPeakReviewDialog(self.ecg_recording, self)
        if review.exec_() != QDialog.Accepted:
            return
        self.ecg_trace.refresh_markers()
        self._set_ecg_sequence_options(default_count=previous_count)
        self._playback_beat_index = min(
            self._playback_beat_index, self._beat_sequence_count() - 1
        )
        self._set_phase(self._playback_phase, restart_clock=False)

    def clear_ecg_gating(self):
        if self.ecg_recording is None:
            return
        self._pause_playback()
        self.ecg_recording = None
        self.ecg_trace.set_recording(None)
        self.ecg_panel.setVisible(False)
        self._playback_beat_index = 0
        self._playback_start_sequence_position = self._playback_phase
        self._playback_start_sequence_ms = 0.0
        self._set_model_sequence_options()
        self.heart_rate_spin.setEnabled(True)
        self.timing_source_label.setText(
            f"Model clock • {self.heart_rate_spin.value()} bpm"
        )
        if self.study is not None:
            self._set_phase(self._playback_phase, restart_clock=False, beat_index=0)
        self.status_label.setText(
            "MODEL CLOCK — the ECG has been detached. Playback again uses the "
            "normal-adult empirical timing model."
        )
        self._update_atlas_evidence_panel()

    def _set_model_sequence_options(self):
        self.beat_sequence_combo.blockSignals(True)
        self.beat_sequence_combo.clear()
        for label, count in (
            ("1 beat", 1),
            ("5 beats (same source cycle)", 5),
            ("10 beats (same source cycle)", 10),
        ):
            self.beat_sequence_combo.addItem(label, count)
        self.beat_sequence_combo.setCurrentIndex(1)
        self.beat_sequence_combo.blockSignals(False)
        self.beat_sequence_combo.setToolTip(
            "The FAU/CONRAD source contains one normalized statistical cardiac cycle. "
            "Without ECG gating, multi-beat modes repeat that cycle at one selected rate."
        )

    def _set_ecg_sequence_options(self, default_count=10):
        if self.ecg_recording is None:
            return
        available = self.ecg_recording.beat_count
        counts = sorted({min(value, available) for value in (1, 5, 10, available) if value > 0})
        target = min(max(1, int(default_count)), available)
        self.beat_sequence_combo.blockSignals(True)
        self.beat_sequence_combo.clear()
        for count in counts:
            label = (
                f"All {available} reviewed ECG cycles"
                if count == available
                else f"{count} reviewed ECG cycle{'s' if count != 1 else ''}"
            )
            self.beat_sequence_combo.addItem(label, count)
        best = min(range(self.beat_sequence_combo.count()), key=lambda i: abs(int(self.beat_sequence_combo.itemData(i)) - target))
        self.beat_sequence_combo.setCurrentIndex(best)
        self.beat_sequence_combo.blockSignals(False)
        self.beat_sequence_combo.setToolTip(
            "Each selected cycle uses its accepted R-trigger duration. Reviewed median-template "
            "P/QRS offsets inform the estimated phase clock; subject-specific mechanics are not inferred."
        )

    def _update_ecg_timing_source(self):
        if self.ecg_recording is None:
            return
        timing = self._current_timing()
        self.timing_source_label.setText(
            f"Recorded ECG • {self.ecg_recording.cycle_reference_name} • "
            f"beat {self._playback_beat_index + 1} • cycle {timing.cycle_ms:.0f} ms • "
            f"{timing.heart_rate_bpm:.1f} bpm"
        )
        if MIN_SUPPORTED_HEART_RATE <= timing.heart_rate_bpm <= MAX_SUPPORTED_HEART_RATE:
            self.heart_rate_spin.blockSignals(True)
            self.heart_rate_spin.setValue(int(round(timing.heart_rate_bpm)))
            self.heart_rate_spin.blockSignals(False)

    def open_demo(self):
        """Retained only as a developer renderer test; it is not offered in the UI."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.set_study(CardiacCineStudy.synthetic_demo())
            if self.gl_view is None:
                self.status_label.setText(
                    "Synthetic source slices loaded, but the 3D OpenGL view is unavailable. "
                    "Run Install_or_Repair.bat, then restart the app."
                )
            elif not self._mesh_items:
                self.status_label.setText(
                    "Synthetic source slices loaded, but no 3D surfaces were generated. "
                    "Check the dependency message above."
                )
            else:
                self.status_label.setText(
                    "Synthetic full-anatomy demo loaded. Try Internal, External and Coronaries-only views."
                )
        finally:
            QApplication.restoreOverrideCursor()

    def load_cine(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load 3D+t cine MRI",
            "",
            "NIfTI images (*.nii *.nii.gz);;All files (*)",
        )
        if not path:
            return
        try:
            self.set_study(CardiacCineStudy.from_nifti(Path(path)))
            self.status_label.setText(
                "Cine MRI loaded without inferred anatomy. Load a chamber mask or paint a reference frame."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not load cine MRI", str(exc))

    def load_masks(self):
        if self.study is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load cardiac anatomy masks",
            "",
            "NIfTI images (*.nii *.nii.gz);;All files (*)",
        )
        if not path:
            return
        mapping_text, ok = QInputDialog.getText(
            self,
            "Map dataset labels",
            "Enter the input value used for each chamber:\n"
            "(omit a chamber if it is not present)",
            text="LV=1,RV=2,LA=3,RA=4,MYO=5,AO=6,PA=7,SVC=8,IVC=9,PV=10,CA=11",
        )
        if not ok:
            return
        try:
            mapping = parse_anatomy_mapping(mapping_text)
            self.study.load_label_nifti(
                Path(path), mapping, current_frame=self.frame_slider.value()
            )
            evidence, accepted = QInputDialog.getItem(
                self,
                "How was this anatomy obtained?",
                "Evidence status for the structures in this mask:",
                ["measured", "statistical", "registered", "propagated", "synthetic", "unknown"],
                0,
                False,
            )
            if accepted:
                for label in mapping.values():
                    self.study.evidence[int(label)] = str(evidence)
            self._invalidate_all_meshes()
            self.set_frame(self.frame_slider.value())
            self.status_label.setText(
                "Masks loaded. Confirm the mapping against the source slices before interpreting the 3D model."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not load masks", str(exc))

    def save_masks(self):
        if self.study is None or not getattr(self.study, "has_image_data", True):
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save corrected chamber masks",
            "cardiac_anatomy_masks.nii.gz",
            "NIfTI image (*.nii.gz *.nii)",
        )
        if not path:
            return
        try:
            self.study.save_label_nifti(Path(path))
            self._sync_provenance_from_fields()
            self._write_sidecar(Path(path), "segmentation")
            self.status_label.setText(f"Corrected masks saved: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not save masks", str(exc))

    def set_study(self, study):
        self._timer.stop()
        self.play_button.setText("Play")
        previous = self.study
        if previous is not None and previous is not study and hasattr(previous, "close"):
            previous.close()
        self.study = study
        self._playback_phase = 0.0
        self._playback_start_phase = 0.0
        self._playback_beat_index = 0
        self._playback_start_sequence_position = 0.0
        self._playback_start_sequence_ms = 0.0
        self._study_revision += 1
        self._mesh_cache.clear()
        self._normal_cache.clear()
        for item in self._mesh_items.values():
            if self.gl_view is not None:
                try:
                    self.gl_view.removeItem(item)
                except Exception:
                    pass
        self._mesh_items.clear()
        self._mesh_topology_keys.clear()
        self._mesh_centres.clear()
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, max(0, study.n_frames - 1))
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setTickInterval(max(1, int(round(1000 / study.n_frames))))
        self.timeline_slider.setValue(0)
        self.timeline_slider.blockSignals(False)
        self.slice_slider.blockSignals(True)
        slices = int(getattr(study, "n_slices", 1))
        self.slice_slider.setRange(0, max(0, slices - 1))
        self.slice_slider.setValue(slices // 2)
        self.slice_slider.blockSignals(False)
        self.canvas.set_study(study)
        self.canvas.set_position(0, self.slice_slider.value())
        self.dataset_edit.setText(study.provenance.get("dataset", ""))
        self.source_edit.setText(study.provenance.get("source_url", ""))
        self.license_edit.setText(study.provenance.get("license", ""))
        self.citation_edit.setText(study.provenance.get("citation", ""))
        atlas_mode = not getattr(study, "has_image_data", True)
        self.orientation_combo.setEnabled(
            atlas_mode and self.gl_view is not None and hasattr(study, "anatomical_axes")
        )
        self.save_opening_view_button.setEnabled(self.orientation_combo.isEnabled())
        self.restore_opening_view_button.setEnabled(self.orientation_combo.isEnabled())
        if atlas_mode:
            self.correction_heading.setText("Evidence and anatomical content")
            self.correction_note.setText(
                "A live evidence summary replaces the unused MRI editor in atlas mode."
            )
        else:
            self.correction_heading.setText("Source-faithful correction view")
            self.correction_note.setText(
                "Paint labels on the actual MRI slice. The 3D surface is regenerated from "
                "the edited mask; the source MRI is never overwritten."
            )
        self.atlas_evidence_panel.setVisible(atlas_mode)
        self.canvas.setVisible(not atlas_mode)
        for widget in (self.slice_slider, self.label_combo, self.brush_spin, self.erase_check):
            widget.setVisible(not atlas_mode)
            field_label = self.slice_form.labelForField(widget)
            if field_label is not None:
                field_label.setVisible(not atlas_mode)
        self._update_atlas_evidence_panel()
        self._update_enabled_state()
        self.set_frame(0)
        self.reset_view()
        if self.orientation_combo.isEnabled():
            self.orientation_combo.blockSignals(True)
            self.orientation_combo.setCurrentText("Anterior")
            self.orientation_combo.blockSignals(False)
            self.set_anatomical_view("Anterior")
        else:
            self.orientation_combo.blockSignals(True)
            self.orientation_combo.setCurrentText("Free rotation")
            self.orientation_combo.blockSignals(False)
        QTimer.singleShot(0, self.reset_view)

    def set_frame(self, frame_index):
        if self.study is None:
            return
        frame_index = int(np.clip(frame_index, 0, self.study.n_frames - 1))
        motion_phase = frame_index / max(1, self.study.n_frames)
        time_phase = time_phase_from_timing(
            motion_phase,
            self._current_timing(),
            self._model_end_systole_phase(),
        )
        self._set_phase(time_phase, restart_clock=True)

    def _model_end_systole_phase(self) -> float:
        if self.study is None:
            return 0.4
        return float(
            getattr(self.study, "end_systole_frame", self.study.n_frames // 3)
        ) / max(1, self.study.n_frames)

    def _set_phase(self, phase, restart_clock=False, beat_index=None):
        """Show one normalized point in the cardiac cycle.

        Atlas meshes are interpolated continuously. Patient masks retain their
        discrete source frames because independently reconstructed surfaces do not
        establish a valid point-to-point correspondence between frames.
        """

        if self.study is None:
            return
        phase = float(phase)
        if phase >= 1.0:
            phase = np.nextafter(1.0, 0.0)
        phase = phase % 1.0
        previous_beat = self._playback_beat_index
        self._playback_phase = phase
        if beat_index is not None:
            self._playback_beat_index = int(
                np.clip(int(beat_index), 0, self._beat_sequence_count() - 1)
            )
        if restart_clock and self._timer.isActive():
            self._playback_start_phase = phase
            if self._ecg_gating_active():
                self._playback_start_sequence_ms = self._current_sequence_elapsed_ms()
            else:
                self._playback_start_sequence_position = (
                    self._playback_beat_index + phase
                )
            self._playback_clock.restart()

        timing = self._current_timing()
        motion_phase = motion_phase_from_timing(
            phase,
            timing,
            self._model_end_systole_phase(),
        )
        frame_position = motion_phase * self.study.n_frames
        frame_index = int(np.floor(frame_position)) % self.study.n_frames
        if self.frame_slider.value() != frame_index:
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(frame_index)
            self.frame_slider.blockSignals(False)
        timeline_value = int(round(phase * 1000.0))
        if self.timeline_slider.value() != timeline_value:
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(timeline_value)
            self.timeline_slider.blockSignals(False)
        self.canvas.set_position(frame_index, self.slice_slider.value())
        if hasattr(self.study, "mesh_for_phase"):
            self._render_phase(motion_phase, phase)
        else:
            self._render_frame(frame_index)
        current_phase, _ = timing.phase_at_fraction(phase)
        selector_index = self.phase_selector.findData(current_phase.key)
        if selector_index >= 0 and self.phase_selector.currentIndex() != selector_index:
            self.phase_selector.blockSignals(True)
            self.phase_selector.setCurrentIndex(selector_index)
            self.phase_selector.blockSignals(False)
        self._update_cycle_readout(phase, frame_position, frame_index)
        if self._ecg_gating_active():
            cursor_time = (
                self.ecg_recording.beat_start_time_s(self._playback_beat_index)
                + phase * timing.cycle_ms / 1000.0
            )
            self.ecg_trace.set_cursor_time(cursor_time)
            if previous_beat != self._playback_beat_index:
                self._update_ecg_timing_source()
                self._update_atlas_evidence_panel()
        if getattr(self.study, "has_image_data", True):
            volumes = []
            for label, definition in CHAMBERS.items():
                value = self.study.chamber_volume_ml(frame_index, label)
                volumes.append(f"{definition.short_name} {value:.1f} mL")
            self.volume_label.setText("  •  ".join(volumes))
        else:
            self.volume_label.setText(
                "Volumes intentionally not reported: atlas surfaces are not same-subject "
                "cavity segmentations."
            )

    def _timeline_changed(self, value):
        self._set_phase(float(value) / 1000.0, restart_clock=True)

    def _phase_selector_changed(self, index):
        if self.study is None or index < 0:
            return
        timing = self._current_timing()
        key = self.phase_selector.itemData(index)
        phase = timing.phase_by_key(str(key))
        target_ms = phase.start_ms + 0.5 * phase.duration_ms
        self._pause_playback()
        self._set_phase(target_ms / timing.cycle_ms, restart_clock=False)

    def _jump_relative_phase(self, direction: int):
        if self.study is None:
            return
        timing = self._current_timing()
        current, _ = timing.phase_at_fraction(self._playback_phase)
        index = next(i for i, phase in enumerate(timing.phases) if phase.key == current.key)
        target = timing.phases[(index + int(direction)) % len(timing.phases)]
        self._pause_playback()
        self._set_phase(
            (target.start_ms + 0.5 * target.duration_ms) / timing.cycle_ms,
            restart_clock=False,
        )

    def _step_time_ms(self, delta_ms: float):
        if self.study is None:
            return
        timing = self._current_timing()
        self._pause_playback()
        self._set_phase(
            (self._playback_phase + float(delta_ms) / timing.cycle_ms) % 1.0,
            restart_clock=False,
        )

    def _pause_playback(self):
        if self._timer.isActive():
            self._timer.stop()
        self.play_button.setText("Play")

    def _playback_speed(self) -> float:
        value = self.playback_speed_combo.currentData()
        return float(value if value is not None else 1.0)

    def _playback_speed_changed(self):
        if self._timer.isActive():
            self._playback_start_phase = self._playback_phase
            if self._ecg_gating_active():
                self._playback_start_sequence_ms = self._current_sequence_elapsed_ms()
            else:
                self._playback_start_sequence_position = (
                    self._playback_beat_index + self._playback_phase
                )
            self._playback_clock.restart()

    def _beat_sequence_count(self) -> int:
        value = self.beat_sequence_combo.currentData()
        return int(value if value is not None else 1)

    def _beat_sequence_changed(self):
        self._playback_beat_index = min(
            self._playback_beat_index, self._beat_sequence_count() - 1
        )
        if self._timer.isActive():
            if self._ecg_gating_active():
                self._playback_start_sequence_ms = self._current_sequence_elapsed_ms()
            else:
                self._playback_start_sequence_position = (
                    self._playback_beat_index + self._playback_phase
                )
            self._playback_clock.restart()
        if self.study is not None:
            motion_phase = motion_phase_from_timing(
                self._playback_phase,
                self._current_timing(),
                self._model_end_systole_phase(),
            )
            frame_position = motion_phase * self.study.n_frames
            self._update_cycle_readout(
                self._playback_phase,
                frame_position,
                int(np.floor(frame_position)) % self.study.n_frames,
            )

    def _ecg_gating_active(self) -> bool:
        return self.ecg_recording is not None and self.ecg_recording.beat_count > 0

    def _current_timing(self, beat_index=None):
        if self._ecg_gating_active():
            index = self._playback_beat_index if beat_index is None else int(beat_index)
            index = int(np.clip(index, 0, self._beat_sequence_count() - 1))
            return ecg_informed_cycle_timing(self.ecg_recording, index).timing
        return healthy_adult_cycle_timing(self.heart_rate_spin.value())

    def _cycle_duration_ms(self) -> float:
        return self._current_timing().cycle_ms

    def _sequence_durations_ms(self) -> np.ndarray:
        count = self._beat_sequence_count()
        if self._ecg_gating_active():
            return np.asarray(
                [self.ecg_recording.beat_duration_ms(index) for index in range(count)],
                dtype=float,
            )
        return np.full(count, self._cycle_duration_ms(), dtype=float)

    def _current_sequence_elapsed_ms(self) -> float:
        durations = self._sequence_durations_ms()
        before = float(np.sum(durations[: self._playback_beat_index]))
        return before + self._playback_phase * float(durations[self._playback_beat_index])

    def _phase_name(self, phase: float) -> str:
        if self.study is None:
            return "No study"
        timing = self._current_timing()
        current, _ = timing.phase_at_fraction(phase)
        return current.name

    def _update_cycle_readout(self, phase, frame_position, frame_index):
        timing = self._current_timing()
        duration_ms = timing.cycle_ms
        elapsed_ms = phase * timing.cycle_ms
        phase_record, _ = timing.phase_at_fraction(phase)
        phase_name = phase_record.name
        durations = self._sequence_durations_ms()
        sequence_elapsed_ms = (
            float(np.sum(durations[: self._playback_beat_index])) + elapsed_ms
        )
        sequence_total_ms = float(np.sum(durations))
        beat_prefix = "ECG beat" if self._ecg_gating_active() else "Beat"
        self.cycle_time_label.setText(
            f"{beat_prefix} {self._playback_beat_index + 1}/{self._beat_sequence_count()}  •  "
            f"{elapsed_ms:,.0f} ms/{duration_ms:,.0f} ms  •  total "
            f"{sequence_elapsed_ms:,.0f}/{sequence_total_ms:,.0f} ms"
        )
        display_phase_name = phase_name
        if elapsed_ms <= 0.5:
            display_phase_name = "End-diastole • IVC begins"
        elif abs(elapsed_ms - timing.systole_ms) <= 0.5:
            display_phase_name = "End-systole • IVR begins"
        estimate_prefix = "ECG-gated estimate" if self._ecg_gating_active() else "Estimated"
        self.cycle_phase_label.setText(
            f"{estimate_prefix}: {display_phase_name}  •  {phase * 100.0:.1f}%"
        )
        fraction = frame_position - np.floor(frame_position)
        if fraction <= 0.01:
            stored_position = f"Stored model phase {frame_index + 1}/{self.study.n_frames}"
        else:
            next_frame = (frame_index + 1) % self.study.n_frames
            stored_position = (
                f"Between stored phases {frame_index + 1} → {next_frame + 1} "
                f"({fraction * 100.0:.0f}%)"
            )
        frame_text = f"Motion geometry: {stored_position.lower()}"
        # During playback the source-frame slider and full-width timeline already
        # move. Freezing this sentence avoids a distracting 20-Hz text ticker.
        if not self._timer.isActive() and self.frame_summary.text() != frame_text:
            self.frame_summary.setText(frame_text)
        phase_text = (
            f"{phase_record.start_ms:.0f}–{phase_record.end_ms:.0f} ms • "
            f"AV valves {phase_record.av_valves} • semilunar valves "
            f"{phase_record.semilunar_valves}\n"
            f"{phase_record.teaching_note}"
        )
        if self.phase_detail.text() != phase_text:
            self.phase_detail.setText(phase_text)
        diastasis = timing.phase_by_key("diastasis")
        if self._ecg_gating_active():
            sync = ecg_informed_cycle_timing(
                self.ecg_recording, self._playback_beat_index
            )
            closure_source = sync.boundary_sources.get(
                "semilunar_close", "ECG-informed estimate"
            )
            timing_text = (
                f"Recorded {sync.reference} cycle {timing.cycle_ms:.0f} ms "
                f"({timing.heart_rate_bpm:.1f} bpm) • estimated mechanical systole "
                f"{timing.systole_ms:.0f} ms • diastole {timing.diastole_ms:.0f} ms • "
                f"diastasis {diastasis.duration_ms:.0f} ms. End-systole source: "
                f"{closure_source}. Geometry remains one normalized statistical source cycle."
            )
        else:
            timing_text = (
                f"Estimated mechanical systole {timing.systole_ms:.0f} ms "
                f"({timing.systolic_fraction * 100.0:.0f}%) • diastole "
                f"{timing.diastole_ms:.0f} ms "
                f"({timing.diastolic_fraction * 100.0:.0f}%) • diastasis "
                f"{diastasis.duration_ms:.0f} ms. Estimated normal-adult teaching model. "
                f"{self._beat_sequence_count()}-beat sequence repeats one source cycle."
            )
        if self.timing_summary.text() != timing_text:
            self.timing_summary.setText(timing_text)
        self.phase_timeline.set_cycle(timing, phase)
        self.ed_marker_label.setText("ED • 0 ms")
        self.es_marker_label.setText(f"ES • {timing.systole_ms:,.0f} ms")
        self.next_ed_marker_label.setText(f"next ED • {duration_ms:,.0f} ms")
        self.timeline_markers_layout.setStretch(
            1, max(1, int(round(timing.systolic_fraction * 100.0)))
        )
        self.timeline_markers_layout.setStretch(
            3, max(1, int(round(timing.diastolic_fraction * 100.0)))
        )

    def set_slice(self, slice_index):
        if self.study is None or not getattr(self.study, "has_image_data", True):
            return
        self.canvas.set_position(self.frame_slider.value(), int(slice_index))

    def toggle_playback(self):
        if self.study is None:
            return
        if self._timer.isActive():
            self._pause_playback()
            self._set_phase(self._playback_phase, restart_clock=False)
        else:
            self._playback_start_phase = self._playback_phase
            if self._ecg_gating_active():
                self._playback_start_sequence_ms = self._current_sequence_elapsed_ms()
            else:
                self._playback_start_sequence_position = (
                    self._playback_beat_index + self._playback_phase
                )
            self._playback_clock.restart()
            self._timer.start()
            self.play_button.setText("Pause")

    def _advance_frame(self):
        if self.study is not None:
            if self._ecg_gating_active():
                elapsed_ms = self._playback_clock.elapsed() * self._playback_speed()
                beat_index, beat_phase = self._sequence_state_from_elapsed_ms(
                    self._playback_start_sequence_ms + elapsed_ms
                )
            else:
                elapsed_cycles = (
                    self._playback_clock.elapsed()
                    / self._cycle_duration_ms()
                    * self._playback_speed()
                )
                beat_index, beat_phase = self._sequence_state_from_elapsed_cycles(
                    elapsed_cycles
                )
            self._set_phase(
                beat_phase,
                restart_clock=False,
                beat_index=beat_index,
            )

    def _sequence_state_from_elapsed_cycles(
        self, elapsed_cycles: float
    ) -> tuple[int, float]:
        sequence_count = self._beat_sequence_count()
        sequence_position = (
            self._playback_start_sequence_position + float(elapsed_cycles)
        ) % sequence_count
        beat_index = min(int(np.floor(sequence_position)), sequence_count - 1)
        return beat_index, sequence_position - beat_index

    def _sequence_state_from_elapsed_ms(
        self, elapsed_ms: float
    ) -> tuple[int, float]:
        """Map elapsed time onto variable-duration reviewed ECG cycles."""

        durations = self._sequence_durations_ms()
        total_ms = float(np.sum(durations))
        if total_ms <= 0.0:
            return 0, 0.0
        position_ms = float(elapsed_ms) % total_ms
        cumulative = np.cumsum(durations)
        beat_index = min(
            int(np.searchsorted(cumulative, position_ms, side="right")),
            len(durations) - 1,
        )
        before_ms = float(cumulative[beat_index - 1]) if beat_index else 0.0
        beat_phase = (position_ms - before_ms) / float(durations[beat_index])
        return beat_index, beat_phase

    def _playback_rate_changed(self):
        if self._ecg_gating_active():
            return
        if self._timer.isActive():
            self._playback_start_phase = self._playback_phase
            self._playback_start_sequence_position = (
                self._playback_beat_index + self._playback_phase
            )
            self._playback_clock.restart()
        if self.study is not None:
            self._set_phase(self._playback_phase, restart_clock=False)
        self.timing_source_label.setText(
            f"Model clock • {self.heart_rate_spin.value()} bpm"
        )
        self._update_atlas_evidence_panel()

    def _update_atlas_evidence_panel(self):
        if not hasattr(self, "atlas_evidence_panel"):
            return
        if self.study is None or getattr(self.study, "has_image_data", True):
            return
        timing = self._current_timing()
        view_name = self.view_mode_combo.currentText() or "External anatomy + coronaries"
        source_faithful = self._source_motion_mode()
        wall_study = self._ventricular_wall_study_mode()
        if source_faithful:
            anatomy_text = "FAU/CONRAD source surfaces only"
        elif wall_study:
            anatomy_text = (
                "FAU/CONRAD ventricular and myocardial source surfaces; "
                "atria hidden"
            )
        else:
            anatomy_text = "Z-Anatomy / BodyParts3D atlas, registered to motion"
        if wall_study:
            view_specific_text = (
                "<p><b>Wall-study scope</b><br>Moving LV, RV and myocardium surfaces "
                "are shown from one statistical source model. They expose nested "
                "wall/cavity geometry, but the bundle does not separately segment "
                "histological epicardial and endocardial layers.</p>"
            )
        elif self._valve_orifice_audit_mode():
            view_specific_text = (
                "<p><b>Valve-registration state</b><br><span style='color:#D4AF37'>"
                "Unfitted leaflet and papillary meshes are hidden.</span> The visible "
                "chamber and root openings are the targets for future annular and "
                "outflow-landmark registration.</p>"
            )
        elif self._registered_atlas_overview_mode():
            view_specific_text = (
                "<p><b>Excluded from this clean overview</b><br>Unfitted valve "
                "leaflets and papillary meshes. They remain available only through "
                "manual structure visibility for registration audit.</p>"
            )
        else:
            view_specific_text = ""
        if self._ecg_gating_active():
            rate_text = f"{timing.heart_rate_bpm:.1f} bpm"
            timing_source_text = (
                f"<p><b>Timing source</b><br>Recorded ECG: "
                f"{self.ecg_recording.source_path.name}<br>"
                f"Beat {self._playback_beat_index + 1}: "
                f"{self.ecg_recording.cycle_reference_name} cycle "
                f"<b>{timing.cycle_ms:.0f} ms</b></p>"
            )
            timing_limit_text = (
                "Reviewed P/QRS offsets are marked once on the filtered median template, then "
                "projected onto accepted R triggers. T is not delineated. These offsets inform, "
                "but do not measure, S1/S2 or valve "
                "opening/closure. Mechanical markers are dashed and override estimates only "
                "when manually annotated from PCG/echo. Wall-motion amplitude remains one "
                "normalized statistical source cycle."
            )
            patient_identity_text = (
                "Anatomy: none — registered open-data composite. The app does not "
                "store an identity for the loaded ECG."
            )
        else:
            rate_text = f"{timing.heart_rate_bpm:g} bpm"
            timing_source_text = "<p><b>Timing source</b><br>Model clock</p>"
            timing_limit_text = (
                "Phase boundaries and valve states are teaching overlays. They are "
                "not measured leaflet tracking."
            )
            patient_identity_text = "None — registered open-data composite"
        self.atlas_evidence_panel.setText(
            "<div style='font-size:10.5pt'>"
            "<p style='color:#D4AF37; font-size:12pt; font-weight:700; margin:0 0 8px 0'>"
            "What you are viewing</p>"
            f"<p><b>View</b><br>{view_name}</p>"
            f"<p><b>Anatomy</b><br>{anatomy_text}</p>"
            "<p><b>Wall motion</b><br>FAU 3D+t CT-derived statistical mean; "
            "one normalized source cycle</p>"
            f"{view_specific_text}"
            "<p><b>Patient identity</b><br><span style='color:#D4AF37'>"
            f"{patient_identity_text}</span></p>"
            "<hr>"
            "<p style='color:#D4AF37; font-size:12pt; font-weight:700'>Current timing</p>"
            f"<p><b>{rate_text}</b> &nbsp;•&nbsp; cycle "
            f"{timing.cycle_ms:.0f} ms<br>"
            f"Estimated mechanical systole <b>{timing.systole_ms:.0f} ms</b><br>"
            f"Estimated diastole <b>{timing.diastole_ms:.0f} ms</b></p>"
            f"{timing_source_text}"
            "<p style='color:#AEB6C5'>The familiar 75 bpm shorthand of about 300 ms "
            "systole + 500 ms diastole is a teaching approximation, not a fixed law. "
            "This app labels its empirical/interpolated estimate explicitly.</p>"
            "<hr>"
            f"<p><b>Interpretation limits</b><br>{timing_limit_text}</p>"
            "</div>"
        )

    def jump_to_end_diastole(self):
        if self.study is None:
            return
        frame = int(getattr(self.study, "end_diastole_frame", 0))
        self.set_frame(frame)

    def jump_to_end_systole(self):
        if self.study is None:
            return
        timing = self._current_timing()
        self._set_phase(timing.systolic_fraction, restart_clock=True)

    def _source_motion_mode(self) -> bool:
        return (
            self.view_mode_combo.currentText()
            == "FAU source-motion surfaces (layered)"
        )

    def _ventricular_wall_study_mode(self) -> bool:
        return self.view_mode_combo.currentText() == "Ventricular walls + myocardium"

    def _valve_orifice_audit_mode(self) -> bool:
        return self.view_mode_combo.currentText() == "Valve orifices (registration audit)"

    def _registered_atlas_overview_mode(self) -> bool:
        return (
            self.view_mode_combo.currentText()
            == "Registered atlas overview (unfitted valves hidden)"
        )

    def _source_motion_for_label(self, label: int) -> bool:
        """Use coherent source surfaces for the dedicated wall-thickness study."""

        return self._source_motion_mode() or (
            self._ventricular_wall_study_mode() and int(label) in {1, 2, 5}
        )

    def _orientation_changed(self, text):
        if text != "Free rotation":
            self.set_anatomical_view(text)

    def _camera_interacted(self):
        if self.orientation_combo.currentText() != "Free rotation":
            self.orientation_combo.blockSignals(True)
            self.orientation_combo.setCurrentText("Free rotation")
            self.orientation_combo.blockSignals(False)
        self._update_transparent_draw_order()

    def _saved_opening_rotation(self):
        raw = QSettings(
            "Open 4D Cardiac Anatomy", "Open 4D Cardiac Anatomy"
        ).value(OPENING_ROTATION_SETTING)
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return None
        try:
            rotation = QQuaternion(*[float(value) for value in raw])
        except (TypeError, ValueError):
            return None
        if rotation.isNull():
            return None
        return rotation.normalized()

    def save_current_as_opening_view(self):
        if (
            self.gl_view is None
            or self.study is None
            or not getattr(self.study, "is_open_heart_atlas", False)
        ):
            return
        rotation = self.gl_view.opts.get("rotation")
        if rotation is None or rotation.isNull():
            return
        settings = QSettings(
            "Open 4D Cardiac Anatomy", "Open 4D Cardiac Anatomy"
        )
        settings.setValue(
            OPENING_ROTATION_SETTING,
            [rotation.scalar(), rotation.x(), rotation.y(), rotation.z()],
        )
        settings.sync()
        self.status_label.setText(
            "Current camera saved as the opening atlas view for future launches."
        )

    def restore_builtin_opening_view(self):
        settings = QSettings(
            "Open 4D Cardiac Anatomy", "Open 4D Cardiac Anatomy"
        )
        settings.remove(OPENING_ROTATION_SETTING)
        settings.sync()
        if self.orientation_combo.isEnabled():
            self.orientation_combo.blockSignals(True)
            self.orientation_combo.setCurrentText("Anterior")
            self.orientation_combo.blockSignals(False)
            self.set_anatomical_view("Anterior")
            self.status_label.setText(
                "Calibrated built-in anterior opening view restored."
            )

    def set_anatomical_view(self, name):
        if (
            self.gl_view is None
            or self.study is None
            or not hasattr(self.study, "anatomical_axes")
        ):
            return
        name = str(name)
        if name not in ATLAS_CAMERA_EULER:
            return
        rotation = (
            self._saved_opening_rotation()
            if name == "Anterior"
            else None
        )
        if rotation is None:
            rotation = atlas_camera_rotation(name)
        self.gl_view.setCameraPosition(rotation=rotation)
        self._update_transparent_draw_order()
        self.gl_view.update()

    def reset_view(self):
        if self.gl_view is not None:
            minimum = np.asarray([-80.0, -80.0, -80.0], dtype=float)
            maximum = np.asarray([80.0, 80.0, 80.0], dtype=float)
            if (
                self.study is not None
                and getattr(self.study, "is_open_heart_atlas", False)
            ):
                minima = []
                maxima = []
                source_mode = self._source_motion_mode()
                for label, check in self.chamber_checks.items():
                    if not check.isChecked():
                        continue
                    mesh = self.study.mesh_for_label(
                        self.frame_slider.value(),
                        label,
                        source_faithful=(
                            source_mode or self._source_motion_for_label(label)
                        ),
                    )
                    if mesh is not None:
                        minima.append(mesh[0].min(axis=0))
                        maxima.append(mesh[0].max(axis=0))
                if minima:
                    minimum = np.min(minima, axis=0)
                    maximum = np.max(maxima, axis=0)
            elif self.study is not None and hasattr(self.study, "bounds"):
                minimum, maximum = self.study.bounds(
                    self.frame_slider.value(), self._source_motion_mode()
                )
            elif self.study is not None:
                extent = np.asarray(self.study.spatial_shape) * np.asarray(
                    self.study.spacing_zyx
                )
                minimum, maximum = -0.5 * extent[::-1], 0.5 * extent[::-1]
            centre = 0.5 * (minimum + maximum)
            radius = max(1.0, 0.5 * float(np.linalg.norm(maximum - minimum)))
            fov = float(self.gl_view.opts.get("fov", 60.0))
            distance = radius / max(np.tan(np.deg2rad(fov * 0.5)), 0.2) * 1.45
            self.gl_view.opts["center"] = QVector3D(*[float(v) for v in centre])
            self.gl_view.setCameraPosition(distance=distance)
            self._update_transparent_draw_order()

    def _render_frame(self, frame_index):
        self._render_meshes(frame_index=frame_index, phase=None, time_phase=None)

    def _render_phase(self, phase, time_phase):
        self._render_meshes(
            frame_index=None, phase=float(phase), time_phase=float(time_phase)
        )

    def _render_meshes(self, frame_index=None, phase=None, time_phase=None):
        if self.study is None or self.gl_view is None or gl is None:
            return
        source_mode = self._source_motion_mode() and getattr(
            self.study, "is_open_heart_atlas", False
        )
        active_labels = set()
        try:
            for label, definition in ANATOMY.items():
                if not self.chamber_checks[label].isChecked():
                    continue
                label_source_mode = source_mode or (
                    getattr(self.study, "is_open_heart_atlas", False)
                    and self._source_motion_for_label(label)
                )
                if phase is not None and hasattr(self.study, "mesh_for_phase"):
                    mesh = self.study.mesh_for_phase(
                        phase, label, source_faithful=label_source_mode
                    )
                else:
                    key = (
                        self._study_revision,
                        int(frame_index),
                        label,
                        label_source_mode,
                    )
                    if key not in self._mesh_cache:
                        if getattr(self.study, "is_open_heart_atlas", False):
                            self._mesh_cache[key] = self.study.mesh_for_label(
                                int(frame_index),
                                label,
                                source_faithful=label_source_mode,
                            )
                        else:
                            self._mesh_cache[key] = self.study.mesh_for_label(
                                int(frame_index), label
                            )
                    mesh = self._mesh_cache[key]
                if mesh is None:
                    continue
                vertices, faces = mesh
                if (
                    time_phase is not None
                    and not label_source_mode
                    and label in {12, 13, 14, 15}
                    and self._procedural_valve_overlay_enabled()
                ):
                    overlay_rate = int(
                        round(
                            np.clip(
                                self._current_timing().heart_rate_bpm,
                                MIN_SUPPORTED_HEART_RATE,
                                MAX_SUPPORTED_HEART_RATE,
                            )
                        )
                    )
                    opening = valve_open_fraction(
                        label, time_phase, overlay_rate
                    )
                    if (
                        phase is not None
                        and hasattr(self.study, "procedural_valve_mesh")
                    ):
                        vertices, faces = self.study.procedural_valve_mesh(
                            label, phase, opening, current_vertices=vertices
                        )
                    elif hasattr(self.study, "animate_valve_vertices"):
                        vertices = self.study.animate_valve_vertices(
                            label, vertices, opening
                        )
                faces = self._cutaway_faces(
                    vertices, faces, label, label_source_mode
                )
                if not len(faces):
                    continue
                red, green, blue = self._colour_for_label(label)
                opacity = self._opacity_for_label(label)
                topology_frame = (
                    None
                    if getattr(self.study, "is_open_heart_atlas", False)
                    else int(frame_index)
                )
                normal_key = (
                    self._study_revision,
                    label,
                    label_source_mode,
                    self.cutaway_slider.value(),
                    topology_frame,
                )
                topology_key = normal_key + (len(vertices), len(faces))
                item = self._mesh_items.get(label)
                if item is None:
                    mesh_data = self._mesh_data_with_cached_normals(
                        vertices, faces, normal_key
                    )
                    item = DynamicMeshItem(
                        meshdata=mesh_data,
                        color=(red, green, blue, opacity),
                        smooth=True,
                        computeNormals=True,
                        shader=MESH_SHADER,
                        drawEdges=False,
                    )
                    self.gl_view.addItem(item)
                    self._mesh_items[label] = item
                    self._mesh_topology_keys[label] = topology_key
                elif (
                    self._mesh_topology_keys.get(label) == topology_key
                    and item.vertexes is not None
                ):
                    item.opts["color"] = (red, green, blue, opacity)
                    item.set_vertexes_fast(vertices)
                else:
                    mesh_data = self._mesh_data_with_cached_normals(
                        vertices, faces, normal_key
                    )
                    # Keep the OpenGL item and camera interaction alive. Replacing
                    # every item on every tick caused the visible stop-start motion.
                    item.setMeshData(
                        meshdata=mesh_data,
                        color=(red, green, blue, opacity),
                        smooth=True,
                        computeNormals=True,
                        drawEdges=False,
                    )
                    self._mesh_topology_keys[label] = topology_key
                self._mesh_centres[label] = 0.5 * (
                    np.asarray(vertices).min(axis=0)
                    + np.asarray(vertices).max(axis=0)
                )
                desired_shader = (
                    DEPTH_GLASS_SHADER
                    if self._uses_depth_cued_transparency(opacity)
                    else MESH_SHADER
                )
                if item.opts.get("shader") != desired_shader:
                    item.setShader(desired_shader)
                self._apply_mesh_render_state(item, label, opacity)
                item.setVisible(True)
                active_labels.add(label)
            for label, item in self._mesh_items.items():
                if label not in active_labels:
                    item.setVisible(False)
            self._update_transparent_draw_order()
            self.gl_view.update()
        except MissingImagingDependency as exc:
            self.status_label.setText(str(exc))
        except Exception as exc:
            self.status_label.setText(f"3D surface could not be regenerated: {exc}")

    def _mesh_data_with_cached_normals(self, vertices, faces, normal_key):
        mesh_data = gl.MeshData(vertexes=vertices, faces=faces)
        normals = self._normal_cache.get(normal_key)
        if normals is None or len(normals) != len(vertices):
            normals = np.asarray(mesh_data.vertexNormals(), dtype=np.float32)
            self._normal_cache[normal_key] = normals
        else:
            # The atlas topology is constant through the cycle. Reusing reference
            # lighting normals avoids a very expensive normal recomputation while
            # the anatomical vertices continue to move. Normals affect shading
            # only; they never alter geometry or spatial measurements.
            mesh_data._vertexNormals = normals
        return mesh_data

    def _opacity_for_label(self, label: int) -> float:
        scale = self.opacity_slider.value() / 100.0
        mode = self.view_mode_combo.currentText()
        if mode == "External anatomy + coronaries":
            # Exact v0.6.3 external opacity: every exterior structure, including
            # the epicardial vessels, shares one near-opaque surface treatment.
            # The dedicated coronary preset separately keeps vessels fully crisp.
            base = 0.98
        elif mode == "Ventricular walls + myocardium":
            # Three co-registered source surfaces: cavity boundaries stay
            # readable through the more subdued myocardial envelope.
            base = 0.56 if label in {1, 2} else (0.30 if label == 5 else 0.18)
        elif mode == "Four chambers (ventricles emphasized)":
            if label in {1, 2}:
                base = 0.54
            elif label in {3, 4}:
                base = 0.11
            else:
                base = 0.55
        elif mode == "Valve orifices (registration audit)":
            if label in {1, 2}:
                base = 0.24
            elif label in {3, 4}:
                base = 0.10
            elif label in {6, 7}:
                base = 0.15
            else:
                base = 0.18
        elif mode == "Coronary circulation":
            base = 1.0 if label in {11, 17} else 0.20
        elif mode == "FAU source-motion surfaces (layered)":
            base = 0.68 if label == 5 else (0.46 if label in CHAMBERS else 0.76)
        elif mode == "Registered atlas overview (unfitted valves hidden)":
            if label in CHAMBERS:
                base = 0.62
            elif label in {11, 17}:
                base = 1.0
            elif label in {12, 13, 14, 15}:
                base = 1.0
            elif label == 16:
                base = 0.68
            else:
                base = 0.84
        else:
            base = 0.90
        return float(np.clip(base * scale, 0.05, 1.0))

    def _uses_v063_exterior_rendering(self) -> bool:
        return self.view_mode_combo.currentText() in {
            "External anatomy + coronaries",
            "Coronary circulation",
        }

    def _preserves_v063_external_movie(self) -> bool:
        """Keep the user-approved v0.6.3 exterior movie treatment intact."""

        return self.view_mode_combo.currentText() == "External anatomy + coronaries"

    def _uses_depth_cued_transparency(self, opacity: float) -> bool:
        return opacity < 0.985 and not self._preserves_v063_external_movie()

    @staticmethod
    def _procedural_valve_overlay_enabled() -> bool:
        """Procedural leaflet discs are withheld until annuli are registered."""

        return False

    def _apply_mesh_render_state(self, item, label: int, opacity: float):
        if self._preserves_v063_external_movie():
            # This is the complete v0.6.3 GL treatment: ordinary pyqtgraph
            # opaque/translucent presets, no per-structure draw-order hierarchy.
            # Keep it outside the newer glass renderer so an internal-view change
            # cannot alter the user-validated external movie.
            item.setGLOptions("opaque" if opacity >= 0.985 else "translucent")
            item.setDepthValue(0.0)
            return
        item.setGLOptions(self._gl_options_for_opacity(opacity))
        item.setDepthValue(self._depth_for_label(label))

    def _gl_options_for_opacity(self, opacity: float):
        """Blend shells without letting them punch false holes into later items."""

        if self._preserves_v063_external_movie():
            # Preserve the v0.6.3 surface treatment exactly for the two presets
            # the user selected as the visual reference.
            return "opaque" if opacity >= 0.985 else "translucent"
        if GL is None:
            return "opaque" if opacity >= 0.985 else "translucent"
        if opacity >= 0.985:
            return {
                GL.GL_DEPTH_TEST: True,
                GL.GL_BLEND: False,
                GL.GL_CULL_FACE: False,
                "glDepthMask": (GL.GL_TRUE,),
            }
        return {
            GL.GL_DEPTH_TEST: True,
            GL.GL_BLEND: True,
            GL.GL_CULL_FACE: False,
            "glBlendFuncSeparate": (
                GL.GL_SRC_ALPHA,
                GL.GL_ONE_MINUS_SRC_ALPHA,
                GL.GL_ONE,
                GL.GL_ONE_MINUS_SRC_ALPHA,
            ),
            "glDepthMask": (GL.GL_FALSE,),
        }

    def _depth_for_label(self, label: int) -> float:
        """Draw glass-like context first and crisp teaching structures last."""

        opacity = self._opacity_for_label(label)
        if self._preserves_v063_external_movie():
            return 0.0
        if opacity < 0.985:
            return -1000.0
        if label in {11, 17}:
            return 20.0
        if label in {12, 13, 14, 15, 16}:
            return 10.0
        return 0.0

    def _update_transparent_draw_order(self):
        """Sort translucent structures far-to-near for the current camera.

        Alpha blending is order dependent. Pyqtgraph otherwise leaves each
        anatomy item at one static depth value, so rotating the heart can make
        a rear chamber look as though it sits in front. Camera-space Z gives
        every visible translucent structure a live painter's-order key, while
        opaque valves and vessels retain their final-pass priorities.
        """

        if self.gl_view is None or not self._mesh_items:
            return
        try:
            view_matrix = self.gl_view.viewMatrix()
            for label, item in self._mesh_items.items():
                if not item.visible():
                    continue
                opacity = self._opacity_for_label(label)
                if not self._uses_depth_cued_transparency(opacity):
                    item.setDepthValue(self._depth_for_label(label))
                    continue
                centre = self._mesh_centres.get(label)
                if centre is None:
                    item.setDepthValue(-1000.0)
                    continue
                camera_point = view_matrix.map(
                    QVector3D(*[float(value) for value in centre])
                )
                # Objects in front of the camera have negative view-space Z;
                # more-negative (farther) items sort first in GLViewWidget.
                item.setDepthValue(-1000.0 + float(camera_point.z()))
        except Exception:
            # Rendering must remain usable on older Qt/OpenGL combinations even
            # if camera-space mapping is unavailable; the shader still provides
            # the surface cue and the static order remains safe.
            for label, item in self._mesh_items.items():
                if item.visible():
                    item.setDepthValue(self._depth_for_label(label))

    def _colour_for_label(self, label: int):
        mode = self.view_mode_combo.currentText()
        if mode == "FAU source-motion surfaces (layered)":
            palette = {
                1: (0.74, 0.24, 0.27),
                2: (0.18, 0.56, 0.65),
                3: (0.66, 0.24, 0.54),
                4: (0.22, 0.58, 0.38),
                5: (0.82, 0.24, 0.25),
                6: (0.86, 0.31, 0.27),
            }
            if label in palette:
                return palette[label]
        if mode in {"External anatomy + coronaries", "Coronary circulation"}:
            if label in V063_EXTERNAL_PALETTE:
                return tuple(
                    min(1.0, channel * V063_EXTERNAL_BRIGHTNESS)
                    for channel in V063_EXTERNAL_PALETTE[label]
                )
        if mode == "Registered atlas overview (unfitted valves hidden)":
            if label in V063_EXTERNAL_PALETTE:
                return V063_EXTERNAL_PALETTE[label]
        red, green, blue = ANATOMY[label].colour_rgb
        return red / 255.0, green / 255.0, blue / 255.0

    def _cutaway_faces(self, vertices, faces, label, source_mode):
        # Retired in v0.7.0. Deleting triangles from a surface-only atlas produces
        # an uncapped, jagged hole that looks like anatomy but has no valid cut-face
        # geometry. Internal teaching now isolates the real valve/papillary meshes.
        return faces

    def _update_mesh_visibility(self):
        if self.study is not None:
            self._set_phase(self._playback_phase, restart_clock=False)

    def _apply_view_preset(self):
        mode = self.view_mode_combo.currentText()
        visible = set(ANATOMY)
        cutaway = self.cutaway_slider.value()
        if mode == "External anatomy + coronaries":
            visible = {1, 2, 3, 4, 6, 7, 8, 9, 10, 11, 17}
            cutaway = 0
        elif mode == "Ventricular walls + myocardium":
            visible = {1, 2, 5}
            cutaway = 0
        elif mode == "Four chambers (ventricles emphasized)":
            visible = {1, 2, 3, 4}
            cutaway = 0
        elif mode == "Valve orifices (registration audit)":
            # Do not present the current undersized, displaced procedural
            # leaflets or incomplete papillary meshes as fitted anatomy.
            visible = {1, 2, 3, 4, 6, 7}
            cutaway = 0
        elif mode == "Coronary circulation":
            visible = {1, 2, 3, 4, 11, 17}
            cutaway = 0
        elif mode == "FAU source-motion surfaces (layered)":
            visible = {1, 2, 3, 4, 5, 6}
            cutaway = 0
        elif mode == "Registered atlas overview (unfitted valves hidden)":
            visible = set(ANATOMY) - {12, 13, 14, 15, 16}
            cutaway = 0
        self.cutaway_slider.blockSignals(True)
        self.cutaway_slider.setValue(cutaway)
        self.cutaway_slider.blockSignals(False)
        for label, check in self.chamber_checks.items():
            check.blockSignals(True)
            check.setChecked(label in visible)
            check.blockSignals(False)
        self._invalidate_all_meshes()
        self._set_phase(self._playback_phase, restart_clock=False)
        self._update_atlas_evidence_panel()
        self.reset_view()
        if getattr(self.study, "is_open_heart_atlas", False):
            if mode == "FAU source-motion surfaces (layered)":
                self.status_label.setText(
                    "SOURCE-MOTION VIEW — layered CT-derived statistical mean surfaces from "
                    "FAU/CONRAD; myocardium is emphasized while cavities remain visible."
                )
            elif mode == "Valve orifices (registration audit)":
                self.status_label.setText(
                    "VALVE REGISTRATION AUDIT — displaced procedural leaflets and incomplete "
                    "papillary meshes are withheld; visible chamber/root openings are landmark targets."
                )
            elif mode == "Ventricular walls + myocardium":
                self.status_label.setText(
                    "VENTRICULAR WALL STUDY — coherent FAU LV, RV and myocardium source "
                    "surfaces; atria and unfitted valve apparatus are hidden."
                )
            elif mode == "Four chambers (ventricles emphasized)":
                self.status_label.setText(
                    "FOUR-CHAMBER VIEW — ventricular surfaces are emphasized while atria "
                    "remain low-opacity context; unfitted valve apparatus is excluded."
                )
            elif mode == "Registered atlas overview (unfitted valves hidden)":
                self.status_label.setText(
                    "REGISTERED ATLAS OVERVIEW — unfitted valves and papillary meshes are "
                    "withheld; junctions remain composite anatomy, not one stitched patient."
                )
            else:
                self.status_label.setText(
                    "OPEN-DATA COMPOSITE — detailed Z-Anatomy/BodyParts3D structures "
                    "registered to FAU CT-derived statistical cardiac motion. Not one patient."
                )

    def show_quality_report(self):
        if self.study is None:
            return
        report = self.study.quality_report()
        missing = ", ".join(report["missing_core_chambers"]) or "none"
        composite = ", ".join(report["composite_or_synthetic_structures"]) or "none"
        jumps = sum(len(v) for v in report["temporal_volume_jump_frames"].values())
        message = (
            f"Present structures: {', '.join(report['present_structures']) or 'none'}\n"
            f"Missing core chambers: {missing}\n"
            f"Composite or synthetic: {composite}\n"
            f"Large temporal-volume jumps flagged: {jumps}\n\n"
            "These are explainable consistency checks, not clinical validation. "
            "Before publication, inspect every flagged frame and compare segmentation "
            "against the source images in all available planes."
        )
        if getattr(self.study, "is_open_heart_atlas", False):
            attachment = report.get("surface_vessel_attachment", {})
            vessel_distances = {}
            for vessel_label in (11, 17):
                vessel_report = next(
                    (
                        item
                        for item in attachment.get("reports", [])
                        if item.get("vessel_label") == vessel_label
                    ),
                    {},
                )
                vessel_distances[vessel_label] = (
                    vessel_report.get("before_end_systole", {}).get(
                        "median_mm", float("nan")
                    ),
                    vessel_report.get("after_end_systole", {}).get(
                        "median_mm", float("nan")
                    ),
                )
            artery_before, artery_after = vessel_distances[11]
            vein_before, vein_after = vessel_distances[17]
            message = (
                f"Detailed atlas structures: {', '.join(report['present_structures'])}\n"
                "Motion-source structures: myocardium, RA, LA, RV, aorta, LV\n"
                "Temporal source: one normalized statistical cycle; no consecutive beats\n"
                f"Atlas-to-motion landmark RMS: {report['atlas_registration_landmark_rms_mm']:.1f} mm\n"
                f"Median coronary-artery-to-surface distance at ES: "
                f"{artery_before:.2f} → {artery_after:.2f} mm\n"
                f"Median cardiac-vein-to-surface distance at ES: "
                f"{vein_before:.2f} → {vein_after:.2f} mm\n"
                "Cavity-volume reporting: disabled\n\n"
                "The detailed view is a registered composite. The FAU source-motion "
                "preset is the source-faithful view of the CT-derived statistical model. "
                "Neither represents one measured patient and neither is diagnostically validated."
            )
        QMessageBox.information(self, "Cardiac anatomy quality report", message)

    def _rebuild_current_meshes(self):
        if self.study is not None:
            self._set_phase(self._playback_phase, restart_clock=False)

    def _invalidate_all_meshes(self):
        self._study_revision += 1
        self._mesh_cache.clear()
        self._normal_cache.clear()

    def _mask_was_edited(self, frame_index, label):
        self._study_revision += 1
        self._mesh_cache.clear()
        self._normal_cache.clear()
        self._mesh_refresh_timer.start()
        self.status_label.setText(
            "Mask edited. Inspect adjacent slices and frames; source MRI remains unchanged."
        )

    def _refresh_after_edit(self):
        if self.study is not None:
            self.set_frame(self.frame_slider.value())

    def _update_brush(self):
        self.canvas.active_label = int(self.label_combo.currentData())
        self.canvas.brush_radius = int(self.brush_spin.value())
        self.canvas.erase = self.erase_check.isChecked()

    def propagate_masks(self):
        if self.study is None or not getattr(self.study, "has_image_data", True):
            return
        reference = self.frame_slider.value()
        answer = QMessageBox.question(
            self,
            "Replace masks on other frames?",
            "Optical-flow propagation will keep the current frame and replace masks "
            "on every other frame. This is not clinically validated and every frame "
            "must be checked. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        progress = QProgressDialog(
            "Propagating chamber masks through the cardiac cycle…",
            "Cancel",
            0,
            max(1, self.study.n_frames - 1),
            self,
        )
        progress.setWindowModality(Qt.WindowModal)

        def update_progress(done, total):
            progress.setMaximum(max(1, total))
            progress.setValue(done)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise RuntimeError("Propagation cancelled; inspect all masks before use")

        try:
            self.study.propagate_from_reference(reference, update_progress)
            self._invalidate_all_meshes()
            self.set_frame(reference)
            self.status_label.setText(
                "Automatic temporal propagation complete. Now inspect and manually correct every frame."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Propagation stopped", str(exc))
        finally:
            progress.close()

    def export_movie(self):
        if self.study is None or self.gl_view is None:
            return
        if getattr(self.study, "has_image_data", True) and not np.any(self.study.labels):
            QMessageBox.warning(
                self,
                "No chamber surfaces",
                "Load, paint or propagate at least one chamber mask before exporting.",
            )
            return
        if imageio is None:
            QMessageBox.warning(
                self, "Export dependency missing", "Install imageio from requirements.txt."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export rotating cardiac-cycle movie",
            "rotating_cardiac_cycle.gif",
            "Animated GIF (*.gif);;MP4 video (*.mp4)",
        )
        if not path:
            return
        output_path = Path(path)
        suffix = output_path.suffix.lower()
        if suffix not in {".gif", ".mp4"}:
            output_path = output_path.with_suffix(".gif")
            suffix = ".gif"
        original_phase = self._playback_phase
        original_beat_index = self._playback_beat_index
        was_playing = self._timer.isActive()
        self._timer.stop()
        export_fps = 30
        export_beat_count = self._beat_sequence_count()
        sequence_duration_ms = float(np.sum(self._sequence_durations_ms()))
        display_sequence_seconds = (
            sequence_duration_ms / 1000.0 / self._playback_speed()
        )
        export_frame_count = max(
            self.study.n_frames * export_beat_count,
            int(round(export_fps * display_sequence_seconds)),
        )
        progress = QProgressDialog(
            "Rendering rotating cardiac-cycle movie…",
            "Cancel",
            0,
            export_frame_count,
            self,
        )
        progress.setWindowModality(Qt.WindowModal)
        frames = []
        try:
            self.reset_view()
            for index in range(export_frame_count):
                if progress.wasCanceled():
                    raise RuntimeError("Movie export cancelled")
                if self._ecg_gating_active():
                    beat_index, beat_phase = self._sequence_state_from_elapsed_ms(
                        index / export_frame_count * sequence_duration_ms
                    )
                else:
                    sequence_position = index / export_frame_count * export_beat_count
                    beat_index = min(
                        int(np.floor(sequence_position)), export_beat_count - 1
                    )
                    beat_phase = sequence_position - beat_index
                self._set_phase(
                    beat_phase,
                    restart_clock=False,
                    beat_index=beat_index,
                )
                self.gl_view.orbit(360.0 / export_frame_count, 0.0)
                QApplication.processEvents()
                qimage = self.gl_view.grabFramebuffer()
                qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
                width, height = qimage.width(), qimage.height()
                pointer = qimage.bits()
                pointer.setsize(qimage.byteCount())
                frame = np.frombuffer(pointer, np.uint8).reshape(height, width, 4).copy()
                frames.append(frame[..., :3])
                progress.setValue(index + 1)
            if suffix == ".gif":
                imageio.mimsave(
                    str(output_path),
                    frames,
                    duration=1.0 / export_fps,
                    loop=0,
                )
            else:
                imageio.mimsave(
                    str(output_path),
                    frames,
                    fps=export_fps,
                    codec="libx264",
                )
            self._sync_provenance_from_fields()
            self._write_sidecar(output_path, "rotating_movie")
            self.status_label.setText(f"Movie and provenance sidecar saved: {output_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Could not export movie", str(exc))
        finally:
            progress.close()
            self._set_phase(
                original_phase,
                restart_clock=False,
                beat_index=original_beat_index,
            )
            if was_playing:
                self._playback_start_phase = self._playback_phase
                if self._ecg_gating_active():
                    self._playback_start_sequence_ms = self._current_sequence_elapsed_ms()
                else:
                    self._playback_start_sequence_position = (
                        self._playback_beat_index + self._playback_phase
                    )
                self._playback_clock.restart()
                self._timer.start()

    def _sync_provenance_from_fields(self):
        if self.study is None:
            return
        self.study.provenance.update(
            {
                "dataset": self.dataset_edit.text().strip(),
                "source_url": self.source_edit.text().strip(),
                "license": self.license_edit.text().strip(),
                "citation": self.citation_edit.text().strip(),
            }
        )

    def _write_sidecar(self, output_path, artifact_type):
        if self.study is None:
            return
        sidecar = Path(str(output_path) + ".provenance.json")
        source_mode = self._source_motion_mode() and getattr(
            self.study, "is_open_heart_atlas", False
        )
        if hasattr(self.study, "available_labels"):
            present_labels = self.study.available_labels(source_mode)
        else:
            present_labels = {
                label for label in ANATOMY if np.any(self.study.labels == label)
            }
        spacing = getattr(self.study, "spacing_zyx", None)
        timing = self._current_timing()
        sequence_duration_ms = float(np.sum(self._sequence_durations_ms()))
        if self._ecg_gating_active():
            ecg_gating = {
                "enabled": True,
                "source_filename": self.ecg_recording.source_path.name,
                "source_sha256": self.ecg_recording.source_sha256,
                "channel": self.ecg_recording.channel_name,
                "time_column": self.ecg_recording.time_column_name,
                "sampling_rate_hz": self.ecg_recording.fs_hz,
                "recording_duration_s": self.ecg_recording.duration_s,
                "reviewed_r_markers": int(len(self.ecg_recording.r_peaks)),
                "reviewed_template_offsets": int(
                    len(self.ecg_recording.median_template.landmark_offsets_s)
                    if self.ecg_recording.median_template is not None else 0
                ),
                "median_template_included_beats": int(
                    len(self.ecg_recording.median_template.included_beat_indices)
                    if self.ecg_recording.median_template is not None else 0
                ),
                "median_template_excluded_beats": int(
                    len(self.ecg_recording.median_template.excluded_beat_indices)
                    if self.ecg_recording.median_template is not None else 0
                ),
                "template_offsets_ms": {
                    kind: float(value * 1000.0)
                    for kind, value in (
                        self.ecg_recording.median_template.landmark_offsets_s.items()
                        if self.ecg_recording.median_template is not None else []
                    )
                },
                "manual_mechanical_landmarks": int(sum(
                    item.group == "mechanical" for item in self.ecg_recording.landmarks
                )),
                "cycle_reference": self.ecg_recording.cycle_reference_name,
                "annotations": [
                    {
                        "kind": item.kind,
                        "time_s": float(self.ecg_recording.time_s[item.sample_index]),
                        "beat_index": int(item.beat_index),
                        "source": item.source,
                        "confidence": float(item.confidence),
                    }
                    for item in self.ecg_recording.landmarks
                    if item.source == "manual" and item.group == "mechanical"
                ],
                "usable_rr_cycles": self.ecg_recording.beat_count,
                "selected_rr_cycles": self._beat_sequence_count(),
                "selected_rr_durations_ms": self._sequence_durations_ms().tolist(),
                "raw_samples_modified": False,
                "review_filter_only": {
                    "bandpass_hz": [0.5, 40.0],
                    "notch_hz": 50.0,
                    "zero_phase": True,
                },
                "scope": (
                    "Reviewed median-template P/QRS offsets and accepted R triggers share the "
                    "animation clock and inform phase placement. T is not delineated. Geometry "
                    "and motion amplitude remain one normalized "
                    "FAU/CONRAD statistical source cycle; valve events are estimates unless "
                    "a manual PCG/echo-derived mechanical annotation is present."
                ),
            }
        else:
            ecg_gating = {"enabled": False}
        payload = {
            "artifact_type": artifact_type,
            "created_by": "Open 4D Cardiac Anatomy",
            "not_for_diagnosis": True,
            "array_convention": "time,z,y,x",
            "chamber_labels": {
                str(label): definition.display_name
                for label, definition in ANATOMY.items()
            },
            "structure_evidence": {
                ANATOMY[label].short_name: (
                    self.study.evidence_for_label(label, source_mode)
                    if hasattr(self.study, "evidence_for_label")
                    else self.study.evidence.get(label, "unknown")
                )
                for label in sorted(present_labels)
            },
            "quality_report": self.study.quality_report(),
            "frames": self.study.n_frames,
            "playback_heart_rate_bpm": timing.heart_rate_bpm,
            "display_cycle_duration_ms": timing.cycle_ms,
            "playback_sequence_beats": self._beat_sequence_count(),
            "playback_sequence_duration_ms": sequence_duration_ms,
            "multi_beat_source_evidence": (
                "No consecutive beats in the bundled source: this sequence repeats "
                "one normalized FAU/CONRAD statistical mean cardiac cycle."
            ),
            "playback_speed_multiplier": self._playback_speed(),
            "exported_sequence_duration_ms": (
                sequence_duration_ms / self._playback_speed()
            ),
            "ecg_gating": ecg_gating,
            "estimated_mechanical_systole_ms": timing.systole_ms,
            "estimated_mechanical_diastole_ms": timing.diastole_ms,
            "estimated_systolic_fraction": timing.systolic_fraction,
            "estimated_diastolic_fraction": timing.diastolic_fraction,
            "estimated_phase_timing_ms": {
                phase.key: {
                    "name": phase.name,
                    "start": phase.start_ms,
                    "end": phase.end_ms,
                    "duration": phase.duration_ms,
                    "av_valves": phase.av_valves,
                    "semilunar_valves": phase.semilunar_valves,
                }
                for phase in timing.phases
            },
            "rate_timing_model": TIMING_MODEL_NAME,
            "rate_timing_model_dois": list(TIMING_MODEL_DOIS),
            "rate_timing_limitation": (
                "Healthy-adult aggregate timing only; geometry amplitude, flow, "
                "preload, afterload and contractility are not re-simulated; imported "
                "patient timing is not inferred from NIfTI."
            ),
            "temporal_display_interpolation": (
                "linear between stored model phases"
                if hasattr(self.study, "mesh_for_phase")
                else "none; discrete source frames"
            ),
            "spacing_zyx_mm": list(spacing) if spacing is not None else None,
            "view_mode": self.view_mode_combo.currentText(),
            "source_faithful_motion_view": source_mode,
            "procedural_valve_motion": False,
            "procedural_valve_topology": None,
            "valve_registration_state": (
                "withheld from clean presets; source atlas leaflets remain incomplete "
                "and unfitted, pending annular/outflow landmark registration"
                if getattr(self.study, "is_open_heart_atlas", False)
                else None
            ),
            "transparency_rendering": (
                "v0.6.3-style near-opaque external anatomy; role-specific transparent "
                "internal presets; crisp vessels and leaflets render afterward"
            ),
            "cutaway_geometry": "disabled: uncapped triangle deletion retired in v0.7.0",
            "provenance": dict(self.study.provenance),
        }
        sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
