#!/usr/bin/env bash
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
binary="$root/bin/inputplumber-xbox-hd-v0.77.4"
checksum="$binary.sha256"
provenance="$binary.provenance"
patch_file="$root/assets/inputplumber/v0.77.4-xbox-hd.patch"
commit="bb7424fd6fc097d123850950aaf1e6988f2093f3"

for path in "$binary" "$checksum" "$provenance" "$patch_file"; do
  test -f "$path" || {
    echo "missing Xbox InputPlumber artifact: $path" >&2
    exit 1
  }
done
test -x "$binary" || {
  echo "Xbox InputPlumber extension is not executable" >&2
  exit 1
}

if command -v sha256sum >/dev/null 2>&1; then
  hash() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
  hash() { shasum -a 256 "$1" | awk '{print $1}'; }
else
  echo "sha256sum or shasum is required" >&2
  exit 1
fi

test "$(hash "$binary")" = "$(tr -d '[:space:]' < "$checksum")" || {
  echo "Xbox InputPlumber checksum mismatch" >&2
  exit 1
}
expected="inputplumber_commit=$commit
patch_sha256=$(hash "$patch_file")"
test "$(cat "$provenance")" = "$expected" || {
  echo "Xbox InputPlumber artifact is stale for the current patch" >&2
  exit 1
}
