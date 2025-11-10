from pathlib import Path
from typing import Optional
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

class AddAppIcon:
    """
    A utility class for managing and setting the application icon in a PyQt5 application.
    Uses pathlib for robust, modern path handling with in-memory caching.
    """

    _cache = {}  # Class-level cache: filename (str) -> QIcon

    @classmethod
    def set_app_icon(cls, custom_path: Optional[str | Path] = None, name: str = "Robux.ico") -> bool:
        """
        Set the QApplication window icon.

        Args:
            name (str): Icon filename (e.g., 'Robux.ico'). Case-insensitive.
                        Automatically appends '.ico' if missing.
            custom_path (str | Path, optional): Full path or directory to search for the icon.
                                                If None, searches in the directory of this module.

        Returns:
            bool: True if the icon was found and applied, False otherwise.
        """
        icon = cls._get_icon(custom_path, name)
        if icon is None or icon.isNull():
            return False

        app = QApplication.instance()
        if app is None:
            return False  # QApplication not initialized yet

        app.setWindowIcon(icon)
        return True

    @classmethod
    def _get_icon(cls, custom_path: Optional[str | Path], name: str) -> Optional[QIcon]:
        """
        Retrieve a QIcon from cache or file system using pathlib.

        Returns:
            QIcon or None if not found/invalid.
        """
        # Normalize filename
        name = name.strip().lower()
        if not name.endswith(".ico"):
            name += ".ico"

        # Return from cache if available
        if name in cls._cache:
            return cls._cache[name]

        # Resolve candidate path
        candidate_path = cls._resolve_path(custom_path, name)

        if not candidate_path or not candidate_path.is_file():
            fallback_path = Path.cwd() / name
            if fallback_path.is_file():
                candidate_path = fallback_path
            else:
                print(f"[GetAppIcon] Icon not found: {name}")
                cls._cache[name] = QIcon()  # Cache empty to avoid repeated lookups
                return None

        icon = QIcon(str(candidate_path))  # QIcon expects str
        if icon.isNull():
            print(f"[GetAppIcon] Failed to load icon (invalid format?): {candidate_path}")
            cls._cache[name] = QIcon()
            return None

        cls._cache[name] = icon
        return icon

    @classmethod
    def _resolve_path(cls, custom_path: Optional[str | Path] = None, name: str = "Robux.ico") -> Optional[Path]:
        """
        Resolve the full path to the icon file using pathlib.
        """
        if custom_path:
            custom_path = Path(custom_path)
            if custom_path.is_file():
                return custom_path
            elif custom_path.is_dir():
                return custom_path / name
            else:
                # Assume it's a parent directory or partial path
                return custom_path / name
        else:
            # Default: same directory as this module
            current_file = Path(__file__).resolve()
            return current_file.parent / name

    @classmethod
    def clear_cache(cls):
        """Clear the icon cache (useful during development or resource cleanup)."""
        cls._cache.clear()