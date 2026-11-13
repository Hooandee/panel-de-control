import dataclasses
import json
from pathlib import Path

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
