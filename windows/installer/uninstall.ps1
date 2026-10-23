# Removes what install.ps1 put in place. Themes, settings and logs under the person's LocalAppData stay,
# so reinstalling keeps their choices.
param(
    [Parameter(Mandatory)][string]$Log,
    [Parameter(Mandatory)][string]$Certificate
)

$ProgressPreference = 'SilentlyContinue'
$packageName = 'PanelDeControl.Windows'
$serviceName = 'PanelDeControlService'

function Write-Step([string]$text) {
    "[$(Get-Date -Format o)] $text" | Out-File -FilePath $Log -Append -Encoding utf8
}

Get-Process -Name 'PanelDeControl.Hardware', 'PanelDeControl.GameBar' -ErrorAction SilentlyContinue | Stop-Process -Force
Get-AppxPackage -Name $packageName | ForEach-Object {
    Write-Step "removing $($_.PackageFullName)"
    Remove-AppxPackage -Package $_.PackageFullName -ErrorAction Continue
}

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne 'Stopped') { Stop-Service -Name $serviceName -Force -ErrorAction Continue }
    sc.exe delete $serviceName | Out-Null
    Write-Step 'service removed'
}

$serviceDir = Join-Path $env:ProgramFiles 'PanelDeControl\Service'
$deadline = (Get-Date).AddSeconds(15)
while ((Test-Path $serviceDir) -and (Get-Date) -lt $deadline) {
    Remove-Item -LiteralPath $serviceDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $serviceDir) { Start-Sleep -Milliseconds 500 }
}

if (Test-Path $Certificate) {
    $thumbprint = (New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $Certificate).Thumbprint
    Remove-Item -LiteralPath "Cert:\LocalMachine\TrustedPeople\$thumbprint" -ErrorAction SilentlyContinue
    Write-Step "certificate $thumbprint removed"
}

Get-Process GameBar, GameBarFTServer, XboxGameBarWidgets -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Step 'done'
exit 0
