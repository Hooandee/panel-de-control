#!/usr/bin/env bash
set -euo pipefail

SOURCE_INPUT="${1:?usage: sync-plugin-payload.sh <source> <destination>}"
DESTINATION_INPUT="${2:?usage: sync-plugin-payload.sh <source> <destination>}"

test -d "$SOURCE_INPUT"
test -d "$DESTINATION_INPUT"

SOURCE="$(cd "$SOURCE_INPUT" && pwd -P)"
DESTINATION="$(cd "$DESTINATION_INPUT" && pwd -P)"

test "$SOURCE" != "/"
test "$DESTINATION" != "/"
test "$SOURCE" != "$DESTINATION"
case "$SOURCE/" in "$DESTINATION/"*) exit 1 ;; esac
case "$DESTINATION/" in "$SOURCE/"*) exit 1 ;; esac

rsync -a --delete -- "$SOURCE/" "$DESTINATION/"
