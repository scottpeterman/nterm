# example.py
from PyQt6.QtWidgets import QApplication, QMainWindow
import sys

from nterm.connection.profile import ConnectionProfile, AuthConfig, JumpHostConfig
from nterm.session.ssh import SSHSession
from nterm.terminal.widget import TerminalWidget
from nterm.theme.engine import Theme

app = QApplication(sys.argv)

# Define connection with jump host
profile = ConnectionProfile(
    name="shell01-via-jump",
    hostname="shell01",
    port=22,
    auth_methods=[
        AuthConfig.agent_auth("speterman"),
    ],
    jump_hosts=[
        JumpHostConfig(
            hostname="jmp02.iad1.kentik.com",
            auth=AuthConfig.agent_auth("speterman"),
            requires_touch=True,
            touch_prompt="Touch your YubiKey for jump host...",
        ),
    ],
    auto_reconnect=True,
)

# Create terminal
window = QMainWindow()
terminal = TerminalWidget()
terminal.set_theme(Theme.default())
window.setCentralWidget(terminal)

# Create and attach session
session = SSHSession(profile)
terminal.attach_session(session)

# Connect
session.connect()

window.resize(1000, 700)
window.show()
sys.exit(app.exec())