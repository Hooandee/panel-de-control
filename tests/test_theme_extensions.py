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
EXTENSION = b"module.exports=Object.freeze({abiVersion:1,mount(){return()=>{}}});\n"


def package(
    root: Path,
    *,
    marker_patch: dict[str, object] | None = None,
    stray_js: bool = False,
    version: str = THEME_VERSION,
    extension_source: bytes = EXTENSION,
):
    archive = root / "theme.zip"
    extension = {
        "abiVersion": 1,
        "entrypoint": "panel-extension.js",
        "size": len(extension_source),
        "sha256": hashlib.sha256(extension_source).hexdigest(),
    }
    marker = {
        "schemaVersion": 2,
        "catalogId": THEME_ID,
        "extension": extension,
        **(marker_patch or {}),
    }
    entries = {
        f"{THEME_NAME}/theme.json": json.dumps({
            "name": THEME_NAME,
            "version": version,
            "manifest_version": 9,
            "inject": {"tokens.css": ["bigpicture"]},
            "patches": {},
        }).encode(),
        f"{THEME_NAME}/panel-theme.json": json.dumps(marker).encode(),
        f"{THEME_NAME}/panel-extension.js": extension_source,
        f"{THEME_NAME}/tokens.css": b"body { color: white; }\n",
    }
    if stray_js:
        entries[f"{THEME_NAME}/extra.js"] = b"alert(1)"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    blob = archive.read_bytes()
    descriptor = {
        "schemaVersion": 1,
        "id": THEME_ID,
        "cssLoaderName": THEME_NAME,
        "version": version,
        "artifact": {
            "file": "theme.zip",
            "size": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
        },
    }
    return archive, descriptor


def paths(root: Path) -> tuple[Path, Path]:
    return root / "themes", root / "settings" / "theme-extension-receipts.json"


def test_commit_persists_a_validated_receipt_and_serves_only_its_exact_extension(tmp_path: Path):
    archive, descriptor = package(tmp_path)
    themes, receipts = paths(tmp_path)

    prepared = theme_packages.prepare_theme_archive(
        archive, descriptor, themes, receipts_path=receipts
    )
    theme_packages.commit_theme_install(
        prepared["transaction"], themes, receipts_path=receipts
    )

    assert theme_packages.list_theme_extensions(themes, receipts) == [{
        "catalogId": THEME_ID,
        "cssLoaderName": THEME_NAME,
        "version": THEME_VERSION,
        "abiVersion": 1,
        "entrypoint": "panel-extension.js",
        "size": len(EXTENSION),
        "sha256": hashlib.sha256(EXTENSION).hexdigest(),
    }]
    assert theme_packages.load_theme_extension(
        THEME_ID, THEME_VERSION, themes, receipts
    ) == {
        "catalogId": THEME_ID,
        "cssLoaderName": THEME_NAME,
        "version": THEME_VERSION,
        "abiVersion": 1,
        "sha256": hashlib.sha256(EXTENSION).hexdigest(),
        "source": EXTENSION.decode("utf-8"),
    }


def test_uncommitted_and_rolled_back_extensions_never_gain_a_receipt(tmp_path: Path):
    archive, descriptor = package(tmp_path)
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(
        archive, descriptor, themes, receipts_path=receipts
    )

    assert theme_packages.list_theme_extensions(themes, receipts) == []
    theme_packages.rollback_theme_install(
        prepared["transaction"], themes, receipts_path=receipts
    )
    assert theme_packages.list_theme_extensions(themes, receipts) == []


@pytest.mark.parametrize(
    "marker_patch",
    [
        {"schemaVersion": 1},
        {"runtime": {"moduleId": "private"}},
        {"extension": {"abiVersion": 2, "entrypoint": "panel-extension.js", "size": len(EXTENSION), "sha256": hashlib.sha256(EXTENSION).hexdigest()}},
        {"extension": {"abiVersion": 1, "entrypoint": "other.js", "size": len(EXTENSION), "sha256": hashlib.sha256(EXTENSION).hexdigest()}},
        {"extension": {"abiVersion": 1, "entrypoint": "panel-extension.js", "size": len(EXTENSION), "sha256": "0" * 64}},
    ],
)
def test_prepare_rejects_invalid_v2_extension_markers(tmp_path: Path, marker_patch: dict[str, object]):
    archive, descriptor = package(tmp_path, marker_patch=marker_patch)
    themes, receipts = paths(tmp_path)

    with pytest.raises(theme_packages.ThemePackageError):
        theme_packages.prepare_theme_archive(
            archive, descriptor, themes, receipts_path=receipts
        )


def test_prepare_rejects_every_undeclared_javascript_file(tmp_path: Path):
    archive, descriptor = package(tmp_path, stray_js=True)
    themes, receipts = paths(tmp_path)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(
            archive, descriptor, themes, receipts_path=receipts
        )

    assert error.value.code == "unsafe_archive"


def test_tampering_or_removing_a_receipt_closes_extension_loading(tmp_path: Path):
    archive, descriptor = package(tmp_path)
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(
        archive, descriptor, themes, receipts_path=receipts
    )
    theme_packages.commit_theme_install(
        prepared["transaction"], themes, receipts_path=receipts
    )
    (themes / THEME_NAME / "panel-extension.js").write_text("tampered", encoding="utf-8")

    assert theme_packages.list_theme_extensions(themes, receipts) == []
    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.load_theme_extension(THEME_ID, THEME_VERSION, themes, receipts)
    assert error.value.code == "extension_unavailable"

    receipts.unlink()
    assert theme_packages.list_theme_extensions(themes, receipts) == []


def test_recovery_restores_the_previous_receipt_after_commit_crashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    themes, receipts = paths(tmp_path)
    previous_source = b"module.exports=Object.freeze({abiVersion:1,mount(){return()=>1}});\n"
    archive, descriptor = package(
        tmp_path,
        version="1.2.2",
        extension_source=previous_source,
    )
    previous = theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        themes,
        receipts_path=receipts,
    )
    theme_packages.commit_theme_install(
        previous["transaction"],
        themes,
        receipts_path=receipts,
    )

    archive, descriptor = package(tmp_path)
    update = theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        themes,
        receipts_path=receipts,
    )
    write_journal = theme_packages._write_journal

    def crash_before_commit_record(path, journal):
        if journal["state"] == "committed":
            raise OSError("simulated crash")
        write_journal(path, journal)

    monkeypatch.setattr(theme_packages, "_write_journal", crash_before_commit_record)
    with pytest.raises(OSError, match="simulated crash"):
        theme_packages.commit_theme_install(
            update["transaction"],
            themes,
            receipts_path=receipts,
        )
    monkeypatch.setattr(theme_packages, "_write_journal", write_journal)

    pending = theme_packages.recover_theme_transactions(
        themes,
        receipts_path=receipts,
    )

    assert len(pending) == 1
    assert theme_packages.load_theme_extension(
        THEME_ID,
        "1.2.2",
        themes,
        receipts,
    )["source"] == previous_source.decode("utf-8")
    with pytest.raises(theme_packages.ThemePackageError):
        theme_packages.load_theme_extension(
            THEME_ID,
            THEME_VERSION,
            themes,
            receipts,
        )
