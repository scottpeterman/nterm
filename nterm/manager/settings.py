"""
Settings dialog with theme selection and persistence.
"""

from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QPushButton,
    QDialogButtonBox, QGroupBox, QLabel, QWidget,
    QFrame, QCheckBox
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont

from nterm.theme.engine import ThemeEngine, Theme
from nterm.config import get_settings, save_settings, AppSettings


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
    Application settings dialog with persistence.

    Signals:
        theme_changed(theme): Emitted when theme selection changes
        settings_changed(settings): Emitted when any settings change
    """

    theme_changed = pyqtSignal(object)  # Theme
    settings_changed = pyqtSignal(object)  # AppSettings

    def __init__(
            self,
            theme_engine: ThemeEngine,
            current_theme: Theme = None,
            parent: QWidget = None
    ):
        super().__init__(parent)
        self.theme_engine = theme_engine
        self._settings = get_settings()
        self._current_theme = current_theme or theme_engine.current
        self._original_theme = self._current_theme
        self._original_settings = AppSettings.from_dict(self._settings.to_dict())

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

        # Terminal behavior group
        behavior_group = QGroupBox("Terminal Behavior")
        behavior_layout = QFormLayout(behavior_group)

        self._multiline_spin = QSpinBox()
        self._multiline_spin.setRange(0, 100)
        self._multiline_spin.setValue(self._settings.multiline_paste_threshold)
        self._multiline_spin.setSpecialValueText("Disabled")
        self._multiline_spin.setToolTip("Warn before pasting text with more than this many lines (0 to disable)")
        behavior_layout.addRow("Multiline paste warning:", self._multiline_spin)

        self._scrollback_spin = QSpinBox()
        self._scrollback_spin.setRange(1000, 100000)
        self._scrollback_spin.setSingleStep(1000)
        self._scrollback_spin.setValue(self._settings.scrollback_lines)
        self._scrollback_spin.setSuffix(" lines")
        behavior_layout.addRow("Scrollback buffer:", self._scrollback_spin)

        self._auto_reconnect_check = QCheckBox()
        self._auto_reconnect_check.setChecked(self._settings.auto_reconnect)
        self._auto_reconnect_check.setToolTip("Automatically attempt to reconnect when connection is lost")
        behavior_layout.addRow("Auto-reconnect:", self._auto_reconnect_check)

        layout.addWidget(behavior_group)

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
        idx = self._theme_combo.findData(self._settings.theme_name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        else:
            # Fallback to current theme
            idx = self._theme_combo.findData(self._current_theme.name)
            if idx >= 0:
                self._theme_combo.setCurrentIndex(idx)

        self._preview.set_theme(self._current_theme)
        self._font_size_spin.setValue(self._settings.font_size)
        self._multiline_spin.setValue(self._settings.multiline_paste_threshold)
        self._scrollback_spin.setValue(self._settings.scrollback_lines)
        self._auto_reconnect_check.setChecked(self._settings.auto_reconnect)

    def _on_theme_changed(self, index: int) -> None:
        """Handle theme selection change."""
        theme_name = self._theme_combo.currentData()
        theme = self.theme_engine.get_theme(theme_name)
        if theme:
            self._current_theme = theme
            self._preview.set_theme(theme)

    def _apply(self) -> None:
        """Apply current settings and persist."""
        # Update settings object
        self._settings.theme_name = self._theme_combo.currentData()
        self._settings.font_size = self._font_size_spin.value()
        self._settings.multiline_paste_threshold = self._multiline_spin.value()
        self._settings.scrollback_lines = self._scrollback_spin.value()
        self._settings.auto_reconnect = self._auto_reconnect_check.isChecked()

        # Update font size on theme
        self._current_theme.font_size = self._font_size_spin.value()
        self.theme_engine.current = self._current_theme

        # Save to disk
        save_settings()

        # Emit signals
        self.theme_changed.emit(self._current_theme)
        self.settings_changed.emit(self._settings)

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

    def get_settings(self) -> AppSettings:
        """Get current settings."""
        return self._settings