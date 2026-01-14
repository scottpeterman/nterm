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
    QMenuBar, QMenu, QTabBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from nterm.manager import (
    SessionTreeWidget, SessionStore, SavedSession, QuickConnectDialog,
    SettingsDialog, ExportDialog, ImportDialog, ImportTerminalTelemetryDialog
)
from nterm.parser.ntc_download_dialog import NTCDownloadDialog
from nterm.parser.api_help_dialog import APIHelpDialog
from nterm.terminal.widget import TerminalWidget
from nterm.session.ssh import SSHSession
from nterm.session.local_terminal import LocalTerminal
from nterm.connection.profile import ConnectionProfile, AuthConfig
from nterm.vault import CredentialManagerWidget
from nterm.vault.resolver import CredentialResolver
from nterm.theme.engine import ThemeEngine, Theme
from nterm.theme.stylesheet import generate_stylesheet
from nterm.manager.connect_dialog import ConnectDialog
from nterm.config import get_settings_manager, get_settings, save_settings



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

    def is_connected(self) -> bool:
        """Check if the session is currently connected."""
        # Try multiple ways to detect connection state
        if hasattr(self.ssh_session, 'is_connected'):
            return self.ssh_session.is_connected
        if hasattr(self.ssh_session, 'connected'):
            return self.ssh_session.connected
        if hasattr(self.ssh_session, '_connected'):
            return self.ssh_session._connected
        if hasattr(self.ssh_session, '_channel'):
            return self.ssh_session._channel is not None
        if hasattr(self.ssh_session, '_transport'):
            transport = self.ssh_session._transport
            return transport is not None and transport.is_active()
        # Default to True if we can't determine - safer to warn
        return True


class LocalTerminalTab(QWidget):
    """A terminal tab for local processes (shell, IPython, etc.)."""

    def __init__(self, name: str, session: LocalTerminal, parent=None):
        super().__init__(parent)
        self.name = name
        self.local_session = session

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.terminal = TerminalWidget()
        layout.addWidget(self.terminal)

        self.terminal.attach_session(self.local_session)

    def connect(self):
        """Start the local process."""
        self.local_session.connect()

    def disconnect(self):
        """Terminate the local process."""
        self.local_session.disconnect()

    def is_connected(self) -> bool:
        """Check if the process is still running."""
        return self.local_session.is_connected


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

        # Load persistent settings
        self.settings_manager = get_settings_manager()
        self.app_settings = self.settings_manager.settings

        # Apply saved window geometry
        self.resize(self.app_settings.window_width, self.app_settings.window_height)
        if self.app_settings.window_x is not None and self.app_settings.window_y is not None:
            self.move(self.app_settings.window_x, self.app_settings.window_y)
        if self.app_settings.window_maximized:
            self.showMaximized()

        # Initialize stores
        self.session_store = SessionStore()
        self.credential_resolver = credential_resolver
        self.theme_engine = ThemeEngine()

        # Load saved theme (instead of default)
        saved_theme = self.theme_engine.get_theme(self.app_settings.theme_name)
        self.current_theme = saved_theme if saved_theme else self.theme_engine.current

        self._setup_ui()
        self._connect_signals()
        self._refresh_credentials()

        # Apply initial stylesheet
        self._apply_qt_theme(self.current_theme)

    def _on_settings_changed(self, settings):
        """Handle settings changes from dialog."""
        self.app_settings = settings

        # Apply multiline threshold to all open terminals
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)):
                tab.terminal.set_multiline_threshold(settings.multiline_paste_threshold)


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

        # Enable tab context menu
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self._show_tab_context_menu)

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

        # --- NEW: Tab management actions ---
        close_tab_action = QAction("Close Tab", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(self._close_current_tab)
        file_menu.addAction(close_tab_action)

        close_all_action = QAction("Close All Tabs", self)
        close_all_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        close_all_action.triggered.connect(self._close_all_tabs)
        file_menu.addAction(close_all_action)

        file_menu.addSeparator()
        # --- END NEW ---

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

        # Dev menu
        dev_menu = menubar.addMenu("&Dev")

        # IPython submenu
        ipython_menu = dev_menu.addMenu("&IPython")

        ipython_tab_action = QAction("Open in &Tab", self)
        ipython_tab_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        ipython_tab_action.triggered.connect(lambda: self._open_local("IPython", LocalTerminal.ipython(), "tab"))
        ipython_menu.addAction(ipython_tab_action)

        ipython_window_action = QAction("Open in &Window", self)
        ipython_window_action.triggered.connect(lambda: self._open_local("IPython", LocalTerminal.ipython(), "window"))
        ipython_menu.addAction(ipython_window_action)

        # Shell submenu
        shell_menu = dev_menu.addMenu("&Shell")

        shell_tab_action = QAction("Open in &Tab", self)
        shell_tab_action.triggered.connect(lambda: self._open_local("Shell", LocalTerminal(), "tab"))
        shell_menu.addAction(shell_tab_action)

        shell_window_action = QAction("Open in &Window", self)
        shell_window_action.triggered.connect(lambda: self._open_local("Shell", LocalTerminal(), "window"))
        shell_menu.addAction(shell_window_action)

        # Separator before tools
        dev_menu.addSeparator()

        # Download NTC Templates
        download_templates_action = QAction("Download &NTC Templates...", self)
        download_templates_action.triggered.connect(self._on_download_ntc_templates)
        dev_menu.addAction(download_templates_action)

        # TextFSM Template Tester
        template_tester_action = QAction("TextFSM &Template Tester...", self)
        template_tester_action.triggered.connect(self._on_textfsm_tester)
        dev_menu.addAction(template_tester_action)

        # API Help
        api_help_action = QAction("&API Help...", self)
        api_help_action.setShortcut(QKeySequence("F1"))
        api_help_action.triggered.connect(self._on_api_help)
        dev_menu.addAction(api_help_action)

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

    def _on_download_ntc_templates(self):
        """Show NTC template download dialog."""
        # Use the same db path as the TextFSM engine would use
        db_path = Path.cwd() / "tfsm_templates.db"
        dialog = NTCDownloadDialog(self, str(db_path))
        dialog.exec()

    def _on_textfsm_tester(self):
        """Launch TextFSM Template Tester."""
        import subprocess
        import sys

        # Launch as separate process
        try:
            subprocess.Popen([sys.executable, "-m", "nterm.parser.tfsm_fire_tester"])
        except Exception as e:
            QMessageBox.critical(
                self,
                "Launch Error",
                f"Failed to launch TextFSM Template Tester:\n{e}"
            )

    def _on_api_help(self):
        """Show API help dialog."""
        dialog = APIHelpDialog(self)
        dialog.exec()

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
            if isinstance(tab, (TerminalTab, LocalTerminalTab)):
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

    def _open_local(self, name: str, session: LocalTerminal, mode: str):
        """Open a local terminal session (IPython, shell, etc.)."""
        if mode == "tab":
            tab = LocalTerminalTab(name, session)
            tab.terminal.set_theme(self.current_theme)
            idx = self.tab_widget.addTab(tab, name)
            self.tab_widget.setCurrentIndex(idx)
            self.tab_widget.setTabToolTip(idx, f"{name} (local)")
            tab.connect()
        else:
            window = LocalTerminalWindow(name, session, self.current_theme)
            window.show()
            if not hasattr(self, '_child_windows'):
                self._child_windows = []
            self._child_windows.append(window)
            window.destroyed.connect(lambda: self._child_windows.remove(window))

    # -------------------------------------------------------------------------
    # Tab Management (NEW)
    # -------------------------------------------------------------------------

    def _get_active_session_count(self) -> int:
        """Count tabs with active connections."""
        count = 0
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)) and tab.is_connected():
                count += 1
        return count

    def _show_tab_context_menu(self, pos):
        """Show context menu for tab bar."""
        tab_bar = self.tab_widget.tabBar()
        index = tab_bar.tabAt(pos)

        menu = QMenu(self)

        if index >= 0:
            # Clicked on a tab
            menu.addAction("Close", lambda: self._close_tab(index))
            menu.addAction("Close Others", lambda: self._close_other_tabs(index))
            menu.addAction("Close Tabs to the Right", lambda: self._close_tabs_to_right(index))
            menu.addSeparator()

        if self.tab_widget.count() > 0:
            menu.addAction("Close All Tabs", self._close_all_tabs)

        if menu.actions():
            menu.exec(tab_bar.mapToGlobal(pos))

    def _close_current_tab(self):
        """Close the currently active tab."""
        index = self.tab_widget.currentIndex()
        if index >= 0:
            self._close_tab(index)

    def _close_tab(self, index: int):
        """Close a terminal tab with confirmation if connected."""
        tab = self.tab_widget.widget(index)

        if isinstance(tab, TerminalTab):
            # Check if session is active
            if tab.is_connected():
                reply = QMessageBox.question(
                    self,
                    "Close Tab",
                    f"'{tab.session.name}' has an active connection.\n\n"
                    "Disconnect and close this tab?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            tab.disconnect()

        elif isinstance(tab, LocalTerminalTab):
            # Check if process is still running
            if tab.is_connected():
                reply = QMessageBox.question(
                    self,
                    "Close Tab",
                    f"'{tab.name}' is still running.\n\n"
                    "Terminate and close this tab?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            tab.disconnect()

        self.tab_widget.removeTab(index)

    def _close_other_tabs(self, keep_index: int):
        """Close all tabs except the specified one."""
        active_count = self._get_active_session_count()
        tab_to_keep = self.tab_widget.widget(keep_index)
        keep_is_active = isinstance(tab_to_keep, (TerminalTab, LocalTerminalTab)) and tab_to_keep.is_connected()
        other_active = active_count - (1 if keep_is_active else 0)

        if other_active > 0:
            reply = QMessageBox.question(
                self,
                "Close Other Tabs",
                f"{other_active} other tab(s) have active connections.\n\n"
                "Disconnect and close them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Close tabs from end to avoid index shifting issues
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if i != keep_index:
                tab = self.tab_widget.widget(i)
                if isinstance(tab, (TerminalTab, LocalTerminalTab)):
                    tab.disconnect()
                self.tab_widget.removeTab(i)

    def _close_tabs_to_right(self, index: int):
        """Close all tabs to the right of the specified index."""
        tabs_to_close = self.tab_widget.count() - index - 1
        if tabs_to_close <= 0:
            return

        # Count active sessions to the right
        active_count = 0
        for i in range(index + 1, self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)) and tab.is_connected():
                active_count += 1

        if active_count > 0:
            reply = QMessageBox.question(
                self,
                "Close Tabs",
                f"{active_count} tab(s) to the right have active connections.\n\n"
                "Disconnect and close them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Close from end to avoid index shifting
        for i in range(self.tab_widget.count() - 1, index, -1):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)):
                tab.disconnect()
            self.tab_widget.removeTab(i)

    def _close_all_tabs(self):
        """Close all tabs with confirmation."""
        if self.tab_widget.count() == 0:
            return

        active_count = self._get_active_session_count()

        if active_count > 0:
            reply = QMessageBox.question(
                self,
                "Close All Tabs",
                f"{active_count} tab(s) have active connections.\n\n"
                "Disconnect and close all tabs?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Close all tabs
        while self.tab_widget.count() > 0:
            tab = self.tab_widget.widget(0)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)):
                tab.disconnect()
            self.tab_widget.removeTab(0)

    # -------------------------------------------------------------------------
    # End Tab Management
    # -------------------------------------------------------------------------

    def closeEvent(self, event):
        """Clean up on close with confirmation for active sessions."""
        # Save window geometry first
        if not self.isMaximized():
            self.app_settings.window_width = self.width()
            self.app_settings.window_height = self.height()
            self.app_settings.window_x = self.x()
            self.app_settings.window_y = self.y()
        self.app_settings.window_maximized = self.isMaximized()

        # Check for active connections
        active_count = self._get_active_session_count()

        if active_count > 0:
            reply = QMessageBox.question(
                self,
                "Quit nterm",
                f"You have {active_count} active session(s).\n\n"
                "Disconnect all and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        save_settings()

        # Disconnect all tabs
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if isinstance(tab, (TerminalTab, LocalTerminalTab)):
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
        """Disconnect on close with confirmation."""
        if self.tab.is_connected():
            reply = QMessageBox.question(
                self,
                "Close Window",
                f"'{self.tab.session.name}' has an active connection.\n\n"
                "Disconnect and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        self.tab.disconnect()
        event.accept()


class LocalTerminalWindow(QMainWindow):
    """Standalone window for local terminal sessions."""

    def __init__(self, name: str, session: LocalTerminal, theme: Theme):
        super().__init__()
        self.setWindowTitle(f"{name} - Local")
        self.resize(1000, 700)

        self.setStyleSheet(generate_stylesheet(theme))

        self.tab = LocalTerminalTab(name, session)
        self.tab.terminal.set_theme(theme)
        self.setCentralWidget(self.tab)

        self.tab.connect()

    def closeEvent(self, event):
        """Terminate on close with confirmation."""
        if self.tab.is_connected():
            reply = QMessageBox.question(
                self,
                "Close Window",
                f"'{self.tab.name}' is still running.\n\nTerminate and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

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