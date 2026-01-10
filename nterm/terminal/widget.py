"""
PyQt6 terminal widget using xterm.js.
"""

from __future__ import annotations
import base64
import json
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebChannel import QWebChannel

from ..session.base import (
    Session, SessionState, SessionEvent,
    DataReceived, StateChanged, InteractionRequired, BannerReceived
)
from ..theme.engine import Theme
from .bridge import TerminalBridge

logger = logging.getLogger(__name__)

RESOURCES = Path(__file__).parent / "resources"


class TerminalWidget(QWidget):
    """
    Themeable terminal widget.
    
    Renders terminal via xterm.js in QWebEngineView.
    Connects to a Session for I/O.
    """
    
    # Public signals
    session_state_changed = pyqtSignal(SessionState, str)
    interaction_required = pyqtSignal(str, str)  # prompt, type
    reconnect_requested = pyqtSignal()  # emitted when user wants to reconnect
    title_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._session: Optional[Session] = None
        self._theme: Optional[Theme] = None
        self._ready = False
        self._pending_writes: list[bytes] = []
        self._awaiting_reconnect_confirm = False

        self._setup_ui()
        self._setup_bridge()

    def _setup_ui(self):
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._webview = QWebEngineView()
        self._webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Configure web settings
        settings = self._webview.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled,
            True
        )

        layout.addWidget(self._webview)

    def _setup_bridge(self):
        """Set up QWebChannel bridge to JavaScript."""
        self._bridge = TerminalBridge()
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._webview.page().setWebChannel(self._channel)

        # Connect bridge signals
        self._bridge.data_from_terminal.connect(self._on_terminal_data)
        self._bridge.size_changed.connect(self._on_terminal_resize)
        self._bridge.terminal_ready.connect(self._on_terminal_ready)
        self._bridge.title_changed.connect(self.title_changed.emit)

        # Load terminal HTML
        html_path = RESOURCES / "terminal.html"
        if html_path.exists():
            self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))
        else:
            logger.error(f"Terminal HTML not found: {html_path}")

    def attach_session(self, session: Session) -> None:
        """
        Attach a session for I/O.

        Args:
            session: Session to attach
        """
        if self._session:
            self.detach_session()

        self._session = session
        self._session.set_event_handler(self._on_session_event)
        self._awaiting_reconnect_confirm = False
        logger.debug(f"Attached session")

    def detach_session(self) -> None:
        """Detach current session."""
        if self._session:
            self._session.set_event_handler(None)
            self._session = None
            self._awaiting_reconnect_confirm = False
            logger.debug("Detached session")

    def set_theme(self, theme: Theme) -> None:
        """
        Apply theme to terminal.

        Args:
            theme: Theme to apply
        """
        self._theme = theme
        if self._ready:
            self._apply_theme()

    def _apply_theme(self):
        """Apply current theme to terminal."""
        if self._theme:
            self._bridge.apply_theme.emit(json.dumps(self._theme.terminal_colors))
            self._bridge.set_font.emit(
                self._theme.font_family,
                self._theme.font_size
            )

    def write(self, data: bytes) -> None:
        """
        Write data to terminal display.

        Args:
            data: Bytes to display
        """
        if self._ready:
            data_b64 = base64.b64encode(data).decode('ascii')
            self._bridge.write_data.emit(data_b64)
        else:
            self._pending_writes.append(data)

    def clear(self) -> None:
        """Clear terminal display."""
        if self._ready:
            self._bridge.clear_terminal.emit()

    def focus(self) -> None:
        """Focus the terminal for input."""
        if self._ready:
            self._bridge.focus_terminal.emit()
        self._webview.setFocus()

    def show_overlay(self, message: str) -> None:
        """
        Show overlay message.

        Args:
            message: Message to display
        """
        if self._ready:
            self._bridge.show_overlay.emit(message)

    def hide_overlay(self) -> None:
        """Hide overlay message."""
        if self._ready:
            self._bridge.hide_overlay.emit()

    def _on_terminal_ready(self):
        """Terminal initialized, apply settings."""
        logger.debug("Terminal ready")
        self._ready = True

        if self._theme:
            self._apply_theme()

        # Flush pending writes
        for data in self._pending_writes:
            self.write(data)
        self._pending_writes.clear()

    def _is_disconnected(self) -> bool:
        """Check if session is in a disconnected state."""
        if not self._session:
            return True
        return self._session.state in (
            SessionState.DISCONNECTED,
            SessionState.FAILED,
        )

    @pyqtSlot(str)
    def _on_terminal_data(self, data_b64: str):
        """User typed in terminal."""
        if self._session and self._session.is_connected:
            data = base64.b64decode(data_b64)
            self._session.write(data)
        elif self._is_disconnected():
            # User typed while disconnected - offer to reconnect
            if self._awaiting_reconnect_confirm:
                # They confirmed - emit reconnect signal
                self._awaiting_reconnect_confirm = False
                self.hide_overlay()
                self.reconnect_requested.emit()
            else:
                # First keypress - show prompt
                self._awaiting_reconnect_confirm = True
                self.show_overlay("Disconnected. Press any key to reconnect...")

    @pyqtSlot(int, int)
    def _on_terminal_resize(self, cols: int, rows: int):
        """Terminal resized."""
        logger.debug(f"Terminal resize: {cols}x{rows}")
        if self._session:
            self._session.resize(cols, rows)

    def _on_session_event(self, event: SessionEvent):
        """Handle session events."""
        if isinstance(event, DataReceived):
            self.write(event.data)

        elif isinstance(event, StateChanged):
            self.session_state_changed.emit(event.new_state, event.message)

            # Reset reconnect confirmation state on any state change
            self._awaiting_reconnect_confirm = False

            if event.new_state == SessionState.CONNECTING:
                self.show_overlay("Connecting...")
            elif event.new_state == SessionState.AUTHENTICATING:
                self.show_overlay("Authenticating...")
            elif event.new_state == SessionState.CONNECTED:
                self.hide_overlay()
            elif event.new_state == SessionState.DISCONNECTED:
                self.show_overlay("Disconnected. Press any key to reconnect...")
                self._awaiting_reconnect_confirm = True
            elif event.new_state == SessionState.FAILED:
                self.show_overlay(f"Connection failed: {event.message}")
                # Don't auto-prompt for reconnect on failure, let them decide

        elif isinstance(event, InteractionRequired):
            self.interaction_required.emit(event.prompt, event.interaction_type)
            self.show_overlay(event.prompt)

        elif isinstance(event, BannerReceived):
            # Could display banner in overlay or write to terminal
            logger.info(f"Banner: {event.banner[:100]}...")