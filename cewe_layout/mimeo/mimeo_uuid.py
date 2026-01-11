"""UUID handling for Mimeo Photos databases.

Mimeo Photos stores UUIDs in a base64-encoded format where:
- The standard '/' character is replaced with '%' (filesystem-safe)
- Padding may be missing

This module decodes Mimeo UUIDs to standard format and maps them to photos
in the Apple Photos library database.
"""

import base64
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


def decode_mimeo_uuid(mimeo_uuid: str) -> str:
    """Decode a Mimeo base64-encoded UUID to standard format.
    
    Mimeo UUIDs are base64-encoded with % replacing / and padding may be missing.
    This decodes them to standard UUID format: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    
    Args:
        mimeo_uuid: Base64-encoded UUID from Mimeo database (e.g., "%5TqQyz2RDCRiQ2yikb2VA")
        
    Returns:
        Standard UUID string with hyphens (e.g., "FF94EA43-2CF6-4430-9189-0DB28A46F654")
        
    Example:
        >>> decode_mimeo_uuid("%5TqQyz2RDCRiQ2yikb2VA")
        'FF94EA43-2CF6-4430-9189-0DB28A46F654'
    """
    # Replace % with / (standard base64 character)
    cleaned = mimeo_uuid.replace('%', '/')
    
    # Add missing base64 padding
    missing_padding = (4 - len(cleaned) % 4) % 4
    cleaned += '=' * missing_padding
    
    # Decode base64 to bytes
    decoded_bytes = base64.b64decode(cleaned)
    
    # Convert to hex string
    uuid_hex = decoded_bytes.hex().upper()
    
    # Format as standard UUID (8-4-4-4-12)
    standard_uuid = f"{uuid_hex[0:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-{uuid_hex[16:20]}-{uuid_hex[20:32]}"
    
    return standard_uuid


class PhotosLibraryMapper:
    """Maps Mimeo UUIDs to photo files in Apple Photos library."""
    
    def __init__(self, photos_library_path: Path):
        """Initialize mapper with Photos library path.
        
        Args:
            photos_library_path: Path to .photoslibrary bundle
        """
        self.photos_library_path = Path(photos_library_path)
        self.db_path = self.photos_library_path / 'database' / 'Photos.sqlite'
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Photos database not found at {self.db_path}")
    
    def query_photo(self, uuid: str) -> Optional[Dict[str, str]]:
        """Query Photos database for photo information by UUID.
        
        Args:
            uuid: Standard UUID string (with hyphens)
            
        Returns:
            Dict with keys:
                - 'uuid': Original UUID
                - 'original_filename': Original filename (e.g., 'IMG_2602.JPG')
                - 'directory': Directory code (e.g., 'F')
                - 'stored_filename': Filename in originals/ (e.g., 'FF94EA43...jpeg')
                - 'path': Full path to photo file
                - 'current_orientation': EXIF orientation value (1-8), user-adjusted
                - 'original_orientation': EXIF orientation value (1-8) from camera
            Returns None if UUID not found
        """
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            
            # Query Photos 5+ schema including orientation
            # ZORIENTATION contains the current orientation (may be user-adjusted)
            # ZORIGINALORIENTATION contains the original EXIF orientation from camera
            cursor.execute("""
                SELECT 
                    ZASSET.ZUUID,
                    ZADDITIONALASSETATTRIBUTES.ZORIGINALFILENAME,
                    ZASSET.ZDIRECTORY,
                    ZASSET.ZFILENAME,
                    ZASSET.ZORIENTATION,
                    ZADDITIONALASSETATTRIBUTES.ZORIGINALORIENTATION
                FROM ZASSET
                JOIN ZADDITIONALASSETATTRIBUTES 
                    ON ZADDITIONALASSETATTRIBUTES.ZASSET = ZASSET.Z_PK
                WHERE ZASSET.ZUUID = ?
            """, (uuid,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                uuid_str, original_filename, directory, stored_filename, current_orientation, original_orientation = row
                photo_path = self.photos_library_path / 'originals' / directory / stored_filename
                
                return {
                    'uuid': uuid_str,
                    'original_filename': original_filename,
                    'directory': directory,
                    'stored_filename': stored_filename,
                    'path': str(photo_path),
                    'current_orientation': current_orientation if current_orientation is not None else 1,
                    'original_orientation': original_orientation if original_orientation is not None else 1
                }
            
            return None
            
        except sqlite3.Error as e:
            logger.error(f"Database error querying UUID {uuid}: {e}")
            return None
    
    def map_mimeo_uuid(self, mimeo_uuid: str) -> Optional[Dict[str, str]]:
        """Decode Mimeo UUID and query for photo information.
        
        Args:
            mimeo_uuid: Base64-encoded UUID or standard UUID from Mimeo database
            
        Returns:
            Photo information dict (see query_photo) or None if not found
        """
        try:
            # Check if UUID is already in standard format (has hyphens)
            if '-' in mimeo_uuid and len(mimeo_uuid) == 36:
                # Already standard format
                standard_uuid = mimeo_uuid
            else:
                # Base64-encoded, need to decode
                standard_uuid = decode_mimeo_uuid(mimeo_uuid)
            
            return self.query_photo(standard_uuid)
        except Exception as e:
            logger.error(f"Error mapping Mimeo UUID {mimeo_uuid}: {e}")
            return None
    
    def map_mimeo_uuids_batch(self, mimeo_uuids: List[str]) -> Dict[str, Optional[Dict[str, str]]]:
        """Map multiple Mimeo UUIDs in batch.
        
        Args:
            mimeo_uuids: List of Mimeo base64-encoded UUIDs
            
        Returns:
            Dict mapping Mimeo UUID → photo info dict
            Missing photos will have None value
        """
        results = {}
        
        for mimeo_uuid in mimeo_uuids:
            results[mimeo_uuid] = self.map_mimeo_uuid(mimeo_uuid)
        
        return results
    
    def get_missing_photos(self, uuid_mappings: Dict[str, Optional[Dict[str, str]]]) -> List[str]:
        """Get list of Mimeo UUIDs that couldn't be mapped.
        
        Args:
            uuid_mappings: Result from map_mimeo_uuids_batch
            
        Returns:
            List of Mimeo UUIDs that are None (not found in Photos library)
        """
        return [uuid for uuid, info in uuid_mappings.items() if info is None]
