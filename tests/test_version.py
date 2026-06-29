import json
import pathlib

from version import read_version  # py_modules is on sys.path via conftest.py


def test_version_matches_package_json():
    pkg = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "package.json").read_text()
    )
    assert read_version() == pkg["version"]
