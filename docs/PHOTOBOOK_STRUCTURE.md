# CEWE Photobook Structure

## Overview

CEWE photobooks use a **two-page spread** layout system where pages are not individual sheets but rather spreads containing left and right pages side-by-side.

## Page Numbering and Types

### Standard Photobook Structure

A typical CEWE photobook has the following structure:

| MCF Order | pagenr | type | Description | PDF Mapping | UI Code
|-----------|--------|------|-------------|-------------|
| 1st | 0 | `fullcover` or `FULLCOVER` | Back cover (left side of spread) | N/A (part of cover spread) | Page "B"
| 2nd | 0 | `spine` | Spine of book | N/A (part of cover spread) |
| 3rd | 0 | `fullcover` or `FULLCOVER` | Front cover (right side of spread) | **PDF Page 1** | Page "F"
| 4th | 0 | `emptypage` or `EMPTY` | Inside front cover (blank page) | **Not in PDF** | Page 0
| 5th | 1 | `normalpage` | First content page (right side) | **PDF Page 2** | Page 1...
| 6th | 2 | `normalpage` | Second content page (left side) | **PDF Page 3** |
| ... | ... | `normalpage` | Content pages | **PDF Pages 4...N-1** |
| Last-1 | N-2 | `normalpage` | Last content page | **PDF Page N-1** |
| Last | 0 | `emptypage` or `EMPTY` | Inside back cover (blank page) | **Not in PDF** | Page N-1

**Notes**: 
- The back cover fullcover page (1st in list) contains both back cover AND front cover areas positioned on the SAME spread. The backcover is the left side of the spread and the front cover is the right side of the same spread.
- The 4th "0" empty page (just before page 1) is where the contents of page 1 actually goes
- In xml, using the usual x-offset is applied to the contents of any odd-numbered pagenr (and the front cover) - i.e. to all of the right-side pages - this is what makes that contents appear on the right side - simply the fact that their x-coordinates are >= half the size of the spread.
- Finally since pages have two sides (!), the last page N-1 (inside back cover) here MUST be an odd number. Our spreads are 0 & 1, 2 & 3, ...., N-2 & N-1. However pagenr="N-1" will not appear in the XML, since pagenr="0" is used for that last right hand side of the spread.

### Key Points

1. **Five `pagenr="0"` pages**: There are 5 pages with `pagenr="0"` in total:
   - 3 before `pagenr="1"` (back cover, spine, front cover, inside front)
   - 1 after the last numbered page (inside back cover)

2. **Only one fullcover has content**: The fullcover page with `pagenr="0"` that contains `<area>` elements is the one with actual cover content

3. **Emptypage distinction**:
   - **Inside front cover** (4th page): Has `pagenr="0"`, `type="emptypage"`, and may contain `<area>` elements or `<background alignment="1">. In particular the content of page 1 is actually inside this
   page in the xml, but offset by the usual x-offset.
   - **Inside back cover** (last page): Has `pagenr="0"`, `type="emptypage"`, no `<area>` elements or has `<background alignment="3">`

## Spread Layout System

### Bundlesize

The `<bundlesize>` element defines the dimensions of a **two-page spread**:
- **Width**: Double the width of a single page
- **Height**: Height of a single page

Example for a 20cm × 15cm page size (in MCF units where 1mm = 10 units):
```xml
<bundlesize width="4000" height="1500"/>
```
This represents a spread of 40cm wide × 15cm tall (two 20cm pages side-by-side).

### Positioning Within Spreads

Content is positioned within the spread using x-offsets:

- **Left pages** (even page numbers: 2, 4, 6...): `x_offset = 0`
- **Right pages** (odd page numbers: 1, 3, 5...): `x_offset = single_page_width`

Special cases:
- **Front cover** (pagenr=0, type=fullcover): `x_offset = single_page_width` (right side)
- **Back cover** (pagenr=0, type=fullcover): `x_offset = 0` (left side, on same spread element)

## PDF to CEWE Mapping

When converting from PDF photobooks to CEWE MCF format:

1. **PDF Page 1** → Front cover (pagenr=0, type=fullcover)
2. **PDF Page 2** → First content (pagenr=1, type=normalpage) - RIGHT side
3. **PDF Page 3** → Second content (pagenr=2, type=normalpage) - LEFT side
4. **PDF Page N** → Back cover (pagenr=0, type=fullcover) - on separate spread OR combined with front cover

### Coordinate Conversion

PDF uses points (72 points = 1 inch), MCF uses 0.1mm units:
- **Conversion factor**: 1 point = 3.52778 MCF units
- **Formula**: `mcf_units = pdf_points × 3.52778`

When positioning content:
```
mcf_left = (pdf_left × 3.52778) + x_offset
mcf_top = pdf_top × 3.52778
mcf_width = pdf_width × 3.52778
mcf_height = pdf_height × 3.52778
```

## Implementation Notes

### From cewe2pdf

The cewe2pdf tool (CEWE → PDF direction) handles special pages as follows:

1. **Page 0 (PDF output page 1)**: Renders front cover from the fullcover element
2. **Page 1 (PDF output page 2)**: Combines inside front cover emptypage + pagenr=1 normalpage
3. **Pages 2...N-2**: Normal content pages (pagenr=2 to pagenr=N-2)
4. **Last page**: Combines last normalpage + inside back cover emptypage

### For pdf2cewe (Reverse Direction)

When generating MCF from PDF:

1. Create front cover as `pagenr="0" type="fullcover"`
2. Create inside front cover as `pagenr="0" type="emptypage"` (no content)
3. Map PDF pages 2...N-1 to CEWE `pagenr="1"` through `pagenr="N-2"` with `type="normalpage"`
4. Create inside back cover as `pagenr="0" type="emptypage"` (no content)
5. Optionally create back cover from PDF page N as part of fullcover spread

## References

- Test-album.xmcf: Example of complete photobook structure
- cewe2pdf.py: Lines 1690-1775 contain page type detection logic
- cewe2pdf.py: Line 121 defines EmptyPage type
- cewe2pdf.py: Lines 203, 214 show handling of inside cover pages
