"""Manage recent albums for QLayout app.

Stores a list of recently opened albums to JSON file in platform-standard location.
Provides methods to add, list, and clear recent albums.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import platform

logger = logging.getLogger(__name__)


def get_app_data_dir() -> Path:
    """Get platform-appropriate app data directory.
    
    Returns:
        Path to app data directory
        - macOS: ~/Library/Application Support/QLayout
        - Windows: %APPDATA%/QLayout
        - Linux: ~/.config/QLayout
    """
    if platform.system() == 'Darwin':  # macOS
        app_data = Path.home() / 'Library' / 'Application Support' / 'QLayout'
    elif platform.system() == 'Windows':
        app_data = Path.home() / 'AppData' / 'Roaming' / 'QLayout'
    else:  # Linux and others
        app_data = Path.home() / '.config' / 'QLayout'
    
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data


def get_recent_albums_file() -> Path:
    """Get path to recent albums JSON file.
    
    Returns:
        Path to recent.json file
    """
    return get_app_data_dir() / 'recent.json'


def get_preferences_file() -> Path:
    """Get path to preferences JSON file.
    
    Returns:
        Path to preferences.json file
    """
    return get_app_data_dir() / 'preferences.json'


class RecentAlbumsManager:
    """Manage recent albums list."""
    
    MAX_RECENT = 10  # Keep max 10 recent albums
    
    def __init__(self):
        self.file = get_recent_albums_file()
        self._albums: List[dict] = self._load()
    
    def _load(self) -> List[dict]:
        """Load recent albums from JSON file.
        
        Returns:
            List of album dicts with keys: path, name, timestamp
        """
        if not self.file.exists():
            return []
        
        try:
            with open(self.file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(f'Failed to load recent albums: {e}')
        
        return []
    
    def _save(self) -> None:
        """Save recent albums to JSON file."""
        try:
            with open(self.file, 'w') as f:
                json.dump(self._albums, f, indent=2)
        except Exception as e:
            logger.error(f'Failed to save recent albums: {e}')
    
    def add(self, album_path: str) -> None:
        """Add album to recent list.
        
        Moves to front if already exists, removes old entries if list is full.
        
        Args:
            album_path: Full path to .mcf or .xmcf file
        """
        album_path = str(Path(album_path).resolve())  # Normalize path
        
        # Remove if already exists
        self._albums = [a for a in self._albums if a['path'] != album_path]
        
        # Determine display name - use .xmcf bundle name if inside one
        path_obj = Path(album_path)
        album_name = path_obj.name  # Default to file name
        
        # If this is a data.mcf inside an .xmcf bundle, use the bundle name instead
        if path_obj.name == 'data.mcf' and path_obj.parent.suffix in ['.xmcf', '.mcfx']:
            album_name = path_obj.parent.name
        
        # Add to front with timestamp
        self._albums.insert(0, {
            'path': album_path,
            'name': album_name,
            'timestamp': datetime.now().isoformat()
        })
        
        # Trim to max recent
        self._albums = self._albums[:self.MAX_RECENT]
        
        self._save()
    
    def list_all(self) -> List[dict]:
        """Get all recent albums in order (newest first).
        
        Returns:
            List of album dicts, filtered to only existing files
        """
        # Filter out albums that no longer exist
        existing = [a for a in self._albums if Path(a['path']).exists()]
        
        # Update if any were removed
        if len(existing) < len(self._albums):
            self._albums = existing
            self._save()
        
        return existing
    
    def clear(self) -> None:
        """Clear all recent albums."""
        self._albums = []
        self._save()
    
    def remove(self, album_path: str) -> None:
        """Remove specific album from recent list.
        
        Args:
            album_path: Full path to album file
        """
        album_path = str(Path(album_path).resolve())
        self._albums = [a for a in self._albums if a['path'] != album_path]
        self._save()


class PreferencesManager:
    """Manage application preferences."""
    
    DEFAULT_PREFERENCES = {
        'dark_mode_follow_system': True,
        'default_photos_folder': None,
        'auto_save_enabled': True,
        'auto_save_interval_seconds': 300,  # 5 minutes
        'window_geometry': None,  # Will store window size/position
        'last_open_folder': None,
    }
    
    def __init__(self):
        self.file = get_preferences_file()
        self.prefs = self._load()
    
    def _load(self) -> dict:
        """Load preferences from JSON file.
        
        Returns:
            Dict of preferences with defaults merged in
        """
        prefs = self.DEFAULT_PREFERENCES.copy()
        
        if not self.file.exists():
            return prefs
        
        try:
            with open(self.file, 'r') as f:
                user_prefs = json.load(f)
                if isinstance(user_prefs, dict):
                    prefs.update(user_prefs)
        except Exception as e:
            logger.warning(f'Failed to load preferences: {e}')
        
        return prefs
    
    def _save(self) -> None:
        """Save preferences to JSON file."""
        try:
            with open(self.file, 'w') as f:
                json.dump(self.prefs, f, indent=2)
        except Exception as e:
            logger.error(f'Failed to save preferences: {e}')
    
    def get(self, key: str, default=None):
        """Get preference value.
        
        Args:
            key: Preference key
            default: Default value if not found
            
        Returns:
            Preference value or default
        """
        return self.prefs.get(key, default)
    
    def set(self, key: str, value) -> None:
        """Set preference value.
        
        Args:
            key: Preference key
            value: Preference value
        """
        self.prefs[key] = value
        self._save()
    
    def set_multiple(self, updates: dict) -> None:
        """Set multiple preferences at once.
        
        Args:
            updates: Dict of key-value pairs to update
        """
        self.prefs.update(updates)
        self._save()
