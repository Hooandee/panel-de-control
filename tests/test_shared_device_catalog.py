import json
import sys
from pathlib import Path

import pytest

from device_profiles import DEVICE_TABLE
from device_registry import detect

ROOT = Path(__file__).parents[1]
DEVICES_DIR = ROOT / "shared" / "devices"
sys.path.insert(0, str(ROOT / "scripts"))

import export_device_catalog  # noqa: E402


def _catalog():
    return json.loads((DEVICES_DIR / "catalog.json").read_text(encoding="utf-8"))


def _cases():
    return json.loads((DEVICES_DIR / "catalog_cases.json").read_text(encoding="utf-8"))["cases"]


def _normalise(value):
    return (value or "").strip().casefold()


def _catalog_match(catalog, product_name, sys_vendor, board_name):
    for profile in catalog["profiles"]:
        if profile["dmi_matches"]:
            for match in profile["dmi_matches"]:
                if match["product_name"] is not None and _normalise(product_name) != _normalise(match["product_name"]):
                    continue
                if _normalise(sys_vendor) != _normalise(match["sys_vendor"]):
                    continue
                boards = {_normalise(board) for board in match["board_names"]}
                if not boards or _normalise(board_name) in boards:
                    return profile["key"]
            continue
        name = (product_name or "").lower()
        if any(needle.lower() in name for needle in profile["match_names"]):
            return profile["key"]
    return catalog["generic"]["key"]


def _detect(tmp_path, product_name, sys_vendor, board_name):
    dmi = tmp_path / "sys/class/dmi/id"
    dmi.mkdir(parents=True, exist_ok=True)
    (dmi / "product_name").write_text(product_name)
    (dmi / "sys_vendor").write_text(sys_vendor)
    (dmi / "board_name").write_text(board_name)
    return detect(root=str(tmp_path)).key


def test_committed_catalog_matches_device_table():
    assert (DEVICES_DIR / "catalog.json").read_text(encoding="utf-8") == export_device_catalog.render_catalog()


def test_catalog_preserves_table_order():
    assert [profile["key"] for profile in _catalog()["profiles"]] == [profile.key for profile in DEVICE_TABLE]


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["id"])
def test_shared_cases_match_linux_detection_and_catalog(case, tmp_path):
    inputs = case["input"]
    expected = case["expected"]["key"]
    assert _detect(tmp_path, inputs["product_name"], inputs["sys_vendor"], inputs["board_name"]) == expected
    assert _catalog_match(_catalog(), inputs["product_name"], inputs["sys_vendor"], inputs["board_name"]) == expected


def test_catalog_matcher_agrees_with_linux_for_every_table_identity(tmp_path):
    catalog = _catalog()
    identities = []
    for profile in DEVICE_TABLE:
        identities.extend((needle, "", "") for needle in profile.match_names)
        for match in profile.dmi_matches:
            boards = match.board_names or ("",)
            identities.extend((match.product_name or "", match.sys_vendor, board) for board in boards)
    for index, identity in enumerate(identities):
        root = tmp_path / str(index)
        assert _catalog_match(catalog, *identity) == _detect(root, *identity), identity
