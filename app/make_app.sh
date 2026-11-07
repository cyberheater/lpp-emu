#!/bin/zsh
# Builds "LPP MK3 Emulator.app" in lpp-emu/app/build/.
#   ./make_app.sh             bundle Renode inside the app (self-contained, ~190 MB)
#   ./make_app.sh --no-renode use ~/Applications/Renode.app at run time (small, for development)
set -euo pipefail
cd "${0:A:h}"
APP="build/LPP MK3 Emulator.app"
RENODE_SRC="$HOME/Applications/Renode.app"

swift build -c release
BIN="$(swift build -c release --show-bin-path)/LPPEmu"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/platform"
cp "$BIN" "$APP/Contents/MacOS/LPPEmu"
for f in lppmk3.repl stm32f745_base.repl STM32_TimerLP.cs STM32DMA_LP.cs LPPM0.cs LPPOTGFS.cs LPPDIN.cs LPPSpiFlash.cs; do
  cp "../renode/$f" "$APP/Contents/Resources/platform/"
done

if [[ "${1:-}" != "--no-renode" ]]; then
  [[ -d "$RENODE_SRC" ]] || { echo "Renode not found at $RENODE_SRC"; exit 1; }
  ditto "$RENODE_SRC" "$APP/Contents/Resources/Renode.app"
fi

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>LPP MK3 Emulator</string>
  <key>CFBundleDisplayName</key><string>LPP MK3 Emulator</string>
  <key>CFBundleIdentifier</key><string>local.lppemu</string>
  <key>CFBundleExecutable</key><string>LPPEmu</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

# Ad-hoc sign the app's own executable; the nested Renode.app keeps its own signature.
codesign --force --sign - "$APP/Contents/MacOS/LPPEmu"
codesign --force --sign - "$APP" 2>/dev/null || true
du -sh "$APP"
echo "built: $PWD/$APP"
