#!/usr/bin/env bash
set -euo pipefail

VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
ZIP="echonote-v${VERSION}.zip"

echo "Building $ZIP ..."
git archive --format=zip --prefix=echonote/ HEAD -o "$ZIP"
echo "Done: $ZIP"
echo ""
echo "To release:"
echo "  gh release create v${VERSION} $ZIP --title \"v${VERSION}\" --notes-file RELEASE_NOTES.md"
