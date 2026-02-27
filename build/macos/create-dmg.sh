#!/bin/bash
# Create a DMG installer for QLayout on macOS

set -e

DMG_NAME="QLayout-0.1.0.dmg"
DMG_TITLE="QLayout"
SOURCE_FOLDER="build/macos/QLayout.app"
MOUNT_POINT="/Volumes/QLayout"

if [ ! -d "$SOURCE_FOLDER" ]; then
    echo "❌ QLayout.app not found at $SOURCE_FOLDER"
    echo "   Build the app first: ./build/macos/build.sh"
    exit 1
fi

echo "📀 Creating DMG installer..."

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

# Add background and icons
mkdir -p "$MOUNT_POINT"/.background
cp build/macos/dmg-background.png "$MOUNT_POINT"/.background/background.png 2>/dev/null || true

# Create symlink to /Applications
ln -sf /Applications "$MOUNT_POINT/Applications"

# Set window properties (if backgroundImageTiffData available)
echo "Setting DMG appearance..."
osascript << END
tell application "Finder"
    tell disk "$DMG_TITLE"
        open
        set current view of container window to icon view
        set arrangement of icon view of container window to not arranged
        set icon size of icon view of container window to 104
        set position of item "QLayout.app" of container window to {150, 100}
        set position of item "Applications" of container window to {350, 100}
        if exists file "background.png" of folder ".background" then
            set background picture of container window to file ".background:background.png"
        end if
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
END

# Detach
echo "Finalizing DMG..."
hdiutil detach "$MOUNT_POINT"

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
