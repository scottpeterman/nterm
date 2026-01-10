"""
Session manager data models and storage.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime
import sqlite3
import logging
import json

logger = logging.getLogger(__name__)

# Default database location (alongside vault.db)
DEFAULT_DB_PATH = Path.home() / ".nterm" / "sessions.db"


@dataclass
class SavedSession:
    """A saved session bookmark."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    hostname: str = ""
    port: int = 22

    # Reference to credential in vault (by name), or None for agent auth
    credential_name: Optional[str] = None

    # Organization
    folder_id: Optional[int] = None
    position: int = 0

    # Metadata
    created_at: Optional[datetime] = None
    last_connected: Optional[datetime] = None
    connect_count: int = 0

    # Optional overrides (JSON-serialized extras)
    extras: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.extras, str):
            self.extras = json.loads(self.extras) if self.extras else {}


@dataclass
class SessionFolder:
    """A folder for organizing sessions."""
    id: Optional[int] = None
    name: str = ""
    parent_id: Optional[int] = None  # None = root level
    position: int = 0
    expanded: bool = True


class SessionStore:
    """
    SQLite-backed storage for saved sessions.
    """

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create database and tables if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                position INTEGER DEFAULT 0,
                expanded INTEGER DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                hostname TEXT NOT NULL,
                port INTEGER DEFAULT 22,
                credential_name TEXT,
                folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_connected TIMESTAMP,
                connect_count INTEGER DEFAULT 0,
                extras TEXT DEFAULT '{}'
            );
            
            CREATE INDEX IF NOT EXISTS idx_sessions_folder ON sessions(folder_id);
            CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
        """)

        conn.commit()
        self._conn = conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # -------------------------------------------------------------------------
    # Folder operations
    # -------------------------------------------------------------------------

    def add_folder(self, name: str, parent_id: int = None) -> int:
        """Create a new folder. Returns folder ID."""
        cursor = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM folders WHERE parent_id IS ?",
            (parent_id,)
        )
        position = cursor.fetchone()[0]

        cursor = self._conn.execute(
            "INSERT INTO folders (name, parent_id, position) VALUES (?, ?, ?)",
            (name, parent_id, position)
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_folder(self, folder_id: int) -> Optional[SessionFolder]:
        """Get folder by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM folders WHERE id = ?", (folder_id,)
        )
        row = cursor.fetchone()
        return self._row_to_folder(row) if row else None

    def list_folders(self, parent_id: int = None) -> list[SessionFolder]:
        """List folders under a parent (None = root level)."""
        cursor = self._conn.execute(
            "SELECT * FROM folders WHERE parent_id IS ? ORDER BY position, name",
            (parent_id,)
        )
        return [self._row_to_folder(row) for row in cursor]

    def update_folder(self, folder: SessionFolder) -> bool:
        """Update folder properties."""
        self._conn.execute(
            """UPDATE folders 
               SET name = ?, parent_id = ?, position = ?, expanded = ?
               WHERE id = ?""",
            (folder.name, folder.parent_id, folder.position,
             1 if folder.expanded else 0, folder.id)
        )
        self._conn.commit()
        return True

    def delete_folder(self, folder_id: int) -> bool:
        """Delete folder (sessions inside move to root)."""
        # Move sessions to root first
        self._conn.execute(
            "UPDATE sessions SET folder_id = NULL WHERE folder_id = ?",
            (folder_id,)
        )
        # Move subfolders to root
        self._conn.execute(
            "UPDATE folders SET parent_id = NULL WHERE parent_id = ?",
            (folder_id,)
        )
        # Delete folder
        self._conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self._conn.commit()
        return True

    def _row_to_folder(self, row: sqlite3.Row) -> SessionFolder:
        return SessionFolder(
            id=row["id"],
            name=row["name"],
            parent_id=row["parent_id"],
            position=row["position"],
            expanded=bool(row["expanded"]),
        )

    # -------------------------------------------------------------------------
    # Session operations
    # -------------------------------------------------------------------------

    def add_session(self, session: SavedSession) -> int:
        """Add a new session. Returns session ID."""
        cursor = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM sessions WHERE folder_id IS ?",
            (session.folder_id,)
        )
        position = cursor.fetchone()[0]

        cursor = self._conn.execute(
            """INSERT INTO sessions 
               (name, description, hostname, port, credential_name, folder_id, position, extras)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.name, session.description, session.hostname, session.port,
             session.credential_name, session.folder_id, position,
             json.dumps(session.extras))
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_session(self, session_id: int) -> Optional[SavedSession]:
        """Get session by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = cursor.fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, folder_id: int = None) -> list[SavedSession]:
        """List sessions in a folder (None = root level)."""
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE folder_id IS ? ORDER BY position, name",
            (folder_id,)
        )
        return [self._row_to_session(row) for row in cursor]

    def list_all_sessions(self) -> list[SavedSession]:
        """List all sessions regardless of folder."""
        cursor = self._conn.execute(
            "SELECT * FROM sessions ORDER BY name"
        )
        return [self._row_to_session(row) for row in cursor]

    def update_session(self, session: SavedSession) -> bool:
        """Update session properties."""
        self._conn.execute(
            """UPDATE sessions 
               SET name = ?, description = ?, hostname = ?, port = ?,
                   credential_name = ?, folder_id = ?, position = ?, extras = ?
               WHERE id = ?""",
            (session.name, session.description, session.hostname, session.port,
             session.credential_name, session.folder_id, session.position,
             json.dumps(session.extras), session.id)
        )
        self._conn.commit()
        return True

    def delete_session(self, session_id: int) -> bool:
        """Delete a session."""
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        return True

    def record_connect(self, session_id: int) -> None:
        """Record that a session was connected to."""
        self._conn.execute(
            """UPDATE sessions 
               SET last_connected = CURRENT_TIMESTAMP, connect_count = connect_count + 1
               WHERE id = ?""",
            (session_id,)
        )
        self._conn.commit()

    def search_sessions(self, query: str) -> list[SavedSession]:
        """Search sessions by name, description, or hostname."""
        pattern = f"%{query}%"
        cursor = self._conn.execute(
            """SELECT * FROM sessions 
               WHERE name LIKE ? OR description LIKE ? OR hostname LIKE ?
               ORDER BY name""",
            (pattern, pattern, pattern)
        )
        return [self._row_to_session(row) for row in cursor]

    def _row_to_session(self, row: sqlite3.Row) -> SavedSession:
        return SavedSession(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            hostname=row["hostname"],
            port=row["port"],
            credential_name=row["credential_name"],
            folder_id=row["folder_id"],
            position=row["position"],
            created_at=row["created_at"],
            last_connected=row["last_connected"],
            connect_count=row["connect_count"],
            extras=row["extras"],
        )

    # -------------------------------------------------------------------------
    # Bulk / tree operations
    # -------------------------------------------------------------------------

    def get_tree(self) -> dict:
        """
        Get full tree structure for UI.

        Returns dict with:
            - folders: list of SessionFolder (all)
            - sessions: list of SavedSession (all)
        """
        folders = []
        cursor = self._conn.execute("SELECT * FROM folders ORDER BY position, name")
        for row in cursor:
            folders.append(self._row_to_folder(row))

        sessions = self.list_all_sessions()

        return {"folders": folders, "sessions": sessions}

    def move_session(self, session_id: int, folder_id: int = None) -> None:
        """Move session to a different folder."""
        # Get new position at end of target folder
        cursor = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM sessions WHERE folder_id IS ?",
            (folder_id,)
        )
        position = cursor.fetchone()[0]

        self._conn.execute(
            "UPDATE sessions SET folder_id = ?, position = ? WHERE id = ?",
            (folder_id, position, session_id)
        )
        self._conn.commit()

    def move_folder(self, folder_id: int, parent_id: int = None) -> None:
        """Move folder to a different parent."""
        # Prevent circular reference
        if parent_id:
            current = parent_id
            while current:
                if current == folder_id:
                    raise ValueError("Cannot move folder into itself")
                folder = self.get_folder(current)
                current = folder.parent_id if folder else None

        cursor = self._conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM folders WHERE parent_id IS ?",
            (parent_id,)
        )
        position = cursor.fetchone()[0]

        self._conn.execute(
            "UPDATE folders SET parent_id = ?, position = ? WHERE id = ?",
            (parent_id, position, folder_id)
        )
        self._conn.commit()