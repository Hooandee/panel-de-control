#!/usr/bin/env bash
set -euo pipefail

pnpm build                               # must produce dist/index.js
STAGING_DIR=$(mktemp -d)
node scripts/copy-plugin-payload.mjs . "$STAGING_DIR/Panel de Control"
sudo rm -rf "$HOME/homebrew/plugins/Panel de Control"
mv "$STAGING_DIR/Panel de Control" "$HOME/homebrew/plugins/Panel de Control"
sudo systemctl restart plugin_loader