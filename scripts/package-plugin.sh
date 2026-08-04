#!/usr/bin/env bash
set -euo pipefail

output="${1:?usage: package-plugin.sh <output.zip> [plugin-name]}"
plugin_name="${2:-Panel de Control}"
root="${PDC_PACKAGE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

case "$plugin_name" in
  ""|.|..|*/*)
    echo "invalid plugin name: $plugin_name" >&2
    exit 1
    ;;
esac
case "$output" in
  /*) ;;
  *) output="$PWD/$output" ;;
esac

binary="$root/bin/inputplumber-xbox-hd-v0.77.4"
checksum="$binary.sha256"
required=(
  dist main.py plugin.json package.json README.md README.en.md LICENSE
  THIRD_PARTY_NOTICES.md py_modules assets bin
  assets/inputplumber/README.md
  assets/inputplumber/v0.77.4-xbox-hd.patch
  scripts/build-inputplumber-xbox-hd.sh
  bin/inputplumber-xbox-hd-v0.77.4
  bin/inputplumber-xbox-hd-v0.77.4.sha256
)
for relative in "${required[@]}"; do
  test -e "$root/$relative" || {
    echo "missing package input: $relative" >&2
    exit 1
  }
done
test -x "$binary" || {
  echo "Xbox InputPlumber extension is not executable" >&2
  exit 1
}

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$binary" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$binary" | awk '{print $1}')"
else
  echo "missing SHA-256 tool" >&2
  exit 1
fi
expected="$(tr -d '[:space:]' < "$checksum")"
test "$actual" = "$expected" || {
  echo "Xbox InputPlumber extension checksum mismatch" >&2
  exit 1
}

staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/$plugin_name/scripts" "$(dirname "$output")"
cp -rL \
  "$root/dist" \
  "$root/main.py" \
  "$root/plugin.json" \
  "$root/package.json" \
  "$root/README.md" \
  "$root/README.en.md" \
  "$root/LICENSE" \
  "$root/THIRD_PARTY_NOTICES.md" \
  "$root/py_modules" \
  "$root/assets" \
  "$root/bin" \
  "$staging/$plugin_name"
cp "$root/scripts/build-inputplumber-xbox-hd.sh" "$staging/$plugin_name/scripts"
rm -f "$output"
(cd "$staging" && zip -qr "$output" "$plugin_name")
