"""Mimeo Photos Project.db database reader.

Reads legacy Mimeo Photos .ppb photobook projects from Apple Photos library.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class MimeoProject:
    """Reader for Mimeo Photos Project.db database."""
    
    def __init__(self, ppb_path: Path):
        """Initialize with path to .ppb bundle.
        
        Args:
            ppb_path: Path to .ppb bundle (e.g., '7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')
        """
        self.ppb_path = Path(ppb_path)
        self.db_path = self.ppb_path / 'Project.db'
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Project.db not found at {self.db_path}")
    
    def _execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        """Execute a query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            List of result rows
        """
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            return rows
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return []
    
    def get_project_metadata(self) -> Dict[str, Any]:
        """Get project metadata from KHProject table.
        
        Returns:
            Dict with project metadata fields
        """
        rows = self._execute_query("SELECT * FROM KHProject LIMIT 1")
        
        if rows:
            row = rows[0]
            return {
                'name': row['name'],
                'product_code': row['productCode'],
                'theme_id': row['themeId'],
                # Add other fields as needed
            }
        
        return {}
    
    def get_photos(self) -> List[Dict[str, Any]]:
        """Get all photos from KHProjectPhoto table.
        
        Returns:
            List of photo dicts with:
                - model_id: Photo model ID
                - photo_id: Base64-encoded UUID
                - index: Photo index (using modelId as index)
        """
        rows = self._execute_query("SELECT * FROM KHProjectPhoto ORDER BY modelId")
        
        photos = []
        for idx, row in enumerate(rows):
            photos.append({
                'model_id': row['modelId'],
                'photo_id': row['photoId'],  # This is the Mimeo base64 UUID
                'index': idx,  # Use enumeration index
            })
        
        return photos
    
    def get_frames(self) -> List[Dict[str, Any]]:
        """Get all photo frames (layout slots) from KHProjectFrame table.
        
        Returns:
            List of frame dicts with:
                - model_id: Frame model ID
                - x, y, width, height: Position and size (in unknown Mimeo units)
                - page_id: Reference to KHProjectLayout.modelId (from parentLayoutId)
        """
        rows = self._execute_query("SELECT * FROM KHProjectFrame ORDER BY parentLayoutId")
        
        frames = []
        for row in rows:
            frames.append({
                'model_id': row['modelId'],
                'x': row['x'],
                'y': row['y'],
                'width': row['width'],
                'height': row['height'],
                'page_id': row['parentLayoutId'],
                # Add other fields as needed
            })
        
        return frames
    
    def get_layouts(self) -> List[Dict[str, Any]]:
        """Get all page layouts from KHProjectLayout table.
        
        Returns:
            List of layout dicts with:
                - model_id: Layout model ID
                - index: Page index (sequence)
                - background_color: Page background color (if available)
        """
        rows = self._execute_query("SELECT * FROM KHProjectLayout ORDER BY sequence")
        
        layouts = []
        for row in rows:
            layout = {
                'model_id': row['modelId'],
                'index': row['sequence'],
            }
            
            # Add background color if column exists
            if 'backgroundColor' in row.keys():
                layout['background_color'] = row['backgroundColor']
            
            layouts.append(layout)
        
        return layouts
    
    def get_photo_frame_mappings(self) -> List[Dict[str, Any]]:
        """Get photo-to-frame mappings from KHProjectPhotoFrame table.
        
        This table may be empty in some projects, in which case the mapping
        might be implicit (e.g., photo index maps to frame index).
        
        Returns:
            List of mapping dicts with:
                - photo_id: Reference to KHProjectPhoto.modelId
                - frame_id: Reference to KHProjectFrame.modelId
        """
        rows = self._execute_query("SELECT * FROM KHProjectPhotoFrame")
        
        mappings = []
        for row in rows:
            mappings.append({
                'photo_id': row['photoId'],
                'frame_id': row['frameId'],
            })
        
        return mappings
    
    def extract_all(self) -> Dict[str, Any]:
        """Extract all relevant data from Mimeo project.
        
        Returns:
            Dict with:
                - metadata: Project metadata
                - photos: List of photos
                - frames: List of layout frames
                - layouts: List of page layouts
                - photo_frame_mappings: Photo-to-frame mappings
        """
        return {
            'metadata': self.get_project_metadata(),
            'photos': self.get_photos(),
            'frames': self.get_frames(),
            'layouts': self.get_layouts(),
            'photo_frame_mappings': self.get_photo_frame_mappings(),
        }
