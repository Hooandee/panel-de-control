#!/usr/bin/env bash

set -euo pipefail

host=""
ssh_user="deck"
package=""

usage() {
  echo "Usage: $0 --host HOST [--user USER] --package panel-de-control.zip" >&2
}

while (($#)); do
  case "$1" in
    --host)
      host="${2:-}"
      shift 2
      ;;
    --user)
      ssh_user="${2:-}"
      shift 2
      ;;
    --package)
      package="${2:-}"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$host" || -z "$ssh_user" || -z "$package" ]]; then
  usage
  exit 2
fi
if [[ ! "$host" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "Invalid SSH host: $host" >&2
  exit 2
fi
if [[ ! "$ssh_user" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Invalid SSH user: $ssh_user" >&2
  exit 2
fi
if [[ ! -f "$package" ]]; then
  echo "Package not found: $package" >&2
  exit 1
fi
if [[ "$(basename "$package")" != "panel-de-control.zip" ]]; then
  echo "Package must be named panel-de-control.zip" >&2
  exit 2
fi

destination=".local/share/opengamepadui/plugins/panel-de-control.zip"
remote="${ssh_user}@${host}"
scp_host="$host"
if [[ "$host" == *:* ]]; then
  scp_host="[$host]"
fi

ssh "$remote" "mkdir -p .local/share/opengamepadui/plugins"
scp "$package" "${ssh_user}@${scp_host}:${destination}"
echo "Installed panel-de-control.zip on ${ssh_user}@${host}"
