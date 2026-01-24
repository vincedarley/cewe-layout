"""High-level interface for photo improvement workflow.

This module provides the main entry point for the GUI to initiate photo improvement searches.
"""

import logging
from pathlib import Path
from typing import Callable
import shutil

from .photo_improver import PhotoImprover
from .photo_comparison_window import PhotoComparisonWindow

logger = logging.getLogger(__name__)


def search_and_show_improvements(
    parent_window,
    album_path: str,
    current_page_photos: list,
    on_photo_replaced: Callable[[str, str], None],
    scope: str = 'page'
) -> None:
    """Search for photo improvements and show comparison window.
    
    This is the main entry point called by the GUI. It handles:
    1. Finding the candidate photos directory
    2. Searching for matches
    3. Opening the comparison window
    4. Handling user acceptances
    
    Args:
        parent_window: Parent tkinter window
        album_path: Path to the MCF file
        current_page_photos: List of photo dicts from current page
        on_photo_replaced: Callback when user accepts a replacement
                          Signature: (old_filename, new_filename)
        scope: Search scope - 'page' or 'album' (future: 'all')
    """
    # Find candidate directory (Album-name-photos)
    album_dir = Path(album_path).parent
    album_name = album_dir.name.replace('.xmcf', '').replace('.mcfx', '')
    candidate_dir = album_dir.parent / f"{album_name}-photos"
    
    if not candidate_dir.exists():
        logger.error(f"Candidate directory not found: {candidate_dir}")
        return
    
    logger.info(f"Searching for photo improvements in {candidate_dir}")
    
    try:
        # Initialize photo improver with candidate directory
        improver = PhotoImprover(candidate_dir)
        
        # Get photobook photos to search for
        if scope == 'page':
            photos_to_search = _get_photobook_paths(album_dir, current_page_photos)
        else:
            # Future: search entire album
            logger.warning(f"Scope '{scope}' not yet implemented")
            return
        
        if not photos_to_search:
            logger.info("No photos to search for on current page")
            return
        
        # Search for matches
        logger.info(f"Searching for matches for {len(photos_to_search)} photos...")
        matches = improver.find_matches_for_photos(
            photos_to_search,
            max_matches_per_photo=5,
            threshold=10  # Hash difference threshold (lower = more similar)
        )
        
        if not matches:
            logger.info("No matches found")
            return
        
        logger.info(f"Found matches for {len(matches)} photos")
        
        # Create callback that handles photo replacement
        def accept_callback(photobook_path: str, replacement_path: str):
            _handle_photo_acceptance(
                photobook_path,
                replacement_path,
                album_dir,
                on_photo_replaced
            )
        
        # Show comparison window
        PhotoComparisonWindow(parent_window, matches, accept_callback)
        
    except Exception as e:
        logger.error(f"Failed to search for photo improvements: {e}", exc_info=True)


def _get_photobook_paths(album_dir: Path, photo_dicts: list) -> list:
    """Convert photo dicts to actual file paths.
    
    Args:
        album_dir: Album directory
        photo_dicts: List of photo dicts with 'filename' key
    
    Returns:
        List of absolute paths to photobook images
    """
    paths = []
    
    for photo in photo_dicts:
        filename = photo.get('filename', '')
        if not filename:
            continue
        
        # Remove safecontainer prefix and leading slashes
        safefn = filename.replace('safecontainer:/', '').lstrip('/')
        
        # Try multiple possible locations
        possible_paths = [
            album_dir / safefn,
            album_dir / 'images' / safefn,
        ]
        
        for path in possible_paths:
            if path.exists():
                paths.append(str(path.absolute()))
                break
        else:
            logger.warning(f"Photo not found: {filename}")
    
    return paths


def _handle_photo_acceptance(
    photobook_path: str,
    replacement_path: str,
    album_dir: Path,
    on_photo_replaced: Callable[[str, str], None]
) -> None:
    """Handle user accepting a photo replacement.
    
    This function:
    1. Copies the replacement photo to the album directory
    2. Renames it with -up suffix to indicate it's an upgrade
    3. Calls the callback to update the in-memory layout
    
    Args:
        photobook_path: Path to original photobook image
        replacement_path: Path to replacement image
        album_dir: Album directory
        on_photo_replaced: Callback to notify GUI of replacement
    """
    try:
        # Get the original filename from photobook
        original_name = Path(photobook_path).name
        
        # Extract base name and extension
        base_parts = original_name.rsplit('.', 1)
        if len(base_parts) == 2:
            base_name, ext = base_parts
        else:
            base_name = base_parts[0]
            ext = 'jpg'
        
        # Add -up suffix (similar to -sz, -pg)
        # If there's already metadata, insert -up before it
        if '-sz' in base_name or '-pg' in base_name:
            # Has metadata - insert -up before the metadata
            parts = base_name.split('-sz')
            if len(parts) == 2:
                new_base = f"{parts[0]}-up-sz{parts[1]}"
            else:
                parts = base_name.split('-pg')
                if len(parts) == 2:
                    new_base = f"{parts[0]}-up-pg{parts[1]}"
                else:
                    new_base = f"{base_name}-up"
        else:
            # No metadata - just add -up
            new_base = f"{base_name}-up"
        
        new_filename = f"{new_base}.{ext}"
        new_path = album_dir / new_filename
        
        # Copy replacement to album directory with new name
        shutil.copy2(replacement_path, new_path)
        logger.info(f"Copied {Path(replacement_path).name} -> {new_filename}")
        
        # Build MCF filename (with safecontainer prefix)
        mcf_filename = f"safecontainer:/{new_filename}"
        
        # Notify GUI to update layout
        original_mcf_filename = f"safecontainer:/{original_name}"
        on_photo_replaced(original_mcf_filename, mcf_filename)
        
        logger.info(f"Replaced {original_name} with {new_filename}")
        
    except Exception as e:
        logger.error(f"Failed to handle photo acceptance: {e}", exc_info=True)
