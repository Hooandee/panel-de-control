#!/usr/bin/env bash
set -euo pipefail

root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
api="https://api.github.com/repos/ShadowBlip/InputPlumber/releases/latest"

for tool in cargo curl git patch python3; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing required tool: $tool" >&2
    exit 1
  }
done

latest_tag="$(
  curl --fail --silent --show-error --location "$api" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
)"
if [[ ! "$latest_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "invalid upstream release tag: $latest_tag" >&2
  exit 1
fi
latest_version="${latest_tag#v}"
if python3 "$root/scripts/inputplumber-manifest.py" \
  "$root" "$latest_version" >/dev/null 2>&1; then
  echo "already_declared version=$latest_version"
  exit 0
fi

declared="$(python3 "$root/scripts/inputplumber-manifest.py" "$root" all)"
IFS=$'\t' read -r base_version base_commit patch_path artifact checksum provenance \
  <<< "$declared"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone --branch "$latest_tag" --depth 1 \
  https://github.com/ShadowBlip/InputPlumber.git "$work/InputPlumber"
if ! patch -d "$work/InputPlumber" --forward --batch -p1 \
  < "$root/$patch_path"; then
  echo "patch_conflict version=$latest_version base=$base_version" >&2
  exit 20
fi
if ! cargo test \
  --manifest-path "$work/InputPlumber/Cargo.toml" \
  drivers::rog_ally::haptics_test; then
  echo "tests_failed version=$latest_version base=$base_version" >&2
  exit 21
fi
if ! cargo build \
  --release \
  --bin inputplumber \
  --manifest-path "$work/InputPlumber/Cargo.toml"; then
  echo "build_failed version=$latest_version base=$base_version" >&2
  exit 22
fi
echo "candidate_builds version=$latest_version base=$base_version"
exit 10
