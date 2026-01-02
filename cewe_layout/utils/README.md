# Mimeo Photos to CEWE Converter

This utility converts legacy Mimeo Photos `.ppb` photobook projects (from macOS Photos library) to CEWE `.xmcf` format.

## Features

- **UUID Mapping**: Decodes Mimeo base64-encoded UUIDs and maps to Apple Photos library
- **Coordinate Transformation**: Transforms Mimeo coordinate system to MCF units with scaling/padding options
- **Code Reuse**: Leverages existing cewe-layout infrastructure:
  - `writer._calculate_cutout` for image fitting
  - `pdf2cewe.mcf_writer` for MCF project creation
  - `colour_utils.COLOR_MAP` for CEWE color handling
  - `gap_utils` for coordinate transformations

## Mimeo Database Structure

### Coordinate System
- **Mimeo Units**: Approximately 2390 x 1067 units for a full page
- **MCF Units**: 0.1mm (254 units ≈ 1 inch)
- **Transformation**: Scale from Mimeo units → MCF units with optional padding

### Database Tables
- `KHProject`: Project metadata (name, productCode, themeId)
- `KHProjectPhoto`: Photo catalog (473 photos with base64 UUIDs)
- `KHProjectFrame`: Photo slots (471 frames with x, y, width, height)
- `KHProjectLayout`: Page layouts (89 pages)
- `KHProjectPhotoFrame`: Junction table (empty - uses index-based mapping)

### Photo-Frame Mapping
Since `KHProjectPhotoFrame` is empty, the mapping is index-based:
- `photo[i]` → `frame[i]`

### Colors
No explicit background color columns found in test database. Uses default white background.

## Usage

### Basic Conversion

```bash
python -m cewe_layout.utils.convert_mimeo_cli \
    --ppb "/path/to/Photos.photoslibrary/resources/projects/legacy/UUID.ppb" \
    --library "/path/to/Photos.photoslibrary" \
    --output "./converted-album.xmcf" \
    --verbose
```

### With Custom Book Size and Padding

```bash
python -m cewe_layout.utils.convert_mimeo_cli \
    --ppb "/path/to/project.ppb" \
    --library "/path/to/Photos.photoslibrary" \
    --output "./album.xmcf" \
    --book-size ALB42 \
    --padding "5,5,5,5" \
    --mode fit \
    --verbose
```

### Options

- `--ppb`: Path to `.ppb` bundle (required)
- `--library`: Path to `.photoslibrary` bundle (required)
- `--output`: Output path for `.xmcf` project (required)
- `--book-size`: CEWE book size ID (ALB45, ALB42, ALB35). Auto-detects if not specified.
- `--padding`: Padding in mm as `left,top,right,bottom` (default: `0,0,0,0`)
- `--mode`: Coordinate mode - `fit` (maintain aspect ratio) or `fill` (stretch to fill)
- `--verbose`: Print detailed conversion info

## Exploring Mimeo Databases

To analyze a Mimeo database before conversion:

```bash
python cewe-layout/cewe_layout/utils/explore_mimeo.py "/path/to/project.ppb"
```

This prints:
- Coordinate ranges and inferred page dimensions
- Available color columns
- Photo-frame mapping strategy
- Page distribution statistics

## Architecture

### Modules

- `mimeo_uuid.py`: UUID decoding and Photos library mapping
- `mimeo_database.py`: Mimeo Project.db reader
- `mimeo_converter.py`: Main conversion orchestrator
- `convert_mimeo_cli.py`: Command-line interface
- `explore_mimeo.py`: Database exploration tool

### Conversion Flow

1. **Read Mimeo Project**: Extract photos, frames, layouts from Project.db
2. **Map UUIDs**: Decode base64 UUIDs → Query Photos.sqlite → Get file paths
3. **Transform Coordinates**: Scale from Mimeo units to MCF units with padding
4. **Build MCF XML**: Create fotobook structure using existing `writer` patterns
5. **Write Project**: Create `.xmcf` directory with `data.mcf` and `folderid.xml`

### Coordinate Transformation

```python
# Mimeo page: ~2390 x ~1067 units
# CEWE page: e.g., 3800 x 1480 MCF units (ALB45 single page)

transformer = MimeoCoordinateTransformer(
    mimeo_page_width=2389.57,
    mimeo_page_height=1066.76,
    cewe_page_width_mcf=3800 // 2,  # Single page
    cewe_page_height_mcf=1480,
    padding_left=50,  # 5mm in MCF
    padding_top=50,
    mode='fit'  # Maintain aspect ratio
)

mcf_x, mcf_y, mcf_w, mcf_h = transformer.transform(mimeo_x, mimeo_y, mimeo_w, mimeo_h)
```

## Known Limitations

- **Colors**: Background colors not yet implemented (needs database exploration)
- **Borders**: Decorative borders not yet implemented
- **Text Areas**: Text blocks not yet supported
- **Covers**: Only interior pages converted (covers skipped for now)
- **Photo Placement**: Assumes index-based photo-frame mapping

## Future Enhancements

1. **Color Mapping**: Add Mimeo → CEWE color code mapping once format is understood
2. **Border Conversion**: Map decorative border attributes to MCF `<decoration>` elements
3. **Text Support**: Extract and convert text blocks
4. **Cover Pages**: Add cover page conversion
5. **Auto-detect Page Size**: Infer CEWE book size from Mimeo productCode

## Testing

To test UUID decoding:

```python
from cewe_layout.utils.mimeo_uuid import decode_mimeo_uuid

uuid = decode_mimeo_uuid("%5TqQyz2RDCRiQ2yikb2VA")
# Returns: 'FF94EA43-2CF6-4430-9189-0DB28A46F654'
```

To test photo mapping:

```python
from pathlib import Path
from cewe_layout.utils.mimeo_uuid import PhotosLibraryMapper

mapper = PhotosLibraryMapper(Path("/path/to/Photos.photoslibrary"))
photo_info = mapper.map_mimeo_uuid("%5TqQyz2RDCRiQ2yikb2VA")
print(photo_info['path'])  # Full path to photo file
```
