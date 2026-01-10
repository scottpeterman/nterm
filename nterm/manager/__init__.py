"""
Session manager - tree-based session browser and storage.
"""

from .models import SavedSession, SessionFolder, SessionStore
from .tree import SessionTreeWidget
from .editor import SessionEditorDialog, QuickConnectDialog
from .settings import SettingsDialog, ThemePreview
from .io import (
    export_sessions, import_sessions, import_terminal_telemetry,
    ExportDialog, ImportDialog, ImportTerminalTelemetryDialog
)

__all__ = [
    "SavedSession",
    "SessionFolder",
    "SessionStore",
    "SessionTreeWidget",
    "SessionEditorDialog",
    "QuickConnectDialog",
    "SettingsDialog",
    "ThemePreview",
    "export_sessions",
    "import_sessions",
    "import_terminal_telemetry",
    "ExportDialog",
    "ImportDialog",
    "ImportTerminalTelemetryDialog",
]