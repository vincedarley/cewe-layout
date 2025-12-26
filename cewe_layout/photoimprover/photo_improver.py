"""Photo improvement module - find and replace low-quality photos with better versions.

This module provides functionality to:
1. Search a directory of candidate photos for close matches to photobook images
2. Compare image quality metrics (file size, resolution, etc.)
3. Generate side-by-side comparison reports
4. Replace photos in the photobook with higher-quality versions
"""

import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import logging
from PIL import Image
import imagehash

logger = logging.getLogger(__name__)


class PhotoMatch:
    """Represents a potential match between a photobook image and a candidate replacement."""
    
    def __init__(self, photobook_path: str, candidate_path: str, similarity_score: float):
        self.photobook_path = photobook_path
        self.candidate_path = candidate_path
        self.similarity_score = similarity_score
        
        # Get metrics for both images
        self.photobook_metrics = self._get_image_metrics(photobook_path)
        self.candidate_metrics = self._get_image_metrics(candidate_path)
    
    def _get_image_metrics(self, path: str) -> Dict:
        """Get metrics for an image file."""
        try:
            file_size = os.path.getsize(path) / 1024  # KB
            with Image.open(path) as img:
                width, height = img.size
                megapixels = (width * height) / 1_000_000
            
            return {
                'width': width,
                'height': height,
                'megapixels': megapixels,
                'file_size_kb': file_size,
                'format': Path(path).suffix.upper()
            }
        except Exception as e:
            logger.error(f"Failed to get metrics for {path}: {e}")
            return {
                'width': 0,
                'height': 0,
                'megapixels': 0,
                'file_size_kb': 0,
                'format': 'UNKNOWN'
            }
    
    def is_improvement(self) -> bool:
        """Determine if candidate is likely an improvement over current photo."""
        # Consider it an improvement if:
        # 1. Higher resolution (megapixels)
        # 2. Similar or larger file size (not overly compressed)
        current_mp = self.photobook_metrics['megapixels']
        candidate_mp = self.candidate_metrics['megapixels']
        
        # At least 10% more megapixels, or similar resolution but larger file size
        if candidate_mp >= current_mp * 1.1:
            return True
        
        # Similar resolution but much larger file size (less compression)
        if (candidate_mp >= current_mp * 0.95 and 
            self.candidate_metrics['file_size_kb'] >= self.photobook_metrics['file_size_kb'] * 1.5):
            return True
        
        return False


class PhotoImprover:
    """Main class for finding and replacing low-quality photos."""
    
    def __init__(self, candidate_dir: Path):
        """Initialize photo improver with a directory of candidate photos.
        
        Args:
            candidate_dir: Directory containing candidate replacement photos
        """
        self.candidate_dir = Path(candidate_dir)
        self.candidates = []
        self.candidate_hashes = {}
        
        if not self.candidate_dir.exists():
            raise ValueError(f"Candidate directory does not exist: {candidate_dir}")
        
        # Load candidate photos
        self._load_candidates()
    
    def _load_candidates(self):
        """Load all candidate photos and compute their perceptual hashes."""
        image_exts = {'.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG', '.heic', '.HEIC', '.heif', '.HEIF'}
        
        logger.info(f"Loading candidate photos from {self.candidate_dir}")
        
        for file_path in self.candidate_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix in image_exts:
                self.candidates.append(str(file_path))
        
        logger.info(f"Found {len(self.candidates)} candidate photos")
        
        # Compute perceptual hashes for all candidates
        for candidate_path in self.candidates:
            try:
                with Image.open(candidate_path) as img:
                    # Use average hash for speed (can switch to phash for more accuracy)
                    hash_value = imagehash.average_hash(img)
                    self.candidate_hashes[candidate_path] = hash_value
            except Exception as e:
                logger.warning(f"Failed to hash {candidate_path}: {e}")
    
    def find_matches(self, photobook_path: str, max_matches: int = 5, 
                    threshold: int = 10) -> List[PhotoMatch]:
        """Find similar images in the candidate directory.
        
        Args:
            photobook_path: Path to the photobook image to match
            max_matches: Maximum number of matches to return
            threshold: Maximum hash difference (lower = more similar, 0 = identical)
        
        Returns:
            List of PhotoMatch objects, sorted by similarity (best first)
        """
        if not os.path.exists(photobook_path):
            logger.error(f"Photobook image not found: {photobook_path}")
            return []
        
        try:
            # Compute hash for photobook image
            with Image.open(photobook_path) as img:
                photobook_hash = imagehash.average_hash(img)
        except Exception as e:
            logger.error(f"Failed to hash photobook image {photobook_path}: {e}")
            return []
        
        # Find similar images
        matches = []
        for candidate_path, candidate_hash in self.candidate_hashes.items():
            hash_diff = photobook_hash - candidate_hash
            
            if hash_diff <= threshold:
                # Convert hash difference to similarity score (0-1, higher = more similar)
                similarity = 1.0 - (hash_diff / 64.0)  # 64 is max possible difference for average_hash
                match = PhotoMatch(photobook_path, candidate_path, similarity)
                matches.append(match)
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        # Return top matches
        return matches[:max_matches]
    
    def find_matches_for_photos(self, photobook_photos: List[str], 
                               max_matches_per_photo: int = 3,
                               threshold: int = 10) -> Dict[str, List[PhotoMatch]]:
        """Find matches for multiple photobook photos.
        
        Args:
            photobook_photos: List of photobook image paths
            max_matches_per_photo: Max matches to find per photo
            threshold: Maximum hash difference threshold
        
        Returns:
            Dict mapping photobook_path -> list of PhotoMatch objects
        """
        results = {}
        
        for photo_path in photobook_photos:
            matches = self.find_matches(photo_path, max_matches_per_photo, threshold)
            if matches:
                results[photo_path] = matches
        
        return results
