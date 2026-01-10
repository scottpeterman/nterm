"""
Bridge between Python and xterm.js via QWebChannel.
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class TerminalBridge(QObject):
    """
    Bridge between Python and xterm.js.
    Exposed to JavaScript via QWebChannel.
    """
    
    # Signals to JS (Python -> JavaScript)
    write_data = pyqtSignal(str)           # base64 encoded data
    apply_theme = pyqtSignal(str)          # JSON theme config
    set_font = pyqtSignal(str, int)        # family, size
    do_resize = pyqtSignal(int, int)       # cols, rows
    show_overlay = pyqtSignal(str, bool)   # message, show_spinner
    hide_overlay = pyqtSignal()
    focus_terminal = pyqtSignal()
    clear_terminal = pyqtSignal()

    # Clipboard signals to JS
    do_copy = pyqtSignal()                 # trigger copy selection
    do_paste = pyqtSignal(str)             # base64 data to paste (confirmed)
    show_paste_confirm = pyqtSignal(str, int)  # preview text, line_count
    hide_paste_confirm = pyqtSignal()

    # Signals from JS (JavaScript -> Python)
    data_from_terminal = pyqtSignal(str)   # base64 encoded
    size_changed = pyqtSignal(int, int)    # cols, rows
    terminal_ready = pyqtSignal()
    title_changed = pyqtSignal(str)

    # Clipboard signals from JS
    selection_copied = pyqtSignal(str)     # copied text
    paste_requested = pyqtSignal(str)      # base64 clipboard content for confirmation
    paste_confirmed = pyqtSignal()         # user confirmed multiline paste
    paste_cancelled = pyqtSignal()         # user cancelled multiline paste

    def __init__(self):
        super().__init__()

    @pyqtSlot(str)
    def onData(self, data_b64: str):
        """Called from JS when user types."""
        self.data_from_terminal.emit(data_b64)

    @pyqtSlot(int, int)
    def onResize(self, cols: int, rows: int):
        """Called from JS on terminal resize."""
        self.size_changed.emit(cols, rows)

    @pyqtSlot()
    def onReady(self):
        """Called from JS when xterm.js is initialized."""
        self.terminal_ready.emit()

    @pyqtSlot(str)
    def onTitleChange(self, title: str):
        """Called from JS when terminal title changes."""
        self.title_changed.emit(title)

    @pyqtSlot(str)
    def onSelectionCopied(self, text: str):
        """Called from JS when selection is copied."""
        self.selection_copied.emit(text)

    @pyqtSlot(str)
    def onPasteRequested(self, data_b64: str):
        """Called from JS when paste is requested (for confirmation check)."""
        self.paste_requested.emit(data_b64)

    @pyqtSlot()
    def onPasteConfirmed(self):
        """Called from JS when user confirms multiline paste."""
        self.paste_confirmed.emit()

    @pyqtSlot()
    def onPasteCancelled(self):
        """Called from JS when user cancels multiline paste."""
        self.paste_cancelled.emit()