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

required=(
  dist main.py plugin.json package.json README.md README.en.md LICENSE
  THIRD_PARTY_NOTICES.md py_modules assets bin
  assets/inputplumber/README.md
  assets/inputplumber/compatibility.json
  scripts/build-inputplumber-xbox-hd.sh
  scripts/inputplumber-manifest.py
  scripts/verify-inputplumber-xbox-hd.sh
)
for relative in "${required[@]}"; do
  test -e "$root/$relative" || {
    echo "missing package input: $relative" >&2
    exit 1
  }
done
entries="$(python3 "$root/scripts/inputplumber-manifest.py" "$root" all)"
while IFS=$'\t' read -r version commit patch_path artifact checksum provenance; do
  for relative in "$patch_path" "$artifact" "$checksum" "$provenance"; do
    test -e "$root/$relative" || {
      echo "missing package input for InputPlumber $version: $relative" >&2
      exit 1
    }
  done
done <<< "$entries"
bash "$root/scripts/verify-inputplumber-xbox-hd.sh" "$root" all

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
cp "$root/scripts/inputplumber-manifest.py" "$staging/$plugin_name/scripts"
cp "$root/scripts/verify-inputplumber-xbox-hd.sh" "$staging/$plugin_name/scripts"
rm -f "$staging/$plugin_name/dist/"*.map
find "$staging/$plugin_name" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$staging/$plugin_name" -type f -name '*.pyc' -delete
rm -f "$output"
(cd "$staging" && zip -qr "$output" "$plugin_name")
