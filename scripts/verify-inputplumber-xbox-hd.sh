#!/usr/bin/env bash
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
selector="${2:-all}"

if command -v sha256sum >/dev/null 2>&1; then
  hash() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
  hash() { shasum -a 256 "$1" | awk '{print $1}'; }
else
  echo "sha256sum or shasum is required" >&2
  exit 1
fi

entries="$(python3 "$root/scripts/inputplumber-manifest.py" "$root" "$selector")"
while IFS=$'\t' read -r version commit patch_path artifact checksum provenance; do
  binary="$root/$artifact"
  checksum_path="$root/$checksum"
  provenance_path="$root/$provenance"
  patch_file="$root/$patch_path"
  for path in "$binary" "$checksum_path" "$provenance_path" "$patch_file"; do
    test -f "$path" || {
      echo "missing Xbox InputPlumber $version artifact: $path" >&2
      exit 1
    }
  done
  test -x "$binary" || {
    echo "Xbox InputPlumber $version extension is not executable" >&2
    exit 1
  }
  test "$(hash "$binary")" = "$(tr -d '[:space:]' < "$checksum_path")" || {
    echo "Xbox InputPlumber $version checksum mismatch" >&2
    exit 1
  }
  expected="inputplumber_commit=$commit
patch_sha256=$(hash "$patch_file")"
  test "$(cat "$provenance_path")" = "$expected" || {
    echo "Xbox InputPlumber $version artifact is stale" >&2
    exit 1
  }
done <<< "$entries"
