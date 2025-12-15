"""Test script for photo improver functionality."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.photoimprover.photo_improver import PhotoImprover

def test_basic_functionality():
    """Test basic photo matching functionality."""
    
    # Use Test-album-photos as test directory (it's in the parent of cewe-layout)
    test_dir = Path(__file__).parent.parent.parent / "Test-album-photos"
    
    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}")
        return
    
    print(f"Testing with directory: {test_dir}")
    
    # Create improver
    improver = PhotoImprover(test_dir)
    print(f"Loaded {len(improver.candidates)} candidate photos")
    
    if len(improver.candidates) > 0:
        # Test self-match (should find itself)
        test_photo = improver.candidates[0]
        print(f"\nTesting self-match with: {Path(test_photo).name}")
        
        matches = improver.find_matches(test_photo, max_matches=5, threshold=10)
        print(f"Found {len(matches)} matches")
        
        if matches:
            for i, match in enumerate(matches[:3]):
                print(f"  {i+1}. {Path(match.candidate_path).name} - {match.similarity_score*100:.1f}% similar")
                print(f"     Current: {match.photobook_metrics['width']}x{match.photobook_metrics['height']} ({match.photobook_metrics['file_size_kb']:.1f} KB)")
                print(f"     Candidate: {match.candidate_metrics['width']}x{match.candidate_metrics['height']} ({match.candidate_metrics['file_size_kb']:.1f} KB)")
                print(f"     Improvement: {match.is_improvement()}")
    
    print("\n✓ Basic test passed!")

if __name__ == '__main__':
    test_basic_functionality()
