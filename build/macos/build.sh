#!/bin/bash
# Build script for QLayout macOS app

set -e

echo "🔨 Building QLayout for macOS..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Check if icon exists
if [ ! -f "build/macos/qlayout.icns" ]; then
    echo "⚠️  Icon not found at build/macos/qlayout.icns"
    echo "   Using default Tkinter icon for now. You can replace this later."
    echo "   To create an icon: convert icon.png -define icon:auto-resize=64,32,16 qlayout.ico"
    echo ""
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/__pycache__ dist/ build/macos/QLayout.app 2>/dev/null || true

# Run PyInstaller
echo "📦 Running PyInstaller..."
pyinstaller build/QLayout.spec

# Move output to build/macos
if [ -d "dist/QLayout.app" ]; then
    echo "📁 Moving app to build/macos/..."
    mkdir -p build/macos
    rm -rf build/macos/QLayout.app 2>/dev/null || true
    mv dist/QLayout.app build/macos/
fi

if [ -d "build/macos/QLayout.app" ]; then
    echo "✅ Build successful!"
    echo ""
    echo "📍 Output: build/macos/QLayout.app"
    echo ""
    echo "Next steps:"
    echo "  1. Test: open build/macos/QLayout.app"
    echo "  2. Create DMG: ./build/macos/create-dmg.sh"
    echo "  3. Sign app (if distributing): codesign --deep --force --verify --verbose --sign 'Developer ID Application' build/macos/QLayout.app"
else
    echo "❌ Build failed. Check output above for errors."
    exit 1
fi
