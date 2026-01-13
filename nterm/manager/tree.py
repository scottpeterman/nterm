"""
Session tree widget with filtering.
"""

from __future__ import annotations
from typing import Optional, Union
from enum import Enum, auto

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QMenu, QInputDialog, QMessageBox,
    QAbstractItemView, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QAction

from .models import SessionStore, SavedSession, SessionFolder

# Item data roles
ROLE_ITEM_TYPE = Qt.ItemDataRole.UserRole
ROLE_ITEM_ID = Qt.ItemDataRole.UserRole + 1


class ItemType(Enum):
    FOLDER = auto()
    SESSION = auto()


class DragDropTreeWidget(QTreeWidget):
    """
    QTreeWidget subclass that emits a signal after internal drag-drop operations.
    """

    items_moved = pyqtSignal()  # Emitted after a drop completes

    def __init__(self, parent=None):
        super().__init__(parent)

    def dropEvent(self, event):
        """Handle drop - let Qt do the visual move, then signal for persistence."""
        # Let Qt handle the visual rearrangement
        super().dropEvent(event)
        # Signal that items have moved and need persistence
        self.items_moved.emit()


class SessionTreeWidget(QWidget):
    """
    Tree-based session browser with filtering.

    Signals:
        connect_requested(session, mode): Emitted when user wants to connect
        session_selected(session): Emitted when selection changes
    """

    # Connect modes
    MODE_TAB = "tab"
    MODE_WINDOW = "window"
    MODE_QUICK = "quick"

    # Signals
    connect_requested = pyqtSignal(object, str)  # (SavedSession, mode)
    session_selected = pyqtSignal(object)  # SavedSession or None
    quick_connect_requested = pyqtSignal()  # For quick connect dialog

    def __init__(self, store: SessionStore = None, parent: QWidget = None):
        super().__init__(parent)
        self.store = store or SessionStore()

        self._filter_timer = QTimer()
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar row
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # Filter input
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter sessions...")
        self._filter_input.setClearButtonEnabled(True)
        self._filter_input.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._filter_input, 1)

        # Quick connect button
        self._quick_btn = QPushButton("Quick Connect")
        self._quick_btn.clicked.connect(self.quick_connect_requested.emit)
        toolbar.addWidget(self._quick_btn)

        layout.addLayout(toolbar)

        # Tree widget (using our custom subclass)
        self._tree = DragDropTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._tree.setAnimated(True)

        # Signals
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
        self._tree.items_moved.connect(self._persist_tree_state)  # Handle drag-drop

        layout.addWidget(self._tree)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._connect_tab_btn = QPushButton("Connect")
        self._connect_tab_btn.setToolTip("Connect in new tab")
        self._connect_tab_btn.clicked.connect(lambda: self._connect_selected(self.MODE_TAB))
        self._connect_tab_btn.setEnabled(False)
        btn_row.addWidget(self._connect_tab_btn)

        self._connect_win_btn = QPushButton("New")
        self._connect_win_btn.setToolTip("Connect in separate window")
        self._connect_win_btn.clicked.connect(lambda: self._connect_selected(self.MODE_WINDOW))
        self._connect_win_btn.setEnabled(False)
        btn_row.addWidget(self._connect_win_btn)

        btn_row.addStretch()

        self._add_btn = QPushButton("+")
        self._add_btn.setFixedWidth(32)
        self._add_btn.setToolTip("Add session or folder")
        self._add_btn.clicked.connect(self._show_add_menu)
        btn_row.addWidget(self._add_btn)

        layout.addLayout(btn_row)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload tree from store."""
        self._tree.clear()
        tree_data = self.store.get_tree()

        # Build folder lookup
        folder_items: dict[int, QTreeWidgetItem] = {}

        # First pass: create all folder items
        for folder in tree_data["folders"]:
            item = self._create_folder_item(folder)
            folder_items[folder.id] = item

        # Second pass: parent folders correctly
        for folder in tree_data["folders"]:
            item = folder_items[folder.id]
            if folder.parent_id and folder.parent_id in folder_items:
                folder_items[folder.parent_id].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            # Restore expanded state
            item.setExpanded(folder.expanded)

        # Add sessions
        for session in tree_data["sessions"]:
            item = self._create_session_item(session)
            if session.folder_id and session.folder_id in folder_items:
                folder_items[session.folder_id].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

        self._apply_filter()

    def get_selected_session(self) -> Optional[SavedSession]:
        """Get currently selected session, or None."""
        items = self._tree.selectedItems()
        if not items:
            return None
        item = items[0]
        if item.data(0, ROLE_ITEM_TYPE) == ItemType.SESSION:
            session_id = item.data(0, ROLE_ITEM_ID)
            return self.store.get_session(session_id)
        return None

    def select_session(self, session_id: int) -> None:
        """Select a session by ID."""
        item = self._find_session_item(session_id)
        if item:
            self._tree.setCurrentItem(item)

    # -------------------------------------------------------------------------
    # Item creation
    # -------------------------------------------------------------------------

    def _create_folder_item(self, folder: SessionFolder) -> QTreeWidgetItem:
        """Create tree item for a folder."""
        item = QTreeWidgetItem()
        item.setText(0, f"📁 {folder.name}")
        item.setData(0, ROLE_ITEM_TYPE, ItemType.FOLDER)
        item.setData(0, ROLE_ITEM_ID, folder.id)
        item.setFlags(
            item.flags() |
            Qt.ItemFlag.ItemIsDragEnabled |  # Folders can be dragged too
            Qt.ItemFlag.ItemIsDropEnabled
        )
        return item

    def _create_session_item(self, session: SavedSession) -> QTreeWidgetItem:
        """Create tree item for a session."""
        item = QTreeWidgetItem()

        # Display text
        display = f"🖥 {session.name}"
        if session.description:
            display += f"  ({session.description})"
        item.setText(0, display)
        item.setToolTip(0, f"{session.hostname}:{session.port}")

        item.setData(0, ROLE_ITEM_TYPE, ItemType.SESSION)
        item.setData(0, ROLE_ITEM_ID, session.id)
        item.setFlags(
            item.flags() |
            Qt.ItemFlag.ItemIsDragEnabled |
            Qt.ItemFlag.ItemNeverHasChildren
        )
        return item

    def _find_session_item(self, session_id: int) -> Optional[QTreeWidgetItem]:
        """Find tree item for a session ID."""
        iterator = self._tree_iterator()
        for item in iterator:
            if (item.data(0, ROLE_ITEM_TYPE) == ItemType.SESSION and
                item.data(0, ROLE_ITEM_ID) == session_id):
                return item
        return None

    def _tree_iterator(self):
        """Iterate all items in tree."""
        def recurse(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                yield child
                yield from recurse(child)

        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            yield item
            yield from recurse(item)

    # -------------------------------------------------------------------------
    # Drag-drop persistence
    # -------------------------------------------------------------------------

    def _persist_tree_state(self) -> None:
        """
        Persist the current tree state to the store after drag-drop.

        Walks the visual tree and updates folder_id/parent_id and positions
        to match the current visual arrangement.
        """
        def get_folder_id_for_item(item: QTreeWidgetItem) -> Optional[int]:
            """Get the folder ID that contains this item, or None for root."""
            parent = item.parent()
            if parent is None:
                return None
            # Parent should be a folder
            if parent.data(0, ROLE_ITEM_TYPE) == ItemType.FOLDER:
                return parent.data(0, ROLE_ITEM_ID)
            return None

        def process_children(parent_item, parent_folder_id: Optional[int]) -> None:
            """Process all children of a parent (either root or folder)."""
            if parent_item is None:
                # Processing root level
                count = self._tree.topLevelItemCount()
                for pos in range(count):
                    item = self._tree.topLevelItem(pos)
                    process_item(item, None, pos)
            else:
                # Processing folder children
                count = parent_item.childCount()
                for pos in range(count):
                    item = parent_item.child(pos)
                    process_item(item, parent_folder_id, pos)

        def process_item(item: QTreeWidgetItem, parent_folder_id: Optional[int], position: int) -> None:
            """Process a single item - update its position and parent."""
            item_type = item.data(0, ROLE_ITEM_TYPE)
            item_id = item.data(0, ROLE_ITEM_ID)

            if item_type == ItemType.SESSION:
                # Update session's folder and position
                session = self.store.get_session(item_id)
                if session and (session.folder_id != parent_folder_id or session.position != position):
                    session.folder_id = parent_folder_id
                    session.position = position
                    self.store.update_session(session)

            elif item_type == ItemType.FOLDER:
                # Update folder's parent and position
                folder = self.store.get_folder(item_id)
                if folder and (folder.parent_id != parent_folder_id or folder.position != position):
                    folder.parent_id = parent_folder_id
                    folder.position = position
                    self.store.update_folder(folder)

                # Recursively process folder's children
                process_children(item, item_id)

        # Start processing from root level
        process_children(None, None)
    
    # -------------------------------------------------------------------------
    # Filtering
    # -------------------------------------------------------------------------
    
    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change (debounced)."""
        self._filter_timer.start(150)  # 150ms debounce
    
    def _apply_filter(self) -> None:
        """Apply current filter to tree."""
        query = self._filter_input.text().strip().lower()
        
        if not query:
            # Show everything
            for item in self._tree_iterator():
                item.setHidden(False)
            return
        
        # Hide non-matching items, but show folders with matching children
        def process_item(item) -> bool:
            """Returns True if item or any child matches."""
            item_type = item.data(0, ROLE_ITEM_TYPE)
            
            if item_type == ItemType.SESSION:
                session_id = item.data(0, ROLE_ITEM_ID)
                session = self.store.get_session(session_id)
                if session:
                    matches = (
                        query in session.name.lower() or
                        query in session.description.lower() or
                        query in session.hostname.lower()
                    )
                    item.setHidden(not matches)
                    return matches
                return False
            
            elif item_type == ItemType.FOLDER:
                # Check all children
                any_child_visible = False
                for i in range(item.childCount()):
                    if process_item(item.child(i)):
                        any_child_visible = True
                
                item.setHidden(not any_child_visible)
                if any_child_visible:
                    item.setExpanded(True)
                return any_child_visible
            
            return False
        
        for i in range(self._tree.topLevelItemCount()):
            process_item(self._tree.topLevelItem(i))
    
    # -------------------------------------------------------------------------
    # Context menu
    # -------------------------------------------------------------------------
    
    def _show_context_menu(self, pos) -> None:
        """Show right-click context menu."""
        item = self._tree.itemAt(pos)
        menu = QMenu(self)
        
        if item:
            item_type = item.data(0, ROLE_ITEM_TYPE)
            
            if item_type == ItemType.SESSION:
                session = self.get_selected_session()
                if session:
                    menu.addAction("Connect in Tab", 
                                   lambda: self._connect_session(session, self.MODE_TAB))
                    menu.addAction("Connect in Window",
                                   lambda: self._connect_session(session, self.MODE_WINDOW))
                    menu.addSeparator()
                    menu.addAction("Edit...", lambda: self._edit_session(session))
                    menu.addAction("Duplicate", lambda: self._duplicate_session(session))
                    menu.addSeparator()
                    menu.addAction("Delete", lambda: self._delete_session(session))
            
            elif item_type == ItemType.FOLDER:
                folder_id = item.data(0, ROLE_ITEM_ID)
                folder = self.store.get_folder(folder_id)
                if folder:
                    menu.addAction("New Session Here...", 
                                   lambda: self._add_session(folder_id))
                    menu.addAction("New Subfolder...",
                                   lambda: self._add_folder(folder_id))
                    menu.addSeparator()
                    menu.addAction("Rename...", lambda: self._rename_folder(folder))
                    menu.addSeparator()
                    menu.addAction("Delete Folder", lambda: self._delete_folder(folder))
        
        else:
            # Clicked on empty space
            menu.addAction("New Session...", lambda: self._add_session(None))
            menu.addAction("New Folder...", lambda: self._add_folder(None))
        
        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(pos))
    
    def _show_add_menu(self) -> None:
        """Show add button menu."""
        menu = QMenu(self)
        menu.addAction("New Session...", lambda: self._add_session(None))
        menu.addAction("New Folder...", lambda: self._add_folder(None))
        menu.exec(self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft()))
    
    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    
    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click - connect to session."""
        if item.data(0, ROLE_ITEM_TYPE) == ItemType.SESSION:
            session = self.get_selected_session()
            if session:
                self._connect_session(session, self.MODE_TAB)
    
    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        session = self.get_selected_session()
        self._connect_tab_btn.setEnabled(session is not None)
        self._connect_win_btn.setEnabled(session is not None)
        self.session_selected.emit(session)
    
    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Save folder expanded state."""
        if item.data(0, ROLE_ITEM_TYPE) == ItemType.FOLDER:
            folder_id = item.data(0, ROLE_ITEM_ID)
            folder = self.store.get_folder(folder_id)
            if folder:
                folder.expanded = True
                self.store.update_folder(folder)
    
    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Save folder collapsed state."""
        if item.data(0, ROLE_ITEM_TYPE) == ItemType.FOLDER:
            folder_id = item.data(0, ROLE_ITEM_ID)
            folder = self.store.get_folder(folder_id)
            if folder:
                folder.expanded = False
                self.store.update_folder(folder)
    
    def _connect_selected(self, mode: str) -> None:
        """Connect to selected session."""
        session = self.get_selected_session()
        if session:
            self._connect_session(session, mode)
    
    def _connect_session(self, session: SavedSession, mode: str) -> None:
        """Emit connect request."""
        self.store.record_connect(session.id)
        self.connect_requested.emit(session, mode)
    
    def _add_session(self, folder_id: int = None) -> None:
        """Add new session (opens editor)."""
        from .editor import SessionEditorDialog
        
        # Get credential names from parent if available
        cred_names = []
        parent = self.parent()
        while parent:
            if hasattr(parent, '_credential_names'):
                cred_names = parent._credential_names
                break
            parent = parent.parent()

        session = SavedSession(folder_id=folder_id)
        dialog = SessionEditorDialog(session, cred_names, parent=self)
        if dialog.exec():
            session = dialog.get_session()
            self.store.add_session(session)
            self.refresh()

    def _edit_session(self, session: SavedSession) -> None:
        """Edit existing session."""
        from .editor import SessionEditorDialog

        # Get credential names from parent if available
        cred_names = []
        parent = self.parent()
        while parent:
            if hasattr(parent, '_credential_names'):
                cred_names = parent._credential_names
                break
            parent = parent.parent()

        dialog = SessionEditorDialog(session, cred_names, parent=self)
        if dialog.exec():
            updated = dialog.get_session()
            updated.id = session.id
            self.store.update_session(updated)
            self.refresh()
            self.select_session(session.id)

    def _duplicate_session(self, session: SavedSession) -> None:
        """Duplicate a session."""
        new_session = SavedSession(
            name=f"{session.name} (copy)",
            description=session.description,
            hostname=session.hostname,
            port=session.port,
            credential_name=session.credential_name,
            folder_id=session.folder_id,
            extras=session.extras.copy(),
        )
        new_id = self.store.add_session(new_session)
        self.refresh()
        self.select_session(new_id)

    def _delete_session(self, session: SavedSession) -> None:
        """Delete a session with confirmation."""
        reply = QMessageBox.question(
            self,
            "Delete Session",
            f"Delete session '{session.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_session(session.id)
            self.refresh()

    def _add_folder(self, parent_id: int = None) -> None:
        """Add new folder."""
        name, ok = QInputDialog.getText(
            self, "New Folder", "Folder name:"
        )
        if ok and name.strip():
            self.store.add_folder(name.strip(), parent_id)
            self.refresh()

    def _rename_folder(self, folder: SessionFolder) -> None:
        """Rename a folder."""
        name, ok = QInputDialog.getText(
            self, "Rename Folder", "Folder name:", text=folder.name
        )
        if ok and name.strip():
            folder.name = name.strip()
            self.store.update_folder(folder)
            self.refresh()

    def _delete_folder(self, folder: SessionFolder) -> None:
        """Delete a folder with confirmation."""
        reply = QMessageBox.question(
            self,
            "Delete Folder",
            f"Delete folder '{folder.name}'?\n\n"
            "Sessions inside will be moved to the root level.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_folder(folder.id)
            self.refresh()