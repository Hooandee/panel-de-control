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
    "plugin.id": "panel-de-control",
    "plugin.name": "Panel de Control",
    "plugin.version": "0.1.0",
    "plugin.min-api-version": "2.0.0",
    "plugin.link": "https://github.com/Hooandee/panel-de-control",
    "plugin.source": "https://github.com/Hooandee/panel-de-control",
    "plugin.summary": "Read-only PowerStation status for OpenGamepadUI.",
    "plugin.description": (
        "Observes GPU identity, TDP, and power profile without applying performance changes."
    ),
    "entrypoint": "plugin.gd",
    "store.tags": ["quick-bar", "performance", "power"],
    "store.images": [],
    "author.name": "Hooandee",
}


class ManifestContractTests(unittest.TestCase):
    def test_package_includes_a_manifest(self):
        self.assertTrue((PACKAGE_ROOT / "plugin.json").is_file())

    def test_port_includes_the_complete_repository_license(self):
        self.assertEqual(
            (PACKAGE_ROOT.parent / "LICENSE").read_bytes(),
            (PACKAGE_ROOT / "LICENSE").read_bytes(),
        )

    def test_repository_manifest_has_the_stable_contract(self):
        manifest = json.loads((PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))

        self.assertEqual("panel-de-control", manifest["plugin.id"])
        self.assertEqual(
            (PACKAGE_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            manifest["plugin.version"],
        )
        self.assertEqual("2.0.0", manifest["plugin.min-api-version"])
        self.assertEqual("plugin.gd", manifest["entrypoint"])
        self.assertEqual(
            ["quick-bar", "performance", "power"],
            manifest["store.tags"],
        )
        self.assertEqual([], manifest["store.images"])
        self.assertEqual("Hooandee", manifest["author.name"])
        for field in ("plugin.link", "plugin.source"):
            self.assertEqual("https://github.com/Hooandee/panel-de-control", manifest[field])
        self.assertTrue(manifest["plugin.summary"])
        self.assertTrue(manifest["plugin.description"])
        self.assertEqual(VALID_MANIFEST["plugin.summary"], manifest["plugin.summary"])
        self.assertEqual(VALID_MANIFEST["plugin.description"], manifest["plugin.description"])
        self.assertNotIn("controls", manifest["plugin.description"].lower())
        self.assertNotIn("release", manifest)
        self.assertNotIn("publish", manifest)
        self.assertNotIn("versions", manifest)
        self.assertNotIn("archive", manifest)

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
        manifest = {**VALID_MANIFEST, "plugin.id": "different-plugin"}
        self.assert_invalid(manifest, "plugin.id must be 'panel-de-control'")

    def test_rejects_a_version_that_does_not_match_version_file(self):
        self.assert_invalid(
            VALID_MANIFEST,
            "plugin.version must match VERSION",
            version="0.1.1",
        )

    def test_rejects_an_incompatible_minimum_api_version(self):
        manifest = {**VALID_MANIFEST, "plugin.min-api-version": "1.0.0"}
        self.assert_invalid(manifest, "plugin.min-api-version must be '2.0.0'")

    def test_rejects_empty_tags(self):
        manifest = {**VALID_MANIFEST, "store.tags": []}
        self.assert_invalid(
            manifest,
            "store.tags must be a non-empty list of non-empty strings",
        )

    def test_rejects_blank_tags(self):
        manifest = {**VALID_MANIFEST, "store.tags": ["performance", ""]}
        self.assert_invalid(
            manifest,
            "store.tags must be a non-empty list of non-empty strings",
        )

    def test_rejects_missing_overlay_discovery_tag(self):
        manifest = {**VALID_MANIFEST, "store.tags": ["performance", "power"]}
        self.assert_invalid(
            manifest,
            "store.tags must include 'quick-bar' for OGUI overlay discovery",
        )

    def test_rejects_release_fields(self):
        release_manifests = {
            "publish": {**VALID_MANIFEST, "publish": {}},
            "release": {**VALID_MANIFEST, "release": {}},
            "archive.url": {**VALID_MANIFEST, "archive.url": "https://example.invalid"},
            "archive.sha256": {**VALID_MANIFEST, "archive.sha256": "a" * 64},
            "versions": {**VALID_MANIFEST, "versions": []},
        }
        for release_field, manifest in release_manifests.items():
            with self.subTest(release_field=release_field):
                self.assert_invalid(
                    manifest,
                    f"unauthorized manifest field: {release_field}",
                )


if __name__ == "__main__":
    unittest.main()
