
import sys
import json
import sqlite3
import hashlib
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QGroupBox, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHeaderView, QAbstractItemView, QMenu, QInputDialog,
    QStatusBar, QToolBar, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QAction, QIcon, QColor, QPalette, QShortcut, QKeySequence

import textfsm
import io
from collections import defaultdict


# Try to import requests for NTC GitHub download
REQUESTS_AVAILABLE = False
try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    pass

# Try to import the engine, but don't fail if not available (manual mode still works)
TFSM_ENGINE_AVAILABLE = False
try:
    from nterm.parser.tfsm_fire import TextFSMAutoEngine

    TFSM_ENGINE_AVAILABLE = True
except ImportError:
    try:
        from .tfsm_fire import TextFSMAutoEngine

        TFSM_ENGINE_AVAILABLE = True
    except ImportError:
        pass

GITHUB_API_URL = "https://api.github.com/repos/networktocode/ntc-templates/contents/ntc_templates/templates"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/networktocode/ntc-templates/master/ntc_templates/templates"

VENDOR_PREFIXES = [
    'cisco', 'arista', 'juniper', 'hp', 'dell', 'paloalto', 'fortinet',
    'brocade', 'extreme', 'huawei', 'mikrotik', 'ubiquiti', 'vmware',
    'checkpoint', 'alcatel', 'avaya', 'ruckus', 'f5', 'a10', 'linux',
    'yamaha', 'zyxel', 'enterasys', 'adtran', 'ciena', 'nokia', 'watchguard'
]

def extract_platform(filename: str) -> str:
    """Extract platform name from template filename."""
    name = filename.replace('.textfsm', '')
    parts = name.split('_')
    if len(parts) >= 2 and parts[0] in VENDOR_PREFIXES:
        return f"{parts[0]}_{parts[1]}"
    if parts[0] in VENDOR_PREFIXES:
        return parts[0]
    return parts[0]


def get_package_db_path() -> Path:
    """Database is in same directory as this module."""
    return Path(__file__).parent / "tfsm_templates.db"


class NTCDownloadWorker(QThread):
    """Worker thread for downloading NTC templates"""
    progress = pyqtSignal(int, int, str)  # current, total, status
    finished = pyqtSignal(dict)  # stats dict
    error = pyqtSignal(str)

    def __init__(self, platforms: list, db_path: str, replace: bool = False):
        super().__init__()
        self.platforms = platforms
        self.db_path = db_path or str(get_package_db_path())
        self.replace = replace
        self.templates_to_download = []

    def run(self):
        try:
            # Fetch template list
            response = requests.get(GITHUB_API_URL, timeout=30)
            response.raise_for_status()

            files = response.json()
            all_templates = [f for f in files if f['name'].endswith('.textfsm')]

            # Group by platform
            platforms_map = defaultdict(list)
            for t in all_templates:
                platform = extract_platform(t['name'])
                platforms_map[platform].append(t)

            # Filter to selected platforms
            for platform in self.platforms:
                if platform in platforms_map:
                    self.templates_to_download.extend(platforms_map[platform])

            if not self.templates_to_download:
                self.finished.emit({'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0})
                return

            # Connect to database
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cli_command TEXT UNIQUE,
                    cli_content TEXT,
                    textfsm_content TEXT,
                    textfsm_hash TEXT,
                    source TEXT,
                    created TEXT
                )
            """)
            cursor = conn.cursor()

            stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
            total = len(self.templates_to_download)

            for i, template in enumerate(self.templates_to_download, 1):
                name = template['name']
                cli_command = name.replace('.textfsm', '')

                try:
                    # Download content
                    url = f"{GITHUB_RAW_BASE}/{name}"
                    resp = requests.get(url, timeout=30)
                    resp.raise_for_status()
                    content = resp.text

                    textfsm_hash = hashlib.md5(content.encode()).hexdigest()
                    created = datetime.now().isoformat()

                    # Check if exists
                    cursor.execute("SELECT textfsm_hash FROM templates WHERE cli_command = ?", (cli_command,))
                    existing = cursor.fetchone()

                    if existing:
                        if self.replace and existing[0] != textfsm_hash:
                            cursor.execute("""
                                UPDATE templates 
                                SET textfsm_content = ?, textfsm_hash = ?, source = ?, created = ?
                                WHERE cli_command = ?
                            """, (content, textfsm_hash, "ntc-templates", created, cli_command))
                            stats['updated'] += 1
                            status = "U"
                        else:
                            stats['skipped'] += 1
                            status = "."
                    else:
                        cursor.execute("""
                            INSERT INTO templates (cli_command, cli_content, textfsm_content, textfsm_hash, source, created)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (cli_command, "", content, textfsm_hash, "ntc-templates", created))
                        stats['imported'] += 1
                        status = "+"

                    self.progress.emit(i, total, f"{status} {cli_command}")

                except Exception as e:
                    stats['errors'] += 1
                    self.progress.emit(i, total, f"E {cli_command}: {str(e)[:30]}")

            conn.commit()
            conn.close()
            self.finished.emit(stats)

        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))



class NTCDownloadDialog(QDialog):
    """Dialog for selecting and downloading NTC templates from GitHub"""

    def __init__(self, parent=None, db_path: str = "tfsm_templates.db"):
        super().__init__(parent)
        self.db_path = db_path
        self.platforms = {}
        self.setWindowTitle("Download NTC Templates from GitHub")
        self.setMinimumSize(600, 500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel("Download TextFSM templates directly from networktocode/ntc-templates GitHub repository.")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Fetch button
        fetch_layout = QHBoxLayout()
        self.fetch_btn = QPushButton("Fetch Available Platforms")
        self.fetch_btn.clicked.connect(self.fetch_platforms)
        fetch_layout.addWidget(self.fetch_btn)
        fetch_layout.addStretch()
        layout.addLayout(fetch_layout)

        # Platform list
        list_group = QGroupBox("Available Platforms")
        list_layout = QVBoxLayout(list_group)

        # Select all / none buttons
        select_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setProperty("secondary", True)
        select_all_btn.clicked.connect(self.select_all)
        select_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.setProperty("secondary", True)
        select_none_btn.clicked.connect(self.select_none)
        select_layout.addWidget(select_none_btn)

        select_layout.addStretch()

        self.status_label = QLabel("")
        select_layout.addWidget(self.status_label)
        list_layout.addLayout(select_layout)

        # Platform table with checkboxes
        self.platform_table = QTableWidget()
        self.platform_table.setColumnCount(3)
        self.platform_table.setHorizontalHeaderLabels(["Select", "Platform", "Templates"])
        self.platform_table.horizontalHeader().setStretchLastSection(True)
        self.platform_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.platform_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        list_layout.addWidget(self.platform_table)

        layout.addWidget(list_group)

        # Options
        options_layout = QHBoxLayout()
        self.replace_check = QCheckBox("Replace existing templates if content changed")
        options_layout.addWidget(self.replace_check)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Progress
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.download_btn = QPushButton("Download Selected")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        btn_layout.addWidget(self.download_btn)

        close_btn = QPushButton("Close")
        close_btn.setProperty("secondary", True)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def fetch_platforms(self):
        """Fetch available platforms from GitHub"""
        if not REQUESTS_AVAILABLE:
            QMessageBox.critical(self, "Error", "requests library not available.\nInstall with: pip install requests")
            return

        self.fetch_btn.setEnabled(False)
        self.status_label.setText("Fetching from GitHub...")
        QApplication.processEvents()

        try:
            response = requests.get(GITHUB_API_URL, timeout=30)
            response.raise_for_status()

            files = response.json()
            templates = [f for f in files if f['name'].endswith('.textfsm')]

            # Group by platform
            self.platforms = defaultdict(list)
            for t in templates:
                platform = extract_platform(t['name'])
                self.platforms[platform].append(t)

            # Populate table
            self.platform_table.setRowCount(len(self.platforms))
            for row, (platform, tmpl_list) in enumerate(sorted(self.platforms.items(), key=lambda x: -len(x[1]))):
                # Checkbox
                checkbox = QCheckBox()
                self.platform_table.setCellWidget(row, 0, checkbox)

                # Platform name
                self.platform_table.setItem(row, 1, QTableWidgetItem(platform))

                # Template count
                self.platform_table.setItem(row, 2, QTableWidgetItem(str(len(tmpl_list))))

            self.status_label.setText(f"Found {len(templates)} templates across {len(self.platforms)} platforms")
            self.download_btn.setEnabled(True)

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to fetch platforms:\n{str(e)}")
            self.status_label.setText("Fetch failed")

        self.fetch_btn.setEnabled(True)

    def select_all(self):
        for row in range(self.platform_table.rowCount()):
            checkbox = self.platform_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(True)

    def select_none(self):
        for row in range(self.platform_table.rowCount()):
            checkbox = self.platform_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(False)

    def get_selected_platforms(self) -> list:
        selected = []
        for row in range(self.platform_table.rowCount()):
            checkbox = self.platform_table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                item = self.platform_table.item(row, 1)
                if item:
                    selected.append(item.text())
        return selected

    def start_download(self):
        selected = self.get_selected_platforms()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select at least one platform")
            return

        self.download_btn.setEnabled(False)
        self.fetch_btn.setEnabled(False)
        self.progress_label.setText("Starting download...")

        self.worker = NTCDownloadWorker(selected, self.db_path, self.replace_check.isChecked())
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.download_finished)
        self.worker.error.connect(self.download_error)
        self.worker.start()

    def update_progress(self, current: int, total: int, status: str):
        self.progress_label.setText(f"[{current}/{total}] {status}")

    def download_finished(self, stats: dict):
        self.download_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)

        msg = f"Download Complete!\n\nImported: {stats['imported']}\nUpdated: {stats['updated']}\nSkipped: {stats['skipped']}\nErrors: {stats['errors']}"
        self.progress_label.setText(
            f"Done: {stats['imported']} imported, {stats['updated']} updated, {stats['skipped']} skipped")
        QMessageBox.information(self, "Download Complete", msg)

    def download_error(self, error: str):
        self.download_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.progress_label.setText("Download failed")
        QMessageBox.critical(self, "Error", f"Download failed:\n{error}")
