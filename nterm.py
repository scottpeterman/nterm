"""
Example: Session Manager with Tabbed Terminal

Demonstrates integrating the session tree with the terminal widget
and vault for a complete SSH client experience.
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QTabWidget,
    QWidget, QVBoxLayout, QHBoxLayout, QMessageBox,
    QDialog, QLabel, QLineEdit, QPushButton, QCheckBox,
    QMenuBar, QMenu
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from nterm.manager import (
    SessionTreeWidget, SessionStore, SavedSession, QuickConnectDialog,
    SettingsDialog, ExportDialog, ImportDialog, ImportTerminalTelemetryDialog
)
from nterm.terminal.widget import TerminalWidget
from nterm.session.ssh import SSHSession
from nterm.connection.profile import ConnectionProfile, AuthConfig
from nterm.vault import CredentialManagerWidget
from nterm.vault.resolver import CredentialResolver
from nterm.theme.engine import ThemeEngine, Theme
from nterm.theme.stylesheet import generate_stylesheet
from nterm.manager.connect_dialog import ConnectDialog



# Vault location
NTERM_DIR = Path.home() / ".nterm"


class VaultUnlockDialog(QDialog):
    """Dialog to unlock the credential vault on startup."""

    def __init__(self, resolver: CredentialResolver, parent=None):
        super().__init__(parent)
        self.resolver = resolver
        self._unlocked = False

        self.setWindowTitle("Unlock Vault")
        self.setFixedWidth(350)
        self.setModal(True)

        # Apply default theme styling
        default_theme = Theme.default()
        self.setStyleSheet(generate_stylesheet(default_theme))

        layout = QVBoxLayout(self)

        # Icon/message
        if not resolver.is_initialized():
            msg = QLabel("No vault found. Create a new vault password:")
            self._is_new = True
        else:
            msg = QLabel("Enter vault password to unlock credentials:")
            self._is_new = False
        layout.addWidget(msg)

        # Password input
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Vault password")
        self._password_input.returnPressed.connect(self._on_unlock)
        layout.addWidget(self._password_input)

        # Confirm password (new vault only)
        if self._is_new:
            self._confirm_input = QLineEdit()
            self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm_input.setPlaceholderText("Confirm password")
            self._confirm_input.returnPressed.connect(self._on_unlock)
            layout.addWidget(self._confirm_input)

        # Error label
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #f38ba8;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._skip_btn = QPushButton("Skip")
        self._skip_btn.setToolTip("Continue without vault (agent auth only)")
        self._skip_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._skip_btn)

        self._unlock_btn = QPushButton("Create Vault" if self._is_new else "Unlock")
        self._unlock_btn.setDefault(True)
        self._unlock_btn.clicked.connect(self._on_unlock)
        btn_layout.addWidget(self._unlock_btn)

        layout.addLayout(btn_layout)

        self._password_input.setFocus()

    def _on_unlock(self):
        """Attempt to unlock/create vault."""
        password = self._password_input.text()

        if not password:
            self._show_error("Password required")
            return

        if self._is_new:
            confirm = self._confirm_input.text()
            if password != confirm:
                self._show_error("Passwords don't match")
                return

            try:
                self.resolver.init_vault(password)
                self._unlocked = True
                self.accept()
            except Exception as e:
                self._show_error(f"Failed to create vault: {e}")
        else:
            if self.resolver.unlock_vault(password):
                self._unlocked = True
                self.accept()
            else:
                self._show_error("Incorrect password")
                self._password_input.selectAll()
                self._password_input.setFocus()

    def _show_error(self, msg: str):
        """Show error message."""
        self._error_label.setText(msg)
        self._error_label.show()

    def is_unlocked(self) -> bool:
        """Check if vault was successfully unlocked."""
        return self._unlocked


class CredentialManagerDialog(QDialog):
    """Dialog wrapper for the credential manager widget."""

    def __init__(
        self,
        credential_resolver: CredentialResolver,
        theme: Theme = None,
        parent=None
    ):
        super().__init__(parent)
        self.credential_resolver = credential_resolver

        self.setWindowTitle("Credential Manager")
        self.setMinimumSize(700, 500)
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Credential manager widget
        self.manager = CredentialManagerWidget(store=credential_resolver.store)
        layout.addWidget(self.manager)

        # Apply theme if provided
        if theme:
            self.manager.set_theme(theme)
            self.setStyleSheet(generate_stylesheet(theme))

        # Try auto-unlock if available
        self.manager.try_auto_unlock()


class TerminalTab(QWidget):
    """A terminal tab with session info."""

    def __init__(
        self,
        session: SavedSession,
        profile: ConnectionProfile,
        credential_resolver: CredentialResolver = None,
        parent=None
    ):
        super().__init__(parent)
        self.session = session
        self.profile = profile
        self.credential_resolver = credential_resolver

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.terminal = TerminalWidget()
        layout.addWidget(self.terminal)

        # Pass the vault to SSHSession for credential resolution
        vault = credential_resolver if credential_resolver else None
        self.ssh_session = SSHSession(profile, vault=vault)
        self.terminal.attach_session(self.ssh_session)

    def connect(self):
        """Start the SSH connection."""
        self.ssh_session.connect()

    def disconnect(self):
        """Disconnect the session."""
        self.ssh_session.disconnect()


class MainWindow(QMainWindow):
    """
    Main application window with session tree and tabbed terminals.
    """

    def __init__(self, credential_resolver: CredentialResolver):
        super().__init__()
        self.setWindowTitle("nterm")
        self.resize(1200, 800)

        # Initialize stores
        self.session_store = SessionStore()
        self.credential_resolver = credential_resolver
        self.theme_engine = ThemeEngine()

        # Current theme
        self.current_theme = self.theme_engine.current

        self._setup_ui()
        self._connect_signals()
        self._refresh_credentials()

        # Apply initial stylesheet
        self._apply_qt_theme(self.current_theme)

    def _refresh_credentials(self):
        """Refresh credential list for session editor."""
        self._credential_names = []
        if self.credential_resolver.is_initialized():
            try:
                creds = self.credential_resolver.list_credentials()
                self._credential_names = [c.name for c in creds]
            except:
                pass

    def _setup_ui(self):
        """Build the main UI."""
        # Menu bar
        self._setup_menu_bar()

        # Main splitter: tree | tabs
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Session tree (left panel)
        self.session_tree = SessionTreeWidget(self.session_store)
        self.session_tree.setMinimumWidth(200)
        self.session_tree.setMaximumWidth(400)
        splitter.addWidget(self.session_tree)

        # Tab widget (right panel)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        splitter.addWidget(self.tab_widget)

        # Set initial sizes (tree: 250px, tabs: rest)
        splitter.setSizes([250, 950])

        self.setCentralWidget(splitter)

    def _connect_signals(self):
        """Connect UI signals."""
        self.session_tree.connect_requested.connect(self._on_connect_requested)
        self.session_tree.quick_connect_requested.connect(self._on_quick_connect)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)

    def _setup_menu_bar(self):
        """Setup application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        quick_connect_action = QAction("&Quick Connect...", self)
        quick_connect_action.setShortcut(QKeySequence("Ctrl+N"))
        quick_connect_action.triggered.connect(self._on_quick_connect)
        file_menu.addAction(quick_connect_action)

        file_menu.addSeparator()

        import_action = QAction("&Import Sessions...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self._on_import_sessions)
        file_menu.addAction(import_action)

        export_action = QAction("&Export Sessions...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_sessions)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        tt_import_action = QAction("Import from &TerminalTelemetry...", self)
        tt_import_action.triggered.connect(self._on_import_terminal_telemetry)
        file_menu.addAction(tt_import_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        settings_action = QAction("&Settings...", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self._on_settings)
        edit_menu.addAction(settings_action)

        edit_menu.addSeparator()

        cred_manager_action = QAction("&Credential Manager...", self)
        cred_manager_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        cred_manager_action.triggered.connect(self._on_credential_manager)
        edit_menu.addAction(cred_manager_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")
        for theme_name in self.theme_engine.list_themes():
            action = QAction(theme_name.replace("_", " ").title(), self)
            action.setData(theme_name)
            action.triggered.connect(lambda checked, n=theme_name: self._apply_theme_by_name(n))
            theme_menu.addAction(action)

    def _on_import_sessions(self):
        """Show import dialog."""
        dialog = ImportDialog(self.session_store, self)
        if dialog.exec():
            self.session_tree.refresh()

    def _on_export_sessions(self):
        """Show export dialog."""
        dialog = ExportDialog(self.session_store, self)
        dialog.exec()

    def _on_import_terminal_telemetry(self):
        """Show TerminalTelemetry import dialog."""
        dialog = ImportTerminalTelemetryDialog(self.session_store, self)
        if dialog.exec():
            self.session_tree.refresh()

    def _on_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.theme_engine, self.current_theme, self)
        dialog.theme_changed.connect(self._apply_theme)
        dialog.exec()

    def _on_credential_manager(self):
        """Show credential manager dialog."""
        dialog = CredentialManagerDialog(
            self.credential_resolver,
            self.current_theme,
            self
        )
        dialog.exec()
        # Refresh credential list in case any were added/removed
        self._refresh_credentials()

    def _apply_theme(self, theme: Theme):
        """Apply theme to all terminals and Qt UI."""
        self.current_theme = theme

        # Update Qt stylesheet
        self._apply_qt_theme(theme)

        # Update all open terminal tabs
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, TerminalTab):
                tab.terminal.set_theme(theme)

    def _apply_qt_theme(self, theme: Theme):
        """Apply theme stylesheet to Qt widgets."""
        stylesheet = generate_stylesheet(theme)
        self.setStyleSheet(stylesheet)

    def _apply_theme_by_name(self, name: str):
        """Apply theme by name."""
        theme = self.theme_engine.get_theme(name)
        if theme:
            self.theme_engine.current = theme
            self._apply_theme(theme)

    def _on_connect_requested(self, session: SavedSession, mode: str):
        """Handle connect request from session tree."""
        # Show connection dialog
        dialog = ConnectDialog(
            session,
            credential_resolver=self.credential_resolver,
            credential_names=self._credential_names,
            parent=self
        )

        if not dialog.exec():
            return  # User cancelled

        profile = dialog.get_profile()
        if not profile:
            return

        if mode == SessionTreeWidget.MODE_TAB:
            self._open_in_tab(session, profile)
        elif mode == SessionTreeWidget.MODE_WINDOW:
            self._open_in_window(session, profile)

    def _on_quick_connect(self):
        """Handle quick connect request."""
        dialog = QuickConnectDialog(self._credential_names, self)
        if dialog.exec():
            session = dialog.get_session()
            mode = dialog.get_connect_mode()

            # Show connection dialog for auth options
            connect_dialog = ConnectDialog(
                session,
                credential_resolver=self.credential_resolver,
                credential_names=self._credential_names,
                parent=self
            )

            if not connect_dialog.exec():
                return

            profile = connect_dialog.get_profile()
            if profile:
                if mode == "tab":
                    self._open_in_tab(session, profile)
                else:
                    self._open_in_window(session, profile)

    def _build_profile(self, session: SavedSession) -> ConnectionProfile:
        """Build ConnectionProfile from SavedSession."""
        auth_methods = []

        # Try to resolve credential from vault
        if session.credential_name and self.credential_resolver.is_initialized():
            try:
                profile = self.credential_resolver.create_profile_for_credential(
                    session.credential_name,
                    session.hostname,
                    session.port
                )
                return profile
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Credential Error",
                    f"Failed to load credential '{session.credential_name}': {e}\n\n"
                    "Falling back to SSH agent."
                )

        # Default to agent auth
        auth_methods.append(AuthConfig.agent_auth("$USER"))  # Will use current user

        return ConnectionProfile(
            name=session.name,
            hostname=session.hostname,
            port=session.port,
            auth_methods=auth_methods,
        )

    def _open_in_tab(self, session: SavedSession, profile: ConnectionProfile):
        """Open session in a new tab."""
        tab = TerminalTab(session, profile, self.credential_resolver)
        tab.terminal.set_theme(self.current_theme)

        idx = self.tab_widget.addTab(tab, session.name)
        self.tab_widget.setCurrentIndex(idx)
        self.tab_widget.setTabToolTip(idx, f"{session.hostname}:{session.port}")

        tab.connect()

    def _open_in_window(self, session: SavedSession, profile: ConnectionProfile):
        """Open session in a separate window."""
        window = TerminalWindow(session, profile, self.current_theme, self.credential_resolver)
        window.show()

        # Keep reference to prevent garbage collection
        if not hasattr(self, '_child_windows'):
            self._child_windows = []
        self._child_windows.append(window)
        window.destroyed.connect(lambda: self._child_windows.remove(window))

    def _close_tab(self, index: int):
        """Close a terminal tab."""
        tab = self.tab_widget.widget(index)
        if isinstance(tab, TerminalTab):
            tab.disconnect()
        self.tab_widget.removeTab(index)

    def closeEvent(self, event):
        """Clean up on close."""
        # Disconnect all tabs
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, TerminalTab):
                tab.disconnect()

        self.session_store.close()
        event.accept()


class TerminalWindow(QMainWindow):
    """Standalone terminal window for a single session."""

    def __init__(
        self,
        session: SavedSession,
        profile: ConnectionProfile,
        theme: Theme,
        credential_resolver: CredentialResolver = None
    ):
        super().__init__()
        self.setWindowTitle(f"{session.name} - {session.hostname}")
        self.resize(1000, 700)

        # Apply Qt theme
        self.setStyleSheet(generate_stylesheet(theme))

        self.tab = TerminalTab(session, profile, credential_resolver)
        self.tab.terminal.set_theme(theme)
        self.setCentralWidget(self.tab)

        self.tab.connect()

    def closeEvent(self, event):
        """Disconnect on close."""
        self.tab.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)

    # Optional: Apply app-wide style
    app.setStyle("Fusion")

    # Ensure .nterm directory exists
    NTERM_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize credential resolver
    resolver = CredentialResolver()

    # Unlock vault on startup
    unlock_dialog = VaultUnlockDialog(resolver)
    unlock_dialog.exec()

    if unlock_dialog.is_unlocked():
        print(f"Vault unlocked: {resolver.db_path}")
    else:
        print("Continuing without vault (agent auth only)")

    # Create and show main window
    window = MainWindow(resolver)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()