#!/usr/bin/env bash
set -euo pipefail

outdir="${1:-bin}"
selector="${2:-all}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for tool in cargo git patch python3 sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing required tool: $tool" >&2
    exit 1
  }
done

mkdir -p "$outdir"
entries="$(python3 "$root/scripts/inputplumber-manifest.py" "$root" "$selector")"
while IFS=$'\t' read -r version commit patch_path artifact checksum provenance; do
  work="$(mktemp -d)"
  git clone --filter=blob:none https://github.com/ShadowBlip/InputPlumber.git "$work/InputPlumber"
  git -C "$work/InputPlumber" checkout --detach "$commit"
  patch -d "$work/InputPlumber" --forward --batch -p1 < "$root/$patch_path"
  cargo test \
    --manifest-path "$work/InputPlumber/Cargo.toml" \
    drivers::rog_ally::haptics_test
  cargo build \
    --release \
    --bin inputplumber \
    --manifest-path "$work/InputPlumber/Cargo.toml"

  binary="$outdir/$(basename "$artifact")"
  checksum_path="$outdir/$(basename "$checksum")"
  provenance_path="$outdir/$(basename "$provenance")"
  cp "$work/InputPlumber/target/release/inputplumber" "$binary"
  chmod 0755 "$binary"
  sha256sum "$binary" | awk '{print $1}' > "$checksum_path"
  {
    echo "inputplumber_commit=$commit"
    echo "patch_sha256=$(sha256sum "$root/$patch_path" | awk '{print $1}')"
  } > "$provenance_path"
  rm -rf "$work"
done <<< "$entries"
