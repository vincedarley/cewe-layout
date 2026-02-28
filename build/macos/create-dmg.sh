#!/bin/bash
# Create a DMG installer for QLayout on macOS

set -e

# Extract version from cewe_layout/__init__.py
VERSION=$(grep -E "^__version__ = " cewe_layout/__init__.py | sed -E "s/__version__ = '(.*)'/\1/")
DMG_NAME="QLayout-${VERSION}.dmg"
DMG_TITLE="QLayout"
SOURCE_FOLDER="build/macos/QLayout.app"
MOUNT_POINT="/Volumes/QLayout"

if [ ! -d "$SOURCE_FOLDER" ]; then
    echo "❌ QLayout.app not found at $SOURCE_FOLDER"
    echo "   Build the app first: ./build/macos/build.sh"
    exit 1
fi

echo "📀 Creating DMG installer (version ${VERSION})..."

# Create temporary DMG (RW)
TEMP_DMG="build/macos/tmp-QLayout.dmg"
rm -f "$TEMP_DMG" 2>/dev/null || true

# Create RW DMG with room for metadata
hdiutil create -srcfolder "$SOURCE_FOLDER" \
    -volname "$DMG_TITLE" \
    -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" \
    -format UDRW \
    -size 500m \
    "$TEMP_DMG"

# Mount it
echo "Mounting DMG..."
hdiutil attach "$TEMP_DMG" -mountpoint "$MOUNT_POINT"

# Create symlink to /Applications
ln -sf /Applications "$MOUNT_POINT/Applications"

# Set window properties (optional - requires Terminal automation permission)
echo "Setting DMG appearance..."
if osascript << END 2>/dev/null
tell application "Finder"
    tell disk "$DMG_TITLE"
        open
        set current view of container window to icon view
        set arrangement of icon view of container window to not arranged
        set icon size of icon view of container window to 104
        set position of item "QLayout.app" of container window to {150, 100}
        set position of item "Applications" of container window to {350, 100}
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
END
then
    echo "✅ DMG appearance customized"
else
    echo "⚠️  Could not customize appearance (Terminal needs Automation permission for Finder)"
    echo "   DMG will still work, just with default appearance"
fi

# Give Finder time to finish
sleep 2

# Close any Finder windows showing the volume
osascript -e "tell application \"Finder\" to close every window whose target is disk \"$DMG_TITLE\"" 2>/dev/null || true

# Detach
echo "Finalizing DMG..."
sync  # Ensure all writes are flushed
if ! hdiutil detach "$MOUNT_POINT" 2>/dev/null; then
    echo "⚠️  Normal detach failed, trying force..."
    hdiutil detach "$MOUNT_POINT" -force
fi

# Remove old DMG if it exists
rm -f "$DMG_NAME" 2>/dev/null || true

# Convert to read-only
hdiutil convert "$TEMP_DMG" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$DMG_NAME"

rm "$TEMP_DMG"

echo "✅ DMG created: $DMG_NAME"
echo ""
echo "To distribute:"
echo "  1. Sign: codesign --verify --verbose $DMG_NAME"
echo "  2. Notarize: xcrun notarytool submit $DMG_NAME --apple-id email --team-id XXXXX"
