
# Widths are spread dimensions (so 2x pages). We list separately the cover and page sizes.
# Note that CEWE calculates a very specific coverWidth which seems to depend on the number of pages
# in the book. This makes some sense if the cover width wraps around the spine - a thicker book will require
# more width to perform that wrapping.  We do not try to replicate that logic here. So when you open and then
# save the book in CEWE Creator, I expect the coverWidth may change slightly.

BOOK_SIZES = {
    'L landscape': {'productname': 'ALB45', 'coverWidth': 3975, 'coverHeight': 1530, 'pageWidth': 3800, 'pageHeight': 1480, 'art_id': 8068},
    'XXL landscape': {'productname': 'ALB42', 'coverWidth': 7870, 'coverHeight': 2960, 'pageWidth': 7640, 'pageHeight': 2900, 'art_id': 9896},
    'XL landscape': {'productname': 'ALB35', 'coverWidth': 5575, 'coverHeight': 2100, 'pageWidth': 5400, 'pageHeight': 2050, 'art_id': 9759},
}


def find_closest_book_size(width: int, height: int) -> str:
    """Find the closest matching book size based on page dimensions.

    Compares the given width and height against the pageWidth and pageHeight
    of each book size, selecting the one with minimum total absolute difference.

    Args:
        width: Page width in MCF units (spread width, not single page)
        height: Page height in MCF units

    Returns:
        Book size key (e.g., 'ALB45', 'ALB42') with closest matching dimensions

    Raises:
        ValueError: If BOOK_SIZES is empty

    Example:
        >>> find_closest_book_size(3800, 1480)
        'ALB45'
        >>> find_closest_book_size(7640, 2900)
        'ALB42'
    """
    best_match = None
    min_difference = float('inf')

    for book_key, dimensions in BOOK_SIZES.items():
        page_width = dimensions['pageWidth']
        page_height = dimensions['pageHeight']

        # Calculate total absolute difference
        width_diff = abs(width - page_width/2)
        height_diff = abs(height - page_height)
        total_diff = width_diff + height_diff

        if total_diff < min_difference:
            min_difference = total_diff
            best_match = book_key

    return best_match
