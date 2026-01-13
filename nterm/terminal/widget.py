"""
PyQt6 terminal widget using xterm.js.
"""

from __future__ import annotations
import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional, BinaryIO

from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication, QFileDialog
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

from nterm.resources import resources

# Default threshold for multiline paste warning
MULTILINE_PASTE_THRESHOLD = 1

# ANSI escape sequence pattern for stripping from capture logs
ANSI_ESCAPE = re.compile(rb'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[[\?0-9;]*[hl]')


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

    def __init__(self, parent=None, multiline_threshold: int = MULTILINE_PASTE_THRESHOLD):
        super().__init__(parent)

        self._session: Optional[Session] = None
        self._theme: Optional[Theme] = None
        self._ready = False
        self._pending_writes: list[bytes] = []
        self._awaiting_reconnect_confirm = False
        self._multiline_threshold = multiline_threshold
        self._pending_paste: Optional[bytes] = None  # held during confirmation

        # Session capture
        self._capture_file: Optional[BinaryIO] = None
        self._capture_path: Optional[Path] = None

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

        # Clipboard signals
        self._bridge.selection_copied.connect(self._on_selection_copied)
        self._bridge.paste_requested.connect(self._on_paste_requested)
        self._bridge.paste_confirmed.connect(self._on_paste_confirmed)
        self._bridge.paste_cancelled.connect(self._on_paste_cancelled)

        # Capture signals
        self._bridge.capture_toggled.connect(self._on_capture_toggle)

        # Load terminal HTML
        try:
            html_path = resources.get_path("terminal", "resources", "terminal.html")
            self._webview.setUrl(QUrl.fromLocalFile(str(html_path)))
        except FileNotFoundError as e:
            logger.error(f"Terminal HTML not found: {e}")

    def attach_session(self, session: Session) -> None:
        """
        Attach a session for I/O.

        Args:
            session: Session to attach
        """
        if self._session:
            self.detach_session()

        self._session = session
        self._session.set_auto_reconnect(False)  # Widget controls reconnect
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

        # Stop any active capture
        self.stop_capture()

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
        # Session capture - strip ANSI escapes for clean text
        if self._capture_file:
            clean = ANSI_ESCAPE.sub(b'', data)
            self._capture_file.write(clean)

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

    def show_overlay(self, message: str, show_spinner: bool = False) -> None:
        """
        Show overlay message.

        Args:
            message: Message to display
            show_spinner: Whether to show the spinner animation
        """
        if self._ready:
            self._bridge.show_overlay.emit(message, show_spinner)

    def hide_overlay(self) -> None:
        """Hide overlay message."""
        if self._ready:
            self._bridge.hide_overlay.emit()

    # -------------------------------------------------------------------------
    # Session capture
    # -------------------------------------------------------------------------

    @property
    def is_capturing(self) -> bool:
        """Check if session capture is active."""
        return self._capture_file is not None

    def start_capture(self, path: Path) -> None:
        """
        Start capturing session output to file.

        Args:
            path: File path to write captured output
        """
        self.stop_capture()  # Close any existing capture
        self._capture_path = path
        self._capture_file = open(path, 'wb')
        self._bridge.set_capture_state.emit(True, path.name)
        logger.info(f"Started capture: {path}")

    def stop_capture(self) -> None:
        """Stop capturing session output."""
        if self._capture_file:
            self._capture_file.close()
            logger.info(f"Stopped capture: {self._capture_path}")
            self._capture_file = None
            self._capture_path = None
        self._bridge.set_capture_state.emit(False, "")

    @pyqtSlot()
    def _on_capture_toggle(self):
        """Handle capture menu item click."""
        if self._capture_file:
            self.stop_capture()
        else:
            # Show file save dialog
            default_name = "session.log"
            if self._session:
                # Use hostname if available for default filename
                default_name = f"session_{self._session.hostname}.log" if hasattr(self._session, 'hostname') else "session.log"

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Session Capture",
                str(Path.home() / default_name),
                "Log Files (*.log *.txt);;All Files (*)"
            )
            if path:
                self.start_capture(Path(path))

    # -------------------------------------------------------------------------
    # Clipboard operations
    # -------------------------------------------------------------------------

    def copy(self) -> None:
        """Copy current terminal selection to clipboard."""
        if self._ready:
            self._bridge.do_copy.emit()

    def paste(self) -> None:
        """
        Paste from clipboard with multiline safety check.

        If content contains more lines than threshold, shows confirmation dialog.
        """
        if not self._ready:
            return

        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text:
            return

        # Count newlines
        line_count = text.count('\n')

        if line_count > self._multiline_threshold:
            # Store pending paste and request confirmation
            self._pending_paste = text.encode('utf-8')

            # Create preview (first few lines)
            lines = text.split('\n')
            preview_lines = lines[:5]
            preview = '\n'.join(preview_lines)
            if len(lines) > 5:
                preview += f'\n... ({len(lines) - 5} more lines)'

            self._bridge.show_paste_confirm.emit(preview, len(lines))
        else:
            # Safe to paste directly
            self._send_paste(text.encode('utf-8'))

    def copy_paste(self) -> None:
        """
        Copy selection, then paste clipboard (combined operation).

        Useful for workflows where you select text, then want to
        immediately paste what was just copied.
        """
        self.copy()
        # Small delay isn't needed since copy is sync to clipboard
        self.paste()

    def _send_paste(self, data: bytes) -> None:
        """Actually send paste data to terminal/session."""
        if self._session and self._session.is_connected:
            self._session.write(data)
        elif self._ready:
            # Even if not connected, let terminal display it
            # (will trigger reconnect flow via _on_terminal_data)
            data_b64 = base64.b64encode(data).decode('ascii')
            self._bridge.do_paste.emit(data_b64)

    def set_multiline_threshold(self, lines: int) -> None:
        """
        Set the line count threshold for multiline paste warnings.

        Args:
            lines: Number of lines that triggers confirmation (0 to disable)
        """
        self._multiline_threshold = lines

    # -------------------------------------------------------------------------
    # Bridge callbacks
    # -------------------------------------------------------------------------

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
                # They confirmed - reconnect
                self._awaiting_reconnect_confirm = False
                self.hide_overlay()
                self.reconnect_requested.emit()
                # Actually trigger the reconnection
                if self._session:
                    self._session.connect()
            else:
                # First keypress - show prompt
                self._awaiting_reconnect_confirm = True
                self.show_overlay("Disconnected. Press any key to reconnect...", show_spinner=False)

    @pyqtSlot(int, int)
    def _on_terminal_resize(self, cols: int, rows: int):
        """Terminal resized."""
        logger.debug(f"Terminal resize: {cols}x{rows}")
        if self._session:
            self._session.resize(cols, rows)

    @pyqtSlot(str)
    def _on_selection_copied(self, text: str):
        """Selection was copied - write to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        logger.debug(f"Copied {len(text)} chars to clipboard")

    @pyqtSlot(str)
    def _on_paste_requested(self, data_b64: str):
        """
        JS requested paste (from context menu or keyboard).
        Route through our paste() method which reads Qt clipboard.
        """
        self.paste()

    @pyqtSlot()
    def _on_paste_confirmed(self):
        """User confirmed multiline paste."""
        self._bridge.hide_paste_confirm.emit()
        if self._pending_paste:
            self._send_paste(self._pending_paste)
            self._pending_paste = None

    @pyqtSlot()
    def _on_paste_cancelled(self):
        """User cancelled multiline paste."""
        self._bridge.hide_paste_confirm.emit()
        self._pending_paste = None
        self.focus()

    def _on_session_event(self, event: SessionEvent):
        """Handle session events."""
        if isinstance(event, DataReceived):
            self.write(event.data)

        elif isinstance(event, StateChanged):
            self.session_state_changed.emit(event.new_state, event.message)

            # Reset reconnect confirmation state on any state change
            self._awaiting_reconnect_confirm = False

            if event.new_state == SessionState.CONNECTING:
                self.show_overlay("Connecting...", show_spinner=True)
            elif event.new_state == SessionState.AUTHENTICATING:
                self.show_overlay("Authenticating...", show_spinner=True)
            elif event.new_state == SessionState.CONNECTED:
                self.hide_overlay()
            elif event.new_state == SessionState.DISCONNECTED:
                self.show_overlay("Disconnected. Press any key to reconnect...", show_spinner=False)
                self._awaiting_reconnect_confirm = True
            elif event.new_state == SessionState.FAILED:
                self.show_overlay(f"Connection failed: {event.message}", show_spinner=False)
                # Don't auto-prompt for reconnect on failure, let them decide

        elif isinstance(event, InteractionRequired):
            self.interaction_required.emit(event.prompt, event.interaction_type)
            self.show_overlay(event.prompt, show_spinner=False)

        elif isinstance(event, BannerReceived):
            # Could display banner in overlay or write to terminal
            logger.info(f"Banner: {event.banner[:100]}...")