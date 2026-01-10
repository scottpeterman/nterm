"""
PyQt6 Credential Manager UI.

Provides a complete interface for managing vault credentials.
"""

from __future__ import annotations
import logging
from typing import Optional, Callable
from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QDialogButtonBox, QMessageBox, QFrame,
    QStackedWidget, QFileDialog, QGroupBox, QSplitter,
    QAbstractItemView, QStyle, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QIcon

from .store import CredentialStore, StoredCredential
from .keychain import KeychainIntegration

logger = logging.getLogger(__name__)


@dataclass
class ManagerTheme:
    """Theme configuration for the credential manager."""
    background_color: str = "#1e1e2e"
    foreground_color: str = "#cdd6f4"
    border_color: str = "#313244"
    accent_color: str = "#89b4fa"
    input_background: str = "#313244"
    button_background: str = "#45475a"
    button_hover: str = "#585b70"
    error_color: str = "#f38ba8"
    success_color: str = "#a6e3a1"
    warning_color: str = "#f9e2af"
    font_family: str = "JetBrains Mono, Cascadia Code, Consolas, monospace"
    font_size: int = 12
    
    @classmethod
    def from_terminal_theme(cls, theme) -> ManagerTheme:
        """Create manager theme from terminal Theme object."""
        return cls(
            background_color=theme.background_color,
            foreground_color=theme.foreground_color,
            border_color=theme.border_color,
            accent_color=theme.accent_color,
            input_background=theme.terminal_colors.get("black", "#313244"),
            font_family=theme.font_family,
            font_size=theme.font_size - 2,  # Slightly smaller for UI
        )
    
    def to_stylesheet(self) -> str:
        """Generate Qt stylesheet from theme."""
        return f"""
            QWidget {{
                background-color: {self.background_color};
                color: {self.foreground_color};
                font-family: {self.font_family};
                font-size: {self.font_size}px;
            }}
            
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {self.input_background};
                border: 1px solid {self.border_color};
                border-radius: 4px;
                padding: 6px 10px;
                color: {self.foreground_color};
                selection-background-color: {self.accent_color};
            }}
            
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border-color: {self.accent_color};
            }}
            
            QPushButton {{
                background-color: {self.button_background};
                border: 1px solid {self.border_color};
                border-radius: 4px;
                padding: 8px 16px;
                color: {self.foreground_color};
                min-width: 80px;
            }}
            
            QPushButton:hover {{
                background-color: {self.button_hover};
                border-color: {self.accent_color};
            }}
            
            QPushButton:pressed {{
                background-color: {self.accent_color};
            }}
            
            QPushButton[primary="true"] {{
                background-color: {self.accent_color};
                color: {self.background_color};
                font-weight: bold;
            }}
            
            QPushButton[primary="true"]:hover {{
                background-color: {self.foreground_color};
            }}
            
            QPushButton[danger="true"] {{
                background-color: {self.error_color};
                color: {self.background_color};
            }}
            
            QTableWidget {{
                background-color: {self.background_color};
                border: 1px solid {self.border_color};
                border-radius: 4px;
                gridline-color: {self.border_color};
            }}
            
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {self.border_color};
            }}
            
            QTableWidget::item:selected {{
                background-color: {self.accent_color};
                color: {self.background_color};
            }}
            
            QHeaderView::section {{
                background-color: {self.input_background};
                color: {self.foreground_color};
                padding: 8px;
                border: none;
                border-bottom: 2px solid {self.accent_color};
                font-weight: bold;
            }}
            
            QGroupBox {{
                border: 1px solid {self.border_color};
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 8px;
                font-weight: bold;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: {self.accent_color};
            }}
            
            QCheckBox {{
                spacing: 8px;
            }}
            
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {self.border_color};
                border-radius: 3px;
                background-color: {self.input_background};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {self.accent_color};
                border-color: {self.accent_color};
            }}
            
            QLabel[heading="true"] {{
                font-size: {self.font_size + 4}px;
                font-weight: bold;
                color: {self.accent_color};
            }}
            
            QLabel[subheading="true"] {{
                color: {self.button_hover};
                font-size: {self.font_size - 1}px;
            }}
            
            QFrame[separator="true"] {{
                background-color: {self.border_color};
                max-height: 1px;
            }}
            
            QDialog {{
                background-color: {self.background_color};
            }}
            
            QMessageBox {{
                background-color: {self.background_color};
            }}
            
            QScrollBar:vertical {{
                background-color: {self.background_color};
                width: 12px;
                border-radius: 6px;
            }}
            
            QScrollBar::handle:vertical {{
                background-color: {self.button_background};
                border-radius: 6px;
                min-height: 30px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background-color: {self.button_hover};
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """


class UnlockDialog(QDialog):
    """Dialog for unlocking the vault."""
    
    def __init__(
        self,
        parent: QWidget = None,
        theme: ManagerTheme = None,
        is_init: bool = False,
    ):
        super().__init__(parent)
        self.theme = theme or ManagerTheme()
        self.is_init = is_init
        self._setup_ui()
    
    def _setup_ui(self):
        self.setWindowTitle("Initialize Vault" if self.is_init else "Unlock Vault")
        self.setMinimumWidth(400)
        self.setStyleSheet(self.theme.to_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Header
        title = QLabel("🔐 " + ("Create Master Password" if self.is_init else "Enter Master Password"))
        title.setProperty("heading", True)
        layout.addWidget(title)
        
        if self.is_init:
            hint = QLabel("This password encrypts all stored credentials.\nChoose a strong password you'll remember.")
            hint.setProperty("subheading", True)
            hint.setWordWrap(True)
            layout.addWidget(hint)
        
        # Password field
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Master password")
        layout.addWidget(self.password_input)
        
        # Confirm field (for init)
        if self.is_init:
            self.confirm_input = QLineEdit()
            self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_input.setPlaceholderText("Confirm password")
            layout.addWidget(self.confirm_input)
        
        # Remember checkbox (if keychain available)
        if KeychainIntegration.is_available():
            self.remember_check = QCheckBox("Remember password in system keychain")
            self.remember_check.setChecked(True)
            layout.addWidget(self.remember_check)
        else:
            self.remember_check = None
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {self.theme.error_color};")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        self.ok_btn = QPushButton("Create Vault" if self.is_init else "Unlock")
        self.ok_btn.setProperty("primary", True)
        self.ok_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.ok_btn)
        
        layout.addLayout(btn_layout)
        
        # Enter key triggers OK
        self.password_input.returnPressed.connect(self._validate_and_accept)
        if self.is_init:
            self.confirm_input.returnPressed.connect(self._validate_and_accept)
    
    def _validate_and_accept(self):
        password = self.password_input.text()
        
        if not password:
            self._show_error("Password is required")
            return
        
        if self.is_init:
            if len(password) < 8:
                self._show_error("Password must be at least 8 characters")
                return
            if password != self.confirm_input.text():
                self._show_error("Passwords don't match")
                return
        
        self.accept()
    
    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
    
    def get_password(self) -> str:
        return self.password_input.text()
    
    def should_remember(self) -> bool:
        return self.remember_check.isChecked() if self.remember_check else False


class CredentialDialog(QDialog):
    """Dialog for adding/editing a credential."""
    
    def __init__(
        self,
        parent: QWidget = None,
        theme: ManagerTheme = None,
        credential: StoredCredential = None,
    ):
        super().__init__(parent)
        self.theme = theme or ManagerTheme()
        self.credential = credential
        self.is_edit = credential is not None
        self._setup_ui()
        
        if credential:
            self._populate_from_credential(credential)
    
    def _setup_ui(self):
        self.setWindowTitle("Edit Credential" if self.is_edit else "Add Credential")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
        self.setStyleSheet(self.theme.to_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Basic info group
        basic_group = QGroupBox("Basic Information")
        basic_layout = QGridLayout(basic_group)
        basic_layout.setSpacing(12)
        
        basic_layout.addWidget(QLabel("Name:"), 0, 0)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., production-servers")
        basic_layout.addWidget(self.name_input, 0, 1)
        
        basic_layout.addWidget(QLabel("Username:"), 1, 0)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("SSH username")
        basic_layout.addWidget(self.username_input, 1, 1)
        
        layout.addWidget(basic_group)
        
        # Authentication group
        auth_group = QGroupBox("Authentication")
        auth_layout = QGridLayout(auth_group)
        auth_layout.setSpacing(12)
        
        auth_layout.addWidget(QLabel("Password:"), 0, 0)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Optional - leave blank for key-only auth")
        auth_layout.addWidget(self.password_input, 0, 1)
        
        auth_layout.addWidget(QLabel("SSH Key:"), 1, 0)
        key_layout = QHBoxLayout()
        self.ssh_key_input = QTextEdit()
        self.ssh_key_input.setPlaceholderText("Paste private key or use Browse...")
        self.ssh_key_input.setMaximumHeight(100)
        key_layout.addWidget(self.ssh_key_input)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key)
        key_layout.addWidget(browse_btn)
        auth_layout.addLayout(key_layout, 1, 1)
        
        auth_layout.addWidget(QLabel("Key Passphrase:"), 2, 0)
        self.key_passphrase_input = QLineEdit()
        self.key_passphrase_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_passphrase_input.setPlaceholderText("If key is encrypted")
        auth_layout.addWidget(self.key_passphrase_input, 2, 1)
        
        layout.addWidget(auth_group)
        
        # Jump host group
        jump_group = QGroupBox("Jump Host (Optional)")
        jump_layout = QGridLayout(jump_group)
        jump_layout.setSpacing(12)
        
        jump_layout.addWidget(QLabel("Jump Host:"), 0, 0)
        self.jump_host_input = QLineEdit()
        self.jump_host_input.setPlaceholderText("e.g., bastion.example.com")
        jump_layout.addWidget(self.jump_host_input, 0, 1)
        
        jump_layout.addWidget(QLabel("Jump Username:"), 1, 0)
        self.jump_username_input = QLineEdit()
        self.jump_username_input.setPlaceholderText("Leave blank to use main username")
        jump_layout.addWidget(self.jump_username_input, 1, 1)
        
        jump_layout.addWidget(QLabel("Jump Auth:"), 2, 0)
        self.jump_auth_combo = QComboBox()
        self.jump_auth_combo.addItems(["SSH Agent", "Password", "Key"])
        jump_layout.addWidget(self.jump_auth_combo, 2, 1)
        
        self.jump_touch_check = QCheckBox("Requires YubiKey touch")
        jump_layout.addWidget(self.jump_touch_check, 3, 1)
        
        layout.addWidget(jump_group)
        
        # Matching group
        match_group = QGroupBox("Matching Rules")
        match_layout = QGridLayout(match_group)
        match_layout.setSpacing(12)
        
        match_layout.addWidget(QLabel("Host Patterns:"), 0, 0)
        self.match_hosts_input = QLineEdit()
        self.match_hosts_input.setPlaceholderText("Comma-separated: *.prod.example.com, 10.0.*")
        match_layout.addWidget(self.match_hosts_input, 0, 1)
        
        match_layout.addWidget(QLabel("Tags:"), 1, 0)
        self.match_tags_input = QLineEdit()
        self.match_tags_input.setPlaceholderText("Comma-separated: production, linux, cisco")
        match_layout.addWidget(self.match_tags_input, 1, 1)
        
        self.default_check = QCheckBox("Use as default credential")
        match_layout.addWidget(self.default_check, 2, 1)
        
        layout.addWidget(match_group)
        
        layout.addStretch()
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {self.theme.error_color};")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save" if self.is_edit else "Add")
        save_btn.setProperty("primary", True)
        save_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SSH Key",
            str(Path.home() / ".ssh"),
            "All Files (*)"
        )
        if path:
            try:
                with open(path) as f:
                    self.ssh_key_input.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to read key: {e}")
    
    def _populate_from_credential(self, cred: StoredCredential):
        self.name_input.setText(cred.name)
        self.name_input.setEnabled(False)  # Can't change name on edit
        self.username_input.setText(cred.username)
        
        # Don't show actual secrets - user must re-enter to change
        if cred.has_password:
            self.password_input.setPlaceholderText("(unchanged - enter new to replace)")
        if cred.has_ssh_key:
            self.ssh_key_input.setPlaceholderText("(unchanged - paste new to replace)")
        
        if cred.jump_host:
            self.jump_host_input.setText(cred.jump_host)
        if cred.jump_username:
            self.jump_username_input.setText(cred.jump_username)
        
        auth_map = {"agent": 0, "password": 1, "key": 2}
        self.jump_auth_combo.setCurrentIndex(auth_map.get(cred.jump_auth_method, 0))
        self.jump_touch_check.setChecked(cred.jump_requires_touch)
        
        if cred.match_hosts:
            self.match_hosts_input.setText(", ".join(cred.match_hosts))
        if cred.match_tags:
            self.match_tags_input.setText(", ".join(cred.match_tags))
        
        self.default_check.setChecked(cred.is_default)
    
    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            self._show_error("Name is required")
            return
        if not self.username_input.text().strip():
            self._show_error("Username is required")
            return
        
        # Must have at least one auth method (for new creds)
        if not self.is_edit:
            has_password = bool(self.password_input.text())
            has_key = bool(self.ssh_key_input.toPlainText().strip())
            if not has_password and not has_key:
                self._show_error("Provide password or SSH key (or both)")
                return
        
        self.accept()
    
    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()
    
    def get_credential_data(self) -> dict:
        """Get credential data as dict for store.add_credential()."""
        data = {
            "name": self.name_input.text().strip(),
            "username": self.username_input.text().strip(),
        }
        
        # Only include secrets if provided
        if self.password_input.text():
            data["password"] = self.password_input.text()
        if self.ssh_key_input.toPlainText().strip():
            data["ssh_key"] = self.ssh_key_input.toPlainText().strip()
        if self.key_passphrase_input.text():
            data["ssh_key_passphrase"] = self.key_passphrase_input.text()
        
        # Jump host
        if self.jump_host_input.text().strip():
            data["jump_host"] = self.jump_host_input.text().strip()
            if self.jump_username_input.text().strip():
                data["jump_username"] = self.jump_username_input.text().strip()
            auth_map = {0: "agent", 1: "password", 2: "key"}
            data["jump_auth_method"] = auth_map[self.jump_auth_combo.currentIndex()]
            data["jump_requires_touch"] = self.jump_touch_check.isChecked()
        
        # Matching
        if self.match_hosts_input.text().strip():
            data["match_hosts"] = [
                h.strip() for h in self.match_hosts_input.text().split(",") if h.strip()
            ]
        if self.match_tags_input.text().strip():
            data["match_tags"] = [
                t.strip() for t in self.match_tags_input.text().split(",") if t.strip()
            ]
        
        data["is_default"] = self.default_check.isChecked()
        
        return data


class CredentialManagerWidget(QWidget):
    """
    Main credential manager widget.
    
    Provides complete CRUD interface for vault credentials.
    
    Signals:
        credential_selected: Emitted when user selects a credential
        vault_locked: Emitted when vault is locked
        vault_unlocked: Emitted when vault is unlocked
    """
    
    credential_selected = pyqtSignal(str)  # credential name
    vault_locked = pyqtSignal()
    vault_unlocked = pyqtSignal()
    
    def __init__(
        self,
        store: CredentialStore = None,
        theme: ManagerTheme = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.store = store or CredentialStore()
        self.theme = theme or ManagerTheme()
        self._setup_ui()
        self._refresh_state()
    
    def set_theme(self, theme) -> None:
        """
        Set theme from terminal Theme object.
        
        Args:
            theme: Theme object from nterm.theme.engine
        """
        self.theme = ManagerTheme.from_terminal_theme(theme)
        self.setStyleSheet(self.theme.to_stylesheet())
    
    def _setup_ui(self):
        self.setStyleSheet(self.theme.to_stylesheet())
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("🔐 Credential Vault")
        title.setProperty("heading", True)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Lock/unlock button
        self.lock_btn = QPushButton("Lock")
        self.lock_btn.clicked.connect(self._toggle_lock)
        header_layout.addWidget(self.lock_btn)
        
        layout.addLayout(header_layout)
        
        # Status line
        self.status_label = QLabel()
        self.status_label.setProperty("subheading", True)
        layout.addWidget(self.status_label)
        
        # Stacked widget for locked/unlocked states
        self.stack = QStackedWidget()
        
        # Locked view
        locked_widget = QWidget()
        locked_layout = QVBoxLayout(locked_widget)
        locked_layout.addStretch()
        
        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("font-size: 48px;")
        lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        locked_layout.addWidget(lock_icon)
        
        locked_msg = QLabel("Vault is locked")
        locked_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        locked_msg.setProperty("heading", True)
        locked_layout.addWidget(locked_msg)
        
        self.unlock_btn = QPushButton("Unlock Vault")
        self.unlock_btn.setProperty("primary", True)
        self.unlock_btn.setMaximumWidth(200)
        self.unlock_btn.clicked.connect(self._show_unlock_dialog)
        locked_layout.addWidget(self.unlock_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        locked_layout.addStretch()
        self.stack.addWidget(locked_widget)
        
        # Unlocked view
        unlocked_widget = QWidget()
        unlocked_layout = QVBoxLayout(unlocked_widget)
        unlocked_layout.setSpacing(12)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("➕ Add")
        self.add_btn.clicked.connect(self._add_credential)
        toolbar_layout.addWidget(self.add_btn)
        
        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.clicked.connect(self._edit_credential)
        self.edit_btn.setEnabled(False)
        toolbar_layout.addWidget(self.edit_btn)
        
        self.delete_btn = QPushButton("🗑️ Delete")
        self.delete_btn.setProperty("danger", True)
        self.delete_btn.clicked.connect(self._delete_credential)
        self.delete_btn.setEnabled(False)
        toolbar_layout.addWidget(self.delete_btn)
        
        toolbar_layout.addStretch()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self._refresh_credentials)
        toolbar_layout.addWidget(self.refresh_btn)
        
        unlocked_layout.addLayout(toolbar_layout)
        
        # Credentials table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Name", "Username", "Auth", "Jump Host", "Default", "Last Used"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._edit_credential)
        
        unlocked_layout.addWidget(self.table)
        
        self.stack.addWidget(unlocked_widget)
        
        layout.addWidget(self.stack)
        
        # Keychain info
        if KeychainIntegration.is_available():
            keychain_label = QLabel(
                f"✓ System keychain available ({KeychainIntegration.get_backend_name()})"
            )
            keychain_label.setProperty("subheading", True)
            layout.addWidget(keychain_label)
    
    def _refresh_state(self):
        """Refresh UI state based on vault status."""
        is_initialized = self.store.is_initialized()
        is_unlocked = self.store.is_unlocked
        
        if not is_initialized:
            self.status_label.setText("Vault not initialized - click Unlock to create")
            self.stack.setCurrentIndex(0)
            self.unlock_btn.setText("Create Vault")
            self.lock_btn.hide()
        elif is_unlocked:
            self.status_label.setText(f"Vault unlocked - {self.store.db_path}")
            self.stack.setCurrentIndex(1)
            self.lock_btn.show()
            self.lock_btn.setText("🔒 Lock")
            self._refresh_credentials()
        else:
            self.status_label.setText(f"Vault locked - {self.store.db_path}")
            self.stack.setCurrentIndex(0)
            self.unlock_btn.setText("Unlock Vault")
            self.lock_btn.hide()
    
    def _toggle_lock(self):
        if self.store.is_unlocked:
            self.store.lock()
            self.vault_locked.emit()
            self._refresh_state()
    
    def _show_unlock_dialog(self):
        is_init = not self.store.is_initialized()
        dialog = UnlockDialog(self, self.theme, is_init=is_init)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            password = dialog.get_password()
            remember = dialog.should_remember()
            
            try:
                if is_init:
                    self.store.init_vault(password)
                    success = self.store.unlock(password)
                else:
                    success = self.store.unlock(password)
                
                if success:
                    if remember:
                        KeychainIntegration.store_master_password(password)
                    self.vault_unlocked.emit()
                    self._refresh_state()
                else:
                    QMessageBox.warning(self, "Error", "Invalid password")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
    
    def try_auto_unlock(self) -> bool:
        """
        Try to auto-unlock using keychain.
        
        Returns:
            True if unlocked successfully
        """
        if not self.store.is_initialized():
            return False
        
        password = KeychainIntegration.get_master_password()
        if password and self.store.unlock(password):
            self.vault_unlocked.emit()
            self._refresh_state()
            return True
        return False
    
    def _refresh_credentials(self):
        """Refresh the credentials table."""
        self.table.setRowCount(0)
        
        try:
            credentials = self.store.list_credentials()
        except Exception as e:
            logger.error(f"Failed to list credentials: {e}")
            return
        
        for cred in credentials:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            self.table.setItem(row, 0, QTableWidgetItem(cred.name))
            self.table.setItem(row, 1, QTableWidgetItem(cred.username))
            
            # Auth methods
            auth_parts = []
            if cred.has_password:
                auth_parts.append("🔑")
            if cred.has_ssh_key:
                auth_parts.append("🗝️")
            self.table.setItem(row, 2, QTableWidgetItem(" ".join(auth_parts) or "Agent"))
            
            self.table.setItem(row, 3, QTableWidgetItem(cred.jump_host or "—"))
            self.table.setItem(row, 4, QTableWidgetItem("✓" if cred.is_default else ""))
            
            last_used = cred.last_used.strftime("%Y-%m-%d %H:%M") if cred.last_used else "Never"
            self.table.setItem(row, 5, QTableWidgetItem(last_used))
    
    def _on_selection_changed(self):
        has_selection = len(self.table.selectedItems()) > 0
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        
        if has_selection:
            row = self.table.currentRow()
            name = self.table.item(row, 0).text()
            self.credential_selected.emit(name)
    
    def _add_credential(self):
        dialog = CredentialDialog(self, self.theme)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_credential_data()
            try:
                self.store.add_credential(**data)
                self._refresh_credentials()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add credential: {e}")
    
    def _edit_credential(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        name = self.table.item(row, 0).text()
        cred = self.store.get_credential(name)
        if not cred:
            QMessageBox.warning(self, "Error", "Credential not found")
            return
        
        dialog = CredentialDialog(self, self.theme, credential=cred)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_credential_data()
            try:
                # Remove old and add updated
                self.store.remove_credential(name)
                self.store.add_credential(**data)
                self._refresh_credentials()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update credential: {e}")
    
    def _delete_credential(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        name = self.table.item(row, 0).text()
        
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete credential '{name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.store.remove_credential(name)
                self._refresh_credentials()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
    
    def get_selected_credential(self) -> Optional[str]:
        """Get currently selected credential name."""
        row = self.table.currentRow()
        if row >= 0:
            return self.table.item(row, 0).text()
        return None


# Import Path for browse dialog
from pathlib import Path


def run_standalone():
    """Run credential manager as standalone app."""
    import sys
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = QWidget()
    window.setWindowTitle("nTerm Credential Manager")
    window.setMinimumSize(800, 600)
    
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    
    manager = CredentialManagerWidget()
    manager.try_auto_unlock()
    layout.addWidget(manager)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_standalone()
