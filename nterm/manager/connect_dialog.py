"""
SSH Connection Dialog - Authentication configuration before connecting.
"""

from pathlib import Path
from typing import Optional, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QFileDialog, QTabWidget, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt

from nterm.connection.profile import ConnectionProfile, AuthConfig, AuthMethod
from nterm.vault.resolver import CredentialResolver
from nterm.manager import SavedSession


class ConnectDialog(QDialog):
    """
    Connection dialog for SSH authentication.

    Shows target host info and allows selecting/configuring auth method.
    Pre-fills from saved session credentials if available.
    """

    def __init__(
        self,
        session: SavedSession,
        credential_resolver: CredentialResolver = None,
        credential_names: List[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.session = session
        self.credential_resolver = credential_resolver
        self.credential_names = credential_names or []

        self._profile: Optional[ConnectionProfile] = None

        self.setWindowTitle(f"Connect to {session.name}")
        self.setMinimumWidth(450)
        self.setModal(True)

        self._setup_ui()
        self._load_defaults()

    def _setup_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Target info header
        header = QGroupBox("Target")
        header_layout = QFormLayout(header)

        self._host_label = QLabel(f"{self.session.hostname}:{self.session.port}")
        self._host_label.setStyleSheet("font-weight: bold;")
        header_layout.addRow("Host:", self._host_label)

        layout.addWidget(header)

        # Auth method tabs
        self._tabs = QTabWidget()

        # Tab 1: Saved Credential
        if self.credential_names:
            cred_tab = QWidget()
            cred_layout = QVBoxLayout(cred_tab)

            form = QFormLayout()
            self._cred_combo = QComboBox()
            self._cred_combo.addItem("(none)", None)
            for name in self.credential_names:
                self._cred_combo.addItem(name, name)

            # Pre-select if session has a credential
            if self.session.credential_name:
                idx = self._cred_combo.findData(self.session.credential_name)
                if idx >= 0:
                    self._cred_combo.setCurrentIndex(idx)

            form.addRow("Credential:", self._cred_combo)
            cred_layout.addLayout(form)

            # Show credential details
            self._cred_info = QLabel()
            self._cred_info.setWordWrap(True)
            self._cred_info.setStyleSheet("color: #888; font-size: 11px;")
            cred_layout.addWidget(self._cred_info)

            self._cred_combo.currentIndexChanged.connect(self._on_credential_changed)
            self._on_credential_changed()  # Initial update

            cred_layout.addStretch()
            self._tabs.addTab(cred_tab, "Saved Credential")

        # Tab 2: Password Auth
        pw_tab = QWidget()
        pw_layout = QFormLayout(pw_tab)

        self._pw_username = QLineEdit()
        self._pw_username.setPlaceholderText("e.g., admin")
        pw_layout.addRow("Username:", self._pw_username)

        self._pw_password = QLineEdit()
        self._pw_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_password.setPlaceholderText("Password")
        pw_layout.addRow("Password:", self._pw_password)

        self._tabs.addTab(pw_tab, "Password")

        # Tab 3: Key File Auth
        key_tab = QWidget()
        key_layout = QFormLayout(key_tab)

        self._key_username = QLineEdit()
        self._key_username.setPlaceholderText("e.g., admin")
        key_layout.addRow("Username:", self._key_username)

        key_path_layout = QHBoxLayout()
        self._key_path = QLineEdit()
        self._key_path.setPlaceholderText("~/.ssh/id_rsa")
        key_path_layout.addWidget(self._key_path)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_key)
        key_path_layout.addWidget(browse_btn)
        key_layout.addRow("Key File:", key_path_layout)

        self._key_passphrase = QLineEdit()
        self._key_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_passphrase.setPlaceholderText("(optional)")
        key_layout.addRow("Passphrase:", self._key_passphrase)

        self._tabs.addTab(key_tab, "Key File")

        # Tab 4: SSH Agent
        agent_tab = QWidget()
        agent_layout = QVBoxLayout(agent_tab)

        agent_form = QFormLayout()
        self._agent_username = QLineEdit()
        self._agent_username.setPlaceholderText("e.g., admin")
        agent_form.addRow("Username:", self._agent_username)
        agent_layout.addLayout(agent_form)

        agent_info = QLabel(
            "Uses keys loaded in your SSH agent (ssh-agent, gpg-agent, etc.).\n"
            "Make sure your agent is running and has keys loaded."
        )
        agent_info.setStyleSheet("color: #888; font-size: 11px;")
        agent_info.setWordWrap(True)
        agent_layout.addWidget(agent_info)
        agent_layout.addStretch()

        self._tabs.addTab(agent_tab, "SSH Agent")

        layout.addWidget(self._tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setDefault(True)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self._connect_btn)

        layout.addLayout(btn_layout)

    def _load_defaults(self):
        """Load default values from session."""
        import os
        default_user = os.environ.get("USER", "admin")

        # Set defaults for all username fields
        self._pw_username.setText(default_user)
        self._key_username.setText(default_user)
        self._agent_username.setText(default_user)

        # Default key path
        default_key = Path.home() / ".ssh" / "id_rsa"
        if default_key.exists():
            self._key_path.setText(str(default_key))

        # If session has a credential, select the credential tab
        if self.session.credential_name and self.credential_names:
            self._tabs.setCurrentIndex(0)
        else:
            # Default to SSH Agent tab if no saved credential
            self._tabs.setCurrentIndex(self._tabs.count() - 1)

    def _on_credential_changed(self):
        """Update credential info display."""
        if not hasattr(self, '_cred_combo'):
            return

        cred_name = self._cred_combo.currentData()
        if cred_name and self.credential_resolver:
            try:
                # Try to get credential info
                creds = self.credential_resolver.list_credentials()
                for cred in creds:
                    if cred.name == cred_name:
                        info_parts = [f"Username: {cred.username}"]
                        if hasattr(cred, 'auth_type'):
                            info_parts.append(f"Type: {cred.auth_type}")
                        if hasattr(cred, 'has_key') and cred.has_key:
                            info_parts.append("Has SSH key")
                        self._cred_info.setText("\n".join(info_parts))
                        return
            except Exception as e:
                self._cred_info.setText(f"Error loading credential: {e}")
                return

        self._cred_info.setText("")

    def _browse_key(self):
        """Browse for SSH key file."""
        ssh_dir = Path.home() / ".ssh"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SSH Key",
            str(ssh_dir) if ssh_dir.exists() else str(Path.home()),
            "All Files (*)"
        )
        if path:
            self._key_path.setText(path)

    def _on_connect(self):
        """Build profile and accept dialog."""
        try:
            self._profile = self._build_profile()
            if self._profile:
                self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to build connection profile:\n{e}")

    def _build_profile(self) -> Optional[ConnectionProfile]:
        """Build ConnectionProfile from current settings."""
        tab_index = self._tabs.currentIndex()
        tab_text = self._tabs.tabText(tab_index)

        auth_methods = []

        if "Saved Credential" in tab_text:
            cred_name = self._cred_combo.currentData()
            if cred_name and self.credential_resolver:
                try:
                    profile = self.credential_resolver.create_profile_for_credential(
                        cred_name,
                        self.session.hostname,
                        self.session.port
                    )
                    # DEBUG: Print what we got
                    print(f"DEBUG: Profile from vault for '{cred_name}':")
                    print(f"  hostname: {profile.hostname}")
                    print(f"  port: {profile.port}")
                    for i, auth in enumerate(profile.auth_methods):
                        print(f"  auth[{i}]: method={auth.method}, user={auth.username}")
                        print(f"    password set: {bool(auth.password)}")
                        print(f"    credential_ref: {auth.credential_ref}")
                        print(f"    key_path: {auth.key_path}")
                        print(f"    key_data set: {bool(auth.key_data)}")
                    return profile
                except Exception as e:
                    raise ValueError(f"Failed to load credential '{cred_name}': {e}")
            else:
                raise ValueError("No credential selected")

        elif "Password" in tab_text:
            username = self._pw_username.text().strip()
            password = self._pw_password.text()

            if not username:
                raise ValueError("Username required")
            if not password:
                raise ValueError("Password required")

            auth_methods.append(AuthConfig.password_auth(username, password))

        elif "Key File" in tab_text:
            username = self._key_username.text().strip()
            key_path = self._key_path.text().strip()
            passphrase = self._key_passphrase.text() or None

            if not username:
                raise ValueError("Username required")
            if not key_path:
                raise ValueError("Key file path required")

            key_path_obj = Path(key_path).expanduser()
            if not key_path_obj.exists():
                raise ValueError(f"Key file not found: {key_path}")

            auth_methods.append(AuthConfig.key_file_auth(
                username=username,
                key_path=str(key_path_obj),
                passphrase=passphrase
            ))

        elif "Agent" in tab_text:
            username = self._agent_username.text().strip()
            if not username:
                raise ValueError("Username required")

            auth_methods.append(AuthConfig.agent_auth(username))

        return ConnectionProfile(
            name=self.session.name,
            hostname=self.session.hostname,
            port=self.session.port,
            auth_methods=auth_methods,
        )

    def get_profile(self) -> Optional[ConnectionProfile]:
        """Get the built connection profile (after accept)."""
        return self._profile