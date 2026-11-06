#!/bin/zsh -f
# Double-click on macOS to package VanishCam.app into a drag-and-drop VanishCam_macOS.dmg installer
set -e
DIR="${0:A:h}"
cd "$DIR"

APP_NAME="VanishCam"
DMG_NAME="VanishCam_macOS.dmg"
STAGING="$DIR/.dmg_staging"

echo "=== VanishCam macOS DMG Packager ==="
rm -rf "$STAGING" "$DIR/$DMG_NAME"
mkdir -p "$STAGING"

# If a local .venv exists next to this script, copy it into VanishCam.app/Contents/Resources/.venv
# so the app works immediately offline
if [[ -d "$DIR/.venv" && ! -d "$DIR/VanishCam.app/Contents/Resources/.venv" ]]; then
    echo "Bundling existing .venv into VanishCam.app..."
    cp -R "$DIR/.venv" "$DIR/VanishCam.app/Contents/Resources/.venv"
fi

cp -R "$DIR/VanishCam.app" "$STAGING/VanishCam.app"
ln -s /Applications "$STAGING/Applications"

# Remove quarantine attributes and ad-hoc sign so macOS Gatekeeper allows double-click launch
xattr -cr "$STAGING/VanishCam.app" 2>/dev/null || true
codesign --force --deep --sign - "$STAGING/VanishCam.app" 2>/dev/null || true

echo "Building $DMG_NAME via hdiutil..."
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGING" -ov -format UDZO "$DIR/$DMG_NAME"
rm -rf "$STAGING"

echo ""
echo "Done! Created: $DIR/$DMG_NAME"
open -R "$DIR/$DMG_NAME"
