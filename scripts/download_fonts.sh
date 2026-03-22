#!/usr/bin/env bash
# Download Google Fonts used for thumbnail text overlays.
# Run from the repository root: bash scripts/download_fonts.sh
#
# Fonts:
#   Bebas Neue Bold  — https://fonts.google.com/specimen/Bebas+Neue
#   Montserrat Extra Bold — https://fonts.google.com/specimen/Montserrat

set -euo pipefail

FONT_DIR="backend/assets/fonts"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$FONT_DIR"

echo "Downloading Bebas Neue..."
curl -fsSL -o "$TMP_DIR/bebas.zip" \
  "https://fonts.google.com/download?family=Bebas+Neue"
unzip -qo "$TMP_DIR/bebas.zip" -d "$TMP_DIR/bebas"
cp "$TMP_DIR/bebas/BebasNeue-Regular.ttf" "$FONT_DIR/BebasNeue-Bold.ttf"
echo "  -> $FONT_DIR/BebasNeue-Bold.ttf"

echo "Downloading Montserrat..."
curl -fsSL -o "$TMP_DIR/montserrat.zip" \
  "https://fonts.google.com/download?family=Montserrat"
unzip -qo "$TMP_DIR/montserrat.zip" -d "$TMP_DIR/montserrat"
# The zip contains static/ subdirectory with weight variants
EXTRABOLD=$(find "$TMP_DIR/montserrat" -name "Montserrat-ExtraBold.ttf" | head -1)
if [ -n "$EXTRABOLD" ]; then
  cp "$EXTRABOLD" "$FONT_DIR/Montserrat-ExtraBold.ttf"
  echo "  -> $FONT_DIR/Montserrat-ExtraBold.ttf"
else
  echo "  WARNING: Montserrat-ExtraBold.ttf not found in zip"
fi

echo "Done. Fonts installed to $FONT_DIR/"
ls -la "$FONT_DIR"/*.ttf
