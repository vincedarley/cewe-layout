# QLayout Build System

This directory contains cross-platform build configurations for packaging QLayout as standalone executables for macOS, Windows, and Linux.

## Quick Start

### macOS

```bash
# Build .app bundle
./build/macos/build.sh

# Test the app
open build/macos/QLayout.app

# Create DMG installer (optional)
./build/macos/create-dmg.sh
```

Output: `build/macos/QLayout.app` or `QLayout-0.1.0.dmg`

### Windows

```bash
# Build .exe
build\windows\build.bat

# Test
build\windows\qlayout.exe
```

Output: `build\windows\qlayout.exe`

### Linux

```bash
# Build directory structure
./build/linux/build.sh

# Test
./build/linux/qlayout/qlayout

# Create AppImage (optional)
linuxdeploy-x86_64.AppImage --appdir=build/linux/qlayout --output=appimage
```

Output: `build/linux/qlayout/qlayout` or `qlayout-x86_64.AppImage`

## Build Requirements

All platforms require:
- Python 3.9+
- PyInstaller: `pip install pyinstaller`

Platform-specific:
- **macOS**: Xcode Command Line Tools (for code signing/notarization)
- **Windows**: Optional InnoSetup for installer creation
- **Linux**: Optional linuxdeploy for AppImage creation

## Icons

**Before building**, generate platform-specific icon files from your source icon.

### Icon Setup

1. Place your 1024×1024 PNG icon at `build/icon-source.png`
2. Generate platform-specific formats:
   ```bash
   python build/convert_icon.py
   ```

This creates:
- **macOS**: `build/macos/qlayout.icns` (ICNS format)
- **Windows**: `build/windows/qlayout.ico` (ICO format with multiple sizes)
- **Linux**: `build/linux/qlayout.png` (512×512 PNG)

**Note**: Icon files are not tracked in git. Regenerate them after updating `icon-source.png`.

## Versioning

**Single Source of Truth**: `cewe_layout/__init__.py`

To update the version:
1. Edit `__version__` in `cewe_layout/__init__.py` (e.g., `'0.2.0'`)
2. The version will automatically propagate to:
   - macOS app Info.plist (CFBundleVersion, CFBundleShortVersionString)
   - DMG filename (e.g., `QLayout-0.2.0.dmg`)
   - Package metadata

Use [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

## Configuration

### PyInstaller Spec File

Main spec file: `build/QLayout.spec`

Edit this file to:
- Add or remove hidden imports
- Include additional data files (docs, assets, etc.)
- Change bundle identifier (currently `com.vince.qlayout`)
- Modify executable behavior

**Note**: Version is read automatically from `cewe_layout/__init__.py`

## Distribution

### macOS

For distribution outside the App Store, you need to:

1. **Code sign** the app:
   ```bash
   codesign --deep --force --verify --verbose --sign 'Developer ID Application' build/macos/QLayout.app
   ```

2. **Notarize** the app (required for macOS 10.15+):
   ```bash
   # Get version from package
   VERSION=$(grep -E "^__version__ = " cewe_layout/__init__.py | sed -E "s/__version__ = '(.*)'/\1/")
   xcrun notarytool submit QLayout-${VERSION}.dmg --apple-id your-email@example.com --team-id XXXXXXXXXX
   ```

3. **Staple** the notarization:
   ```bash
   xcrun stapler staple QLayout-${VERSION}.dmg
   ```

### Windows

Create an installer with InnoSetup:
1. Download InnoSetup
2. Create `build/windows/QLayout-installer.iss` (example below)
3. Build: `iscc build/windows/QLayout-installer.iss`

Example InnoSetup script:
```ini
[Setup]
AppName=QLayout
AppVersion=0.1.0
DefaultDirName={pf}\QLayout
OutputDir=dist
OutputBaseFilename=QLayout-0.1.0-Setup

[Files]
Source: "build/windows/qlayout.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commonprograms}\QLayout"; Filename: "{app}\qlayout.exe"
```

### Linux

Most Linux users prefer package managers. Options:
- **Snap**: `snapcraft` (create `snap/snapcraft.yaml`)
- **AppImage**: `linuxdeploy` script (handles app dependencies automatically)
- **Flatpak**: For GNOME/KDE distribution

## Troubleshooting

### "Icon file not found"
Create a placeholder icon or download from `build/<platform>/` directory. See Icons section above.

### PyInstaller build errors
- Ensure all imports are in `cewe_layout/__init__.py` or spec's `hiddenimports`
- Check that data files are included in spec's `datas` list
- Use `--debug=imports` flag to see what PyInstaller is finding

### macOS app won't launch
- Check logs: `log show --predicate 'process == "QLayout"' --last 1h`
- Verify code signature: `codesign -v build/macos/QLayout.app`
- Remove quarantine attribute: `xattr -d com.apple.quarantine build/macos/QLayout.app`

### Windows EXE won't run
- Check for missing DLLs: Use Dependency Walker
- Run from command line to see error messages: `build\windows\qlayout.exe`
- Ensure Python runtime libraries are bundled

## Development

During development, use:

```bash
# Run from source (no build needed)
python run_qlayout.py --cewe path/to/album.xmcf
```

To test the bundled version:

```bash
# macOS
open build/macos/QLayout.app

# Windows
build\windows\qlayout.exe

# Linux
./build/linux/qlayout/qlayout
```

## Future Enhancements

- [ ] Automated GitHub Actions builds for all platforms
- [ ] Auto-updating framework (Sparkle for macOS, WinSparkle for Windows)
- [ ] Cloud distribution (S3, GitHub Releases)
- [ ] CI/CD pipeline for automated notarization
- [ ] Language/localization support

## References

- [PyInstaller Docs](https://pyinstaller.org/)
- [macOS Code Signing](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [Windows Installer Creation](https://www.innosetup.com/)
- [Linux AppImage](https://appimage.org/)
