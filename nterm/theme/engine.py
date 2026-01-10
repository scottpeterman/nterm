"""
Theme system.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging
import yaml
from nterm.resources import resources

logger = logging.getLogger(__name__)


@dataclass
class Theme:
    """Terminal theme definition."""
    name: str
    
    # Terminal colors (xterm.js ITheme)
    terminal_colors: dict = field(default_factory=dict)
    
    # Font
    font_family: str = "JetBrains Mono, Cascadia Code, Consolas, monospace"
    font_size: int = 14
    
    # Widget styling (Qt)
    background_color: str = "#1e1e2e"
    foreground_color: str = "#cdd6f4"
    border_color: str = "#313244"
    accent_color: str = "#89b4fa"
    
    # Overlay styling
    overlay_background: str = "rgba(30, 30, 46, 0.9)"
    overlay_text_color: str = "#cdd6f4"
    
    @classmethod
    def load(cls, path: Path) -> Theme:
        """Load theme from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    def save(self, path: Path) -> None:
        """Save theme to YAML file."""
        data = {
            'name': self.name,
            'terminal_colors': self.terminal_colors,
            'font_family': self.font_family,
            'font_size': self.font_size,
            'background_color': self.background_color,
            'foreground_color': self.foreground_color,
            'border_color': self.border_color,
            'accent_color': self.accent_color,
            'overlay_background': self.overlay_background,
            'overlay_text_color': self.overlay_text_color,
        }
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    @classmethod
    def default(cls) -> Theme:
        """Default dark theme (Catppuccin Mocha inspired)."""
        return cls(
            name="default",
            terminal_colors={
                "background": "#1e1e2e",
                "foreground": "#cdd6f4",
                "cursor": "#f5e0dc",
                "cursorAccent": "#1e1e2e",
                "selectionBackground": "#585b70",
                "selectionForeground": "#cdd6f4",
                "black": "#45475a",
                "red": "#f38ba8",
                "green": "#a6e3a1",
                "yellow": "#f9e2af",
                "blue": "#89b4fa",
                "magenta": "#f5c2e7",
                "cyan": "#94e2d5",
                "white": "#bac2de",
                "brightBlack": "#585b70",
                "brightRed": "#f38ba8",
                "brightGreen": "#a6e3a1",
                "brightYellow": "#f9e2af",
                "brightBlue": "#89b4fa",
                "brightMagenta": "#f5c2e7",
                "brightCyan": "#94e2d5",
                "brightWhite": "#a6adc8",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#1e1e2e",
            foreground_color="#cdd6f4",
            border_color="#313244",
            accent_color="#89b4fa",
        )
    
    @classmethod
    def dracula(cls) -> Theme:
        """Dracula theme."""
        return cls(
            name="dracula",
            terminal_colors={
                "background": "#282a36",
                "foreground": "#f8f8f2",
                "cursor": "#f8f8f2",
                "cursorAccent": "#282a36",
                "selectionBackground": "#44475a",
                "selectionForeground": "#f8f8f2",
                "black": "#21222c",
                "red": "#ff5555",
                "green": "#50fa7b",
                "yellow": "#f1fa8c",
                "blue": "#bd93f9",
                "magenta": "#ff79c6",
                "cyan": "#8be9fd",
                "white": "#f8f8f2",
                "brightBlack": "#6272a4",
                "brightRed": "#ff6e6e",
                "brightGreen": "#69ff94",
                "brightYellow": "#ffffa5",
                "brightBlue": "#d6acff",
                "brightMagenta": "#ff92df",
                "brightCyan": "#a4ffff",
                "brightWhite": "#ffffff",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#282a36",
            foreground_color="#f8f8f2",
            border_color="#44475a",
            accent_color="#bd93f9",
        )
    
    @classmethod
    def nord(cls) -> Theme:
        """Nord theme."""
        return cls(
            name="nord",
            terminal_colors={
                "background": "#2e3440",
                "foreground": "#d8dee9",
                "cursor": "#d8dee9",
                "cursorAccent": "#2e3440",
                "selectionBackground": "#434c5e",
                "selectionForeground": "#d8dee9",
                "black": "#3b4252",
                "red": "#bf616a",
                "green": "#a3be8c",
                "yellow": "#ebcb8b",
                "blue": "#81a1c1",
                "magenta": "#b48ead",
                "cyan": "#88c0d0",
                "white": "#e5e9f0",
                "brightBlack": "#4c566a",
                "brightRed": "#bf616a",
                "brightGreen": "#a3be8c",
                "brightYellow": "#ebcb8b",
                "brightBlue": "#81a1c1",
                "brightMagenta": "#b48ead",
                "brightCyan": "#8fbcbb",
                "brightWhite": "#eceff4",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#2e3440",
            foreground_color="#d8dee9",
            border_color="#3b4252",
            accent_color="#88c0d0",
        )
    
    @classmethod
    def solarized_dark(cls) -> Theme:
        """Solarized Dark theme."""
        return cls(
            name="solarized_dark",
            terminal_colors={
                "background": "#002b36",
                "foreground": "#839496",
                "cursor": "#839496",
                "cursorAccent": "#002b36",
                "selectionBackground": "#073642",
                "selectionForeground": "#93a1a1",
                "black": "#073642",
                "red": "#dc322f",
                "green": "#859900",
                "yellow": "#b58900",
                "blue": "#268bd2",
                "magenta": "#d33682",
                "cyan": "#2aa198",
                "white": "#eee8d5",
                "brightBlack": "#002b36",
                "brightRed": "#cb4b16",
                "brightGreen": "#586e75",
                "brightYellow": "#657b83",
                "brightBlue": "#839496",
                "brightMagenta": "#6c71c4",
                "brightCyan": "#93a1a1",
                "brightWhite": "#fdf6e3",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#002b36",
            foreground_color="#839496",
            border_color="#073642",
            accent_color="#268bd2",
        )

    @classmethod
    def gruvbox_dark(cls) -> Theme:
        """Gruvbox Dark theme."""
        return cls(
            name="gruvbox_dark",
            terminal_colors={
                "background": "#282828",
                "foreground": "#ebdbb2",
                "cursor": "#ebdbb2",
                "cursorAccent": "#282828",
                "selectionBackground": "#504945",
                "selectionForeground": "#ebdbb2",
                "black": "#282828",
                "red": "#cc241d",
                "green": "#98971a",
                "yellow": "#d79921",
                "blue": "#458588",
                "magenta": "#b16286",
                "cyan": "#689d6a",
                "white": "#a89984",
                "brightBlack": "#928374",
                "brightRed": "#fb4934",
                "brightGreen": "#b8bb26",
                "brightYellow": "#fabd2f",
                "brightBlue": "#83a598",
                "brightMagenta": "#d3869b",
                "brightCyan": "#8ec07c",
                "brightWhite": "#ebdbb2",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#282828",
            foreground_color="#ebdbb2",
            border_color="#3c3836",
            accent_color="#d79921",
            overlay_background="rgba(40, 40, 40, 0.9)",
            overlay_text_color="#ebdbb2",
        )

    @classmethod
    def gruvbox_light(cls) -> Theme:
        """Gruvbox Light theme."""
        return cls(
            name="gruvbox_light",
            terminal_colors={
                "background": "#fbf1c7",
                "foreground": "#3c3836",
                "cursor": "#3c3836",
                "cursorAccent": "#fbf1c7",
                "selectionBackground": "#d5c4a1",
                "selectionForeground": "#3c3836",
                "black": "#fbf1c7",
                "red": "#cc241d",
                "green": "#98971a",
                "yellow": "#d79921",
                "blue": "#458588",
                "magenta": "#b16286",
                "cyan": "#689d6a",
                "white": "#7c6f64",
                "brightBlack": "#928374",
                "brightRed": "#9d0006",
                "brightGreen": "#79740e",
                "brightYellow": "#b57614",
                "brightBlue": "#076678",
                "brightMagenta": "#8f3f71",
                "brightCyan": "#427b58",
                "brightWhite": "#3c3836",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            background_color="#fbf1c7",
            foreground_color="#3c3836",
            border_color="#d5c4a1",
            accent_color="#b57614",
            overlay_background="rgba(251, 241, 199, 0.95)",
            overlay_text_color="#3c3836",
        )

    @classmethod
    def gruvbox_hybrid(cls) -> Theme:
        """
        Gruvbox Hybrid theme.

        Dark UI chrome (Qt widgets) with light terminal.
        Best of both worlds: comfortable dark UI, high-contrast terminal.
        """
        return cls(
            name="gruvbox_hybrid",
            # Terminal: Gruvbox LIGHT for readability
            terminal_colors={
                "background": "#fbf1c7",
                "foreground": "#3c3836",
                "cursor": "#3c3836",
                "cursorAccent": "#fbf1c7",
                "selectionBackground": "#d5c4a1",
                "selectionForeground": "#3c3836",
                "black": "#fbf1c7",
                "red": "#cc241d",
                "green": "#98971a",
                "yellow": "#d79921",
                "blue": "#458588",
                "magenta": "#b16286",
                "cyan": "#689d6a",
                "white": "#7c6f64",
                "brightBlack": "#928374",
                "brightRed": "#9d0006",
                "brightGreen": "#79740e",
                "brightYellow": "#b57614",
                "brightBlue": "#076678",
                "brightMagenta": "#8f3f71",
                "brightCyan": "#427b58",
                "brightWhite": "#3c3836",
            },
            font_family="JetBrains Mono, Cascadia Code, Consolas, Menlo, monospace",
            font_size=14,
            # UI chrome: Gruvbox DARK for comfort
            background_color="#282828",
            foreground_color="#ebdbb2",
            border_color="#3c3836",
            accent_color="#d79921",
            overlay_background="rgba(40, 40, 40, 0.9)",
            overlay_text_color="#ebdbb2",
        )


class ThemeEngine:
    """Manages theme loading and switching."""

    def __init__(self, theme_dir: Path = None):
        """
        Initialize theme engine.

        Args:
            theme_dir: Directory to load custom themes from
        """
        self.theme_dir = theme_dir or resources.get_path("theme", "themes")

        self._themes: dict[str, Theme] = {}
        self._current: Optional[Theme] = None

        # Register built-in themes
        self._themes["default"] = Theme.default()
        self._themes["dracula"] = Theme.dracula()
        self._themes["nord"] = Theme.nord()
        self._themes["solarized_dark"] = Theme.solarized_dark()
        self._themes["gruvbox_dark"] = Theme.gruvbox_dark()
        self._themes["gruvbox_light"] = Theme.gruvbox_light()
        self._themes["gruvbox_hybrid"] = Theme.gruvbox_hybrid()

    def load_themes(self) -> None:
        """Load all themes from theme directory."""
        if not self.theme_dir.exists():
            logger.debug(f"Theme directory not found: {self.theme_dir}")
            return

        for path in self.theme_dir.glob("*.yaml"):
            try:
                theme = Theme.load(path)
                self._themes[theme.name] = theme
                logger.debug(f"Loaded theme: {theme.name}")
            except Exception as e:
                logger.warning(f"Failed to load theme {path}: {e}")

    def get_theme(self, name: str) -> Optional[Theme]:
        """
        Get theme by name.

        Args:
            name: Theme name

        Returns:
            Theme if found, None otherwise
        """
        return self._themes.get(name)

    def list_themes(self) -> list[str]:
        """
        List available theme names.

        Returns:
            List of theme names
        """
        return sorted(self._themes.keys())

    def register_theme(self, theme: Theme) -> None:
        """
        Register a theme.

        Args:
            theme: Theme to register
        """
        self._themes[theme.name] = theme

    @property
    def current(self) -> Theme:
        """Current active theme."""
        return self._current or self._themes["default"]

    @current.setter
    def current(self, theme: Theme) -> None:
        """Set current active theme."""
        self._current = theme