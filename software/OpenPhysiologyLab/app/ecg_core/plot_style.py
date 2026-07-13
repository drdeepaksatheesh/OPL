
from __future__ import annotations

from .config import (
    ECG_BG,
    ECG_GRID_ALPHA,
    ECG_TEXT,
    ECG_PANEL_BG,
    ECG_PANEL_BORDER,
)


def apply_ecg_plot_style(plot, bottom_label: str = "Time (s)", left_label: str = "ECG"):
    """Apply common OPL ECG pyqtgraph styling."""
    try:
        plot.setBackground(ECG_BG)
    except Exception:
        pass
    try:
        plot.showGrid(x=True, y=True, alpha=ECG_GRID_ALPHA)
    except Exception:
        pass
    try:
        plot.setLabel("bottom", bottom_label)
        plot.setLabel("left", left_label)
    except Exception:
        pass
    try:
        plot.getAxis("bottom").enableAutoSIPrefix(False)
        plot.getAxis("left").enableAutoSIPrefix(False)
    except Exception:
        pass


def text_box_stylesheet() -> str:
    """Shared stylesheet for right-side ECG explanation/measurement boxes."""
    return (
        f"QTextEdit {{ color: {ECG_TEXT}; background-color: {ECG_PANEL_BG}; "
        f"border: 1px solid {ECG_PANEL_BORDER}; border-radius: 4px; }}"
    )


def group_box_stylesheet() -> str:
    """Shared stylesheet for ECG group boxes."""
    return "QGroupBox { color: #E6C200; font-weight: bold; }"


def title_stylesheet() -> str:
    return "font-size: 18px; font-weight: bold; color: #E6C200;"


def subtitle_stylesheet() -> str:
    return "color: #AAB3C0;"
