"""Resource manager for development and installed package modes."""
from pathlib import Path
from functools import lru_cache


class ResourceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._package_root = Path(__file__).parent
        return cls._instance

    @property
    def dev_mode(self) -> bool:
        """True if running from source checkout."""
        return (self._package_root.parent / "pyproject.toml").exists()

    def get_path(self, *parts: str) -> Path:
        """Get absolute path to a package resource."""
        path = self._package_root.joinpath(*parts)
        if not path.exists():
            raise FileNotFoundError(f"Resource not found: {path}")
        return path

    def get_uri(self, *parts: str) -> str:
        """Get file:// URI for QWebEngineView."""
        return self.get_path(*parts).as_uri()

    def read_text(self, *parts: str) -> str:
        return self.get_path(*parts).read_text(encoding="utf-8")

    def read_bytes(self, *parts: str) -> bytes:
        return self.get_path(*parts).read_bytes()

    # Convenience shortcuts
    @property
    def terminal_resources(self) -> Path:
        return self.get_path("terminal", "resources")

    @property
    def themes_dir(self) -> Path:
        return self.get_path("theme", "themes")


# Singleton instance
resources = ResourceManager()