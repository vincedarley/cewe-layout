# Test Guidelines for cewe-layout

This document explains how to create and run tests for the cewe-layout project.

## Quick Start: Running Tests

### From the cewe-layout directory
```bash
cd /path/to/cewe-layout
source ../.env/bin/activate
python tests/test_name.py
```

**IMPORTANT**: Always activate the virtual environment before running tests!

## Creating New Test Scripts

### Template Structure

Every test script should follow this template:

```python
#!/usr/bin/env python3
"""Brief description of what this test does.

Longer description if needed.

Usage:
    python tests/test_name.py
"""

import sys
from pathlib import Path

# REQUIRED: Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now you can import cewe_layout modules
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info

def main():
    """Main entry point."""
    # Your test code here
    pass

if __name__ == '__main__':
    main()
```

### Critical Requirements

1. **Import Path Setup** (REQUIRED):
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent.parent))
   ```
   This must appear before any `cewe_layout` imports.

2. **Virtual Environment**: Always activate `.env/bin/activate` before running.

3. **Module Paths**: Use correct import paths:
   - ✅ `from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path`
   - ❌ `from cewe_layout.mcf_parser import parse_mcf_file`
   
   If unsure, check the actual file structure in `cewe_layout/`.

4. **Executable Bit**: Make test scripts executable:
   ```bash
   chmod +x tests/test_name.py
   ```

5. **Shebang**: Include `#!/usr/bin/env python3` as the first line.

## Working with MCF Files

### Parsing MCF Files (Two-Step Process)

```python
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info

# Step 1: Parse XML
root = parse_mcf_from_path("path/to/album.xmcf")

# Step 2: Extract pages (returns CEWEPhotobook object)
photobook = extract_pages_info(root)

# Step 3: Access pages using the Photobook API
for page_idx in range(photobook.get_page_count()):
    page = photobook.get_page(page_idx)
    if page is None:
        continue  # Inside covers may be None if they don't exist
    
    pageno = page.get_page_number()
    images = page.get_images()
    text_blocks = page.get_text_blocks()
    page_info = page.get_page_info()  # Legacy dict format
```

### Path Resolution

`parse_mcf_from_path()` handles both `.mcf` files and `.xmcf` directories:

```python
# All of these work:
parse_mcf_from_path("../Test-album.xmcf")  # Directory
parse_mcf_from_path("../Test-album.xmcf/data.mcf")  # File directly
parse_mcf_from_path("some-album.mcf")  # MCF file
```

## Test Data Paths

### Use Relative Paths from Script Location

```python
script_dir = Path(__file__).parent
default_album = script_dir.parent.parent / "2009-2010-album.xmcf"
```

This works regardless of where the script is run from.

### Standard Test Albums

Available test albums (in workspace root):
- `2009-2010-album.xmcf` - Regular photobook
- `Test-album.xmcf` - Small test album
- `Abueli-calendar.xmcf` - Calendar format

## Installing Dependencies

If your test needs additional packages:

```bash
cd /path/to/
source .env/bin/activate
pip install package-name
```

Document any special dependencies in your test's docstring.

## Debugging Import Errors

If you get `ModuleNotFoundError`:

1. **Check virtual environment is activated**:
   ```bash
   which python  # Should show .env/bin/python
   ```

2. **Verify import path setup**:
   ```python
   import sys
   print(sys.path)  # Should include parent directory
   ```

3. **Check actual module structure**:
   ```bash
   find cewe-layout/cewe_layout -name "*.py" | grep the_module
   ```

4. **Verify function exists**:
   ```bash
   grep "^def function_name" cewe-layout/cewe_layout/path/to/module.py
   ```

## Example: Complete Test Script

See `tests/test_tkhtmlview.py` for a complete working example that demonstrates:
- Proper import setup
- Command-line argument handling
- Path resolution
- MCF parsing
- Error handling
- GUI integration (optional)

## Running All Tests

From the cewe-layout directory:

```bash
cd cewe-layout
source ../.env/bin/activate
python runAllTests.py
```

This sets `IGNORELOCALFONTS` and calls `pytest` on all test files.

## Summary Checklist

When creating a new test:

- [ ] Add shebang: `#!/usr/bin/env python3`
- [ ] Add import path setup before cewe_layout imports
- [ ] Use correct module paths (check with `find` or file browser)
- [ ] Make executable: `chmod +x tests/test_name.py`
- [ ] Test from workspace root: `source .env/bin/activate && python cewe-layout/tests/test_name.py`
- [ ] Document special dependencies in docstring
- [ ] Use relative paths from `Path(__file__).parent`

Following these guidelines will help tests work **first time** instead of requiring 11 tries! 🎯
