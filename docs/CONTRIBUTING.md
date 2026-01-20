# Contributing

Thank you for your interest in cewe-layout! This document covers guidelines for contributions.

## Development Setup

1. Clone the repository and set up a virtual environment:
```bash
git clone <repo>
cd cewe-layout
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the GUI for manual testing:
```bash
python run_qlayout.py --cewe path/to/test/album.xmcf
```

## Adding a New Layout Algorithm

1. Create a new file in `cewe_layout/algorithms/`, e.g., `my_algorithm.py`.
2. Subclass `LayoutAlgorithm` from `cewe_layout/algorithms/base.py` and implement `generate_layout()`.
3. Update imports in `cewe_layout/collage_wrapper.py` if needed; algorithms are typically selected by caller.
4. Include attribution and license info in your algorithm module docstring.

## Testing

Manual testing focuses on:
- Parsing `.mcf` and `.xmcf` files correctly.
- Thumbnail display and EXIF rotation.
- Layout generation on both left and right pages.
- Undo/history and weight adjustment.

For new algorithms, verify:
- Generated layouts have realistic photo areas (non-overlapping, in bounds).
- Coordinate system matches MCF units (0.1mm).

## Licensing

All contributions are licensed under the MIT License (same as the project). If you include external code or algorithms, include proper attribution and ensure license compatibility.
