"""Modern dark-mode styling for VisOPU application."""

# ═══════════════════════════════════════════════════════════════════
# COLOR PALETTE
# ═══════════════════════════════════════════════════════════════════

COLOR_BG = "#1e1e1e"
COLOR_SURFACE = "#252526"
COLOR_PANEL = "#2d2d2d"
COLOR_PANEL_HOVER = "#333333"
COLOR_BORDER = "#3c3c3c"
COLOR_BORDER_LIGHT = "#48484a"
COLOR_TEXT_PRIMARY = "#f5f5f7"
COLOR_TEXT_SECONDARY = "#98989d"
COLOR_TEXT_DIM = "#636366"
COLOR_ACCENT = "#0a84ff"
COLOR_ACCENT_HOVER = "#409cff"
COLOR_SUCCESS = "#30d158"
COLOR_DISCONNECTED = "#636366"
COLOR_ERROR = "#ff453a"
COLOR_ACTIVE = "#0a84ff"
COLOR_INPUT_BG = "#2a2a2c"

FONT = "'SF Pro Display'"
FONT_MONO = "'SF Mono', 'Menlo', 'Consolas'"


def apply_apple_dark_style(widget):
    """Apply modern dark stylesheet to the main window."""
    widget.setStyleSheet(f"""
        /* ── Base ── */
        QMainWindow {{
            background: {COLOR_BG};
        }}
        QWidget {{
            background: transparent;
        }}

        /* ── Labels ── */
        QLabel {{
            color: {COLOR_TEXT_SECONDARY};
            font: 11px {FONT};
        }}

        /* ── Inputs ── */
        QLineEdit, QSpinBox, QDoubleSpinBox {{
            background: {COLOR_INPUT_BG};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            padding: 6px 10px;
            border-radius: 6px;
            font: 12px {FONT};
            selection-background-color: {COLOR_ACCENT};
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {COLOR_ACCENT};
        }}
        QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {COLOR_BORDER_LIGHT};
        }}

        /* ── Buttons ── */
        QPushButton {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font: 600 11px {FONT};
        }}
        QPushButton:hover {{
            background: {COLOR_PANEL_HOVER};
        }}
        QPushButton:pressed {{
            background: {COLOR_ACCENT};
            color: #ffffff;
        }}

        /* ── Checkbox ── */
        QCheckBox {{
            color: {COLOR_TEXT_SECONDARY};
            font: 11px {FONT};
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1.5px solid {COLOR_TEXT_DIM};
            border-radius: 4px;
            background: {COLOR_INPUT_BG};
        }}
        QCheckBox::indicator:checked {{
            background: {COLOR_ACCENT};
            border-color: {COLOR_ACCENT};
        }}

        /* ── Combobox ── */
        QComboBox {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            padding: 6px 10px;
            border-radius: 6px;
            font: 600 11px {FONT};
            min-height: 20px;
        }}
        QComboBox:hover {{ background: {COLOR_PANEL_HOVER}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid {COLOR_TEXT_SECONDARY};
            margin-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            selection-background-color: {COLOR_ACCENT};
            padding: 4px;
            outline: none;
        }}

        /* ── Tab Widget (VS Code style) ── */
        QTabWidget::pane {{
            border: none;
            background: {COLOR_BG};
            top: -1px;
        }}
        QTabBar {{
            background: transparent;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {COLOR_TEXT_DIM};
            padding: 8px 20px;
            border: none;
            border-bottom: 2px solid transparent;
            font: 600 11px {FONT};
            min-width: 60px;
        }}
        QTabBar::tab:hover {{
            color: {COLOR_TEXT_SECONDARY};
            background: {COLOR_SURFACE};
        }}
        QTabBar::tab:selected {{
            color: {COLOR_ACCENT};
            border-bottom-color: {COLOR_ACCENT};
        }}

        /* ── Splitter ── */
        QSplitter::handle {{
            background: {COLOR_BORDER};
            width: 1px;
            height: 1px;
        }}
        QSplitter::handle:hover {{
            background: {COLOR_ACCENT};
        }}

        /* ── Scrollbar ── */
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_BORDER};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {COLOR_TEXT_DIM};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 6px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLOR_BORDER};
            border-radius: 3px;
            min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {COLOR_TEXT_DIM};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* ── Frames ── */
        QFrame[frameShape="4"] {{
            color: {COLOR_BORDER};
        }}

        /* ── Menu Bar ── */
        QMenuBar {{
            background: {COLOR_SURFACE};
            border-bottom: 1px solid {COLOR_BORDER};
            padding: 2px 0px;
            font: 11px {FONT};
        }}
        QMenuBar::item {{
            background: transparent;
            color: {COLOR_TEXT_SECONDARY};
            padding: 4px 12px;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
        }}
        QMenu {{
            background: {COLOR_PANEL};
            border: 1px solid {COLOR_BORDER};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            color: {COLOR_TEXT_PRIMARY};
            padding: 6px 24px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background: {COLOR_ACCENT};
            color: #ffffff;
        }}
        QMenu::separator {{
            height: 1px;
            background: {COLOR_BORDER};
            margin: 4px 8px;
        }}

        /* ── Status Bar ── */
        QStatusBar {{
            background: {COLOR_SURFACE};
            border-top: 1px solid {COLOR_BORDER};
            color: {COLOR_TEXT_DIM};
            font: 10px {FONT};
        }}

        /* ── Tooltip ── */
        QToolTip {{
            background: {COLOR_PANEL};
            color: {COLOR_TEXT_PRIMARY};
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            padding: 4px 8px;
            font: 11px {FONT};
        }}
    """)


# ═══════════════════════════════════════════════════════════════════
# BUTTON STYLE TEMPLATES
# ═══════════════════════════════════════════════════════════════════

STYLE_GO_BUTTON = f"""
    QPushButton {{
        background: {COLOR_ACCENT}; color: #ffffff; border: none;
        font: 600 12px {FONT}; padding: 10px; border-radius: 8px;
    }}
    QPushButton:hover {{ background: {COLOR_ACCENT_HOVER}; }}
    QPushButton:pressed {{ background: #0060c0; }}
"""

STYLE_STOP_ALL = f"""
    QPushButton {{
        background: {COLOR_SURFACE}; color: {COLOR_ERROR}; border: none;
        font: 700 14px {FONT}; padding: 14px; border-radius: 8px;
    }}
    QPushButton:hover {{ background: {COLOR_PANEL}; }}
    QPushButton:pressed {{ background: {COLOR_ERROR}; color: #ffffff; }}
"""

STYLE_HOME_BUTTON = f"""
    QPushButton {{
        background: {COLOR_SURFACE}; color: {COLOR_TEXT_PRIMARY}; border: none;
        font: 600 13px {FONT}; padding: 12px; border-radius: 8px;
    }}
    QPushButton:hover {{ background: {COLOR_PANEL}; }}
    QPushButton:pressed {{ background: {COLOR_ACCENT}; color: #ffffff; }}
"""

STYLE_DIAG_BUTTON = f"""
    QPushButton {{
        background: transparent; color: {COLOR_TEXT_DIM};
        border: 1px solid {COLOR_BORDER};
        font: 600 10px {FONT}; padding: 6px 12px; border-radius: 6px;
    }}
    QPushButton:hover {{ background: {COLOR_PANEL}; color: {COLOR_TEXT_SECONDARY}; }}
    QPushButton:pressed {{ background: {COLOR_ACCENT}; color: #ffffff; }}
"""

STYLE_LOG_TEXT = f"""
    QPlainTextEdit {{
        color: {COLOR_TEXT_DIM};
        font: 10px {FONT_MONO};
        background: {COLOR_SURFACE};
        border: 1px solid {COLOR_BORDER};
        border-radius: 6px;
        padding: 6px;
    }}
"""

# Section header style for sidebar
STYLE_SECTION = f"""
    QLabel {{
        color: {COLOR_TEXT_DIM};
        font: 700 9px {FONT};
        letter-spacing: 1px;
        padding: 4px 0px;
    }}
"""

STYLE_SECTION_DIVIDER = f"""
    QFrame {{
        background: {COLOR_BORDER};
        max-height: 1px;
        min-height: 1px;
    }}
"""

# ═══════════════════════════════════════════════════════════════════
# STATUS INDICATOR COLORS
# ═══════════════════════════════════════════════════════════════════

COLOR_CONNECTED = "#30d158"      # Green
COLOR_DISCONNECTED = "#636366"   # Grey
COLOR_ERROR = "#ff453a"          # Red
COLOR_ACTIVE = "#0a84ff"         # Blue
