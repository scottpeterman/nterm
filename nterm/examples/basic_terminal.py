#!/usr/bin/env python3
"""
Example nterm application.

Demonstrates basic usage of the terminal widget with different session types:
- SSHSession: Paramiko-based (for password/key auth)
- AskpassSSHSession: Native SSH with GUI prompts (recommended for YubiKey)
- InteractiveSSHSession: Native SSH with PTY
"""

import sys
import logging
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QLabel, QPushButton, QStatusBar, QLineEdit, QSpinBox,
    QGroupBox, QFormLayout, QMessageBox, QDialog, QDialogButtonBox,
    QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from nterm import (
    ConnectionProfile, AuthConfig, AuthMethod, JumpHostConfig,
    SSHSession, SessionState, TerminalWidget, Theme, ThemeEngine,
    InteractiveSSHSession, is_pty_available
)
from nterm.session import AskpassSSHSession

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class YubiKeyDialog(QDialog):
    """Dialog shown when YubiKey touch is required."""
    
    def __init__(self, prompt: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YubiKey Authentication")
        self.setModal(True)
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        
        # Icon/visual indicator
        icon_label = QLabel("🔑")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Prompt
        prompt_label = QLabel(prompt)
        prompt_label.setWordWrap(True)
        prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prompt_label.setStyleSheet("font-size: 14px; margin: 10px;")
        layout.addWidget(prompt_label)
        
        # Instructions
        instructions = QLabel("Touch your YubiKey to authenticate...")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet("color: gray;")
        layout.addWidget(instructions)
        
        # Cancel button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class NTermWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("nterm - SSH Terminal")
        self.resize(1200, 800)
        
        self._session = None
        self._theme_engine = ThemeEngine()
        self._yubikey_dialog = None
        
        self._setup_ui()
        self._apply_theme("default")
    
    def _setup_ui(self):
        """Set up the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Terminal
        self._terminal = TerminalWidget()
        self._terminal.session_state_changed.connect(self._on_state_changed)
        self._terminal.interaction_required.connect(self._on_interaction)
        layout.addWidget(self._terminal, 1)
        
        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Disconnected")
    
    def _create_toolbar(self) -> QWidget:
        """Create connection toolbar."""
        toolbar = QWidget()
        toolbar.setFixedHeight(100)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Connection group
        conn_group = QGroupBox("Connection")
        conn_layout = QFormLayout(conn_group)
        conn_layout.setContentsMargins(8, 4, 8, 4)
        
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("hostname or IP")
        self._host_input.setText("localhost")
        conn_layout.addRow("Host:", self._host_input)
        
        port_layout = QHBoxLayout()
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        port_layout.addWidget(self._port_input)
        
        self._user_input = QLineEdit()
        self._user_input.setPlaceholderText("username")
        port_layout.addWidget(QLabel("User:"))
        port_layout.addWidget(self._user_input)
        conn_layout.addRow("Port:", port_layout)
        
        layout.addWidget(conn_group)
        
        # Session type group
        session_group = QGroupBox("Session Type")
        session_layout = QVBoxLayout(session_group)
        session_layout.setContentsMargins(8, 4, 8, 4)
        
        self._session_combo = QComboBox()
        self._session_combo.addItem("Askpass (YubiKey GUI)", "askpass")
        self._session_combo.addItem("Interactive (PTY)", "interactive")
        self._session_combo.addItem("Paramiko", "paramiko")
        self._session_combo.currentIndexChanged.connect(self._on_session_type_changed)
        session_layout.addWidget(self._session_combo)
        
        # Status indicator
        self._pty_label = QLabel("✓ GUI auth prompts" if is_pty_available() else "⚠ Limited")
        self._pty_label.setStyleSheet("color: green;" if is_pty_available() else "color: orange;")
        session_layout.addWidget(self._pty_label)
        
        layout.addWidget(session_group)
        
        # Auth group (for Paramiko mode)
        self._auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout(self._auth_group)
        auth_layout.setContentsMargins(8, 4, 8, 4)
        
        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["Agent", "Password", "Key File"])
        auth_layout.addRow("Method:", self._auth_combo)
        
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("(for password auth)")
        auth_layout.addRow("Password:", self._password_input)
        
        self._auth_group.setVisible(False)
        layout.addWidget(self._auth_group)
        
        # Jump host group
        jump_group = QGroupBox("Jump Host (Optional)")
        jump_layout = QFormLayout(jump_group)
        jump_layout.setContentsMargins(8, 4, 8, 4)
        
        self._jump_host_input = QLineEdit()
        self._jump_host_input.setPlaceholderText("bastion.example.com")
        jump_layout.addRow("Host:", self._jump_host_input)
        
        self._jump_user_input = QLineEdit()
        self._jump_user_input.setPlaceholderText("(same as main if empty)")
        jump_layout.addRow("User:", self._jump_user_input)
        
        layout.addWidget(jump_group)
        
        # Theme selector
        theme_group = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.setContentsMargins(8, 4, 8, 4)
        
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(self._theme_engine.list_themes())
        self._theme_combo.currentTextChanged.connect(self._apply_theme)
        theme_layout.addWidget(self._theme_combo)
        
        layout.addWidget(theme_group)
        
        # Buttons
        btn_layout = QVBoxLayout()
        
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._connect)
        self._connect_btn.setDefault(True)
        btn_layout.addWidget(self._connect_btn)
        
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect)
        self._disconnect_btn.setEnabled(False)
        btn_layout.addWidget(self._disconnect_btn)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        return toolbar
    
    def _on_session_type_changed(self, index: int):
        """Handle session type change."""
        session_type = self._session_combo.currentData()
        self._auth_group.setVisible(session_type == "paramiko")
        
        # Update status label
        if session_type == "askpass":
            self._pty_label.setText("✓ GUI auth prompts")
            self._pty_label.setStyleSheet("color: green;")
        elif session_type == "interactive":
            self._pty_label.setText("⚠ Console prompts")
            self._pty_label.setStyleSheet("color: orange;")
        else:
            self._pty_label.setText("✓ Programmatic auth")
            self._pty_label.setStyleSheet("color: green;")
    
    def _apply_theme(self, theme_name: str):
        """Apply selected theme."""
        theme = self._theme_engine.get_theme(theme_name)
        if theme:
            self._terminal.set_theme(theme)
    
    def _connect(self):
        """Establish connection."""
        hostname = self._host_input.text().strip()
        port = self._port_input.value()
        username = self._user_input.text().strip()
        session_type = self._session_combo.currentData()
        
        if not hostname:
            QMessageBox.warning(self, "Error", "Please enter a hostname")
            return
        
        if not username:
            QMessageBox.warning(self, "Error", "Please enter a username")
            return
        
        # Build auth config
        if session_type in ("askpass", "interactive"):
            auth = AuthConfig.agent_auth(username)
        else:
            auth_method = self._auth_combo.currentText()
            if auth_method == "Agent":
                auth = AuthConfig.agent_auth(username)
            elif auth_method == "Password":
                password = self._password_input.text()
                if not password:
                    QMessageBox.warning(self, "Error", "Please enter a password")
                    return
                auth = AuthConfig.password_auth(username, password)
            else:
                auth = AuthConfig.agent_auth(username, allow_fallback=True)
        
        # Build jump host config if specified
        jump_hosts = []
        jump_host = self._jump_host_input.text().strip()
        if jump_host:
            jump_user = self._jump_user_input.text().strip() or username
            jump_hosts.append(JumpHostConfig(
                hostname=jump_host,
                auth=AuthConfig.agent_auth(jump_user),
            ))
        
        # Create profile
        profile = ConnectionProfile(
            name=f"{username}@{hostname}",
            hostname=hostname,
            port=port,
            auth_methods=[auth],
            jump_hosts=jump_hosts,
            auto_reconnect=False,  # Disable for testing
        )
        
        # Create appropriate session type
        if session_type == "askpass":
            if not is_pty_available():
                QMessageBox.warning(self, "Error", "PTY support required")
                return
            self._session = AskpassSSHSession(profile)
        elif session_type == "interactive":
            if not is_pty_available():
                QMessageBox.warning(self, "Error", "PTY support required")
                return
            self._session = InteractiveSSHSession(profile)
        else:
            self._session = SSHSession(profile)
        
        self._terminal.attach_session(self._session)
        
        # Connect
        self._session.connect()
        self._connect_btn.setEnabled(False)
        self._disconnect_btn.setEnabled(True)
    
    def _disconnect(self):
        """Disconnect session."""
        # Close any open dialogs
        if self._yubikey_dialog:
            self._yubikey_dialog.close()
            self._yubikey_dialog = None
        
        if self._session:
            self._session.disconnect()
            self._terminal.detach_session()
            self._session = None
        
        self._connect_btn.setEnabled(True)
        self._disconnect_btn.setEnabled(False)
    
    def _on_state_changed(self, state: SessionState, message: str):
        """Handle session state changes."""
        status_text = {
            SessionState.DISCONNECTED: "Disconnected",
            SessionState.CONNECTING: "Connecting...",
            SessionState.AUTHENTICATING: "Authenticating...",
            SessionState.CONNECTED: "Connected",
            SessionState.RECONNECTING: f"Reconnecting: {message}",
            SessionState.FAILED: f"Failed: {message}",
        }.get(state, str(state))
        
        self._status.showMessage(status_text)
        
        # Close YubiKey dialog on connect/disconnect
        if state in (SessionState.CONNECTED, SessionState.DISCONNECTED, SessionState.FAILED):
            if self._yubikey_dialog:
                self._yubikey_dialog.close()
                self._yubikey_dialog = None
        
        if state == SessionState.CONNECTED:
            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(True)
            self._terminal.focus()
        elif state in (SessionState.DISCONNECTED, SessionState.FAILED):
            self._connect_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(False)
    
    def _on_interaction(self, prompt: str, interaction_type: str):
        """Handle SSH authentication prompts."""
        logger.info(f"Interaction required: {interaction_type} - {prompt}")
        
        if not isinstance(self._session, AskpassSSHSession):
            return
        
        if interaction_type == "yubikey_touch":
            # Show YubiKey dialog
            self._yubikey_dialog = YubiKeyDialog(prompt, self)
            result = self._yubikey_dialog.exec()
            self._yubikey_dialog = None
            
            if result == QDialog.DialogCode.Rejected:
                # User cancelled
                self._session.provide_askpass_response(False, error="Cancelled by user")
            else:
                # YubiKey was touched (dialog closed by external event)
                self._session.provide_askpass_response(True, value="")
        
        elif interaction_type == "password":
            # Show password dialog
            password, ok = QInputDialog.getText(
                self, "SSH Authentication", prompt,
                QLineEdit.EchoMode.Password
            )
            
            if ok and password:
                self._session.provide_askpass_response(True, value=password)
            else:
                self._session.provide_askpass_response(False, error="Cancelled by user")
        
        else:
            # Generic input
            text, ok = QInputDialog.getText(
                self, "SSH Authentication", prompt
            )
            
            if ok:
                self._session.provide_askpass_response(True, value=text)
            else:
                self._session.provide_askpass_response(False, error="Cancelled by user")
    
    def closeEvent(self, event):
        """Handle window close."""
        if self._session:
            self._session.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("nterm")
    
    window = NTermWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
