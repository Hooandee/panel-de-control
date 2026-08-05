import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/package-plugin.sh"


def _runtime_tree(root: Path, include_xbox_extension=True, version="0.77.4") -> None:
    commit = (
        "bb7424fd6fc097d123850950aaf1e6988f2093f3"
        if version == "0.77.4" else "b" * 40
    )
    for directory in (
        "dist", "py_modules/__pycache__", "assets/inputplumber", "bin",
        "scripts",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for relative in (
        "dist/index.js", "dist/index.js.map", "py_modules/runtime.py",
        "py_modules/__pycache__/runtime.cpython-314.pyc",
        "assets/icon.txt",
        "main.py", "plugin.json", "package.json", "README.md",
        "README.en.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
        "assets/inputplumber/README.md",
        f"assets/inputplumber/v{version}-xbox-hd.patch",
        "scripts/build-inputplumber-xbox-hd.sh",
    ):
        (root / relative).write_text(relative)
    shutil.copyfile(
        ROOT / "scripts/verify-inputplumber-xbox-hd.sh",
        root / "scripts/verify-inputplumber-xbox-hd.sh",
    )
    shutil.copyfile(
        ROOT / "scripts/inputplumber-manifest.py",
        root / "scripts/inputplumber-manifest.py",
    )
    (root / "py_modules/controllers").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "py_modules/controllers/__init__.py",
        root / "py_modules/controllers/__init__.py",
    )
    shutil.copyfile(
        ROOT / "py_modules/controllers/inputplumber_compat.py",
        root / "py_modules/controllers/inputplumber_compat.py",
    )
    manifest = {
        "schema": 1,
        "device": "rog_xbox_ally_x",
        "builds": [{
            "version": version,
            "upstream_commit": commit,
            "patch": f"assets/inputplumber/v{version}-xbox-hd.patch",
            "artifact": f"bin/inputplumber-xbox-hd-v{version}",
            "artifact_sha256": f"bin/inputplumber-xbox-hd-v{version}.sha256",
            "provenance": f"bin/inputplumber-xbox-hd-v{version}.provenance",
            "stock_sha256": ["4" * 64],
            "verified_platforms": ["steamos-test-rc73xa"],
        }],
    }
    (root / "assets/inputplumber/compatibility.json").write_text(
        json.dumps(manifest)
    )
    if not include_xbox_extension:
        return
    binary = root / f"bin/inputplumber-xbox-hd-v{version}"
    binary.write_bytes(b"inputplumber")
    binary.chmod(0o755)
    Path(f"{binary}.sha256").write_text(
        f"{hashlib.sha256(binary.read_bytes()).hexdigest()}\n"
    )
    patch = root / f"assets/inputplumber/v{version}-xbox-hd.patch"
    Path(f"{binary}.provenance").write_text(
        f"inputplumber_commit={commit}\n"
        f"patch_sha256={hashlib.sha256(patch.read_bytes()).hexdigest()}\n"
    )


def _package(root: Path, output: Path):
    return subprocess.run(
        ["bash", str(SCRIPT), str(output), "Panel de Control"],
        cwd=ROOT,
        env={**os.environ, "PDC_PACKAGE_ROOT": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_package_contains_the_verified_xbox_extension(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "plugin.zip"
    _runtime_tree(source)

    result = _package(source, output)

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(output) as archive:
        assert archive.read(
            "Panel de Control/bin/inputplumber-xbox-hd-v0.77.4"
        ) == b"inputplumber"
        assert (
            "Panel de Control/THIRD_PARTY_NOTICES.md"
            in archive.namelist()
        )
        assert (
            "Panel de Control/assets/inputplumber/v0.77.4-xbox-hd.patch"
            in archive.namelist()
        )
        assert (
            "Panel de Control/scripts/build-inputplumber-xbox-hd.sh"
            in archive.namelist()
        )
        assert (
            "Panel de Control/scripts/verify-inputplumber-xbox-hd.sh"
            in archive.namelist()
        )
        assert "Panel de Control/dist/index.js.map" not in archive.namelist()
        assert not any(
            "__pycache__" in name or name.endswith(".pyc")
            for name in archive.namelist()
        )


def test_package_refuses_to_publish_without_the_xbox_extension(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "plugin.zip"
    _runtime_tree(source, include_xbox_extension=False)

    result = _package(source, output)

    assert result.returncode != 0
    assert not output.exists()


def test_package_uses_manifest_paths_without_version_literals(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "plugin.zip"
    _runtime_tree(source, version="0.78.0")

    result = _package(source, output)

    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(output) as archive:
        assert archive.read(
            "Panel de Control/bin/inputplumber-xbox-hd-v0.78.0"
        ) == b"inputplumber"
        assert (
            "Panel de Control/assets/inputplumber/v0.78.0-xbox-hd.patch"
            in archive.namelist()
        )
