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

Each platform requires an app icon:

- **macOS**: `build/macos/qlayout.icns` (512×512, ICNS format)
- **Windows**: `build/windows/qlayout.ico` (256×256, ICO format)
- **Linux**: `build/linux/qlayout.png` (512×512, PNG format)

Placeholder icons currently exist. **Replace them with your custom icon before building for distribution.**

### Creating Icons

**From PNG source (1024×1024 recommended):**

```bash
# macOS:
pip install pillow
python3 -c "from PIL import Image; img = Image.open('icon.png'); img.save('build/macos/qlayout.icns')"

# Windows:
convert icon.png -define icon:auto-resize=256,128,96,64,48,32,16 build/windows/qlayout.ico

# Linux:
convert icon.png -resize 512x512 build/linux/qlayout.png
```

Or use online icon converters:
- macOS: https://image2icon.com/
- Windows: https://icoconvert.com/
- Linux: ImageMagick's `convert` command

## Configuration

### PyInstaller Spec File

Main spec file: `build/QLayout.spec`

Edit this file to:
- Add or remove hidden imports
- Include additional data files (docs, assets, etc.)
- Change bundle identifiers or version numbers
- Modify executable behavior

### Version Updates

Update version numbers in:
1. `build/QLayout.spec` - Bundle version
2. `build/macos/qlayout.icns` - Plist version (CFBundleVersion, CFBundleShortVersionString)
3. `build/macos/create-dmg.sh` - DMG filename
4. `cewe_layout/__init__.py` - Package version (if desired)

## Distribution

### macOS

For distribution outside the App Store, you need to:

1. **Code sign** the app:
   ```bash
   codesign --deep --force --verify --verbose --sign 'Developer ID Application' build/macos/QLayout.app
   ```

2. **Notarize** the app (required for macOS 10.15+):
   ```bash
   xcrun notarytool submit QLayout-0.1.0.dmg --apple-id your-email@example.com --team-id XXXXXXXXXX
   ```

3. **Staple** the notarization:
   ```bash
   xcrun stapler staple QLayout-0.1.0.dmg
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
