#!/usr/bin/env bash
set -euo pipefail

PKG_URL="https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz"
EXPECTED_SHA="7461aefcd27c4ef0dd76f9ca5760f09466eb6b3f934432670c12132e7b3d6faa"
DEST="pdfjs-dist.tgz"

echo "Downloading pdfjs-dist..."
curl -sSL "$PKG_URL" -o "$DEST"

echo "Verifying SHA256..."
ACTUAL_SHA=$(sha256sum "$DEST" | cut -d' ' -f1)
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
    echo "SHA256 mismatch! Expected: $EXPECTED_SHA, got: $ACTUAL_SHA"
    exit 1
fi

echo "Installing pdfjs-dist..."
mkdir -p node_modules/pdfjs-dist
tar -xzf "$DEST" -C node_modules/pdfjs-dist --strip-components=1
rm -f "$DEST"
echo "pdfjs-dist installed successfully."
