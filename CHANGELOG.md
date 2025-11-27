# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2025-11-27

### Added

- Initial release of `cewe-layout`.
- Parser for CEWE `.mcf` / `.xmcf` photobook XML files.
- Tkinter GUI viewer to browse pages and inspect photo slot layouts.
- Integration with collage-generator for automatic layout generation.
- Per-photo weight adjustment UI for layout tuning.
- Diagnostic thumbnail button for troubleshooting image loading.
- OpenCV fallback for image loading when Pillow fails.
- Layout history (undo/back) and original layout restoration.
- Pluggable layout algorithm abstraction for future algorithm variants.

### Technical Notes

- Handles two-page spreads correctly by splitting areas by horizontal center.
- Supports both relative and absolute image path resolution.
- Graceful fallback for older Pillow versions (ImageOps.exif_transpose).
