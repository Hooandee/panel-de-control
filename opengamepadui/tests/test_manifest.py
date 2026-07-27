"""Contract tests for OpenGamepadUI package metadata."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PACKAGE_ROOT / "tests" / "fixtures" / "powerstation" / "ally-testing-44.json"
VALIDATOR_PATH = PACKAGE_ROOT / "scripts" / "validate_manifest.py"
VALID_MANIFEST = {
    "id": "panel-de-control",
    "name": "Panel de Control",
    "version": "0.1.0",
    "minimum_api_version": "2.0.0",
    "tags": ["quick-bar"],
    "description": "Read-only contract.",
    "license": "GPL-3.0-only",
}


class ManifestContractTests(unittest.TestCase):
    def test_package_includes_a_manifest(self):
        self.assertTrue((PACKAGE_ROOT / "plugin.json").is_file())

    def test_repository_manifest_has_the_stable_contract(self):
        manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual("panel-de-control", manifest["id"])
        self.assertEqual(
            (PACKAGE_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            manifest["version"],
        )
        self.assertEqual("2.0.0", manifest["minimum_api_version"])
        self.assertIn("quick-bar", manifest["tags"])
        self.assertNotIn("release", manifest)
        self.assertNotIn("publish", manifest)

    def test_neutral_ally_fixture_preserves_unknown_states(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(15, fixture["tdp"]["observed_limit_w"])
        self.assertEqual("ambiguous_zero", fixture["tdp"]["minimum_w"]["status"])
        self.assertEqual("ambiguous_zero", fixture["tdp"]["maximum_w"]["status"])
        self.assertEqual("unavailable", fixture["thermal"]["status"])
        self.assertEqual(800, fixture["gpu_clock"]["allowed_range_mhz"]["minimum"])
        self.assertEqual(2700, fixture["gpu_clock"]["allowed_range_mhz"]["maximum"])
        self.assertEqual("ambiguous", fixture["gpu_clock"]["manual"]["status"])


class ManifestValidatorTests(unittest.TestCase):
    def run_validator(self, manifest=VALID_MANIFEST, version="0.1.0"):
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = Path(temporary_directory)
            (package / "VERSION").write_text(version + "\n", encoding="utf-8")
            if manifest is not None:
                (package / "plugin.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR_PATH),
                    "--manifest",
                    str(package / "plugin.json"),
                    "--version-file",
                    str(package / "VERSION"),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

    def assert_invalid(self, manifest, expected_message, version="0.1.0"):
        result = self.run_validator(manifest, version)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(expected_message, result.stderr)

    def test_accepts_a_valid_temporary_contract(self):
        result = self.run_validator()
        self.assertEqual(0, result.returncode, result.stderr)

    def test_rejects_a_missing_manifest(self):
        self.assert_invalid(None, "manifest is missing")

    def test_rejects_an_unstable_id(self):
        manifest = {**VALID_MANIFEST, "id": "different-plugin"}
        self.assert_invalid(manifest, "id must be 'panel-de-control'")

    def test_rejects_a_version_that_does_not_match_version_file(self):
        self.assert_invalid(VALID_MANIFEST, "version must match VERSION", version="0.1.1")

    def test_rejects_an_incompatible_minimum_api_version(self):
        manifest = {**VALID_MANIFEST, "minimum_api_version": "1.0.0"}
        self.assert_invalid(manifest, "minimum_api_version must be '2.0.0'")

    def test_rejects_a_manifest_without_quick_bar(self):
        manifest = {**VALID_MANIFEST, "tags": ["performance"]}
        self.assert_invalid(manifest, "tags must include 'quick-bar'")

    def test_rejects_release_fields(self):
        for release_field in ("publish", "release"):
            with self.subTest(release_field=release_field):
                manifest = {**VALID_MANIFEST, release_field: {}}
                self.assert_invalid(
                    manifest,
                    f"unauthorized manifest fields: {release_field}",
                )


if __name__ == "__main__":
    unittest.main()
