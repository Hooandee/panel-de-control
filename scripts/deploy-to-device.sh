#!/usr/bin/env bash
#
# Deploy the built plugin to a Decky device over SSH.
#
#   scripts/deploy-to-device.sh <device-ip> [plugin-name]
#
# Builds the frontend, packages the plugin runtime, copies it to the device and
# installs it into ~/homebrew/plugins/<plugin-name>, then restarts the loader.
#
# Requirements: key-based SSH as deck@<device-ip>; passwordless or password sudo
# on the device (set DECK_SUDO_PASS, default "deck"). The plugin name may contain
# spaces — it is quoted throughout.
#
set -euo pipefail

IP="${1:?usage: deploy-to-device.sh <device-ip> [plugin-name]}"
PLUGIN="${2:-Panel de Control}"
HOST="deck@${IP}"
SUDO_PASS="${DECK_SUDO_PASS:-deck}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Building frontend"
pnpm build

echo "==> Packaging plugin runtime"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TARBALL="$WORK/plugin.tgz"
# --no-xattrs avoids the macOS AppleDouble (._*) droppings on the device.
tar --no-xattrs \
  --exclude='__pycache__' --exclude='*.pyc' \
  -czf "$TARBALL" \
  dist main.py py_modules plugin.json package.json assets LICENSE README.md

echo "==> Copying to ${HOST}"
scp -q "$TARBALL" "${HOST}:/tmp/pdc-plugin.tgz"

echo "==> Installing into ~/homebrew/plugins/${PLUGIN} and restarting loader"
ssh "$HOST" "PLUGIN=$(printf %q "$PLUGIN") SUDO_PASS=$(printf %q "$SUDO_PASS") bash -s" <<'REMOTE'
set -euo pipefail
DEST="/home/deck/homebrew/plugins/${PLUGIN}"
STAGE="$(mktemp -d)"
tar -xzf /tmp/pdc-plugin.tgz -C "$STAGE"
sudo() { command sudo -S "$@" <<<"$SUDO_PASS"; }
sudo mkdir -p "$DEST"
sudo rsync -a --exclude='__pycache__' "$STAGE"/ "$DEST"/
sudo chown -R root:root "$DEST"
rm -rf "$STAGE" /tmp/pdc-plugin.tgz
sudo systemctl restart plugin_loader
echo "installed into $DEST"
REMOTE

echo "==> Done. plugin_loader restarted on ${IP}"
