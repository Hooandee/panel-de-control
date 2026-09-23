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


def _remote_script(stdout):
    marker = "deploy.ps1:\n"
    assert marker in stdout
    return stdout.split(marker, 1)[1].split("==> Copying", 1)[0]


def _register_script(stdout):
    marker = "register.ps1:\n"
    assert marker in stdout
    return stdout.split(marker, 1)[1].split("+ write", 1)[0]


def _encoded_scripts(stdout):
    return [base64.b64decode(item).decode("utf-16-le") for item in re.findall(r"-EncodedCommand (\S+)", stdout)]


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
    assert "+ ssh me@handheld powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File pdc-deploy/deploy.ps1" in result.stdout


def test_host_can_come_from_the_environment():
    result = _run("--dry-run", "--run-id", "7", env={"PDC_WINDOWS_HOST": "me@ally"})

    assert result.returncode == 0, result.stderr
    assert "+ ssh me@ally powershell" in result.stdout


def test_remote_script_requires_developer_mode_and_registers_the_layout():
    stdout = _run("--dry-run", "--run-id", "42", "me@handheld").stdout
    remote = _remote_script(stdout)
    register = _register_script(stdout)

    assert "AllowDevelopmentWithoutDevLicense -ne 1" in remote
    assert remote.index("throw 'Developer Mode is off") < remote.index("Expand-Archive")
    assert "-LogonType Interactive" in remote
    assert "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries" in remote
    assert remote.index("Start-ScheduledTask") < remote.index("Unregister-ScheduledTask")
    assert "Get-AppxPackage -Name 'PanelDeControl.Windows' | Remove-AppxPackage" in register
    assert "Add-AppxPackage -Register (Join-Path $layout 'AppxManifest.xml')" in register
    assert register.index("Add-AppxPackage -Path $dependency.FullName") < register.index("Remove-AppxPackage")
    assert "register.done" in register


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


def test_widget_only_deploy_never_touches_the_service():
    remote = _remote_script(_run("--dry-run", "--run-id", "42", "me@handheld").stdout)

    assert "PanelDeControlService" not in remote
    assert "IsInRole" not in remote


def test_with_service_installs_into_program_files_after_the_widget():
    result = _run("--dry-run", "--run-id", "42", "--with-service", "me@handheld")
    remote = _remote_script(result.stdout)

    assert result.returncode == 0, result.stderr
    assert "gh run download 42 --name panel-de-control-service-x64" in result.stdout
    assert remote.index("IsInRole") < remote.index("Start-ScheduledTask")
    assert remote.index("Unregister-ScheduledTask") < remote.index("New-Service")
    assert "Join-Path $env:ProgramFiles 'PanelDeControl\\Service'" in remote
    assert "ProgramData" not in remote
    assert remote.index("sc.exe delete") < remote.index("New-Service")
    assert remote.index("Get-Process -Name 'PanelDeControl.Service'") < remote.index("sc.exe delete")
    assert "-StartupType Automatic" in remote
    assert remote.rstrip().endswith("Remove-Item -LiteralPath $stage -Recurse -Force")


def test_remove_service_skips_downloads_and_requires_admin():
    result = _run("--dry-run", "--remove-service", "me@handheld")
    scripts = _encoded_scripts(result.stdout)

    assert result.returncode == 0, result.stderr
    assert "gh run" not in result.stdout
    assert len(scripts) == 1
    assert scripts[0].index("IsInRole") < scripts[0].index("sc.exe delete")
    assert "New-Service" not in scripts[0]


def test_service_flags_are_exclusive():
    assert _run("--dry-run", "--with-service", "--remove-service", "me@handheld").returncode == 2
