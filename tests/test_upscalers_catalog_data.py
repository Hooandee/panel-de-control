import dataclasses
import json
from pathlib import Path

import pytest

from upscalers import catalog

SNAPSHOT = Path(__file__).parent / "fixtures" / "upscaler_catalog_snapshot.json"
DATA_NAMES = (
    "OPTISCALER_ARCHIVE", "OPTISCALER_BETA", "LSFG_ARCHIVE", "HELIXSR_ARCHIVE", "OPTIPATCHER",
    "ASSETS", "AMD", "EVERY_GPU", "BUILDS", "PREFERRED", "QUALITY_RATIOS", "EASY_MODES",
    "SHARPNESS", "PROXIES", "BASE_INI", "FFX_LOADER",
)
DEVICES = ("", "steam_deck_lcd", "rog_ally")


def _canonical(value):
    """Keeps container types and key order, so a list where a tuple was or a reordered dict is a difference."""
    if dataclasses.is_dataclass(value):
        return {type(value).__name__: [[f.name, _canonical(getattr(value, f.name))] for f in dataclasses.fields(value)]}
    if isinstance(value, dict):
        return {"dict": [[_canonical(key), _canonical(item)] for key, item in value.items()]}
    if isinstance(value, tuple):
        return {"tuple": [_canonical(item) for item in value]}
    if isinstance(value, list):
        return {"list": [_canonical(item) for item in value]}
    if isinstance(value, (frozenset, set)):
        return {type(value).__name__: sorted(_canonical(item) for item in value)}
    if value is None or isinstance(value, (bool, str)):
        return value
    return {type(value).__name__: value}


def snapshot() -> dict:
    gpus = (*catalog.EVERY_GPU, "nvidia")
    return {
        "data": {name: _canonical(getattr(catalog, name)) for name in DATA_NAMES},
        "describe": {f"{gpu}/{device}": _canonical(catalog.describe(gpu, device)) for gpu in gpus for device in DEVICES},
    }


def test_catalog_data_matches_the_published_snapshot():
    assert snapshot() == json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _raw():
    return json.loads(catalog.CATALOG_PATH.read_text(encoding="utf-8"))


def _parsed(raw, tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return catalog._parse(catalog._read(path))


def test_catalog_file_lives_beside_the_plugin_not_inside_python_modules():
    plugin_root = Path(catalog.__file__).resolve().parents[2]
    assert catalog.CATALOG_PATH == plugin_root / "shared" / "upscalers" / "catalog.json"
    assert catalog.CATALOG_PATH.is_file()
    payload = (plugin_root / "scripts" / "copy-plugin-payload.mjs").read_text(encoding="utf-8")
    assert f'"{catalog.CATALOG_PATH.parent.relative_to(plugin_root).as_posix()}",' in payload


@pytest.mark.parametrize("change", [
    lambda raw: raw.update(schema_version=2),
    lambda raw: raw.update(unexpected=True),
    lambda raw: raw["builds"][0].update(unexpected=True),
    lambda raw: raw["builds"][0].pop("archive"),
    lambda raw: raw["builds"][0].update(replace={"a.dll": "missing-asset"}),
    lambda raw: raw["builds"].append(dict(raw["builds"][0])),
    lambda raw: raw["assets"][0].update(sha256="no"),
    lambda raw: raw["assets"][0].update(size=True),
    lambda raw: raw["preferred"].update(rdna2="missing-build"),
    lambda raw: raw["archives"].update(lsfg="missing-asset"),
])
def test_invalid_catalog_rejected(tmp_path, change):
    raw = _raw()
    change(raw)
    with pytest.raises(catalog.CatalogError):
        _parsed(raw, tmp_path)


def test_duplicate_key_rejected(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
    with pytest.raises(catalog.CatalogError, match="duplicate_key"):
        catalog._read(path)
