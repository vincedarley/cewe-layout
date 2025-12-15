"""Photo Improver package - find and replace low-quality photos with better versions.

This package provides a clean interface for the GUI to search for photo improvements
without cluttering the main GUI code.
"""

from .interface import search_and_show_improvements

__all__ = ['search_and_show_improvements']
