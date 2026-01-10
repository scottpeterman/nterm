#!/usr/bin/env python3
"""
Example: Credential Manager with Theme Integration

Shows how to use the credential manager with nterm's theme system.
"""

import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QComboBox, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from nterm.vault import CredentialManagerWidget, CredentialResolver, ManagerTheme
from nterm.theme import Theme, ThemeEngine


class CredentialManagerWindow(QMainWindow):
    """Main window with theme-aware credential manager."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("nTerm Credential Manager")
        self.setMinimumSize(900, 700)
        
        # Initialize theme engine
        self.theme_engine = ThemeEngine()
        self.theme_engine.load_themes()
        
        # Initialize credential resolver (includes store)
        self.resolver = CredentialResolver()
        
        # Setup UI
        self._setup_ui()
        
        # Apply default theme
        self._apply_theme(self.theme_engine.current)
        
        # Try auto-unlock from keychain
        self.manager.try_auto_unlock()
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Theme selector bar
        theme_bar = QWidget()
        theme_bar.setObjectName("themeBar")
        theme_layout = QHBoxLayout(theme_bar)
        theme_layout.setContentsMargins(16, 8, 16, 8)
        
        theme_layout.addWidget(QLabel("Theme:"))
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(self.theme_engine.list_themes())
        self.theme_combo.setCurrentText("default")
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self.theme_combo)
        
        theme_layout.addStretch()
        
        # Keychain management
        from nterm.vault import KeychainIntegration
        if KeychainIntegration.is_available():
            clear_keychain_btn = QPushButton("Clear Keychain Password")
            clear_keychain_btn.clicked.connect(self._clear_keychain)
            theme_layout.addWidget(clear_keychain_btn)
        
        layout.addWidget(theme_bar)
        
        # Credential manager
        self.manager = CredentialManagerWidget(store=self.resolver.store)
        self.manager.credential_selected.connect(self._on_credential_selected)
        self.manager.vault_unlocked.connect(self._on_vault_unlocked)
        self.manager.vault_locked.connect(self._on_vault_locked)
        layout.addWidget(self.manager)
    
    def _apply_theme(self, theme: Theme):
        """Apply theme to entire window."""
        self.theme_engine.current = theme
        
        # Apply to credential manager
        self.manager.set_theme(theme)
        
        # Style the theme bar to match
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme.background_color};
            }}
            #themeBar {{
                background-color: {theme.terminal_colors.get('black', '#313244')};
                border-bottom: 1px solid {theme.border_color};
            }}
            #themeBar QLabel {{
                color: {theme.foreground_color};
                font-family: {theme.font_family};
            }}
            #themeBar QComboBox {{
                background-color: {theme.background_color};
                color: {theme.foreground_color};
                border: 1px solid {theme.border_color};
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 120px;
            }}
            #themeBar QPushButton {{
                background-color: {theme.background_color};
                color: {theme.foreground_color};
                border: 1px solid {theme.border_color};
                border-radius: 4px;
                padding: 4px 12px;
            }}
            #themeBar QPushButton:hover {{
                border-color: {theme.accent_color};
            }}
        """)
    
    def _on_theme_changed(self, theme_name: str):
        theme = self.theme_engine.get_theme(theme_name)
        if theme:
            self._apply_theme(theme)
    
    def _on_credential_selected(self, name: str):
        print(f"Selected credential: {name}")
    
    def _on_vault_unlocked(self):
        print("Vault unlocked")
    
    def _on_vault_locked(self):
        print("Vault locked")
    
    def _clear_keychain(self):
        from nterm.vault import KeychainIntegration
        if KeychainIntegration.clear_master_password():
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Success", "Keychain password cleared")
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Failed to clear keychain")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = CredentialManagerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
