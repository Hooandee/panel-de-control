from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

import theme_packages


THEME_ID = "example-theme"
THEME_NAME = "Example Theme"
THEME_VERSION = "1.2.3"


def package(
    root: Path,
    *,
    css: bytes = b":root { color: white; }\n",
    extra: dict[str, bytes] | None = None,
    panel: object | None = None,
    manifest: object | None = None,
) -> tuple[Path, dict[str, object]]:
    archive = root / "example-theme.zip"
    theme_manifest = manifest or {
        "name": THEME_NAME,
        "display_name": THEME_NAME,
        "author": "Example Author",
        "version": THEME_VERSION,
        "manifest_version": 9,
        "inject": {"tokens.css": ["bigpicture"]},
        "patches": {},
    }
    panel_manifest = panel or {"schemaVersion": 2, "catalogId": THEME_ID}
    entries = {
        f"{THEME_NAME}/theme.json": json.dumps(theme_manifest).encode(),
        f"{THEME_NAME}/panel-theme.json": json.dumps(panel_manifest).encode(),
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
            "file": archive.name,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
        },
    }


def prepare(root: Path, archive: Path, descriptor: object) -> dict[str, object]:
    return theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        root / "themes",
        receipts_path=root / "settings" / "receipts.json",
    )


def finish(root: Path, result: dict[str, object]) -> None:
    token = str(result["transaction"])
    receipts = root / "settings" / "receipts.json"
    theme_packages.rollback_theme_install(token, root / "themes", receipts_path=receipts)
    theme_packages.acknowledge_theme_rollback(token, root / "themes", receipts_path=receipts)


def test_remote_v1_accepts_a_neutral_declarative_theme(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path)
    result = prepare(tmp_path, archive, descriptor)
    assert result["code"] == "prepared"
    finish(tmp_path, result)


def test_remote_v1_accepts_reachable_relative_and_css_loader_mount_assets(tmp_path: Path) -> None:
    archive, descriptor = package(
        tmp_path,
        css=(
            b'body { background-image: url("assets/preview.webp"); }\n'
            b'@font-face { src: url("/themes_custom/Example%20Theme/assets/font.woff2") '
            b'format("woff2"); }\n'
        ),
        extra={
            f"{THEME_NAME}/assets/preview.webp": b"preview-image",
            f"{THEME_NAME}/assets/font.woff2": b"font-data",
            f"{THEME_NAME}/assets/LICENSE.txt": b"Example license\n",
        },
    )
    result = prepare(tmp_path, archive, descriptor)
    assert result["code"] == "prepared"
    finish(tmp_path, result)


@pytest.mark.parametrize("suffix", ["svg", "html", "xml", "js", "md", "sh", "exe"])
def test_remote_v1_rejects_active_or_unknown_content_types(tmp_path: Path, suffix: str) -> None:
    archive, descriptor = package(tmp_path, extra={f"{THEME_NAME}/payload.{suffix}": b"content"})
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


@pytest.mark.parametrize(
    "css",
    [
        b'@import "other.css";\n',
        b'@im\\70ort "other.css";\n',
        b'body { background: url("https://attacker.invalid/a.png"); }\n',
        b'body { background: u\\72l("assets/preview.webp"); }\n',
        b'body { background: u/**/rl("assets/preview.webp"); }\n',
        b'body { background: image-set("assets/preview.webp" 1x); }\n',
        b'body { background: im/**/age-set("assets/preview.webp" 1x); }\n',
        b'@font-face { src: local("Sensitive Local Font"); }\n',
        b'body { background: -webkit-canvas(host-content); }\n',
        b'body { background: -webkit-named-image(host-content); }\n',
        b'body { background: -moz-image-rect(host-content, 0, 0, 1, 1); }\n',
        b'body { background: paint(host-content); }\n',
        b'body { background: element(#host); }\n',
        b'body { background: cross-fade(url("assets/a.png"), url("assets/b.png")); }\n',
        b'body { background: url("//attacker.invalid/a.png"); }\n',
        b'body { background: url("data:image/png;base64,aaaa"); }\n',
        b'body { background: url("assets/missing.png"); }\n',
        b'body { background: url("../outside.png"); }\n',
        b'body { background: url("assets/a.png?query"); }\n',
        b'body { background: url("assets/a.png#fragment"); }\n',
        b'body { background: url(assets/a.png); }\n',
        b'body { background: url("/themes_custom/Second%20Theme/assets/a.png"); }\n',
        b'body { background: url("/themes_custom/Example Theme/assets/a.png"); }\n',
        b'body::before { content: "broken\n; background: url(https://attacker.invalid/a.png); "; }\n',
    ],
)
def test_remote_v1_rejects_imports_active_functions_and_unsafe_urls(tmp_path: Path, css: bytes) -> None:
    archive, descriptor = package(tmp_path, css=css)
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_v1_does_not_treat_string_contents_as_css_tokens(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path, css=b'body::before { content: "url(image-set(@import))"; }\n')
    result = prepare(tmp_path, archive, descriptor)
    assert result["code"] == "prepared"
    finish(tmp_path, result)


def test_remote_v1_rejects_css_not_declared_by_the_manifest(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path, extra={f"{THEME_NAME}/unreferenced.css": b"body {}\n"})
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_v1_rejects_a_manifest_reference_without_a_packaged_css_file(tmp_path: Path) -> None:
    manifest = {
        "name": THEME_NAME,
        "version": THEME_VERSION,
        "manifest_version": 9,
        "inject": {"tokens.css": ["bigpicture"], "missing.css": ["bigpicture"]},
        "patches": {},
    }
    archive, descriptor = package(tmp_path, manifest=manifest)
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


@pytest.mark.parametrize(
    "manifest",
    [
        {"name": THEME_NAME, "version": THEME_VERSION, "manifest_version": 0, "inject": {"tokens.css": ["bigpicture"]}, "patches": {}},
        {"name": THEME_NAME, "version": THEME_VERSION, "manifest_version": True, "inject": {"tokens.css": ["bigpicture"]}, "patches": {}},
        {"name": THEME_NAME, "version": THEME_VERSION, "manifest_version": 9_007_199_254_740_992, "inject": {"tokens.css": ["bigpicture"]}, "patches": {}},
        {"name": THEME_NAME, "version": THEME_VERSION, "manifest_version": 9, "inject": {"tokens.css": "bigpicture"}, "patches": {}},
        {"name": THEME_NAME, "version": THEME_VERSION, "manifest_version": 9, "inject": {"tokens.css": ["bigpicture"]}, "patches": {"Mode": {"default": "On", "type": "checkbox", "values": []}}},
    ],
)
def test_remote_v1_rejects_invalid_css_loader_manifest_declarations(tmp_path: Path, manifest: object) -> None:
    archive, descriptor = package(tmp_path, manifest=manifest)
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code in {"identity_mismatch", "unsafe_archive"}


@pytest.mark.parametrize(
    "panel",
    [
        {"schemaVersion": 2, "catalogId": THEME_ID, "runtime": {}},
        {"schemaVersion": 2, "catalogId": THEME_ID, "capabilities": []},
        {"schemaVersion": 2, "catalogId": THEME_ID, "executableContent": False},
    ],
)
def test_remote_v1_rejects_private_or_executable_panel_marker_fields(tmp_path: Path, panel: object) -> None:
    archive, descriptor = package(tmp_path, panel=panel)
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "identity_mismatch"


def test_remote_v1_rejects_an_unreferenced_binary_asset(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path, extra={f"{THEME_NAME}/assets/unused.png": b"unused-image"})
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_v1_rejects_extreme_compression_ratios(tmp_path: Path) -> None:
    archive, descriptor = package(tmp_path, css=b"a" * (2 * 1024 * 1024))
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "unsafe_archive"


def test_remote_v1_checks_available_space_before_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive, descriptor = package(tmp_path)
    disk_usage = type("DiskUsage", (), {"total": 100, "used": 99, "free": 1})()
    monkeypatch.setattr(theme_packages.shutil, "disk_usage", lambda _path: disk_usage)
    with pytest.raises(theme_packages.ThemePackageError) as error:
        prepare(tmp_path, archive, descriptor)
    assert error.value.code == "insufficient_space"
