# Installs what Setup unpacked into -Payload: the package dependencies, the unsigned widget package and the
# read-only service. Setup runs it elevated in the person's own session, so the package is added for them.
param(
    [Parameter(Mandatory)][string]$Payload,
    [Parameter(Mandatory)][string]$Log
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$packageName = 'PanelDeControl.Windows'
$serviceName = 'PanelDeControlService'
$serviceDir = Join-Path $env:ProgramFiles 'PanelDeControl\Service'

function Write-Step([string]$text) {
    "[$(Get-Date -Format o)] $text" | Out-File -FilePath $Log -Append -Encoding utf8
}

function Remove-PanelService {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service) {
        if ($service.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force }
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Process -Name 'PanelDeControl.Service' -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 250
        }
        sc.exe delete $serviceName | Out-Null
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Service -Name $serviceName -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 250
        }
    }
}

try {
    Write-Step "Windows $([Environment]::OSVersion.Version)"

    # The companion holds the old package's files; it restarts on its own when the widget or the
    # service needs it.
    Get-Process -Name 'PanelDeControl.Hardware', 'PanelDeControl.GameBar' -ErrorAction SilentlyContinue | Stop-Process -Force

    foreach ($dependency in Get-ChildItem -Path (Join-Path $Payload 'Dependencies') -File -ErrorAction SilentlyContinue | Where-Object Extension -in '.appx', '.msix') {
        try {
            Add-AppxPackage -Path $dependency.FullName -ForceApplicationShutdown
            Write-Step "dependency $($dependency.Name) installed"
        } catch {
            # Already present (often a newer version in use by other apps): nothing to do.
            Write-Step "dependency $($dependency.Name) skipped: $($_.Exception.Message)"
        }
    }

    Get-AppxPackage -Name $packageName | ForEach-Object {
        Write-Step "removing $($_.PackageFullName)"
        Remove-AppxPackage -Package $_.PackageFullName
    }

    $msix = Get-ChildItem -Path $Payload -Filter '*.msix' -File | Select-Object -First 1
    if (-not $msix) { throw 'The widget package is missing from the installer.' }
    Add-AppxPackage -Path $msix.FullName -AllowUnsigned -ForceApplicationShutdown
    $installed = Get-AppxPackage -Name $packageName
    if (-not $installed) { throw 'Windows did not register the widget package.' }
    Write-Step "package $($installed.PackageFullName) installed"

    Remove-PanelService
    if (Test-Path $serviceDir) { Remove-Item -LiteralPath $serviceDir -Recurse -Force }
    New-Item -ItemType Directory -Path $serviceDir -Force | Out-Null
    Copy-Item -Path (Join-Path $Payload 'service\*') -Destination $serviceDir -Recurse -Force
    $binary = Join-Path $serviceDir 'PanelDeControl.Service.exe'
    # The package is unsigned: the service trusts only the companion files installed right now.
    & $binary --trust-broker (Join-Path $installed.InstallLocation 'HardwareBroker') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'The service could not record the companion fingerprint.' }
    Write-Step 'companion fingerprint recorded'
    New-Service -Name $serviceName -BinaryPathName ('"' + $binary + '"') -DisplayName 'Panel de Control' -StartupType Automatic | Out-Null
    Start-Service -Name $serviceName
    Write-Step "service $((Get-Service -Name $serviceName).Status)"

    # Game Bar keeps the widget list it read at start; a restart makes it list the new package.
    Get-Process GameBar, GameBarFTServer, XboxGameBarWidgets -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Step 'done'
    exit 0
} catch {
    Write-Step "failed: $($_ | Out-String)"
    exit 1
}
