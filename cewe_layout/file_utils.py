"""Utilities for filename manipulation and metadata encoding/decoding."""
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def split_safecontainer_prefix(filename):
    """Split filename into (prefix, clean_name) tuple.
    
    Args:
        filename: Filename that may have safecontainer:/ prefix
        
    Returns:
        Tuple of (prefix, clean_name) where prefix is 'safecontainer:/' or ''
    """
    if not filename or not filename.startswith('safecontainer:/'):
        return '', filename
    return 'safecontainer:/', filename[len('safecontainer:/'):].lstrip('/')


def safe_parse_number(value_str, field_name, filename):
    """Parse number with consistent error handling.
    
    Args:
        value_str: String to parse as number
        field_name: Name of field being parsed (for error messages)
        filename: Filename being processed (for error messages)
        
    Returns:
        Parsed float/int or None if parsing fails
    """
    try:
        # Parse as float if it has decimal point, otherwise int
        return float(value_str) if '.' in value_str else int(value_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse {field_name} from '{filename}': {e}")
        return None


def extract_metadata_from_filename(filename: str) -> tuple:
    """
    Extract both size and page number from filename.
    
    Args:
        filename: Filename like 'photo-sz2.5-pg10.jpg' or 'safecontainer:/photo-sz1.0-pg5.png'
    
    Returns:
        Tuple of (base_filename, preferred_size_or_None, page_number_or_None)
        For 'photo-sz2.5-pg10.jpg' returns ('photo.jpg', 2.5, 10)
        For 'photo-sz2.5.png' returns ('photo.png', 2.5, None)
        For 'photo-pg10.jpg' returns ('photo.jpg', None, 10)
        For 'photo.jpg' returns ('photo.jpg', None, None)
    """
    # Handle None or empty filename
    if not filename:
        return filename, None, None
    
    # Handle safecontainer prefix using helper
    prefix, clean_name = split_safecontainer_prefix(filename)
    
    # Split into name and extension first
    p = Path(clean_name)
    extension = p.suffix
    name_part = p.stem
    
    # Extract size and page in any order
    size = None
    page_num = None
    
    # Look for -szN.NN pattern
    size_match = re.search(r'-sz([0-9]+(?:[.][0-9]{1,2})?)', name_part)
    if size_match:
        size = safe_parse_number(size_match.group(1), 'size', filename)
    
    # Look for -pgN pattern
    page_match = re.search(r'-pg([0-9]+)', name_part)
    if page_match:
        page_num = safe_parse_number(page_match.group(1), 'page number', filename)
    
    # Remove both patterns to get base name
    base_name = name_part
    if size_match:
        base_name = base_name.replace(size_match.group(0), '')
    if page_match:
        base_name = base_name.replace(page_match.group(0), '')
    
    base_filename = base_name + extension
    # Return base filename WITHOUT the safecontainer prefix (that's only used in MCF, not for file lookup)
    return base_filename, size, page_num


def encode_metadata_in_filename(filename: str, preferred_size: float = None, page_number: int = None) -> str:
    """
    Encode both preferred size and page number into filename.
    
    Args:
        filename: Original filename (may already have -sz or -pg suffixes)
        preferred_size: Size value to encode (e.g., 3.45), or None to preserve existing
        page_number: Page number to encode (e.g., 10), or None to preserve existing
    
    Returns:
        Filename with metadata encoded like 'photo-sz3.45-pg10.jpg' or 'photo-sz2.0.png'
        Order is always: basename + -sz + -pg + extension
    """
    # Handle None or empty filename
    if not filename:
        return filename
    
    # Handle safecontainer prefix using helper
    prefix, clean_name = split_safecontainer_prefix(filename)
    
    # Extract existing metadata
    base_name, existing_size, existing_page = extract_metadata_from_filename(clean_name)
    
    # Remove prefix from base_name if it got added
    if base_name.startswith('safecontainer:/'):
        base_name = base_name[len('safecontainer:/'):]
    
    # Use provided values or fall back to existing
    final_size = preferred_size if preferred_size is not None else existing_size
    final_page = page_number if page_number is not None else existing_page
    
    # Split into name and extension
    p = Path(base_name)
    stem = p.stem
    suffix = p.suffix
    
    # Build new filename: always use order -sz then -pg
    new_name = stem
    
    if final_size is not None:
        size_str = f"{final_size:.2f}".rstrip('0').rstrip('.')
        new_name += f"-sz{size_str}"
    
    if final_page is not None:
        new_name += f"-pg{final_page}"
    
    new_name += suffix
    
    return prefix + new_name
