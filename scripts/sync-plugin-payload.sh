#!/usr/bin/env bash
set -euo pipefail

SOURCE_INPUT="${1:?usage: sync-plugin-payload.sh <source> <destination> <destination-root>}"
DESTINATION_INPUT="${2:?usage: sync-plugin-payload.sh <source> <destination> <destination-root>}"
DESTINATION_ROOT_INPUT="${3:?usage: sync-plugin-payload.sh <source> <destination> <destination-root>}"

test ! -L "$SOURCE_INPUT"
test ! -L "$DESTINATION_INPUT"
test ! -L "$DESTINATION_ROOT_INPUT"
test -d "$SOURCE_INPUT"
test -d "$DESTINATION_INPUT"
test -d "$DESTINATION_ROOT_INPUT"

SOURCE="$(cd "$SOURCE_INPUT" && pwd -P)"
DESTINATION="$(cd "$DESTINATION_INPUT" && pwd -P)"
DESTINATION_ROOT="$(cd "$DESTINATION_ROOT_INPUT" && pwd -P)"
DESTINATION_PARENT="$(cd "$(dirname "$DESTINATION_INPUT")" && pwd -P)"

test "$SOURCE" != "/"
test "$DESTINATION" != "/"
test "$DESTINATION_ROOT" != "/"
test "$SOURCE" != "$DESTINATION"
test "$DESTINATION_PARENT" = "$DESTINATION_ROOT"
test "$(dirname "$DESTINATION")" = "$DESTINATION_ROOT"
case "$SOURCE/" in "$DESTINATION/"*) exit 1 ;; esac
case "$DESTINATION/" in "$SOURCE/"*) exit 1 ;; esac

RSYNC_ARGS=(-a --delete)
if test ! -e "$SOURCE/bin/ryzenadj" \
  && test -f "$DESTINATION/bin/ryzenadj" \
  && test ! -L "$DESTINATION/bin/ryzenadj" \
  && test -x "$DESTINATION/bin/ryzenadj"; then
  RSYNC_ARGS+=(--filter="protect /bin/ryzenadj")
  if test ! -e "$SOURCE/bin/ryzenadj-LICENSE.txt" \
    && test -f "$DESTINATION/bin/ryzenadj-LICENSE.txt" \
    && test ! -L "$DESTINATION/bin/ryzenadj-LICENSE.txt"; then
    RSYNC_ARGS+=(--filter="protect /bin/ryzenadj-LICENSE.txt")
  fi
fi

rsync "${RSYNC_ARGS[@]}" -- "$SOURCE/" "$DESTINATION/"
