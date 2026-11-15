from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import types
import zipfile
from pathlib import Path

import pytest

from main_harness import load_main

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
    abi_version: int = 1,
):
    archive = root / "theme.zip"
    extension = {
        "abiVersion": abi_version,
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
            "display_name": THEME_NAME,
            "author": "Example Author",
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


ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def theme_rpc(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path / "settings")
    fake.DECKY_USER_HOME = str(tmp_path / "home")
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    monkeypatch.syspath_prepend(str(ROOT / "py_modules"))
    monkeypatch.syspath_prepend(str(ROOT))
    main = load_main(monkeypatch)
    plugin = main.Plugin()
    plugin._init = lambda: None
    return main, plugin, fake
