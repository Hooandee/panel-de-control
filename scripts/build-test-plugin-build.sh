#!/usr/bin/env bash
set -euo pipefail

outputDir="${1:-.}"
pnpm build                               # must produce dist/index.js
STAGING_DIR=$(mktemp -d)
node scripts/copy-plugin-payload.mjs . "$STAGING_DIR/Panel de Control"
(cd "$STAGING_DIR" && zip -r "Panel de Control.zip" "Panel de Control")
mv "$STAGING_DIR/Panel de Control.zip" "$outputDir/Panel de Control.zip"