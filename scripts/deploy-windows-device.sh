#!/usr/bin/env bash
#
# Install the latest Windows CI build of the Game Bar widget on a Windows device over SSH.
#
#   scripts/deploy-windows-device.sh [--dry-run] [--run-id ID] [--branch NAME] [--with-service] <user@host>
#   scripts/deploy-windows-device.sh [--dry-run] --remove-service <user@host>
#
# The host can also come from PDC_WINDOWS_HOST. The device needs OpenSSH Server with key-based
# login and Developer Mode enabled: the CI package is unsigned, so it is registered from its
# unpacked layout instead of installed as a signed package. --with-service also installs the
# read-only PanelDeControlService, which needs an administrator SSH account.
#
set -euo pipefail

usage() {
  echo "usage: deploy-windows-device.sh [--dry-run] [--run-id ID] [--branch NAME] [--with-service] <user@host>" >&2
  echo "       deploy-windows-device.sh [--dry-run] --remove-service <user@host>" >&2
  exit 2
}

DRY_RUN=0
WITH_SERVICE=0
REMOVE_SERVICE=0
RUN_ID=""
BRANCH=""
HOST="${PDC_WINDOWS_HOST:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --with-service) WITH_SERVICE=1 ;;
    --remove-service) REMOVE_SERVICE=1 ;;
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
if [ "$WITH_SERVICE" -eq 1 ] && [ "$REMOVE_SERVICE" -eq 1 ]; then
  echo "--with-service and --remove-service are exclusive" >&2
  exit 2
fi
if [ -n "$RUN_ID" ] && [[ ! "$RUN_ID" =~ ^[0-9]+$ ]]; then
  echo "run id must be numeric" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_NAME="PanelDeControl.Windows"
ARTIFACT="panel-de-control-gamebar-x64"
SERVICE_ARTIFACT="panel-de-control-service-x64"
SERVICE_NAME="PanelDeControlService"
REMOTE_STAGE="pdc-deploy"

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

REQUIRE_ADMIN=$(cat <<'POWERSHELL'
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'The service needs an administrator SSH account.'
}
POWERSHELL
)

REMOVE_SERVICE_SCRIPT=$(cat <<POWERSHELL
\$service = Get-Service -Name '${SERVICE_NAME}' -ErrorAction SilentlyContinue
if (\$service) {
  if (\$service.Status -ne 'Stopped') { Stop-Service -Name '${SERVICE_NAME}' -Force }
  \$deadline = (Get-Date).AddSeconds(15)
  while ((Get-Process -Name 'PanelDeControl.Service' -ErrorAction SilentlyContinue) -and (Get-Date) -lt \$deadline) {
    Start-Sleep -Milliseconds 250
  }
  if (Get-Process -Name 'PanelDeControl.Service' -ErrorAction SilentlyContinue) { throw 'The old service process did not exit; nothing was removed.' }
  sc.exe delete '${SERVICE_NAME}' | Out-Null
  \$deadline = (Get-Date).AddSeconds(15)
  while ((Get-Service -Name '${SERVICE_NAME}' -ErrorAction SilentlyContinue) -and (Get-Date) -lt \$deadline) {
    Start-Sleep -Milliseconds 250
  }
  if (Get-Service -Name '${SERVICE_NAME}' -ErrorAction SilentlyContinue) { throw 'The old service is still registered.' }
}
\$serviceDir = Join-Path \$env:ProgramFiles 'PanelDeControl\\Service'
if (Test-Path \$serviceDir) { Remove-Item -LiteralPath \$serviceDir -Recurse -Force }
POWERSHELL
)

INSTALL_SERVICE_SCRIPT=$(cat <<POWERSHELL
New-Item -ItemType Directory -Path \$serviceDir -Force | Out-Null
Copy-Item -Path (Join-Path \$stage 'service\\*') -Destination \$serviceDir -Recurse -Force
\$binary = Join-Path \$serviceDir 'PanelDeControl.Service.exe'
New-Service -Name '${SERVICE_NAME}' -BinaryPathName ('"' + \$binary + '"') -DisplayName 'Panel de Control' -StartupType Automatic | Out-Null
Start-Service -Name '${SERVICE_NAME}'
Get-Service -Name '${SERVICE_NAME}' | Select-Object Name, Status, StartType | Format-List
POWERSHELL
)

# Appx registration needs the user's interactive desktop session (Process Lifetime Manager);
# over SSH it fails with 0x80070005, so this part runs as an interactive scheduled task.
REGISTER_SCRIPT=$(cat <<POWERSHELL
\$ErrorActionPreference = 'Stop'
\$ProgressPreference = 'SilentlyContinue'
\$stage = Join-Path \$HOME '${REMOTE_STAGE}'
\$root = Join-Path \$env:LOCALAPPDATA 'PanelDeControl'
\$layout = Join-Path \$root 'dev-layout'
\$incoming = Join-Path \$root 'dev-layout-incoming'
\$log = Join-Path \$stage 'register.log'
\$code = 1
try {
  foreach (\$dependency in Get-ChildItem -Path (Join-Path \$stage 'Dependencies') -File -ErrorAction SilentlyContinue) {
    try {
      Add-AppxPackage -Path \$dependency.FullName
    } catch {
      "Dependency \$(\$dependency.Name) not installed: \$(\$_.Exception.Message)" | Out-File -Append \$log
    }
  }
  Get-AppxPackage -Name '${PACKAGE_NAME}' | Remove-AppxPackage
  if (Test-Path \$layout) { Remove-Item -LiteralPath \$layout -Recurse -Force }
  Move-Item -LiteralPath \$incoming -Destination \$layout
  Add-AppxPackage -Register (Join-Path \$layout 'AppxManifest.xml')
  Get-AppxPackage -Name '${PACKAGE_NAME}' | Select-Object Name, Version, InstallLocation | Format-List | Out-String | Out-File -Append \$log
  \$code = 0
} catch {
  \$_ | Out-String | Out-File -Append \$log
} finally {
  \$code | Out-File (Join-Path \$stage 'register.done')
}
POWERSHELL
)

WIDGET_SCRIPT=$(cat <<POWERSHELL
\$ErrorActionPreference = 'Stop'
\$ProgressPreference = 'SilentlyContinue'
\$unlock = Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\AppModelUnlock' -ErrorAction SilentlyContinue
if (-not \$unlock -or \$unlock.AllowDevelopmentWithoutDevLicense -ne 1) {
  throw 'Developer Mode is off: enable it in Settings > System > For developers.'
}
\$stage = Join-Path \$HOME '${REMOTE_STAGE}'
\$root = Join-Path \$env:LOCALAPPDATA 'PanelDeControl'
\$incoming = Join-Path \$root 'dev-layout-incoming'
if (Test-Path \$incoming) { Remove-Item -LiteralPath \$incoming -Recurse -Force }
\$archive = Join-Path \$stage 'package.zip'
Copy-Item -LiteralPath (Join-Path \$stage 'package.msix') -Destination \$archive -Force
Expand-Archive -LiteralPath \$archive -DestinationPath \$incoming -Force
\$task = 'PanelDeControlDeploy'
\$register = Join-Path \$stage 'register.ps1'
\$done = Join-Path \$stage 'register.done'
\$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
\$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + \$register + '"')
\$principal = New-ScheduledTaskPrincipal -UserId \$user -LogonType Interactive -RunLevel Limited
\$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName \$task -Action \$action -Principal \$principal -Settings \$settings -Force | Out-Null
try {
  Start-ScheduledTask -TaskName \$task
  \$deadline = (Get-Date).AddSeconds(180)
  while (-not (Test-Path \$done) -and (Get-Date) -lt \$deadline) { Start-Sleep -Milliseconds 500 }
} finally {
  Unregister-ScheduledTask -TaskName \$task -Confirm:\$false
}
if (-not (Test-Path \$done)) { throw 'The widget was not registered: sign in on the device and run the deploy again.' }
Get-Content -Path (Join-Path \$stage 'register.log') -ErrorAction SilentlyContinue
if ((Get-Content -Path \$done -Raw).Trim() -ne '0') { throw 'Widget registration failed; see the log above.' }
POWERSHELL
)

if [ "$REMOVE_SERVICE" -eq 1 ]; then
  REMOTE_SCRIPT="$REQUIRE_ADMIN
$REMOVE_SERVICE_SCRIPT"
elif [ "$WITH_SERVICE" -eq 1 ]; then
  REMOTE_SCRIPT="$REQUIRE_ADMIN
$WIDGET_SCRIPT
$REMOVE_SERVICE_SCRIPT
$INSTALL_SERVICE_SCRIPT
Remove-Item -LiteralPath \$stage -Recurse -Force"
else
  REMOTE_SCRIPT="$WIDGET_SCRIPT
Remove-Item -LiteralPath \$stage -Recurse -Force"
fi
encode_powershell() {
  printf '%s' "$1" | iconv -f UTF-8 -t UTF-16LE | base64 | tr -d '\n'
}
ENCODED_SCRIPT="$(encode_powershell "$REMOTE_SCRIPT")"
ENCODED_CLEAN="$(encode_powershell "\$ProgressPreference = 'SilentlyContinue'; Remove-Item -LiteralPath (Join-Path \$HOME '${REMOTE_STAGE}') -Recurse -Force -ErrorAction SilentlyContinue; exit 0")"

if [ "$REMOVE_SERVICE" -eq 1 ]; then
  echo "==> Removing $SERVICE_NAME from $HOST"
  [ "$DRY_RUN" -eq 0 ] || printf '%s\n' "$REMOTE_SCRIPT"
  run ssh "$HOST" powershell -NoProfile -NonInteractive -EncodedCommand "$ENCODED_SCRIPT"
  echo "==> Done."
  exit 0
fi

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
  # CI builds in store-upload mode, which wraps the .msix and its symbols in a .msixupload zip.
  find "$WORK" -path "$STAGE" -prune -o \( -name '*.msixupload' -o -name '*.appxupload' \) -print |
    while IFS= read -r upload; do unzip -o -q "$upload" -d "$WORK/unpacked"; done
  MSIX="$(find "$WORK" -path "$STAGE" -prune -o -name '*.msix' -print | head -n 1)"
  [ -n "$MSIX" ] || { echo "the artifact contains no .msix" >&2; exit 1; }
  cp "$MSIX" "$STAGE/package.msix"
  find "$WORK" -path "$STAGE" -prune -o -path '*/Dependencies/x64/*' -type f \
    \( -name '*.appx' -o -name '*.msix' \) -exec cp {} "$STAGE/Dependencies/" \;
fi
if [ "$WITH_SERVICE" -eq 1 ]; then
  echo "==> Downloading $SERVICE_ARTIFACT from run $RUN_ID"
  run gh run download "$RUN_ID" --name "$SERVICE_ARTIFACT" --dir "$STAGE/service"
fi

printf '%s\n' "$REMOTE_SCRIPT" > "$STAGE/deploy.ps1"
printf '%s\n' "$REGISTER_SCRIPT" > "$STAGE/register.ps1"
[ "$DRY_RUN" -eq 0 ] || { echo "+ write $STAGE/register.ps1:"; printf '%s\n' "$REGISTER_SCRIPT"; }
[ "$DRY_RUN" -eq 0 ] || { echo "+ write $STAGE/deploy.ps1:"; printf '%s\n' "$REMOTE_SCRIPT"; }

echo "==> Copying package to $HOST"
run ssh "$HOST" powershell -NoProfile -NonInteractive -EncodedCommand "$ENCODED_CLEAN"
run scp -q -r "$STAGE" "$HOST:$REMOTE_STAGE"

echo "==> Registering $PACKAGE_NAME on $HOST"
[ "$WITH_SERVICE" -eq 0 ] || echo "==> Installing $SERVICE_NAME on $HOST"
run ssh "$HOST" powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$REMOTE_STAGE/deploy.ps1"

echo "==> Done. Open Xbox Game Bar (Win+G) > Widgets > Panel de Control on $HOST"
