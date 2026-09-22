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
    matches = re.findall(r"-EncodedCommand (\S+)", stdout)
    assert len(matches) == 2
    return base64.b64decode(matches[-1]).decode("utf-16-le")


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
    assert "me@handheld:pdc-deploy" in result.stdout
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
    assert remote.index("Expand-Archive") < remote.index("Remove-AppxPackage")
    assert remote.index("Add-AppxPackage -Path $dependency.FullName") < remote.index("Remove-AppxPackage")


def test_detached_head_needs_an_explicit_build(tmp_path):
    import shutil

    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, repo / "scripts" / SCRIPT.name)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach"], check=True)

    result = subprocess.run(
        ["bash", str(repo / "scripts" / SCRIPT.name), "--dry-run", "me@handheld"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "detached HEAD" in result.stderr


def test_package_name_matches_the_manifest_identity():
    manifest = (Path(__file__).parents[1] / "windows" / "src" / "PanelDeControl.GameBar" / "Package.appxmanifest").read_text(encoding="utf-8")
    identity = re.search(r'<Identity\s+Name="([^"]+)"', manifest).group(1)

    assert f'PACKAGE_NAME="{identity}"' in SCRIPT.read_text(encoding="utf-8")
