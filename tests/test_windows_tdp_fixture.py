import json
import unittest
from pathlib import Path

from device_profiles import DEVICE_TABLE

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "shared" / "fixtures" / "windows_tdp.json"


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


class WindowsTdpFixtureTests(unittest.TestCase):
    def test_fixture_matches_the_shared_catalog(self):
        for case in _cases():
            with self.subTest(case=case["id"]):
                profile = next(
                    profile
                    for profile in DEVICE_TABLE
                    if profile.key == case["profile"]
                )
                maximum = (
                    profile.tdp_max_charger
                    if case["external_power"]
                    else profile.tdp_max
                )
                target = min(
                    max(case["requested_watts"], profile.tdp_min),
                    maximum,
                )

                self.assertEqual("rog_xbox_ally_x", case["profile"])
                self.assertEqual(case["expected_target_watts"], target)


if __name__ == "__main__":
    unittest.main()
