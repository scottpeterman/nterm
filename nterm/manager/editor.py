"""
Session editor dialog.
"""

from __future__ import annotations
from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QPushButton, QDialogButtonBox, QGroupBox, QLabel,
    QWidget
)
from PyQt6.QtCore import Qt

from .models import SavedSession


class SessionEditorDialog(QDialog):
    """
    Dialog for creating or editing a saved session.
    """
    
    def __init__(
        self, 
        session: SavedSession = None,
        credential_names: List[str] = None,
        parent: QWidget = None
    ):
        super().__init__(parent)
        self._session = session or SavedSession()
        self._credential_names = credential_names or []
        
        self._setup_ui()
        self._load_session()
    
    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        self.setWindowTitle("Session" if self._session.id else "New Session")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Basic info group
        basic_group = QGroupBox("Connection")
        basic_layout = QFormLayout(basic_group)
        
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("My Server")
        basic_layout.addRow("Name:", self._name_input)
        
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("Optional description")
        basic_layout.addRow("Description:", self._desc_input)
        
        # Host row
        host_row = QHBoxLayout()
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("hostname or IP")
        host_row.addWidget(self._host_input, 1)
        
        host_row.addWidget(QLabel(":"))
        
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        self._port_input.setFixedWidth(80)
        host_row.addWidget(self._port_input)
        
        basic_layout.addRow("Host:", host_row)
        
        layout.addWidget(basic_group)
        
        # Auth group
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout(auth_group)
        
        self._cred_combo = QComboBox()
        self._cred_combo.addItem("(SSH Agent)", None)
        self._cred_combo.addItem("(Ask on connect)", "__ask__")
        for name in self._credential_names:
            self._cred_combo.addItem(name, name)
        auth_layout.addRow("Credential:", self._cred_combo)
        
        layout.addWidget(auth_group)
        
        # Button box
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Focus
        self._name_input.setFocus()
    
    def _load_session(self) -> None:
        """Load session data into form."""
        self._name_input.setText(self._session.name)
        self._desc_input.setText(self._session.description)
        self._host_input.setText(self._session.hostname)
        self._port_input.setValue(self._session.port)
        
        # Select credential
        if self._session.credential_name:
            idx = self._cred_combo.findData(self._session.credential_name)
            if idx >= 0:
                self._cred_combo.setCurrentIndex(idx)
    
    def _on_accept(self) -> None:
        """Validate and accept."""
        name = self._name_input.text().strip()
        hostname = self._host_input.text().strip()
        
        if not name:
            self._name_input.setFocus()
            return
        
        if not hostname:
            self._host_input.setFocus()
            return
        
        self.accept()
    
    def get_session(self) -> SavedSession:
        """Get the edited session data."""
        cred_data = self._cred_combo.currentData()
        cred_name = cred_data if cred_data and cred_data != "__ask__" else None
        
        return SavedSession(
            id=self._session.id,
            name=self._name_input.text().strip(),
            description=self._desc_input.text().strip(),
            hostname=self._host_input.text().strip(),
            port=self._port_input.value(),
            credential_name=cred_name,
            folder_id=self._session.folder_id,
            position=self._session.position,
            extras=self._session.extras,
        )
    
    def set_credential_names(self, names: List[str]) -> None:
        """Update available credential names."""
        current = self._cred_combo.currentData()
        
        self._cred_combo.clear()
        self._cred_combo.addItem("(SSH Agent)", None)
        self._cred_combo.addItem("(Ask on connect)", "__ask__")
        
        for name in names:
            self._cred_combo.addItem(name, name)
        
        # Restore selection
        if current:
            idx = self._cred_combo.findData(current)
            if idx >= 0:
                self._cred_combo.setCurrentIndex(idx)


class QuickConnectDialog(QDialog):
    """
    Quick connect dialog - doesn't save the session.
    """
    
    def __init__(
        self,
        credential_names: List[str] = None,
        parent: QWidget = None
    ):
        super().__init__(parent)
        self._credential_names = credential_names or []
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        self.setWindowTitle("Quick Connect")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        # Host row
        host_row = QHBoxLayout()
        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("hostname or IP")
        host_row.addWidget(self._host_input, 1)
        
        host_row.addWidget(QLabel(":"))
        
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        self._port_input.setFixedWidth(80)
        host_row.addWidget(self._port_input)
        
        form.addRow("Host:", host_row)
        
        # Credential
        self._cred_combo = QComboBox()
        self._cred_combo.addItem("(SSH Agent)", None)
        self._cred_combo.addItem("(Ask on connect)", "__ask__")
        for name in self._credential_names:
            self._cred_combo.addItem(name, name)
        form.addRow("Credential:", self._cred_combo)
        
        layout.addLayout(form)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self._connect_tab_btn = QPushButton("Connect")
        self._connect_tab_btn.setDefault(True)
        self._connect_tab_btn.clicked.connect(lambda: self._accept_with_mode("tab"))
        btn_layout.addWidget(self._connect_tab_btn)
        
        self._connect_win_btn = QPushButton("New Window")
        self._connect_win_btn.clicked.connect(lambda: self._accept_with_mode("window"))
        btn_layout.addWidget(self._connect_win_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        
        # Focus
        self._host_input.setFocus()
        
        # Connect mode result
        self._connect_mode = "tab"
    
    def _accept_with_mode(self, mode: str) -> None:
        """Accept with specified connect mode."""
        hostname = self._host_input.text().strip()
        if not hostname:
            self._host_input.setFocus()
            return
        
        self._connect_mode = mode
        self.accept()
    
    def get_session(self) -> SavedSession:
        """Get session data (not saved, just for connecting)."""
        cred_data = self._cred_combo.currentData()
        cred_name = cred_data if cred_data and cred_data != "__ask__" else None
        
        hostname = self._host_input.text().strip()
        
        return SavedSession(
            name=hostname,  # Use hostname as name
            hostname=hostname,
            port=self._port_input.value(),
            credential_name=cred_name,
        )
    
    def get_connect_mode(self) -> str:
        """Get selected connect mode ('tab' or 'window')."""
        return self._connect_mode
