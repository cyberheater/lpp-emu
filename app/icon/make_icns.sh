#!/bin/zsh
# Renders the app icon at every macOS size and packs AppIcon.icns (used by make_app.sh).
set -euo pipefail
cd "${0:A:h}"
tool=$(mktemp -d)/make_icon
swiftc -O make_icon.swift -o "$tool"
set=$(mktemp -d)/AppIcon.iconset
mkdir -p "$set"
for size in 16 32 128 256 512; do
  "$tool" "$set/icon_${size}x${size}.png" $size >/dev/null
  "$tool" "$set/icon_${size}x${size}@2x.png" $((size * 2)) >/dev/null
done
iconutil -c icns "$set" -o AppIcon.icns
"$tool" icon.png 1024 >/dev/null          # preview for the README
echo "built: $PWD/AppIcon.icns"
