"""
Settings dialog with theme selection.
"""

from __future__ import annotations
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QFontComboBox, QPushButton,
    QDialogButtonBox, QGroupBox, QLabel, QWidget,
    QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from nterm.theme.engine import ThemeEngine, Theme


class ThemePreview(QFrame):
    """Small preview of theme colors."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self._theme: Optional[Theme] = None
        self._update_style()

    def set_theme(self, theme: Theme) -> None:
        """Update preview with theme colors."""
        self._theme = theme
        self._update_style()

    def _update_style(self) -> None:
        if not self._theme:
            return

        colors = self._theme.terminal_colors
        bg = colors.get("background", "#1e1e2e")
        fg = colors.get("foreground", "#cdd6f4")

        # Build color swatches
        swatch_colors = [
            colors.get("red", "#f38ba8"),
            colors.get("green", "#a6e3a1"),
            colors.get("yellow", "#f9e2af"),
            colors.get("blue", "#89b4fa"),
            colors.get("magenta", "#f5c2e7"),
            colors.get("cyan", "#94e2d5"),
        ]

        self.setStyleSheet(f"""
            ThemePreview {{
                background-color: {bg};
                border: 1px solid {self._theme.border_color};
                border-radius: 4px;
            }}
        """)

        # Clear existing widgets
        if self.layout():
            while self.layout().count():
                child = self.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        else:
            layout = QHBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(4)

        # Add sample text
        sample = QLabel("user@host:~$")
        sample.setStyleSheet(f"color: {fg}; background: transparent;")
        sample.setFont(QFont(self._theme.font_family.split(",")[0].strip(), 11))
        self.layout().addWidget(sample)

        self.layout().addStretch()

        # Add color swatches
        for color in swatch_colors:
            swatch = QFrame()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(f"""
                background-color: {color};
                border-radius: 2px;
            """)
            self.layout().addWidget(swatch)


class SettingsDialog(QDialog):
    """
    Application settings dialog.

    Signals:
        theme_changed(theme): Emitted when theme selection changes
    """

    theme_changed = pyqtSignal(object)  # Theme

    def __init__(
            self,
            theme_engine: ThemeEngine,
            current_theme: Theme = None,
            parent: QWidget = None
    ):
        super().__init__(parent)
        self.theme_engine = theme_engine
        self._current_theme = current_theme or theme_engine.current
        self._original_theme = self._current_theme

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Theme group
        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout(theme_group)

        # Theme selector
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Theme:"))

        self._theme_combo = QComboBox()
        for name in self.theme_engine.list_themes():
            theme = self.theme_engine.get_theme(name)
            self._theme_combo.addItem(name.replace("_", " ").title(), name)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        selector_row.addWidget(self._theme_combo, 1)

        theme_layout.addLayout(selector_row)

        # Theme preview
        self._preview = ThemePreview()
        theme_layout.addWidget(self._preview)

        layout.addWidget(theme_group)

        # Font group
        font_group = QGroupBox("Terminal Font")
        font_layout = QFormLayout(font_group)

        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 32)
        self._font_size_spin.setValue(14)
        self._font_size_spin.setSuffix(" pt")
        font_layout.addRow("Size:", self._font_size_spin)

        layout.addWidget(font_group)

        # Spacer
        layout.addStretch()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self._on_reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        layout.addWidget(buttons)

    def _load_settings(self) -> None:
        """Load current settings into form."""
        # Select current theme
        idx = self._theme_combo.findData(self._current_theme.name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

        self._preview.set_theme(self._current_theme)
        self._font_size_spin.setValue(self._current_theme.font_size)

    def _on_theme_changed(self, index: int) -> None:
        """Handle theme selection change."""
        theme_name = self._theme_combo.currentData()
        theme = self.theme_engine.get_theme(theme_name)
        if theme:
            self._current_theme = theme
            self._preview.set_theme(theme)

    def _apply(self) -> None:
        """Apply current settings."""
        # Update font size on theme
        self._current_theme.font_size = self._font_size_spin.value()
        self.theme_engine.current = self._current_theme
        self.theme_changed.emit(self._current_theme)

    def _on_accept(self) -> None:
        """Accept and close."""
        self._apply()
        self.accept()

    def _on_reject(self) -> None:
        """Cancel - revert to original theme."""
        if self._current_theme != self._original_theme:
            self.theme_engine.current = self._original_theme
            self.theme_changed.emit(self._original_theme)
        self.reject()

    def get_theme(self) -> Theme:
        """Get selected theme."""
        return self._current_theme