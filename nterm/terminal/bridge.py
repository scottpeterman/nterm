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
    write_data = pyqtSignal(str)       # base64 encoded data
    apply_theme = pyqtSignal(str)      # JSON theme config
    set_font = pyqtSignal(str, int)    # family, size
    do_resize = pyqtSignal(int, int)   # cols, rows
    show_overlay = pyqtSignal(str)     # message
    hide_overlay = pyqtSignal()
    focus_terminal = pyqtSignal()
    clear_terminal = pyqtSignal()
    
    # Signals from JS (JavaScript -> Python)
    data_from_terminal = pyqtSignal(str)  # base64 encoded
    size_changed = pyqtSignal(int, int)   # cols, rows
    terminal_ready = pyqtSignal()
    title_changed = pyqtSignal(str)
    
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
