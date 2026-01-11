"""
Persistent application settings for nterm.
Stored in ~/.nterm/config.json
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default config location
DEFAULT_CONFIG_DIR = Path.home() / ".nterm"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"


@dataclass
class AppSettings:
    """
    Application settings that persist across sessions.
    """
    # Appearance
    theme_name: str = "catppuccin_mocha"
    font_size: int = 14

    # Terminal behavior
    multiline_paste_threshold: int = 1
    scrollback_lines: int = 10000

    # Connection defaults
    default_term_type: str = "xterm-256color"
    default_keepalive_interval: int = 30
    auto_reconnect: bool = True

    # Window state
    window_width: int = 1200
    window_height: int = 800
    window_x: Optional[int] = None
    window_y: Optional[int] = None
    window_maximized: bool = False

    # Session tree state
    tree_width: int = 250

    # Recent connections (just names/refs, not credentials)
    recent_profiles: list[str] = field(default_factory=list)
    max_recent: int = 10

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AppSettings:
        """Deserialize from dict, ignoring unknown keys."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def add_recent_profile(self, profile_name: str) -> None:
        """Add a profile to recent list (moves to front if exists)."""
        if profile_name in self.recent_profiles:
            self.recent_profiles.remove(profile_name)
        self.recent_profiles.insert(0, profile_name)
        self.recent_profiles = self.recent_profiles[:self.max_recent]


class SettingsManager:
    """
    Manages loading and saving application settings.

    Usage:
        manager = SettingsManager()
        settings = manager.settings

        # Modify settings
        settings.theme_name = "dracula"
        settings.font_size = 16

        # Save
        manager.save()
    """

    def __init__(self, config_path: Path = None):
        self._config_path = config_path or DEFAULT_CONFIG_FILE
        self._settings: Optional[AppSettings] = None

    @property
    def settings(self) -> AppSettings:
        """Get current settings, loading from disk if needed."""
        if self._settings is None:
            self._settings = self.load()
        return self._settings

    @property
    def config_dir(self) -> Path:
        """Get the config directory path."""
        return self._config_path.parent

    def load(self) -> AppSettings:
        """Load settings from disk, or return defaults."""
        if self._config_path.exists():
            try:
                data = json.loads(self._config_path.read_text())
                logger.debug(f"Loaded settings from {self._config_path}")
                return AppSettings.from_dict(data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to load settings: {e}, using defaults")
                return AppSettings()
        else:
            logger.debug("No settings file found, using defaults")
            return AppSettings()

    def save(self) -> None:
        """Save current settings to disk."""
        if self._settings is None:
            return

        # Ensure directory exists
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._config_path.write_text(
                json.dumps(self._settings.to_dict(), indent=2)
            )
            logger.debug(f"Saved settings to {self._config_path}")
        except OSError as e:
            logger.error(f"Failed to save settings: {e}")

    def reset(self) -> AppSettings:
        """Reset to default settings (does not save automatically)."""
        self._settings = AppSettings()
        return self._settings


# Global instance for convenience
_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance."""
    global _manager
    if _manager is None:
        _manager = SettingsManager()
    return _manager


def get_settings() -> AppSettings:
    """Convenience function to get current settings."""
    return get_settings_manager().settings


def save_settings() -> None:
    """Convenience function to save current settings."""
    get_settings_manager().save()