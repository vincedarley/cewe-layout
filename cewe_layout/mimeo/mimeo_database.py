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
                - is_extra: True if photo is not placed in layout (isExtra=1)
        """
        rows = self._execute_query("SELECT * FROM KHProjectPhoto ORDER BY modelId")
        
        photos = []
        for idx, row in enumerate(rows):
            photos.append({
                'model_id': row['modelId'],
                'photo_id': row['photoId'],  # This is the Mimeo base64 UUID
                'index': idx,  # Use enumeration index
                'is_extra': row['isExtra'] == 1,  # True if photo is not in layout
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
                - width: Page width
                - height: Page height
                - background_color: Page background color (if available)
        """
        # Get layout background colors via treatmentId -> layer -> fillColor
        # Query: layout.treatmentId -> KHProjectTreatmentLayer.treatmentId -> layerId -> KHProjectLayerAttribute.fillColor
        bg_colors = {}
        bg_rows = self._execute_query(
            "SELECT DISTINCT l.modelId, la.value "
            "FROM KHProjectLayout l "
            "JOIN KHProjectTreatmentLayer tl ON l.treatmentId = tl.treatmentId "
            "JOIN KHProjectLayerAttribute la ON tl.layerId = la.layerId "
            "WHERE la.key = 'fillColor'"
        )
        for row in bg_rows:
            bg_colors[row['modelId']] = row['value']
        
        rows = self._execute_query("SELECT * FROM KHProjectLayout ORDER BY sequence")
        
        layouts = []
        for row in rows:
            layout = {
                'model_id': row['modelId'],
                'index': row['sequence'],
            }
            
            # Add width and height if columns exist
            if 'width' in row.keys():
                layout['width'] = row['width']
            if 'height' in row.keys():
                layout['height'] = row['height']
            
            # Add background color if available
            model_id = row['modelId']
            if model_id in bg_colors:
                layout['background_color'] = bg_colors[model_id]
            
            layouts.append(layout)
        
        return layouts
    
    def get_photo_frame_mappings(self) -> Dict[int, int]:
        """Get photo-to-frame mappings from KHProjectFrameAttribute table.
        
        The actual mapping is stored in KHProjectFrameAttribute with key='projectPhotoId',
        which links frameId to photo modelId.
        
        Returns:
            Dict mapping frame_id -> photo_id (both are modelId values)
        """
        rows = self._execute_query(
            "SELECT frameId, value FROM KHProjectFrameAttribute WHERE key = 'projectPhotoId'"
        )
        
        mappings = {}
        for row in rows:
            frame_id = row['frameId']
            photo_id = int(row['value'])  # value is stored as string
            mappings[frame_id] = photo_id
        
        return mappings
    
    def get_frame_text(self) -> Dict[int, Dict[str, Any]]:
        """Get text content for frames from KHProjectFrameAttribute table.
        
        Text frames have various text-related attributes:
        - rawText: The actual text content
        - textStyleName: Font style identifier
        - textColor: RGB color values
        - textType: Type of text (0=user text, 1=title, 2=page number, etc.)
        
        Returns:
            Dict mapping frame_id -> {text, style_name, color, text_type}
        """
        # Get all text-related attributes for frames
        rows = self._execute_query(
            "SELECT frameId, key, value FROM KHProjectFrameAttribute "
            "WHERE key IN ('rawText', 'textStyleName', 'textColor', 'textType') "
            "ORDER BY frameId"
        )
        
        # Group by frame_id
        frame_text = {}
        for row in rows:
            frame_id = row['frameId']
            key = row['key']
            value = row['value']
            
            if frame_id not in frame_text:
                frame_text[frame_id] = {}
            
            if key == 'rawText':
                frame_text[frame_id]['text'] = value
            elif key == 'textStyleName':
                frame_text[frame_id]['style_name'] = value
            elif key == 'textColor':
                frame_text[frame_id]['color'] = value
            elif key == 'textType':
                frame_text[frame_id]['text_type'] = int(value) if value else 0
        
        # Only return frames that have text
        return {fid: data for fid, data in frame_text.items() if 'text' in data}
    
    def extract_all(self) -> Dict[str, Any]:
        """Extract all relevant data from Mimeo project.
        
        Returns:
            Dict with:
                - metadata: Project metadata
                - photos: List of photos
                - frames: List of layout frames
                - layouts: List of page layouts
                - frame_to_photo: Dict mapping frame_id -> photo_id (from KHProjectFrameAttribute)
                - frame_text: Dict mapping frame_id -> text data
        """
        return {
            'metadata': self.get_project_metadata(),
            'photos': self.get_photos(),
            'frames': self.get_frames(),
            'layouts': self.get_layouts(),
            'frame_to_photo': self.get_photo_frame_mappings(),
            'frame_text': self.get_frame_text(),
        }
