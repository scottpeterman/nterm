#!/usr/bin/env python3
"""
TextFSM Template Tester - Enhanced Edition (Refactored for nterm)
Debug tool for testing template matching, manual parsing, and template management

Features:
- Database-driven template testing with auto-scoring
- Manual TextFSM template testing (no database required)
- Full CRUD interface for tfsm_templates.db
- Integrated with nterm's theme engine

Author: Scott Peterman
License: MIT
"""

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

# Import nterm theme engine
try:
    from nterm.theme.engine import Theme, ThemeEngine

    NTERM_THEME_AVAILABLE = True
except ImportError:
    NTERM_THEME_AVAILABLE = False


def get_package_db_path() -> Path:
    """Database is in same directory as this module."""
    return Path(__file__).parent / "tfsm_templates.db"


def get_cwd_db_path() -> Path:
    """Database in current working directory."""
    return Path.cwd() / "tfsm_templates.db"


def find_database(db_path: Optional[str] = None) -> Optional[Path]:
    """Find database - explicit path first, then current working directory, then package location."""

    def is_valid_db(path: Path) -> bool:
        return path.exists() and path.is_file() and path.stat().st_size > 0

    if db_path:
        p = Path(db_path)
        return p if is_valid_db(p) else None

    # Check current working directory first
    cwd_db = get_cwd_db_path()
    if is_valid_db(cwd_db):
        return cwd_db

    # Fall back to package location
    package_db = get_package_db_path()
    return package_db if is_valid_db(package_db) else None


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
    from tfsm_fire import TextFSMAutoEngine

    TFSM_ENGINE_AVAILABLE = True
except ImportError:
    try:
        from .tfsm_fire import TextFSMAutoEngine

        TFSM_ENGINE_AVAILABLE = True
    except ImportError:
        pass

# =============================================================================
# NTC TEMPLATES GITHUB DOWNLOAD
# =============================================================================

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


class NTCDownloadWorker(QThread):
    """Worker thread for downloading NTC templates"""
    progress = pyqtSignal(int, int, str)  # current, total, status
    finished = pyqtSignal(dict)  # stats dict
    error = pyqtSignal(str)

    def __init__(self, platforms: list, db_path: str, replace: bool = False):
        super().__init__()
        self.platforms = platforms
        self.db_path = db_path or str(get_cwd_db_path())
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


# =============================================================================
# STYLESHEET GENERATOR FOR NTERM THEME
# =============================================================================

def generate_tfsm_stylesheet(theme: 'Theme') -> str:
    """
    Generate Qt stylesheet from nterm Theme object.
    Maps nterm's theme properties to the tfsm_fire_tester UI.
    """
    # Color mappings from nterm theme
    window_bg = theme.background_color
    surface_bg = theme.background_color
    surface_alt = theme.border_color
    primary = theme.accent_color
    # Derive hover color by lightening/darkening the primary
    primary_hover = theme.accent_color  # Could be enhanced
    primary_text = theme.foreground_color
    text = theme.foreground_color
    text_secondary = theme.foreground_color  # Could use a dimmer variant
    border = theme.border_color
    input_bg = theme.background_color
    input_border = theme.border_color
    input_focus = theme.accent_color

    # Status colors - use reasonable defaults
    success = "#4CAF50"
    warning = "#FF9800"
    error = "#F44336"

    table_header = theme.border_color
    table_alt_row = theme.background_color
    selection = theme.accent_color
    scrollbar_bg = theme.background_color
    scrollbar_handle = theme.border_color
    code_bg = theme.background_color

    return f"""
        QMainWindow, QWidget {{
            background-color: {window_bg};
            color: {text};
            font-family: 'Segoe UI', 'SF Pro', 'Helvetica Neue', Arial, sans-serif;
            font-size: 13px;
        }}

        QGroupBox {{
            background-color: {surface_bg};
            border: 1px solid {border};
            border-radius: 8px;
            margin-top: 16px;
            padding: 16px;
            font-weight: 600;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 4px 12px;
            background-color: {surface_bg};
            color: {primary};
            border-radius: 4px;
        }}

        QTabWidget::pane {{
            background-color: {surface_bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 16px;
        }}

        QTabBar::tab {{
            background-color: {surface_alt};
            color: {text_secondary};
            border: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 8px 16px;
            margin-right: 2px;
        }}

        QTabBar::tab:selected {{
            background-color: {surface_bg};
            color: {primary};
            border-bottom: 2px solid {primary};
        }}

        QTabBar::tab:hover:!selected {{
            background-color: {selection};
        }}

        QPushButton {{
            background-color: {primary};
            color: {primary_text};
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
        }}

        QPushButton:hover {{
            background-color: {primary_hover};
        }}

        QPushButton:pressed {{
            background-color: {primary};
        }}

        QPushButton:disabled {{
            background-color: {border};
            color: {text_secondary};
        }}

        QPushButton[secondary="true"] {{
            background-color: {surface_alt};
            color: {text};
            border: 1px solid {border};
        }}

        QPushButton[secondary="true"]:hover {{
            background-color: {selection};
            border-color: {primary};
        }}

        QPushButton[danger="true"] {{
            background-color: {error};
        }}

        QPushButton[danger="true"]:hover {{
            background-color: {error};
        }}

        QLineEdit, QSpinBox {{
            background-color: {input_bg};
            color: {text};
            border: 1px solid {input_border};
            border-radius: 6px;
            padding: 8px 12px;
        }}

        QLineEdit:focus, QSpinBox:focus {{
            border-color: {input_focus};
            border-width: 2px;
        }}

        QTextEdit {{
            background-color: {code_bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 8px;
            font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
            font-size: 12px;
        }}

        QTextEdit:focus {{
            border-color: {input_focus};
        }}

        QComboBox {{
            background-color: {input_bg};
            color: {text};
            border: 1px solid {input_border};
            border-radius: 6px;
            padding: 8px 12px;
            min-width: 120px;
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {text_secondary};
            margin-right: 8px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {surface_bg};
            color: {text};
            border: 1px solid {border};
            selection-background-color: {selection};
        }}

        QTableWidget {{
            background-color: {surface_bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            gridline-color: {border};
        }}

        QTableWidget QTableCornerButton::section {{
            background-color: {table_header};
            border: none;
        }}

        QTableWidget QHeaderView {{
            background-color: {table_header};
        }}

        QTableView {{
            background-color: {surface_bg};
            color: {text};
            gridline-color: {border};
        }}

        QTableView::item {{
            background-color: {surface_bg};
            color: {text};
            padding: 8px;
        }}

        QTableWidget::item {{
            background-color: {surface_bg};
            color: {text};
            padding: 8px;
        }}

        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {selection};
        }}

        QTableWidget::item:alternate {{
            background-color: {table_alt_row};
        }}

        QHeaderView {{
            background-color: {table_header};
        }}

        QHeaderView::section {{
            background-color: {table_header};
            color: {text};
            border: none;
            border-bottom: 1px solid {border};
            border-right: 1px solid {border};
            padding: 10px 8px;
            font-weight: 600;
        }}

        QCheckBox {{
            spacing: 8px;
        }}

        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 2px solid {input_border};
            border-radius: 4px;
            background-color: {input_bg};
        }}

        QCheckBox::indicator:checked {{
            background-color: {primary};
            border-color: {primary};
        }}

        QLabel {{
            color: {text};
        }}

        QLabel[heading="true"] {{
            font-size: 16px;
            font-weight: 600;
            color: {text};
        }}

        QLabel[subheading="true"] {{
            color: {text_secondary};
            font-size: 12px;
        }}

        QSplitter::handle {{
            background-color: {border};
        }}

        QSplitter::handle:horizontal {{
            width: 2px;
        }}

        QSplitter::handle:vertical {{
            height: 2px;
        }}

        QScrollBar:vertical {{
            background-color: {scrollbar_bg};
            width: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:vertical {{
            background-color: {scrollbar_handle};
            min-height: 30px;
            border-radius: 6px;
            margin: 2px;
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background-color: {scrollbar_bg};
            height: 12px;
            border-radius: 6px;
        }}

        QScrollBar::handle:horizontal {{
            background-color: {scrollbar_handle};
            min-width: 30px;
            border-radius: 6px;
            margin: 2px;
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        QStatusBar {{
            background-color: {surface_alt};
            color: {text_secondary};
            border-top: 1px solid {border};
        }}

        QMenu {{
            background-color: {surface_bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 4px;
        }}

        QMenu::item {{
            padding: 8px 24px;
            border-radius: 4px;
        }}

        QMenu::item:selected {{
            background-color: {selection};
        }}

        QToolBar {{
            background-color: {surface_alt};
            border: none;
            border-bottom: 1px solid {border};
            padding: 4px;
            spacing: 4px;
        }}

        QFrame[frameShape="4"] {{
            background-color: {border};
            max-height: 1px;
        }}
    """


# =============================================================================
# WORKER THREADS
# =============================================================================

class TemplateTestWorker(QThread):
    """Worker thread for database template testing"""
    # Signal: best_template, best_parsed, best_score, all_scores, template_content
    results_ready = pyqtSignal(str, list, float, list, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, db_path: str, device_output: str, filter_string: str, verbose: bool = True):
        super().__init__()
        self.db_path = db_path
        self.device_output = device_output
        self.filter_string = filter_string
        self.verbose = verbose

    def run(self):
        if not TFSM_ENGINE_AVAILABLE:
            self.error_occurred.emit("TextFSM Engine not available. Use Manual Test tab instead.")
            return

        try:
            engine = TextFSMAutoEngine(self.db_path, verbose=self.verbose)

            # find_best_template returns: (best_template, best_parsed, best_score, all_scores)
            # all_scores is List[Tuple[str, float, int]] - (template_name, score, record_count)
            result = engine.find_best_template(self.device_output, self.filter_string)

            best_template, best_parsed, best_score, all_scores = result

            # Fetch template content from database
            template_content = None
            if best_template:
                with engine.connection_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT textfsm_content FROM templates WHERE cli_command = ?",
                        (best_template,)
                    )
                    row = cursor.fetchone()
                    if row:
                        template_content = row['textfsm_content'] if isinstance(row, dict) else row[0]

            self.results_ready.emit(
                best_template or "None",
                best_parsed or [],
                best_score,
                all_scores or [],  # List of (template_name, score, record_count) tuples
                template_content or ""
            )
        except Exception as e:
            traceback.print_exc()
            self.error_occurred.emit(str(e))


class ManualTestWorker(QThread):
    """Worker thread for manual template testing"""
    results_ready = pyqtSignal(list, list, str)  # headers, data, error

    def __init__(self, template_content: str, device_output: str):
        super().__init__()
        self.template_content = template_content
        self.device_output = device_output

    def run(self):
        try:
            template = textfsm.TextFSM(io.StringIO(self.template_content))
            parsed = template.ParseText(self.device_output)
            headers = template.header
            self.results_ready.emit(headers, parsed, "")
        except Exception as e:
            traceback.print_exc()
            self.results_ready.emit([], [], str(e))


# =============================================================================
# TEMPLATE EDITOR DIALOG
# =============================================================================

class TemplateEditorDialog(QDialog):
    """Dialog for creating/editing templates"""

    def __init__(self, parent=None, template_data: Optional[Dict] = None):
        super().__init__(parent)
        self.template_data = template_data
        self.setWindowTitle("Edit Template" if template_data else "New Template")
        self.setMinimumSize(800, 600)
        self.init_ui()

        if template_data:
            self.load_template(template_data)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Form fields
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        self.cli_command_input = QLineEdit()
        self.cli_command_input.setPlaceholderText("e.g., cisco_ios_show_ip_arp")
        form_layout.addRow("CLI Command:", self.cli_command_input)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("e.g., ntc-templates, custom")
        form_layout.addRow("Source:", self.source_input)

        layout.addLayout(form_layout)

        # Template content
        content_label = QLabel("TextFSM Template Content:")
        content_label.setProperty("heading", True)
        layout.addWidget(content_label)

        self.textfsm_content = QTextEdit()
        self.textfsm_content.setPlaceholderText("""Value IP_ADDRESS (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value MAC_ADDRESS ([a-fA-F0-9:.-]+)
Value INTERFACE (\\S+)

Start
  ^${IP_ADDRESS}\\s+${MAC_ADDRESS}\\s+${INTERFACE} -> Record

End""")
        self.textfsm_content.setMinimumHeight(300)
        layout.addWidget(self.textfsm_content)

        # CLI content (optional)
        cli_label = QLabel("CLI Content (optional):")
        layout.addWidget(cli_label)

        self.cli_content = QTextEdit()
        self.cli_content.setMaximumHeight(100)
        self.cli_content.setPlaceholderText("Original CLI command documentation or notes...")
        layout.addWidget(self.cli_content)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def load_template(self, data: Dict):
        self.cli_command_input.setText(data.get('cli_command', ''))
        self.source_input.setText(data.get('source', ''))
        self.textfsm_content.setPlainText(data.get('textfsm_content', ''))
        self.cli_content.setPlainText(data.get('cli_content', ''))

    def get_template_data(self) -> Dict:
        content = self.textfsm_content.toPlainText()
        return {
            'cli_command': self.cli_command_input.text().strip(),
            'source': self.source_input.text().strip() or 'custom',
            'textfsm_content': content,
            'textfsm_hash': hashlib.md5(content.encode()).hexdigest(),
            'cli_content': self.cli_content.toPlainText().strip(),
            'created': datetime.now().isoformat()
        }

    def validate(self) -> tuple:
        if not self.cli_command_input.text().strip():
            return False, "CLI Command is required"
        if not self.textfsm_content.toPlainText().strip():
            return False, "TextFSM content is required"

        # Try to parse the template
        try:
            textfsm.TextFSM(io.StringIO(self.textfsm_content.toPlainText()))
        except Exception as e:
            return False, f"Invalid TextFSM template: {str(e)}"

        return True, ""

    def accept(self):
        valid, error = self.validate()
        if not valid:
            QMessageBox.warning(self, "Validation Error", error)
            return
        super().accept()


# =============================================================================
# MAIN APPLICATION (Continuing from previous upload...)
# =============================================================================

class TextFSMTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TextFSM Template Tester")
        self.setGeometry(100, 100, 1400, 900)

        # Settings
        db = find_database()
        self.db_path = str(db) if db else str(get_cwd_db_path())

        # Initialize theme engine
        if NTERM_THEME_AVAILABLE:
            self.theme_engine = ThemeEngine()
            self.current_theme = self.theme_engine.get_theme("default")
        else:
            self.theme_engine = None
            self.current_theme = None

        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self.create_toolbar()

        # Main content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)

        # Main tabs
        self.main_tabs = QTabWidget()

        # Tab 1: Database Testing
        self.main_tabs.addTab(self.create_db_test_tab(), "Database Test")

        # Tab 2: Manual Testing
        self.main_tabs.addTab(self.create_manual_test_tab(), "Manual Test")

        # Tab 3: Template Manager (CRUD)
        self.main_tabs.addTab(self.create_template_manager_tab(), "Template Manager")

        content_layout.addWidget(self.main_tabs)
        layout.addWidget(content_widget)

        # Status bar
        self.statusBar().showMessage("Ready")

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        # Theme selector
        theme_label = QLabel("  Theme: ")
        toolbar.addWidget(theme_label)

        self.theme_combo = QComboBox()
        if NTERM_THEME_AVAILABLE and self.theme_engine:
            # Populate with nterm themes
            theme_names = self.theme_engine.list_themes()
            self.theme_combo.addItems([n.replace("_", " ").title() for n in theme_names])
            self.theme_combo.setCurrentText("Default")
        else:
            # Fallback to basic themes
            self.theme_combo.addItems(["Light", "Dark"])
            self.theme_combo.setCurrentText("Dark")

        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        toolbar.addWidget(self.theme_combo)

        toolbar.addSeparator()

        # Database selector
        db_label = QLabel("  Database: ")
        toolbar.addWidget(db_label)

        self.db_path_input = QLineEdit(self.db_path)
        self.db_path_input.setMinimumWidth(300)
        toolbar.addWidget(self.db_path_input)

        browse_btn = QPushButton("Browse")
        browse_btn.setProperty("secondary", True)
        browse_btn.clicked.connect(self.browse_database)
        toolbar.addWidget(browse_btn)

        toolbar.addSeparator()

        # Quick actions
        new_db_btn = QPushButton("New DB")
        new_db_btn.setProperty("secondary", True)
        new_db_btn.clicked.connect(self.create_new_database)
        toolbar.addWidget(new_db_btn)

    def on_theme_changed(self, theme_text: str):
        """Handle theme selection change"""
        if NTERM_THEME_AVAILABLE and self.theme_engine:
            # Convert display name back to theme key
            theme_key = theme_text.lower().replace(" ", "_")
            theme = self.theme_engine.get_theme(theme_key)
            if theme:
                self.current_theme = theme
                self.apply_theme()
        else:
            # Fallback behavior (if needed)
            pass

    def apply_theme(self):
        """Apply the current theme to the application"""
        if NTERM_THEME_AVAILABLE and self.current_theme:
            stylesheet = generate_tfsm_stylesheet(self.current_theme)
            self.setStyleSheet(stylesheet)
        else:
            # Basic fallback styling if nterm is not available
            pass

    def create_db_test_tab(self) -> QWidget:
        """Create the database testing tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Controls
        controls_group = QGroupBox("Test Controls")
        controls_layout = QVBoxLayout(controls_group)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter String:"))
        self.filter_input = QLineEdit("show_lldp_neighbor")
        self.filter_input.setPlaceholderText("e.g., show_lldp_neighbor, show_cdp_neighbor, show_ip_arp")
        filter_layout.addWidget(self.filter_input)
        controls_layout.addLayout(filter_layout)

        options_layout = QHBoxLayout()
        self.verbose_check = QCheckBox("Verbose Output")
        self.verbose_check.setChecked(True)
        options_layout.addWidget(self.verbose_check)
        options_layout.addStretch()

        self.db_test_btn = QPushButton("Test Against Database")
        self.db_test_btn.clicked.connect(self.test_db_templates)
        options_layout.addWidget(self.db_test_btn)
        controls_layout.addLayout(options_layout)

        layout.addWidget(controls_group)

        # Splitter for input/output
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Input
        input_group = QGroupBox("Device Output")
        input_layout = QVBoxLayout(input_group)

        sample_btn = QPushButton("Load Sample LLDP")
        sample_btn.setProperty("secondary", True)
        sample_btn.clicked.connect(self.load_sample_output)
        input_layout.addWidget(sample_btn)

        self.db_input_text = QTextEdit()
        self.db_input_text.setPlaceholderText("Paste device output here...")
        input_layout.addWidget(self.db_input_text)
        splitter.addWidget(input_group)

        # Results
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)

        self.db_results_tabs = QTabWidget()

        # Best results tab
        best_tab = QWidget()
        best_layout = QVBoxLayout(best_tab)

        self.best_match_label = QLabel("Best Match: None")
        self.best_match_label.setProperty("heading", True)
        best_layout.addWidget(self.best_match_label)

        self.score_label = QLabel("Score: 0.0")
        self.score_label.setProperty("subheading", True)
        best_layout.addWidget(self.score_label)

        self.db_results_table = QTableWidget()
        self.db_results_table.setAlternatingRowColors(True)
        best_layout.addWidget(self.db_results_table)

        # Export buttons for database test results
        db_export_layout = QHBoxLayout()
        export_db_json_btn = QPushButton("Export JSON")
        export_db_json_btn.setProperty("secondary", True)
        export_db_json_btn.clicked.connect(self.export_db_results_json)
        db_export_layout.addWidget(export_db_json_btn)

        export_db_csv_btn = QPushButton("Export CSV")
        export_db_csv_btn.setProperty("secondary", True)
        export_db_csv_btn.clicked.connect(self.export_db_results_csv)
        db_export_layout.addWidget(export_db_csv_btn)

        db_export_layout.addStretch()
        best_layout.addLayout(db_export_layout)

        self.db_results_tabs.addTab(best_tab, "Best Results")

        # All templates scores tab
        all_tab = QWidget()
        all_layout = QVBoxLayout(all_tab)

        self.all_templates_table = QTableWidget()
        self.all_templates_table.setColumnCount(3)
        self.all_templates_table.setHorizontalHeaderLabels(["Template", "Score", "Records"])
        self.all_templates_table.horizontalHeader().setStretchLastSection(True)
        self.all_templates_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.all_templates_table.setAlternatingRowColors(True)
        self.all_templates_table.setSortingEnabled(True)
        all_layout.addWidget(self.all_templates_table)

        self.db_results_tabs.addTab(all_tab, "All Scores")

        # Debug Log tab
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        self.db_log_text = QTextEdit()
        self.db_log_text.setReadOnly(True)
        log_layout.addWidget(self.db_log_text)
        self.db_results_tabs.addTab(log_tab, "Debug Log")

        # Template Content tab (shows the winning template)
        template_tab = QWidget()
        template_tab_layout = QVBoxLayout(template_tab)

        template_info_layout = QHBoxLayout()
        self.template_name_label = QLabel("No template matched yet")
        self.template_name_label.setProperty("heading", True)
        template_info_layout.addWidget(self.template_name_label)
        template_info_layout.addStretch()

        copy_template_btn = QPushButton("Copy to Clipboard")
        copy_template_btn.setProperty("secondary", True)
        copy_template_btn.clicked.connect(self.copy_template_to_clipboard)
        template_info_layout.addWidget(copy_template_btn)

        use_in_manual_btn = QPushButton("Open in Manual Test")
        use_in_manual_btn.setProperty("secondary", True)
        use_in_manual_btn.clicked.connect(self.use_template_in_manual)
        template_info_layout.addWidget(use_in_manual_btn)

        template_tab_layout.addLayout(template_info_layout)

        self.template_content_text = QTextEdit()
        self.template_content_text.setReadOnly(True)
        self.template_content_text.setPlaceholderText("The matched template content will appear here...")
        template_tab_layout.addWidget(self.template_content_text)

        self.db_results_tabs.addTab(template_tab, "Template Content")

        results_layout.addWidget(self.db_results_tabs)
        splitter.addWidget(results_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        return widget

    def create_manual_test_tab(self) -> QWidget:
        """Create the manual testing tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Controls
        controls_group = QGroupBox("Manual Test Controls")
        controls_layout = QHBoxLayout(controls_group)
        controls_layout.addStretch()

        self.manual_test_btn = QPushButton("Test Template")
        self.manual_test_btn.clicked.connect(self.test_manual_template)
        controls_layout.addWidget(self.manual_test_btn)

        layout.addWidget(controls_group)

        # Splitter for template/output/results
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Template input
        template_group = QGroupBox("TextFSM Template")
        template_layout = QVBoxLayout(template_group)

        load_template_btn = QPushButton("Load from File")
        load_template_btn.setProperty("secondary", True)
        load_template_btn.clicked.connect(self.load_template_file)
        template_layout.addWidget(load_template_btn)

        self.manual_template_text = QTextEdit()
        self.manual_template_text.setPlaceholderText("""Value IP_ADDRESS (\\d+\\.\\d+\\.\\d+\\.\\d+)
Value MAC_ADDRESS ([a-fA-F0-9:.-]+)
Value INTERFACE (\\S+)

Start
  ^${IP_ADDRESS}\\s+${MAC_ADDRESS}\\s+${INTERFACE} -> Record

End""")
        template_layout.addWidget(self.manual_template_text)
        splitter.addWidget(template_group)

        # Device output
        output_group = QGroupBox("Device Output")
        output_layout = QVBoxLayout(output_group)

        load_output_btn = QPushButton("Load from File")
        load_output_btn.setProperty("secondary", True)
        load_output_btn.clicked.connect(self.load_output_file)
        output_layout.addWidget(load_output_btn)

        self.manual_output_text = QTextEdit()
        self.manual_output_text.setPlaceholderText("Paste device output here...")
        output_layout.addWidget(self.manual_output_text)
        splitter.addWidget(output_group)

        # Results
        results_group = QGroupBox("Parsed Results")
        results_layout = QVBoxLayout(results_group)

        self.manual_results_table = QTableWidget()
        self.manual_results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.manual_results_table)

        self.manual_error_label = QLabel("")
        self.manual_error_label.setStyleSheet("color: #f38ba8;")
        self.manual_error_label.setWordWrap(True)
        self.manual_error_label.hide()
        results_layout.addWidget(self.manual_error_label)

        # Export buttons for manual test results
        manual_export_layout = QHBoxLayout()
        export_manual_json_btn = QPushButton("Export JSON")
        export_manual_json_btn.setProperty("secondary", True)
        export_manual_json_btn.clicked.connect(self.export_manual_results_json)
        manual_export_layout.addWidget(export_manual_json_btn)

        export_manual_csv_btn = QPushButton("Export CSV")
        export_manual_csv_btn.setProperty("secondary", True)
        export_manual_csv_btn.clicked.connect(self.export_manual_results_csv)
        manual_export_layout.addWidget(export_manual_csv_btn)

        manual_export_layout.addStretch()
        results_layout.addLayout(manual_export_layout)

        splitter.addWidget(results_group)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        layout.addWidget(splitter)

        return widget

    def create_template_manager_tab(self) -> QWidget:
        """Create the template manager tab (CRUD operations)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Toolbar
        toolbar_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("secondary", True)
        refresh_btn.clicked.connect(self.load_all_templates)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()

        new_template_btn = QPushButton("New Template")
        new_template_btn.clicked.connect(self.create_new_template)
        toolbar_layout.addWidget(new_template_btn)

        import_btn = QPushButton("Import from NTC Directory")
        import_btn.setProperty("secondary", True)
        import_btn.clicked.connect(self.import_from_ntc)
        toolbar_layout.addWidget(import_btn)

        if REQUESTS_AVAILABLE:
            download_btn = QPushButton("Download from GitHub")
            download_btn.setProperty("secondary", True)
            download_btn.clicked.connect(self.download_from_ntc)
            toolbar_layout.addWidget(download_btn)

        layout.addLayout(toolbar_layout)

        # Template table
        self.mgr_table = QTableWidget()
        self.mgr_table.setColumnCount(5)
        self.mgr_table.setHorizontalHeaderLabels(["ID", "CLI Command", "Source", "Hash", "Created"])
        self.mgr_table.horizontalHeader().setStretchLastSection(True)
        self.mgr_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mgr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.mgr_table.setAlternatingRowColors(True)
        self.mgr_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.mgr_table.customContextMenuRequested.connect(self.show_template_context_menu)
        self.mgr_table.itemDoubleClicked.connect(lambda: self.edit_selected_template())
        layout.addWidget(self.mgr_table)

        # Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.mgr_search_input = QLineEdit()
        self.mgr_search_input.setPlaceholderText("Filter by CLI command...")
        self.mgr_search_input.textChanged.connect(self.filter_templates)
        search_layout.addWidget(self.mgr_search_input)
        layout.addLayout(search_layout)

        return widget

    # ... (The rest of the implementation would continue with all the methods from the original file)
    # For brevity, I'll include key methods that interface with the database and testing

    def test_db_templates(self):
        """Test device output against database templates"""
        device_output = self.db_input_text.toPlainText().strip()
        filter_string = self.filter_input.text().strip()

        if not device_output:
            QMessageBox.warning(self, "Warning", "Please enter device output to test")
            return

        if not filter_string:
            QMessageBox.warning(self, "Warning", "Please provide a filter string")
            return

        # Check if database exists
        db_path = self.db_path_input.text()
        if not Path(db_path).exists():
            QMessageBox.critical(self, "Error", f"Database not found: {db_path}")
            return

        self.db_path = db_path
        self.db_test_btn.setEnabled(False)
        self.statusBar().showMessage("Testing templates...")
        self.db_log_text.clear()

        self.worker = TemplateTestWorker(db_path, device_output, filter_string, self.verbose_check.isChecked())
        self.worker.results_ready.connect(self.handle_db_results)
        self.worker.error_occurred.connect(self.handle_db_error)
        self.worker.start()

    def handle_db_results(self, best_template: str, best_parsed: list, best_score: float,
                          all_scores: list, template_content: str):
        """Handle results from TemplateTestWorker.

        Args:
            best_template: Name of best matching template
            best_parsed: List of parsed dicts from best template
            best_score: Score of best template
            all_scores: List of (template_name, score, record_count) tuples
            template_content: TextFSM content of best template
        """
        self.db_test_btn.setEnabled(True)
        self.statusBar().showMessage("Testing complete")

        self.best_match_label.setText(f"Best Match: {best_template}")
        self.score_label.setText(f"Score: {best_score:.2f}")

        # Store template content for later use
        self._current_template_content = template_content
        self._current_template_name = best_template

        # Store parsed data for export
        self._db_parsed_data = best_parsed

        # Update results table
        if best_parsed:
            self.db_results_table.setRowCount(len(best_parsed))
            self.db_results_table.setColumnCount(len(best_parsed[0]))
            self.db_results_table.setHorizontalHeaderLabels(list(best_parsed[0].keys()))

            for row, item in enumerate(best_parsed):
                for col, (key, value) in enumerate(item.items()):
                    self.db_results_table.setItem(row, col, QTableWidgetItem(str(value)))

            self.db_results_table.resizeColumnsToContents()
        else:
            self.db_results_table.setRowCount(0)
            self.db_results_table.setColumnCount(0)

        # Update all scores table
        self.all_templates_table.setSortingEnabled(False)
        self.all_templates_table.setRowCount(len(all_scores))

        for row, (tmpl_name, score, record_count) in enumerate(all_scores):
            name_item = QTableWidgetItem(tmpl_name)
            score_item = QTableWidgetItem(f"{score:.2f}")
            records_item = QTableWidgetItem(str(record_count))

            # Highlight best match
            if tmpl_name == best_template:
                for item in [name_item, score_item, records_item]:
                    item.setBackground(QColor("#264F78"))

            self.all_templates_table.setItem(row, 0, name_item)
            self.all_templates_table.setItem(row, 1, score_item)
            self.all_templates_table.setItem(row, 2, records_item)

        self.all_templates_table.setSortingEnabled(True)
        self.all_templates_table.resizeColumnsToContents()

        # Update template content tab
        self.template_name_label.setText(f"Template: {best_template}")
        if template_content:
            self.template_content_text.setPlainText(template_content)
        else:
            self.template_content_text.setPlainText("(Template content not available)")

        # Log
        self.log_db_results(best_template, best_parsed, best_score, all_scores)
        self.db_results_tabs.setCurrentIndex(0)

    def handle_db_error(self, error: str):
        """Handle database test errors"""
        self.db_test_btn.setEnabled(True)
        self.statusBar().showMessage("Error occurred")
        QMessageBox.critical(self, "Error", error)

    def log_db_results(self, best_template: str, best_parsed: list, best_score: float, all_scores: list):
        """Generate detailed log of test results"""
        log = []
        log.append("=" * 60)
        log.append("TEXTFSM TEMPLATE TEST RESULTS")
        log.append("=" * 60)
        log.append(f"Filter String: {self.filter_input.text()}")
        log.append(f"Templates Scored: {len(all_scores)}")
        log.append(f"Best Template: {best_template}")
        log.append(f"Best Score: {best_score:.2f}")
        log.append(f"Records Parsed: {len(best_parsed) if best_parsed else 0}")
        log.append("")

        if best_parsed:
            log.append("PARSED DATA SAMPLE:")
            log.append("-" * 40)
            for i, record in enumerate(best_parsed[:3]):
                log.append(f"Record {i + 1}:")
                log.append(json.dumps(record, indent=2))
                log.append("")

            if len(best_parsed) > 3:
                log.append(f"... and {len(best_parsed) - 3} more records")

        log.append("")
        log.append("TOP 10 SCORING TEMPLATES:")
        log.append("-" * 40)
        for tmpl_name, score, records in all_scores[:10]:
            marker = " <-- BEST" if tmpl_name == best_template else ""
            log.append(f"  {tmpl_name}: score={score:.2f}, records={records}{marker}")

        self.db_log_text.setPlainText("\n".join(log))

    def copy_template_to_clipboard(self):
        """Copy the current template content to clipboard"""
        if hasattr(self, '_current_template_content') and self._current_template_content:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._current_template_content)
            self.statusBar().showMessage("Template copied to clipboard")
        else:
            QMessageBox.warning(self, "Warning", "No template content to copy")

    def use_template_in_manual(self):
        """Load the current template into the Manual Test tab"""
        if hasattr(self, '_current_template_content') and self._current_template_content:
            self.manual_template_text.setPlainText(self._current_template_content)
            device_output = self.db_input_text.toPlainText()
            if device_output:
                self.manual_output_text.setPlainText(device_output)
            self.main_tabs.setCurrentIndex(1)
            self.statusBar().showMessage("Template loaded into Manual Test tab")
        else:
            QMessageBox.warning(self, "Warning", "No template content to load")

    def test_manual_template(self):
        """Test manual template"""
        template_content = self.manual_template_text.toPlainText().strip()
        device_output = self.manual_output_text.toPlainText().strip()

        if not template_content:
            QMessageBox.warning(self, "Warning", "Please provide a TextFSM template")
            return

        if not device_output:
            QMessageBox.warning(self, "Warning", "Please provide device output")
            return

        self.manual_test_btn.setEnabled(False)
        self.manual_error_label.hide()
        self.statusBar().showMessage("Testing template...")

        self.worker = ManualTestWorker(template_content, device_output)
        self.worker.results_ready.connect(self.display_manual_results)
        self.worker.start()

    def display_manual_results(self, headers: list, data: list, error: str):
        """Display manual test results"""
        self.manual_test_btn.setEnabled(True)

        if error:
            self.statusBar().showMessage("Test failed")
            self.manual_error_label.setText(f"Error: {error}")
            self.manual_error_label.show()
            self.manual_results_table.setRowCount(0)
            self.manual_results_table.setColumnCount(0)
            return

        self.statusBar().showMessage("Test complete")
        self.manual_error_label.hide()

        if headers and data:
            self.manual_results_table.setColumnCount(len(headers))
            self.manual_results_table.setHorizontalHeaderLabels(headers)
            self.manual_results_table.setRowCount(len(data))

            for row, record in enumerate(data):
                for col, value in enumerate(record):
                    self.manual_results_table.setItem(row, col, QTableWidgetItem(str(value)))

            self.manual_results_table.resizeColumnsToContents()
        else:
            self.manual_results_table.setRowCount(0)
            self.manual_results_table.setColumnCount(0)

    def load_sample_output(self):
        """Load sample LLDP output"""
        sample = """Last table change time   : 1 day, 14:33:46 ago
Number of table inserts  : 6
Number of table deletes  : 2
Number of table drops    : 0
Number of table age-outs : 0

Port          Neighbor Device ID         Neighbor Port ID    TTL
---------- -------------------------- ---------------------- ---
Et1           eng-rtr-1.lab.local        Gi0/2               120
Et3           eng-leaf-1.lab.local       Gi0/0               120
Et4           eng-leaf-2.lab.local       Gi0/0               120
Et5           eng-leaf-3.lab.local       Gi0/0               120"""
        self.db_input_text.setPlainText(sample)

    def load_template_file(self):
        """Load template from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Template", "", "TextFSM Files (*.textfsm *.template);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.manual_template_text.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load template:\n{str(e)}")

    def load_output_file(self):
        """Load output from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Output", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.manual_output_text.setPlainText(f.read())
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load output:\n{str(e)}")

    def export_db_results_json(self):
        """Export database test results as JSON"""
        if not hasattr(self, '_db_parsed_data') or not self._db_parsed_data:
            QMessageBox.warning(self, "Warning", "No results to export. Run a test first.")
            return

        default_name = "results.json"
        if hasattr(self, '_current_template_name') and self._current_template_name:
            default_name = f"{self._current_template_name}_results.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", default_name, "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self._db_parsed_data, f, indent=2)
                self.statusBar().showMessage(f"Exported {len(self._db_parsed_data)} records to {file_path}")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def export_db_results_csv(self):
        """Export database test results as CSV"""
        if not hasattr(self, '_db_parsed_data') or not self._db_parsed_data:
            QMessageBox.warning(self, "Warning", "No results to export. Run a test first.")
            return

        default_name = "results.csv"
        if hasattr(self, '_current_template_name') and self._current_template_name:
            default_name = f"{self._current_template_name}_results.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name, "CSV Files (*.csv)"
        )
        if file_path:
            try:
                import csv
                headers = list(self._db_parsed_data[0].keys())
                with open(file_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(self._db_parsed_data)
                self.statusBar().showMessage(f"Exported {len(self._db_parsed_data)} records to {file_path}")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Export failed: {str(e)}")

    def export_manual_results_json(self):
        """Export manual test results as JSON"""
        self._export_table_json(self.manual_results_table, "manual_results")

    def export_manual_results_csv(self):
        """Export manual test results as CSV"""
        self._export_table_csv(self.manual_results_table, "manual_results")

    def _export_table_json(self, table: QTableWidget, default_name: str):
        """Export table to JSON file"""
        if table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No data to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", f"{default_name}.json", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            # Extract data
            headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
            data = []
            for row in range(table.rowCount()):
                record = {}
                for col, header in enumerate(headers):
                    item = table.item(row, col)
                    record[header] = item.text() if item else ""
                data.append(record)

            # Write JSON
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)

            self.statusBar().showMessage(f"Exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{str(e)}")

    def _export_table_csv(self, table: QTableWidget, default_name: str):
        """Export table to CSV file"""
        if table.rowCount() == 0:
            QMessageBox.warning(self, "Warning", "No data to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", f"{default_name}.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            import csv
            headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]

            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

                for row in range(table.rowCount()):
                    row_data = []
                    for col in range(table.columnCount()):
                        item = table.item(row, col)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)

            self.statusBar().showMessage(f"Exported to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed:\n{str(e)}")

    def browse_database(self):
        """Browse for database file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Database", "", "SQLite Database (*.db);;All Files (*)"
        )
        if file_path:
            self.db_path_input.setText(file_path)
            self.db_path = file_path

    def create_new_database(self):
        """Create a new database"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Create New Database", "tfsm_templates.db", "SQLite Database (*.db)"
        )
        if not file_path:
            return

        try:
            conn = sqlite3.connect(file_path)
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
            conn.commit()
            conn.close()

            self.db_path_input.setText(file_path)
            self.db_path = file_path
            self.statusBar().showMessage(f"Created database: {file_path}")
            QMessageBox.information(self, "Success", f"Database created:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create database:\n{str(e)}")

    def get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Get database connection"""
        db_path = self.db_path_input.text()
        if not Path(db_path).exists():
            QMessageBox.warning(self, "Warning", f"Database not found: {db_path}")
            return None

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Database connection failed:\n{str(e)}")
            return None

    def load_all_templates(self):
        """Load all templates from database"""
        conn = self.get_db_connection()
        if not conn:
            return

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, cli_command, source, textfsm_hash, created FROM templates ORDER BY cli_command")
            templates = cursor.fetchall()
            conn.close()

            self.mgr_table.setRowCount(len(templates))
            for row, template in enumerate(templates):
                self.mgr_table.setItem(row, 0, QTableWidgetItem(str(template['id'])))
                self.mgr_table.setItem(row, 1, QTableWidgetItem(template['cli_command']))
                self.mgr_table.setItem(row, 2, QTableWidgetItem(template['source'] or ''))
                self.mgr_table.setItem(row, 3, QTableWidgetItem((template['textfsm_hash'] or '')[:12]))
                self.mgr_table.setItem(row, 4, QTableWidgetItem(template['created'] or ''))

            self.mgr_table.resizeColumnsToContents()
            self.statusBar().showMessage(f"Loaded {len(templates)} templates")
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to load templates:\n{str(e)}")

    def filter_templates(self):
        """Filter templates by search text"""
        search_text = self.mgr_search_input.text().lower()

        for row in range(self.mgr_table.rowCount()):
            item = self.mgr_table.item(row, 1)  # CLI command column
            if item:
                match = search_text in item.text().lower()
                self.mgr_table.setRowHidden(row, not match)

    def create_new_template(self):
        """Create a new template"""
        dialog = TemplateEditorDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_template_data()

            conn = self.get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO templates (cli_command, cli_content, textfsm_content, textfsm_hash, source, created)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        data['cli_command'],
                        data['cli_content'],
                        data['textfsm_content'],
                        data['textfsm_hash'],
                        data['source'],
                        data['created']
                    ))
                    conn.commit()
                    conn.close()

                    self.statusBar().showMessage(f"Created template: {data['cli_command']}")
                    self.load_all_templates()
                except sqlite3.IntegrityError:
                    QMessageBox.warning(self, "Warning", "A template with this CLI command already exists")
                except Exception as e:
                    traceback.print_exc()
                    QMessageBox.critical(self, "Error", f"Failed to create template:\n{str(e)}")

    def show_template_context_menu(self, position):
        """Show context menu for template"""
        menu = QMenu()

        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(self.edit_selected_template)
        menu.addAction(edit_action)

        duplicate_action = QAction("Duplicate", self)
        duplicate_action.triggered.connect(self.duplicate_selected_template)
        menu.addAction(duplicate_action)

        test_action = QAction("Test in Manual Tab", self)
        test_action.triggered.connect(self.test_selected_in_manual)
        menu.addAction(test_action)

        menu.addSeparator()

        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_selected_template)
        menu.addAction(delete_action)

        menu.exec(self.mgr_table.viewport().mapToGlobal(position))

    def edit_selected_template(self):
        """Edit the selected template"""
        selected = self.mgr_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        template_id = self.mgr_table.item(row, 0).text()

        conn = self.get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
                template = dict(cursor.fetchone())
                conn.close()

                dialog = TemplateEditorDialog(self, template)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    data = dialog.get_template_data()

                    conn = self.get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE templates 
                            SET cli_command = ?, cli_content = ?, textfsm_content = ?, 
                                textfsm_hash = ?, source = ?, created = ?
                            WHERE id = ?
                        """, (
                            data['cli_command'],
                            data['cli_content'],
                            data['textfsm_content'],
                            data['textfsm_hash'],
                            data['source'],
                            data['created'],
                            template_id
                        ))
                        conn.commit()
                        conn.close()

                        self.statusBar().showMessage(f"Updated template: {data['cli_command']}")
                        self.load_all_templates()
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to edit template:\n{str(e)}")

    def delete_selected_template(self):
        """Delete the selected template"""
        selected = self.mgr_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        template_id = self.mgr_table.item(row, 0).text()
        cli_command = self.mgr_table.item(row, 1).text()

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{cli_command}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            conn = self.get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM templates WHERE id = ?", (template_id,))
                    conn.commit()
                    conn.close()

                    self.statusBar().showMessage(f"Deleted template: {cli_command}")
                    self.load_all_templates()
                except Exception as e:
                    traceback.print_exc()
                    QMessageBox.critical(self, "Error", f"Failed to delete:\n{str(e)}")

    def duplicate_selected_template(self):
        """Duplicate the selected template"""
        selected = self.mgr_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        template_id = self.mgr_table.item(row, 0).text()

        conn = self.get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
                template = dict(cursor.fetchone())

                template['cli_command'] = template['cli_command'] + '_copy'
                template['created'] = datetime.now().isoformat()

                cursor.execute("""
                    INSERT INTO templates (cli_command, cli_content, textfsm_content, textfsm_hash, source, created)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    template['cli_command'],
                    template.get('cli_content', ''),
                    template['textfsm_content'],
                    template.get('textfsm_hash', ''),
                    template.get('source', 'duplicate'),
                    template['created']
                ))
                conn.commit()
                conn.close()

                self.statusBar().showMessage(f"Duplicated template: {template['cli_command']}")
                self.load_all_templates()
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to duplicate:\n{str(e)}")

    def test_selected_in_manual(self):
        """Load selected template into manual test tab"""
        selected = self.mgr_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        template_id = self.mgr_table.item(row, 0).text()

        conn = self.get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT textfsm_content FROM templates WHERE id = ?", (template_id,))
                result = cursor.fetchone()
                conn.close()

                if result:
                    self.manual_template_text.setPlainText(result['textfsm_content'])
                    self.main_tabs.setCurrentIndex(1)
                    self.statusBar().showMessage("Template loaded into Manual Test tab")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to load template:\n{str(e)}")

    def import_from_ntc(self):
        """Import templates from ntc-templates directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select ntc-templates Directory"
        )
        if not dir_path:
            return

        templates_dir = Path(dir_path)
        if not templates_dir.exists():
            QMessageBox.critical(self, "Error", "Directory not found")
            return

        template_files = list(templates_dir.glob("**/*.textfsm"))
        if not template_files:
            template_files = list(templates_dir.glob("**/*.template"))

        if not template_files:
            QMessageBox.warning(self, "Warning", "No TextFSM template files found")
            return

        conn = self.get_db_connection()
        if not conn:
            return

        imported = 0
        skipped = 0

        try:
            cursor = conn.cursor()

            for file_path in template_files:
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()

                    cli_command = file_path.stem

                    cursor.execute("SELECT id FROM templates WHERE cli_command = ?", (cli_command,))
                    if cursor.fetchone():
                        skipped += 1
                        continue

                    cursor.execute("""
                        INSERT INTO templates (cli_command, textfsm_content, textfsm_hash, source, created)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        cli_command,
                        content,
                        hashlib.md5(content.encode()).hexdigest(),
                        'ntc-templates',
                        datetime.now().isoformat()
                    ))
                    imported += 1

                except Exception as e:
                    traceback.print_exc()
                    print(f"Error importing {file_path}: {e}")
                    continue

            conn.commit()
            conn.close()

            self.statusBar().showMessage(f"Imported {imported} templates, skipped {skipped} duplicates")
            QMessageBox.information(
                self, "Import Complete",
                f"Imported: {imported}\nSkipped (duplicates): {skipped}"
            )
            self.load_all_templates()

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Import failed:\n{str(e)}")

    def download_from_ntc(self):
        """Download templates from ntc-templates GitHub repository"""
        if not REQUESTS_AVAILABLE:
            QMessageBox.critical(
                self, "Error",
                "requests library not available.\nInstall with: pip install requests"
            )
            return

        dialog = NTCDownloadDialog(self, self.db_path_input.text())
        dialog.exec()
        self.load_all_templates()


# =============================================================================
# MAIN
# =============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = TextFSMTester()
    window.show()

    # Load templates on startup if database exists
    if Path(window.db_path).exists():
        window.load_all_templates()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()