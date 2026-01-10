"""
Abstract session interface.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Callable


class SessionState(Enum):
    """Session lifecycle states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    AUTHENTICATING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    FAILED = auto()


@dataclass
class SessionEvent:
    """Base class for session events."""
    pass


@dataclass
class DataReceived(SessionEvent):
    """Data received from remote."""
    data: bytes


@dataclass  
class StateChanged(SessionEvent):
    """Session state changed."""
    old_state: SessionState
    new_state: SessionState
    message: str = ""


@dataclass
class InteractionRequired(SessionEvent):
    """User interaction needed."""
    prompt: str
    interaction_type: str  # "touch", "password", "keyboard_interactive"


@dataclass
class BannerReceived(SessionEvent):
    """SSH banner received."""
    banner: str


class Session(ABC):
    """
    Abstract session interface.
    
    Handles connection lifecycle, data I/O, and reconnection.
    Terminal widget talks to this, doesn't know about SSH/Telnet/Serial.
    """
    
    @property
    @abstractmethod
    def state(self) -> SessionState:
        """Current session state."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Is session currently connected and usable?"""
        pass
    
    @abstractmethod
    def connect(self) -> None:
        """
        Initiate connection.
        Async - fires state change events as it progresses.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully disconnect."""
        pass
    
    @abstractmethod
    def write(self, data: bytes) -> None:
        """Send data to remote."""
        pass
    
    @abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """Notify remote of terminal resize."""
        pass
    
    @abstractmethod
    def set_event_handler(self, handler: Callable[[SessionEvent], None]) -> None:
        """Set callback for session events."""
        pass
