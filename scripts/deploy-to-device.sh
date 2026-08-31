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
# on the device (set DECK_SUDO_PASS to the sudo password). The plugin name may
# contain spaces — it is quoted throughout.
#
set -euo pipefail

IP="${1:?usage: deploy-to-device.sh <device-ip> [plugin-name]}"
PLUGIN="${2:-Panel de Control}"
HOST="deck@${IP}"
SUDO_PASS="${DECK_SUDO_PASS:?set DECK_SUDO_PASS to the device sudo password}"

case "$PLUGIN" in
  ""|.|..|*/*) echo "invalid plugin name" >&2; exit 1 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Building frontend"
pnpm test:fe tests/pluginPayload.test.ts tests/themeBundledPin.test.ts tests/themeBundledCopy.test.ts tests/galleryPackage.test.ts
pnpm build

echo "==> Packaging plugin runtime"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TARBALL="$WORK/plugin.tgz"
PLUGIN_STAGE="$WORK/plugin"
node scripts/copy-plugin-payload.mjs . "$PLUGIN_STAGE"
node scripts/copy-bundled-theme.mjs themes/bundled/hooandee-gallery/0.7.8 "$PLUGIN_STAGE/theme-packages"
# --no-xattrs avoids the macOS AppleDouble (._*) droppings on the device.
COPYFILE_DISABLE=1 tar --no-xattrs \
  -czf "$TARBALL" -C "$PLUGIN_STAGE" .

echo "==> Copying to ${HOST}"
scp -q "$TARBALL" "${HOST}:/tmp/pdc-plugin.tgz"
scp -q scripts/sync-plugin-payload.sh "${HOST}:/tmp/pdc-sync-plugin-payload.sh"

echo "==> Installing into ~/homebrew/plugins/${PLUGIN} and restarting loader"
ssh "$HOST" "PLUGIN=$(printf %q "$PLUGIN") SUDO_PASS=$(printf %q "$SUDO_PASS") bash -s" <<'REMOTE'
set -euo pipefail
PLUGIN_ROOT="/home/deck/homebrew/plugins"
DEST="${PLUGIN_ROOT}/${PLUGIN}"
STAGE="$(mktemp -d)"
tar -xzf /tmp/pdc-plugin.tgz -C "$STAGE"
sudo() { command sudo -S "$@" <<<"$SUDO_PASS"; }
sudo mkdir -p "$DEST"
sudo bash /tmp/pdc-sync-plugin-payload.sh "$STAGE" "$DEST" "$PLUGIN_ROOT"
sudo chown -R root:root "$DEST"
sudo chmod 755 "$DEST"
rm -rf "$STAGE" /tmp/pdc-plugin.tgz /tmp/pdc-sync-plugin-payload.sh
sudo systemctl restart plugin_loader
echo "installed into $DEST"
REMOTE

echo "==> Done. plugin_loader restarted on ${IP}"
