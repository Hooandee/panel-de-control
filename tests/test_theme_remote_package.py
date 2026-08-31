from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import theme_packages


THEME_ID = "hooandee-gallery"
THEME_NAME = "Hooandee Gallery"
THEME_VERSION = "0.7.9"


def package(
    root: Path,
    *,
    css: bytes = b":root { color: white; }\n",
    extra: dict[str, bytes] | None = None,
    panel_runtime: object = ...,  # type: ignore[assignment]
) -> tuple[Path, dict[str, object]]:
    archive = root / "gallery.zip"
    runtime = (
        {
            "moduleId": "gallery",
            "surfaces": ["library", "library-grid", "game-details", "settings"],
        }
        if panel_runtime is ...
        else panel_runtime
    )
    panel = {"schemaVersion": 1, "catalogId": THEME_ID}
    if runtime is not None:
        panel["runtime"] = runtime
    entries = {
        f"{THEME_NAME}/theme.json": json.dumps(
            {
                "name": THEME_NAME,
                "display_name": THEME_NAME,
                "author": "Hooandee",
                "version": THEME_VERSION,
                "manifest_version": 9,
                "inject": {"tokens.css": ["bigpicture"]},
                "patches": {},
            }
        ).encode(),
        f"{THEME_NAME}/panel-theme.json": json.dumps(panel).encode(),
        f"{THEME_NAME}/tokens.css": css,
        **(extra or {}),
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    blob = archive.read_bytes()
    return archive, {
        "schemaVersion": 1,
        "id": THEME_ID,
        "cssLoaderName": THEME_NAME,
        "version": THEME_VERSION,
        "artifact": {
            "file": "gallery.zip",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
        },
    }


def prepare(root: Path, archive: Path, descriptor: object) -> dict[str, object]:
    return theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        root / "themes",
        profile=theme_packages.PackageProfile.REMOTE_V1,
    )


def test_remote_profile_accepts_gallery_css_and_exact_compiled_runtime(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path)

    result = prepare(tmp_path, archive, descriptor)

    assert result["code"] == "prepared"
    theme_packages.rollback_theme_install(result["transaction"], tmp_path / "themes")
    theme_packages.acknowledge_theme_rollback(result["transaction"], tmp_path / "themes")


@pytest.mark.parametrize("suffix", ["svg", "html", "xml", "js"])
def test_remote_profile_rejects_executable_or_active_content_types(
    tmp_path: Path,
    suffix: str,
) -> None:
    archive, descriptor = package(
        tmp_path,
        extra={f"{THEME_NAME}/payload.{suffix}": b"content"},
    )

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


@pytest.mark.parametrize(
    "css",
    [
        b'@import "other.css";\n',
        b'@im\\70ort "other.css";\n',
        b'body { background: url("https://attacker.invalid/a.css"); }\n',
        b'body { background: u\\72l("https://attacker.invalid/a.css"); }\n',
        b'body { background: u/**/rl("https://attacker.invalid/a.css"); }\n',
        b'body { background: image-set("https://attacker.invalid/a.png" 1x); }\n',
        b'body { background: im/**/age-set("https://attacker.invalid/a.png" 1x); }\n',
        b'@font-face { src: local("Sensitive Local Font"); }\n',
        b'body { background: -webkit-canvas(host-content); }\n',
        b'body { background: -webkit-named-image(host-content); }\n',
        b'body { background: -moz-image-rect(host-content, 0, 0, 1, 1); }\n',
        b'body { background: url("//attacker.invalid/a.css"); }\n',
        b'body { background: url("missing.css"); }\n',
        b'@im/**/port "other.css";\n',
        b'body::before { content: "broken\n; background: url(https://attacker.invalid/a.png); "; }\n',
    ],
)
def test_remote_profile_rejects_imports_external_and_missing_resources(
    tmp_path: Path,
    css: bytes,
) -> None:
    archive, descriptor = package(tmp_path, css=css)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_profile_does_not_treat_string_contents_as_css_tokens(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        css=b'body::before { content: "url(image-set(@import))"; }\n',
    )

    result = prepare(tmp_path, archive, descriptor)

    assert result["code"] == "prepared"
    theme_packages.rollback_theme_install(result["transaction"], tmp_path / "themes")
    theme_packages.acknowledge_theme_rollback(result["transaction"], tmp_path / "themes")


def test_remote_profile_rejects_css_not_declared_by_the_manifest(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        extra={f"{THEME_NAME}/unreferenced.css": b"body {}\n"},
    )

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_profile_rejects_a_runtime_not_compiled_into_panel(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        panel_runtime={"moduleId": "downloaded-code", "surfaces": ["library"]},
    )

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "identity_mismatch"


def test_remote_profile_rejects_extreme_compression_ratios(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        css=b"a" * (2 * 1024 * 1024),
    )

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_profile_checks_available_space_before_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, descriptor = package(tmp_path)
    disk_usage = type("DiskUsage", (), {"total": 100, "used": 99, "free": 1})()
    monkeypatch.setattr(theme_packages.shutil, "disk_usage", lambda _path: disk_usage)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "insufficient_space"


def test_bundled_compatibility_profile_still_accepts_declarative_svg(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        extra={f"{THEME_NAME}/decorative.svg": b"<svg/>"},
    )

    result = theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        tmp_path / "themes",
    )

    assert result["code"] == "prepared"
