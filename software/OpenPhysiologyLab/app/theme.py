"""
OpenPhysiologyLab Clean Black-Gold Opal Theme.

Design:
- black/charcoal base
- silver-white readable text
- muted gold as the global accent
- emerald only for pass/active/ready
- red only for fail/clipping
- cyan/magenta/violet mainly for plots and small signal/event accents
"""

BLACK_OPAL = {
    # Base surfaces
    'main_bg': '#050608',
    'panel_bg': '#0A0D12',
    'panel_bg_2': '#10141B',
    'group_bg': '#0E1218',
    'inspector_bg': '#080B10',
    'field_bg': '#030406',

    # Borders
    'border': '#2D333F',
    'border_soft': '#202630',
    'border_bright': '#4A5263',

    # Text
    'text': '#F2F2F4',
    'text_secondary': '#C6CBD5',
    'text_muted': '#8F96A6',
    'silver': '#D7D9DE',

    # Accent palette
    'gold': '#D4AF37',
    'amber': '#D4AF37',
    'orange': '#D4AF37',
    'emerald': '#50C878',
    'green': '#50C878',
    'cyan': '#25D8FF',
    'magenta': '#FF3FCB',
    'violet': '#9B6DFF',
    'blue': '#3D7BFF',

    # States
    'pass': '#50C878',
    'warning': '#D4AF37',
    'caution': '#D4AF37',
    'fail': '#FF5C5C',
}

LIGHT = {
    'main_bg': '#F4F6F8',
    'panel_bg': '#FFFFFF',
    'panel_bg_2': '#EDF1F5',
    'group_bg': '#FFFFFF',
    'inspector_bg': '#FFFFFF',
    'field_bg': '#FFFFFF',

    'border': '#C7CCD1',
    'border_soft': '#D9DDE2',
    'border_bright': '#AAB2BE',

    'text': '#1F2328',
    'text_secondary': '#4A515A',
    'text_muted': '#69707A',
    'silver': '#45505C',

    'gold': '#8A6500',
    'amber': '#8A6500',
    'orange': '#8A6500',
    'emerald': '#007A3D',
    'green': '#007A3D',
    'cyan': '#007C9E',
    'magenta': '#B6007D',
    'violet': '#4B2BC9',
    'blue': '#005BD1',

    'pass': '#007A3D',
    'warning': '#8A6500',
    'caution': '#8A6500',
    'fail': '#B42318',
}

PLOT_DARK = {
    'background': '#020304',
    'axis': '#C6CBD5',
    'grid': (85, 90, 100),

    # Functional plot colours
    'raw': (80, 200, 120),          # cyan
    'filtered': (212, 175, 55),     # muted gold
    'rr': (80, 200, 120),           # emerald
    'peak': (255, 92, 92),          # red
    'marker': (255, 63, 203),       # magenta
    'selection': (155, 109, 255, 45),
    'selection_edge': (155, 109, 255),
    'cursor': (212, 175, 55),
}

PLOT_LIGHT = {
    'background': '#FFFFFF',
    'axis': '#1F2328',
    'grid': (160, 165, 172),

    'raw': (0, 122, 61),
    'filtered': (138, 101, 0),
    'rr': (0, 122, 61),
    'peak': (180, 35, 45),
    'marker': (170, 40, 160),
    'selection': (155, 109, 255, 55),
    'selection_edge': (95, 60, 190),
    'cursor': (138, 101, 0),
}


def get_plot_palette(mode='dark'):
    return PLOT_LIGHT if str(mode).lower() == 'light' else PLOT_DARK


def build_stylesheet(mode='dark'):
    c = LIGHT if str(mode).lower() == 'light' else BLACK_OPAL

    return f"""
    QMainWindow {{
        background-color: {c['main_bg']};
    }}

    QWidget {{
        background-color: {c['panel_bg']};
        color: {c['text']};
        font-family: Segoe UI, Arial;
        font-size: 10pt;
    }}

    QLabel {{
        color: {c['text']};
        background-color: transparent;
    }}

    /* Tabs */

    QTabWidget::pane {{
        border: 1px solid {c['border']};
        background-color: {c['main_bg']};
        top: -1px;
    }}

    QTabBar::tab {{
        background-color: {c['panel_bg_2']};
        color: {c['text_secondary']};
        padding: 7px 18px;
        border: 1px solid {c['border']};
        border-bottom: none;
        margin-right: 2px;
        min-width: 85px;
    }}

    QTabBar::tab:selected {{
        background-color: {c['main_bg']};
        color: {c['gold']};
        font-weight: bold;
        border-top: 2px solid {c['gold']};
    }}

    QTabBar::tab:hover {{
        background-color: {c['group_bg']};
        color: {c['gold']};
        border-top: 2px solid {c['gold']};
    }}

    /* Cards and group boxes */

    QGroupBox {{
        background-color: {c['group_bg']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        margin-top: 10px;
        padding-top: 9px;
        font-weight: bold;
        color: {c['gold']};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 9px;
        padding: 0px 6px;
        background-color: {c['group_bg']};
        color: {c['gold']};
        font-weight: bold;
    }}

    QFrame {{
        background-color: {c['panel_bg']};
        border: none;
    }}

    QFrame#heroFrame {{
        background-color: {c['panel_bg_2']};
        border: 1px solid {c['border']};
        border-radius: 12px;
    }}

    QFrame#contentFrame {{
        background-color: {c['panel_bg']};
        border: 1px solid {c['border_soft']};
        border-radius: 10px;
    }}

    /* Buttons */

    QPushButton {{
        background-color: {c['panel_bg_2']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        padding: 5px 10px;
        min-height: 22px;
    }}

    QPushButton:hover {{
        background-color: {c['group_bg']};
        border: 1px solid {c['gold']};
        color: {c['gold']};
    }}

    QPushButton:pressed {{
        background-color: {c['main_bg']};
        border: 1px solid {c['gold']};
        color: {c['text']};
    }}

    QPushButton:disabled {{
        background-color: {c['border_soft']};
        color: {c['text_muted']};
        border: 1px solid {c['border_soft']};
    }}

    QPushButton#primaryButton {{
        background-color: #17140A;
        color: {c['text']};
        border: 1px solid {c['gold']};
        font-weight: bold;
        padding: 7px 14px;
    }}

    QPushButton#primaryButton:hover {{
        background-color: #211B0B;
        border: 1px solid {c['gold']};
        color: {c['gold']};
    }}

    /* Inputs */

    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QLineEdit {{
        background-color: {c['field_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 4px 6px;
        min-height: 22px;
    }}

    QComboBox:hover,
    QDoubleSpinBox:hover,
    QSpinBox:hover,
    QLineEdit:hover {{
        border: 1px solid {c['gold']};
    }}

    QComboBox:focus,
    QDoubleSpinBox:focus,
    QSpinBox:focus,
    QLineEdit:focus {{
        border: 1px solid {c['gold']};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {c['panel_bg']};
        color: {c['text']};
        selection-background-color: {c['group_bg']};
        selection-color: {c['gold']};
        border: 1px solid {c['border']};
    }}

    /* Checkboxes */

    QCheckBox {{
        color: {c['text']};
        spacing: 6px;
        background-color: transparent;
    }}

    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 2px;
        border: 1px solid {c['border']};
        background-color: {c['field_bg']};
    }}

    QCheckBox::indicator:checked {{
        background-color: {c['emerald']};
        border: 1px solid {c['emerald']};
    }}

    QCheckBox::indicator:hover {{
        border: 1px solid {c['gold']};
    }}

    /* Text panels */

    QTextEdit {{
        background-color: {c['inspector_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        padding: 6px;
        selection-background-color: {c['gold']};
        selection-color: #000000;
    }}

    QTextEdit#dashboardCard {{
        background-color: rgba(8, 11, 16, 235);
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 10px;
    }}

    /* Splitters and scrollbars */

    QSplitter::handle {{
        background-color: {c['border']};
    }}

    QSplitter::handle:hover {{
        background-color: {c['gold']};
    }}

    QScrollBar:vertical {{
        background-color: {c['main_bg']};
        width: 13px;
        margin: 0px;
    }}

    QScrollBar::handle:vertical {{
        background-color: {c['border']};
        min-height: 24px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {c['gold']};
    }}

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: {c['main_bg']};
        height: 13px;
        margin: 0px;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {c['border']};
        min-width: 24px;
        border-radius: 5px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {c['gold']};
    }}

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    QToolTip {{
        background-color: {c['main_bg']};
        color: {c['text']};
        border: 1px solid {c['gold']};
        padding: 6px;
    }}
    """
