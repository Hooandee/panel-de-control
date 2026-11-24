"""Newest-release cases shared with the Windows port (windows/tests/PanelDeControl.Core.Tests/Upscalers/LatestReleasesTests.cs).

Both sides replay the same fake GitHub answers at the same clock readings and must pick the same asset.
"""

import json
from pathlib import Path

import pytest

from upscalers import latest
from upscalers.catalog import Asset, Track

FIXTURE = json.loads((Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "latest_releases.json").read_text(encoding="utf-8"))
CASES = {case["id"]: case for case in FIXTURE["cases"]}
PINNED = FIXTURE["pinned"]


def _pinned() -> Asset:
    return Asset(PINNED["id"], PINNED["filename"], PINNED["sha256"], PINNED["size"], (PINNED["url"],), archive=True)


@pytest.mark.parametrize("case_id", CASES)
def test_pick_matches_the_shared_cases(case_id, tmp_path, monkeypatch):
    case = CASES[case_id]
    track = {**FIXTURE["track"], **case.get("track", {})}
    monkeypatch.setitem(latest.TRACKS, PINNED["id"], Track(track["repo"], track["name"], track["prerelease"]))
    clock = [FIXTURE["base_clock"]]
    answer = [None]
    requested = []

    def fetch(url):
        requested.append(url)
        if answer[0] is None:
            raise OSError("offline")
        return json.dumps(answer[0]).encode()

    resolver = latest.Resolver(tmp_path, fetch=fetch, clock=lambda: clock[0])
    for step in case["steps"]:
        clock[0] = FIXTURE["base_clock"] + step["at"]
        answer[0] = step["response"]
        before = len(requested)
        picked = resolver.resolve(_pinned())
        assert (len(requested) - before == 1) == step["fetched"]
        assert requested[before:] in ([], [FIXTURE["api_url"]])
        expected = step["expected"]
        if expected.get("pinned"):
            assert picked == _pinned()
            continue
        assert (picked.filename, picked.sha256, picked.size, list(picked.urls)) == (
            expected["filename"], expected["sha256"], expected["size"], expected["urls"])
        assert (picked.archive, picked.id) == (True, PINNED["id"])
        assert resolver.version(picked) == expected["version"]


def test_untracked_asset_is_never_looked_up(tmp_path):
    resolver = latest.Resolver(tmp_path, fetch=lambda url: pytest.fail("no lookup expected"))
    other = Asset("not-tracked", "x.zip", "1" * 64, 1, ("https://example.com/x.zip",))
    assert resolver.resolve(other) is other
    assert not resolver.tracked(other)


def test_the_catalog_tracks_load_as_data():
    from upscalers import catalog

    assert catalog.TRACKS["optiscaler-10-nightly"] == Track("optiscaler/OptiScaler-nightly", r"OptiScaler_v10\.\d+\.\d+[^/]*\.7z", True)
    assert catalog.TRACKS["optiscaler-0.9.4"].prerelease is False
    assert latest.TRACKS is catalog.TRACKS
