"""
Qt stylesheet generation from themes.
"""

from nterm.theme.engine import Theme


def generate_stylesheet(theme: Theme) -> str:
    """
    Generate Qt stylesheet from theme.

    Args:
        theme: Theme to generate stylesheet from

    Returns:
        Qt stylesheet string
    """
    bg = theme.background_color
    fg = theme.foreground_color
    border = theme.border_color
    accent = theme.accent_color

    # Derive additional colors
    bg_lighter = _lighten(bg, 0.1)
    bg_darker = _darken(bg, 0.1)
    accent_hover = _lighten(accent, 0.1)
    accent_pressed = _darken(accent, 0.1)

    # Get terminal colors for additional UI elements
    tc = theme.terminal_colors
    red = tc.get("red", "#f38ba8")
    green = tc.get("green", "#a6e3a1")
    yellow = tc.get("yellow", "#f9e2af")

    return f"""
    /* Main window and containers */
    QMainWindow, QDialog, QWidget {{
        background-color: {bg};
        color: {fg};
    }}

    /* Splitter */
    QSplitter::handle {{
        background-color: {border};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QSplitter::handle:vertical {{
        height: 2px;
    }}

    /* Menu bar */
    QMenuBar {{
        background-color: {bg};
        color: {fg};
        border-bottom: 1px solid {border};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 4px 8px;
        background-color: transparent;
    }}
    QMenuBar::item:selected {{
        background-color: {bg_lighter};
        border-radius: 4px;
    }}

    /* Menus */
    QMenu {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 8px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {accent};
        color: {bg};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {border};
        margin: 4px 8px;
    }}

    /* Tab widget */
    QTabWidget::pane {{
        border: 1px solid {border};
        border-radius: 4px;
        background-color: {bg};
    }}
    QTabBar::tab {{
        background-color: {bg_darker};
        color: {fg};
        border: 1px solid {border};
        border-bottom: none;
        padding: 6px 12px;
        margin-right: 2px;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    QTabBar::tab:selected {{
        background-color: {bg};
        border-bottom: 1px solid {bg};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {bg_lighter};
    }}
    QTabBar::close-button {{
        image: none;
        subcontrol-position: right;
    }}
    QTabBar::close-button:hover {{
        background-color: {red};
        border-radius: 2px;
    }}

    /* Tree widget */
    QTreeWidget, QTreeView {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        outline: none;
    }}
    QTreeWidget::item, QTreeView::item {{
        padding: 4px;
        border-radius: 4px;
    }}
    QTreeWidget::item:hover, QTreeView::item:hover {{
        background-color: {bg_lighter};
    }}
    QTreeWidget::item:selected, QTreeView::item:selected {{
        background-color: {accent};
        color: {bg};
    }}
    QTreeWidget::branch {{
        background-color: {bg};
    }}

    /* Line edit */
    QLineEdit {{
        background-color: {bg_darker};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 8px;
        selection-background-color: {accent};
        selection-color: {bg};
    }}
    QLineEdit:focus {{
        border-color: {accent};
    }}
    QLineEdit:disabled {{
        background-color: {bg};
        color: {border};
    }}

    /* Spin box */
    QSpinBox {{
        background-color: {bg_darker};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QSpinBox:focus {{
        border-color: {accent};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background-color: {bg_lighter};
        border: none;
        width: 16px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background-color: {accent};
    }}

    /* Combo box */
    QComboBox {{
        background-color: {bg_darker};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 8px;
        min-width: 100px;
    }}
    QComboBox:focus {{
        border-color: {accent};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        width: 12px;
        height: 12px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {bg};
        color: {fg};
        border: 1px solid {border};
        selection-background-color: {accent};
        selection-color: {bg};
    }}

    /* Push button */
    QPushButton {{
        background-color: {bg_lighter};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 6px 16px;
        min-width: 60px;
    }}
    QPushButton:hover {{
        background-color: {accent};
        color: {bg};
        border-color: {accent};
    }}
    QPushButton:pressed {{
        background-color: {accent_pressed};
    }}
    QPushButton:disabled {{
        background-color: {bg_darker};
        color: {border};
        border-color: {bg_darker};
    }}
    QPushButton:default {{
        border-color: {accent};
    }}

    /* Group box */
    QGroupBox {{
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        color: {fg};
    }}

    /* Labels */
    QLabel {{
        color: {fg};
        background-color: transparent;
    }}

    /* Scroll bars */
    QScrollBar:vertical {{
        background-color: {bg};
        width: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {border};
        border-radius: 6px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background-color: {bg};
        height: 12px;
        border-radius: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {border};
        border-radius: 6px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {accent};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* Check box */
    QCheckBox {{
        color: {fg};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {border};
        border-radius: 4px;
        background-color: {bg_darker};
    }}
    QCheckBox::indicator:checked {{
        background-color: {accent};
        border-color: {accent};
    }}
    QCheckBox::indicator:hover {{
        border-color: {accent};
    }}

    /* Tool tip */
    QToolTip {{
        background-color: {bg_lighter};
        color: {fg};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
    }}

    /* Message box */
    QMessageBox {{
        background-color: {bg};
    }}
    QMessageBox QLabel {{
        color: {fg};
    }}

    /* Dialog button box */
    QDialogButtonBox {{
        button-layout: 3;
    }}

    /* Frame */
    QFrame {{
        background-color: transparent;
    }}

    /* Header view (for tree/table) */
    QHeaderView::section {{
        background-color: {bg_darker};
        color: {fg};
        border: none;
        border-right: 1px solid {border};
        padding: 4px 8px;
    }}
    """


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB to hex color."""
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(hex_color: str, amount: float) -> str:
    """Lighten a hex color by amount (0-1)."""
    r, g, b = _hex_to_rgb(hex_color)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return _rgb_to_hex(r, g, b)


def _darken(hex_color: str, amount: float) -> str:
    """Darken a hex color by amount (0-1)."""
    r, g, b = _hex_to_rgb(hex_color)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return _rgb_to_hex(r, g, b)