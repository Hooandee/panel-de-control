import hashlib
import os
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/package-plugin.sh"


def _runtime_tree(root: Path, include_xbox_extension=True) -> None:
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
        "assets/inputplumber/v0.77.4-xbox-hd.patch",
        "scripts/build-inputplumber-xbox-hd.sh",
    ):
        (root / relative).write_text(relative)
    if not include_xbox_extension:
        return
    binary = root / "bin/inputplumber-xbox-hd-v0.77.4"
    binary.write_bytes(b"inputplumber")
    binary.chmod(0o755)
    Path(f"{binary}.sha256").write_text(
        f"{hashlib.sha256(binary.read_bytes()).hexdigest()}\n"
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
