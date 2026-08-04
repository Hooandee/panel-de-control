#!/usr/bin/env bash
set -euo pipefail

INPUTPLUMBER_COMMIT="${INPUTPLUMBER_COMMIT:-bb7424fd6fc097d123850950aaf1e6988f2093f3}"
outdir="${1:-bin}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for tool in cargo git patch sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing required tool: $tool" >&2
    exit 1
  }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --filter=blob:none https://github.com/ShadowBlip/InputPlumber.git "$work/InputPlumber"
git -C "$work/InputPlumber" checkout --detach "$INPUTPLUMBER_COMMIT"
patch -d "$work/InputPlumber" -p1 < "$root/assets/inputplumber/v0.77.4-xbox-hd.patch"
cargo test --manifest-path "$work/InputPlumber/Cargo.toml" drivers::rog_ally::haptics_test
cargo build --release --bin inputplumber --manifest-path "$work/InputPlumber/Cargo.toml"

mkdir -p "$outdir"
binary="$outdir/inputplumber-xbox-hd-v0.77.4"
cp "$work/InputPlumber/target/release/inputplumber" "$binary"
chmod 0755 "$binary"
sha256sum "$binary" | awk '{print $1}' > "$binary.sha256"
{
  echo "inputplumber_commit=$INPUTPLUMBER_COMMIT"
  echo "patch_sha256=$(sha256sum "$root/assets/inputplumber/v0.77.4-xbox-hd.patch" | awk '{print $1}')"
} > "$binary.provenance"
