#!/bin/bash
# Build script for QLayout Linux AppImage

set -e

echo "🔨 Building QLayout for Linux..."

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# Check for linuxdeploy (optional, for AppImage)
if ! command -v linuxdeploy &> /dev/null; then
    echo "⚠️  linuxdeploy not found. AppImage creation will be skipped."
    echo "   Install with: https://github.com/linuxdeploy/linuxdeploy"
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/__pycache__ dist/ build/linux/qlayout build/linux/qlayout.spec 2>/dev/null || true

# Run PyInstaller
echo "📦 Running PyInstaller..."
pyinstaller --onedir \
    --name=qlayout \
    --distpath=build/linux \
    --workpath=build/__pycache__ \
    --icon=build/linux/qlayout.png \
    --hidden-import=cewe_layout \
    --hidden-import=cewe_layout.mcf_io \
    --hidden-import=cewe_layout.algorithms \
    --hidden-import=cewe_layout.utils \
    --hidden-import=cewe_layout.book \
    run_qlayout.py

if [ -d "build/linux/qlayout" ]; then
    echo "✅ Build successful!"
    echo ""
    echo "📍 Output: build/linux/qlayout/"
    echo ""
    echo "Next steps:"
    echo "  1. Test: build/linux/qlayout/qlayout"
    echo "  2. Create AppImage (optional):"
    echo "     linuxdeploy-x86_64.AppImage --appdir=build/linux/qlayout --output=appimage"
    echo "  3. Or create Snap:"
    echo "     snapcraft"
else
    echo "❌ Build failed. Check output above for errors."
    exit 1
fi
