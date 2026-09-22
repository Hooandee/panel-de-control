import base64
import os
import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "deploy-windows-device.sh"


def _run(*args, env=None):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PDC_WINDOWS_HOST": "", **(env or {})},
        check=False,
    )


def _encoded_script(stdout):
    match = re.search(r"-EncodedCommand (\S+)", stdout)
    assert match
    return base64.b64decode(match.group(1)).decode("utf-16-le")


def test_requires_a_user_at_host_target():
    assert _run().returncode == 2
    assert _run("--dry-run", "handheld").returncode == 2


def test_rejects_non_numeric_run_ids():
    result = _run("--dry-run", "--run-id", "latest", "me@handheld")
    assert result.returncode == 2
    assert "numeric" in result.stderr


def test_dry_run_prints_every_step_without_touching_the_device():
    result = _run("--dry-run", "--run-id", "42", "me@handheld")

    assert result.returncode == 0, result.stderr
    assert "+ gh run download 42 --name panel-de-control-gamebar-x64" in result.stdout
    assert "+ scp -q " in result.stdout
    assert "me@handheld:pdc-gamebar.msix" in result.stdout
    assert "+ ssh me@handheld powershell -NoProfile -NonInteractive -EncodedCommand" in result.stdout


def test_host_can_come_from_the_environment():
    result = _run("--dry-run", "--run-id", "7", env={"PDC_WINDOWS_HOST": "me@ally"})

    assert result.returncode == 0, result.stderr
    assert "+ ssh me@ally powershell" in result.stdout


def test_remote_script_requires_developer_mode_and_registers_the_layout():
    remote = _encoded_script(_run("--dry-run", "--run-id", "42", "me@handheld").stdout)

    assert "AllowDevelopmentWithoutDevLicense -ne 1" in remote
    assert remote.index("throw 'Developer Mode is off") < remote.index("Remove-AppxPackage")
    assert "Get-AppxPackage -Name 'PanelDeControl.Windows' | Remove-AppxPackage" in remote
    assert "Add-AppxPackage -Register (Join-Path $layout 'AppxManifest.xml')" in remote


def test_package_name_matches_the_manifest_identity():
    manifest = (Path(__file__).parents[1] / "windows" / "src" / "PanelDeControl.GameBar" / "Package.appxmanifest").read_text(encoding="utf-8")
    identity = re.search(r'<Identity\s+Name="([^"]+)"', manifest).group(1)

    assert f'PACKAGE_NAME="{identity}"' in SCRIPT.read_text(encoding="utf-8")
