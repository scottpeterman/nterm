"""
Session import/export functionality.

Supports JSON format for portability.
Also supports importing from TerminalTelemetry YAML format.
"""

from __future__ import annotations
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import asdict

from PyQt6.QtWidgets import (
    QWidget, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QDialogButtonBox, QTreeWidget,
    QTreeWidgetItem, QGroupBox
)
from PyQt6.QtCore import Qt

from .models import SessionStore, SavedSession, SessionFolder


# Export format version for future compatibility
EXPORT_VERSION = 1


def export_sessions(
    store: SessionStore,
    path: Path,
    include_stats: bool = False
) -> int:
    """
    Export all sessions to JSON file.

    Args:
        store: Session store instance
        path: Output file path
        include_stats: Include connect_count and last_connected

    Returns:
        Number of sessions exported
    """
    tree_data = store.get_tree()

    # Build export structure
    export_data = {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(),
        "folders": [],
        "sessions": [],
    }

    # Export folders
    for folder in tree_data["folders"]:
        export_data["folders"].append({
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "position": folder.position,
        })

    # Export sessions
    for session in tree_data["sessions"]:
        session_data = {
            "name": session.name,
            "description": session.description,
            "hostname": session.hostname,
            "port": session.port,
            "credential_name": session.credential_name,
            "folder_id": session.folder_id,
            "position": session.position,
        }

        if session.extras:
            session_data["extras"] = session.extras

        if include_stats:
            session_data["connect_count"] = session.connect_count
            if session.last_connected:
                session_data["last_connected"] = str(session.last_connected)

        export_data["sessions"].append(session_data)

    # Write file
    with open(path, "w") as f:
        json.dump(export_data, f, indent=2)

    return len(export_data["sessions"])


def import_sessions(
    store: SessionStore,
    path: Path,
    merge: bool = True
) -> tuple[int, int]:
    """
    Import sessions from JSON file.

    Args:
        store: Session store instance
        path: Input file path
        merge: If True, merge with existing. If False, skip duplicates.

    Returns:
        Tuple of (sessions_imported, sessions_skipped)
    """
    with open(path) as f:
        data = json.load(f)

    version = data.get("version", 1)

    # Build folder ID mapping (old ID -> new ID)
    folder_map: dict[int, int] = {}

    # Import folders first
    if "folders" in data:
        # Sort by parent to ensure parents are created first
        folders = sorted(data["folders"], key=lambda f: (f.get("parent_id") or 0, f.get("position", 0)))

        for folder_data in folders:
            old_id = folder_data.get("id")
            parent_id = folder_data.get("parent_id")

            # Map parent ID if it was imported
            if parent_id and parent_id in folder_map:
                parent_id = folder_map[parent_id]
            elif parent_id:
                parent_id = None  # Parent not found, put at root

            # Check if folder with same name exists at same level
            existing = store.list_folders(parent_id)
            existing_folder = next(
                (f for f in existing if f.name == folder_data["name"]),
                None
            )

            if existing_folder:
                folder_map[old_id] = existing_folder.id
            else:
                new_id = store.add_folder(folder_data["name"], parent_id)
                folder_map[old_id] = new_id

    # Import sessions
    imported = 0
    skipped = 0

    existing_sessions = {s.hostname: s for s in store.list_all_sessions()}

    for session_data in data.get("sessions", []):
        hostname = session_data.get("hostname")
        name = session_data.get("name")

        # Check for duplicate by hostname
        if hostname in existing_sessions and not merge:
            skipped += 1
            continue

        # Map folder ID
        folder_id = session_data.get("folder_id")
        if folder_id and folder_id in folder_map:
            folder_id = folder_map[folder_id]
        else:
            folder_id = None

        session = SavedSession(
            name=name or hostname,
            description=session_data.get("description", ""),
            hostname=hostname,
            port=session_data.get("port", 22),
            credential_name=session_data.get("credential_name"),
            folder_id=folder_id,
            extras=session_data.get("extras", {}),
        )

        # Check if we're updating existing
        if hostname in existing_sessions and merge:
            existing = existing_sessions[hostname]
            session.id = existing.id
            store.update_session(session)
        else:
            store.add_session(session)

        imported += 1

    return imported, skipped


def import_terminal_telemetry(
    store: SessionStore,
    path: Path,
    merge: bool = True
) -> tuple[int, int, int]:
    """
    Import sessions from TerminalTelemetry YAML format.

    Args:
        store: Session store instance
        path: Path to TerminalTelemetry sessions.yaml
        merge: If True, merge with existing. If False, skip duplicates.

    Returns:
        Tuple of (folders_created, sessions_imported, sessions_skipped)
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError("Invalid TerminalTelemetry format: expected list of folders")

    folders_created = 0
    sessions_imported = 0
    sessions_skipped = 0

    existing_sessions = {s.hostname: s for s in store.list_all_sessions()}

    for folder_entry in data:
        folder_name = folder_entry.get("folder_name", "Imported")
        sessions = folder_entry.get("sessions", [])

        if not sessions:
            continue  # Skip empty folders

        # Find or create folder
        existing_folders = store.list_folders(None)  # Root level
        folder = next((f for f in existing_folders if f.name == folder_name), None)

        if not folder:
            folder_id = store.add_folder(folder_name)
            folders_created += 1
        else:
            folder_id = folder.id

        # Import sessions in this folder
        for sess in sessions:
            hostname = sess.get("host", "")
            if not hostname:
                continue

            # Check for duplicate
            if hostname in existing_sessions and not merge:
                sessions_skipped += 1
                continue

            # Build description from DeviceType and Model
            device_type = sess.get("DeviceType", "")
            model = sess.get("Model", "")
            vendor = sess.get("Vendor", "")

            desc_parts = []
            if device_type:
                desc_parts.append(device_type)
            if model:
                desc_parts.append(model)
            description = " - ".join(desc_parts) if desc_parts else ""

            # Store extra metadata
            extras = {}
            if vendor:
                extras["vendor"] = vendor
            if device_type:
                extras["device_type"] = device_type
            if model:
                extras["model"] = model

            session = SavedSession(
                name=sess.get("display_name", hostname),
                description=description,
                hostname=hostname,
                port=int(sess.get("port", 22)),
                credential_name=None,  # Use agent auth by default
                folder_id=folder_id,
                extras=extras,
            )

            # Check if updating existing
            if hostname in existing_sessions and merge:
                existing = existing_sessions[hostname]
                session.id = existing.id
                store.update_session(session)
            else:
                store.add_session(session)
                existing_sessions[hostname] = session  # Track for duplicates

            sessions_imported += 1

    return folders_created, sessions_imported, sessions_skipped


class ExportDialog(QDialog):
    """Dialog for export options."""

    def __init__(self, store: SessionStore, parent: QWidget = None):
        super().__init__(parent)
        self.store = store

        self.setWindowTitle("Export Sessions")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Info
        tree_data = store.get_tree()
        count = len(tree_data["sessions"])
        folder_count = len(tree_data["folders"])

        info = QLabel(f"Export {count} sessions and {folder_count} folders to JSON file.")
        layout.addWidget(info)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._include_stats = QCheckBox("Include connection statistics")
        self._include_stats.setToolTip("Export connect count and last connected timestamp")
        options_layout.addWidget(self._include_stats)

        layout.addWidget(options_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        """Handle save button."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Sessions",
            "nterm_sessions.json",
            "JSON Files (*.json)"
        )

        if path:
            try:
                count = export_sessions(
                    self.store,
                    Path(path),
                    include_stats=self._include_stats.isChecked()
                )
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Exported {count} sessions to:\n{path}"
                )
                self.accept()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export sessions:\n{e}"
                )


class ImportDialog(QDialog):
    """Dialog for import options and preview."""

    def __init__(self, store: SessionStore, parent: QWidget = None):
        super().__init__(parent)
        self.store = store
        self._import_path: Optional[Path] = None
        self._import_data: Optional[dict] = None

        self.setWindowTitle("Import Sessions")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # File selection
        file_row = QHBoxLayout()
        self._file_label = QLabel("No file selected")
        file_row.addWidget(self._file_label, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)

        layout.addLayout(file_row)

        # Preview tree
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_tree = QTreeWidget()
        self._preview_tree.setHeaderLabels(["Name", "Host", "Port"])
        self._preview_tree.setRootIsDecorated(True)
        preview_layout.addWidget(self._preview_tree)

        layout.addWidget(preview_group)

        # Options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        self._merge_check = QCheckBox("Merge with existing (update duplicates)")
        self._merge_check.setChecked(True)
        self._merge_check.setToolTip(
            "If checked, sessions with matching hostnames will be updated.\n"
            "If unchecked, duplicates will be skipped."
        )
        options_layout.addWidget(self._merge_check)

        layout.addWidget(options_group)

        # Buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_import)
        self._button_box.rejected.connect(self.reject)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        layout.addWidget(self._button_box)

    def _browse_file(self) -> None:
        """Browse for import file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Sessions",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if path:
            self._load_preview(Path(path))

    def _load_preview(self, path: Path) -> None:
        """Load and preview import file."""
        try:
            with open(path) as f:
                data = json.load(f)

            self._import_path = path
            self._import_data = data
            self._file_label.setText(path.name)

            # Build preview tree
            self._preview_tree.clear()

            # Create folder items
            folder_items: dict[int, QTreeWidgetItem] = {}
            for folder_data in data.get("folders", []):
                item = QTreeWidgetItem()
                item.setText(0, f"📁 {folder_data['name']}")
                folder_items[folder_data["id"]] = item

            # Parent folders
            for folder_data in data.get("folders", []):
                item = folder_items[folder_data["id"]]
                parent_id = folder_data.get("parent_id")
                if parent_id and parent_id in folder_items:
                    folder_items[parent_id].addChild(item)
                else:
                    self._preview_tree.addTopLevelItem(item)

            # Add sessions
            for session_data in data.get("sessions", []):
                item = QTreeWidgetItem()
                item.setText(0, session_data.get("name", ""))
                item.setText(1, session_data.get("hostname", ""))
                item.setText(2, str(session_data.get("port", 22)))

                folder_id = session_data.get("folder_id")
                if folder_id and folder_id in folder_items:
                    folder_items[folder_id].addChild(item)
                else:
                    self._preview_tree.addTopLevelItem(item)

            self._preview_tree.expandAll()
            self._preview_tree.resizeColumnToContents(0)

            # Enable import button
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load file:\n{e}"
            )

    def _on_import(self) -> None:
        """Perform import."""
        if not self._import_path:
            return

        try:
            imported, skipped = import_sessions(
                self.store,
                self._import_path,
                merge=self._merge_check.isChecked()
            )

            msg = f"Imported {imported} sessions."
            if skipped:
                msg += f"\nSkipped {skipped} duplicates."

            QMessageBox.information(self, "Import Complete", msg)
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to import sessions:\n{e}"
            )


class ImportTerminalTelemetryDialog(QDialog):
    """Dialog for importing TerminalTelemetry sessions.yaml."""

    def __init__(self, store: SessionStore, parent: QWidget = None):
        super().__init__(parent)
        self.store = store
        self._import_path: Optional[Path] = None
        self._import_data: Optional[list] = None

        self.setWindowTitle("Import from TerminalTelemetry")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            "Import sessions from TerminalTelemetry sessions.yaml file.\n"
            "Folders and sessions will be created automatically."
        )
        layout.addWidget(info)

        # File selection
        file_row = QHBoxLayout()
        self._file_label = QLabel("No file selected")
        file_row.addWidget(self._file_label, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)

        layout.addLayout(file_row)

        # Preview tree
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_tree = QTreeWidget()
        self._preview_tree.setHeaderLabels(["Name", "Host", "Description"])
        self._preview_tree.setRootIsDecorated(True)
        preview_layout.addWidget(self._preview_tree)

        layout.addWidget(preview_group)

        # Options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        self._merge_check = QCheckBox("Merge with existing (update duplicates)")
        self._merge_check.setChecked(True)
        options_layout.addWidget(self._merge_check)

        layout.addWidget(options_group)

        # Buttons
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_import)
        self._button_box.rejected.connect(self.reject)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        layout.addWidget(self._button_box)

    def _browse_file(self) -> None:
        """Browse for sessions.yaml file."""
        # Default to common TerminalTelemetry location
        default_path = Path.home() / ".terminaltelemetry" / "sessions.yaml"
        start_dir = str(default_path.parent) if default_path.parent.exists() else ""

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select TerminalTelemetry sessions.yaml",
            start_dir,
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if path:
            self._load_preview(Path(path))

    def _load_preview(self, path: Path) -> None:
        """Load and preview the YAML file."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if not isinstance(data, list):
                raise ValueError("Invalid format: expected list of folders")

            self._import_path = path
            self._import_data = data
            self._file_label.setText(path.name)

            # Build preview tree
            self._preview_tree.clear()

            for folder_entry in data:
                folder_name = folder_entry.get("folder_name", "Unknown")
                sessions = folder_entry.get("sessions", [])

                # Create folder item
                folder_item = QTreeWidgetItem()
                folder_item.setText(0, f"📁 {folder_name}")
                folder_item.setText(1, "")
                folder_item.setText(2, f"{len(sessions)} sessions")
                self._preview_tree.addTopLevelItem(folder_item)

                # Add sessions
                for sess in sessions:
                    item = QTreeWidgetItem()
                    item.setText(0, sess.get("display_name", ""))
                    item.setText(1, sess.get("host", ""))

                    # Build description preview
                    device_type = sess.get("DeviceType", "")
                    model = sess.get("Model", "")
                    desc = f"{device_type} - {model}" if model else device_type
                    item.setText(2, desc)

                    folder_item.addChild(item)

            self._preview_tree.expandAll()
            for i in range(3):
                self._preview_tree.resizeColumnToContents(i)

            # Enable import button
            self._button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load file:\n{e}"
            )

    def _on_import(self) -> None:
        """Perform import."""
        if not self._import_path:
            return

        try:
            folders, imported, skipped = import_terminal_telemetry(
                self.store,
                self._import_path,
                merge=self._merge_check.isChecked()
            )

            msg = f"Created {folders} folders.\nImported {imported} sessions."
            if skipped:
                msg += f"\nSkipped {skipped} duplicates."

            QMessageBox.information(self, "Import Complete", msg)
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to import sessions:\n{e}"
            )