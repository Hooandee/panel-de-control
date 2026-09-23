#!/usr/bin/env bash
#
# Install the latest Windows CI build of the Game Bar widget on a Windows device over SSH.
#
#   scripts/deploy-windows-device.sh [--dry-run] [--run-id ID] [--branch NAME] <user@host>
#
# The host can also come from PDC_WINDOWS_HOST. The device needs OpenSSH Server with key-based
# login and Developer Mode enabled: the CI package is unsigned, so it is registered from its
# unpacked layout instead of installed as a signed package.
#
set -euo pipefail

usage() {
  echo "usage: deploy-windows-device.sh [--dry-run] [--run-id ID] [--branch NAME] <user@host>" >&2
  exit 2
}

DRY_RUN=0
RUN_ID=""
BRANCH=""
HOST="${PDC_WINDOWS_HOST:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --run-id) shift; RUN_ID="${1:-}"; [ -n "$RUN_ID" ] || usage ;;
    --branch) shift; BRANCH="${1:-}"; [ -n "$BRANCH" ] || usage ;;
    -h|--help) usage ;;
    -*) echo "unknown option: $1" >&2; usage ;;
    *) HOST="$1" ;;
  esac
  shift
done

[ -n "$HOST" ] || usage
case "$HOST" in
  *@*) ;;
  *) echo "host must be user@host" >&2; exit 2 ;;
esac
if [ -n "$RUN_ID" ] && [[ ! "$RUN_ID" =~ ^[0-9]+$ ]]; then
  echo "run id must be numeric" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="PanelDeControl.Windows"
ARTIFACT="panel-de-control-gamebar-x64"
REMOTE_STAGE="pdc-deploy"

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

REMOTE_SCRIPT=$(cat <<POWERSHELL
\$ErrorActionPreference = 'Stop'
\$unlock = Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModelUnlock' -ErrorAction SilentlyContinue
if (-not \$unlock -or \$unlock.AllowDevelopmentWithoutDevLicense -ne 1) {
  throw 'Developer Mode is off: enable it in Settings > System > For developers.'
}
\$stage = Join-Path \$HOME '${REMOTE_STAGE}'
\$root = Join-Path \$env:LOCALAPPDATA 'PanelDeControl'
\$layout = Join-Path \$root 'dev-layout'
\$incoming = Join-Path \$root 'dev-layout-incoming'
foreach (\$dependency in Get-ChildItem -Path (Join-Path \$stage 'Dependencies') -File -ErrorAction SilentlyContinue) {
  try {
    Add-AppxPackage -Path \$dependency.FullName
  } catch {
    Write-Warning "Dependency \$(\$dependency.Name) not installed: \$(\$_.Exception.Message)"
  }
}
if (Test-Path \$incoming) { Remove-Item -LiteralPath \$incoming -Recurse -Force }
\$archive = Join-Path \$stage 'package.zip'
Copy-Item -LiteralPath (Join-Path \$stage 'package.msix') -Destination \$archive -Force
Expand-Archive -LiteralPath \$archive -DestinationPath \$incoming -Force
Get-AppxPackage -Name '${PACKAGE_NAME}' | Remove-AppxPackage
if (Test-Path \$layout) { Remove-Item -LiteralPath \$layout -Recurse -Force }
Move-Item -LiteralPath \$incoming -Destination \$layout
Remove-Item -LiteralPath \$stage -Recurse -Force
Add-AppxPackage -Register (Join-Path \$layout 'AppxManifest.xml')
Get-AppxPackage -Name '${PACKAGE_NAME}' | Select-Object Name, Version, InstallLocation | Format-List
POWERSHELL
)
encode_powershell() {
  printf '%s' "$1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n'
}
ENCODED_SCRIPT="$(encode_powershell "$REMOTE_SCRIPT")"
ENCODED_CLEAN="$(encode_powershell "Remove-Item -LiteralPath (Join-Path \$HOME '${REMOTE_STAGE}') -Recurse -Force -ErrorAction SilentlyContinue")"

if [ -z "$RUN_ID" ]; then
  [ -n "$BRANCH" ] || BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  if [ "$BRANCH" = "HEAD" ]; then
    echo "detached HEAD: pass --branch NAME or --run-id ID" >&2
    exit 2
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    RUN_ID="<latest-successful-run>"
    echo "+ gh run list --workflow windows-ci.yml --branch $BRANCH --status success --limit 1"
  else
    RUN_ID="$(gh run list --workflow windows-ci.yml --branch "$BRANCH" --status success \
      --limit 1 --json databaseId --jq '.[0].databaseId')"
    [ -n "$RUN_ID" ] || { echo "no successful Windows CI run for $BRANCH" >&2; exit 1; }
  fi
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Downloading $ARTIFACT from run $RUN_ID"
run gh run download "$RUN_ID" --name "$ARTIFACT" --dir "$WORK"

STAGE="$WORK/stage"
mkdir -p "$STAGE/Dependencies"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ stage <package>.msix and Dependencies/x64/* into $STAGE"
else
  MSIX="$(find "$WORK" -path "$STAGE" -prune -o -name '*.msix' -print | head -n 1)"
  [ -n "$MSIX" ] || { echo "the artifact contains no .msix" >&2; exit 1; }
  cp "$MSIX" "$STAGE/package.msix"
  find "$WORK" -path "$STAGE" -prune -o -path '*/Dependencies/x64/*' -type f \
    \( -name '*.appx' -o -name '*.msix' \) -exec cp {} "$STAGE/Dependencies/" \;
fi

echo "==> Copying package to $HOST"
run ssh "$HOST" powershell -NoProfile -NonInteractive -EncodedCommand "$ENCODED_CLEAN"
run scp -q -r "$STAGE" "$HOST:$REMOTE_STAGE"

echo "==> Registering $PACKAGE_NAME on $HOST"
if [ "$DRY_RUN" -eq 1 ]; then
  printf '%s\n' "$REMOTE_SCRIPT"
fi
run ssh "$HOST" powershell -NoProfile -NonInteractive -EncodedCommand "$ENCODED_SCRIPT"

echo "==> Done. Open Xbox Game Bar (Win+G) > Widgets > Panel de Control on $HOST"
