import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest
import zipfile


PLUGIN_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLUGIN_DIR.parent
CONFIGURE_EXPORT = PLUGIN_DIR / "scripts" / "configure_export.py"
VALIDATE_PACKAGE = PLUGIN_DIR / "scripts" / "validate_package.py"
INSTALL_TO_DEVICE = PLUGIN_DIR / "scripts" / "install_to_device.sh"
EXPORT_PRESET = PLUGIN_DIR / "export_presets.cfg"
OGUI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "opengamepadui-ci.yml"
DECKY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
WINDOWS_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "windows-ci.yml"
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "release-please.yml"
RELEASE_PLEASE_CONFIG = REPOSITORY_ROOT / "release-please-config.json"
RELEASE_PLEASE_MANIFEST = REPOSITORY_ROOT / ".release-please-manifest.json"


def _manifest(version: str) -> dict[str, object]:
    return {
        "plugin.id": "panel-de-control",
        "plugin.name": "Panel de Control",
        "plugin.version": version,
        "plugin.min-api-version": "2.0.0",
        "plugin.link": "https://github.com/Hooandee/panel-de-control",
        "plugin.source": "https://github.com/Hooandee/panel-de-control",
        "plugin.summary": "Read-only PowerStation status for OpenGamepadUI.",
        "plugin.description": (
            "Observes GPU identity, TDP, and power profile without applying "
            "performance changes."
        ),
        "entrypoint": "plugin.gd",
        "store.tags": ["quick-bar", "performance", "power"],
        "store.images": [],
        "author.name": "Hooandee",
    }


def _run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        **kwargs,
    )


def _preset_blocks(contents: str) -> list[str]:
    return re.findall(
        r"(?ms)^\[preset\.\d+\]\n.*?(?=^\[preset\.\d+\]\n|\Z)",
        contents,
    )


def _named_preset(contents: str, name: str) -> str:
    for block in _preset_blocks(contents):
        if f'name="{name}"' in block:
            return block
    raise AssertionError(f"Preset not found: {name}")


def _event_paths(contents: str, event: str) -> list[str]:
    event_body = _event_body(contents, event)
    paths_match = re.search(
        r"(?m)^    paths:\n(?P<paths>(?:      - [^\n]*\n)+)",
        event_body,
    )
    if paths_match is None:
        raise AssertionError(f"Positive paths not found for: {event}")
    return [
        line.strip()[2:].strip('"')
        for line in paths_match.group("paths").splitlines()
    ]


def _event_body(contents: str, event: str) -> str:
    event_match = re.search(
        rf"(?ms)^  {re.escape(event)}:\n(?P<body>.*?)(?=^  [a-z_]+:|\npermissions:)",
        contents,
    )
    if event_match is None:
        raise AssertionError(f"Workflow event not found: {event}")
    return event_match.group("body")


def _filter_paths(contents: str, filter_name: str) -> list[str]:
    filter_match = re.search(
        rf"(?ms)^            {re.escape(filter_name)}:\n"
        r"(?P<paths>(?:              - [^\n]*\n)+)",
        contents,
    )
    if filter_match is None:
        raise AssertionError(f"Workflow filter not found: {filter_name}")
    return [
        line.strip()[2:].strip("'\"")
        for line in filter_match.group("paths").splitlines()
    ]


def _job_body(contents: str, job_name: str) -> str:
    job_match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n"
        r"(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        contents,
    )
    if job_match is None:
        raise AssertionError(f"Workflow job not found: {job_name}")
    return job_match.group("body")


def _job_steps(contents: str, job_name: str) -> list[str]:
    return re.findall(
        r"(?ms)^      - (?P<step>.*?)(?=^      - |\Z)",
        _job_body(contents, job_name),
    )


def _matches(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        expression = re.escape(pattern)
        expression = expression.replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
        if re.fullmatch(expression, path):
            return True
    return False


def _matches_every(path: str, patterns: list[str]) -> bool:
    return all(
        not _matches(path, [pattern[1:]])
        if pattern.startswith("!")
        else _matches(path, [pattern])
        for pattern in patterns
    )


class ConfigureExportTests(unittest.TestCase):
    def test_adds_limited_linux_preset_without_changing_existing_preset(self) -> None:
        existing = """[preset.0]

name="Existing"
platform="Linux"

[preset.0.options]

binary_format/architecture="x86_64"
"""
        with tempfile.TemporaryDirectory() as directory:
            ogui_dir = Path(directory)
            presets = ogui_dir / "export_presets.cfg"
            presets.write_text(existing, encoding="utf-8")

            result = _run(
                "python3",
                str(CONFIGURE_EXPORT),
                "--ogui-dir",
                str(ogui_dir),
                "--template",
                str(EXPORT_PRESET),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            configured = presets.read_text(encoding="utf-8")
            self.assertIn(existing.strip(), configured)
            plugin_preset = _named_preset(configured, "Panel de Control")
            self.assertIn('platform="Linux"', plugin_preset)
            self.assertIn('export_filter="resources"', plugin_preset)
            self.assertIn('include_filter="plugins/panel-de-control/*"', plugin_preset)
            self.assertIn("script_export_mode=2", plugin_preset)
            self.assertIn("plugins/panel-de-control/.agents/*", plugin_preset)
            self.assertIn("plugins/panel-de-control/.notes/*", plugin_preset)
            self.assertIn("plugins/panel-de-control/AGENTS.md", plugin_preset)

    def test_repeated_configuration_is_byte_for_byte_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ogui_dir = Path(directory)
            presets = ogui_dir / "export_presets.cfg"
            presets.write_text(
                '[preset.0]\n\nname="Existing"\n\n[preset.0.options]\n',
                encoding="utf-8",
            )
            command = (
                "python3",
                str(CONFIGURE_EXPORT),
                "--ogui-dir",
                str(ogui_dir),
                "--template",
                str(EXPORT_PRESET),
            )

            first = _run(*command)
            self.assertEqual(first.returncode, 0, first.stderr)
            once = presets.read_bytes()
            second = _run(*command)

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(presets.read_bytes(), once)

    def test_replaces_outdated_plugin_preset_without_duplicate(self) -> None:
        outdated = """[preset.0]

name="Panel de Control"
platform="Linux/X11"
include_filter="plugins/wrong/*"

[preset.0.options]

script_export_mode=1

[preset.1]

name="Keep Me"
platform="Linux"

[preset.1.options]
"""
        with tempfile.TemporaryDirectory() as directory:
            ogui_dir = Path(directory)
            presets = ogui_dir / "export_presets.cfg"
            presets.write_text(outdated, encoding="utf-8")

            result = _run(
                "python3",
                str(CONFIGURE_EXPORT),
                "--ogui-dir",
                str(ogui_dir),
                "--template",
                str(EXPORT_PRESET),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            configured = presets.read_text(encoding="utf-8")
            self.assertEqual(configured.count('name="Panel de Control"'), 1)
            self.assertIn('name="Keep Me"', configured)
            plugin_preset = _named_preset(configured, "Panel de Control")
            self.assertIn('platform="Linux"', plugin_preset)
            self.assertNotIn("Linux/X11", plugin_preset)


class PackageValidationTests(unittest.TestCase):
    def _source(
        self,
        directory: Path,
        version: str = "0.1.0",
        *,
        import_source: str = (
            "res://plugins/panel-de-control/assets/icon.svg"
        ),
        import_path: str = (
            "res://.godot/imported/icon.svg-test.ctex"
        ),
        import_destination: str = (
            "res://.godot/imported/icon.svg-test.ctex"
        ),
    ) -> Path:
        source = directory / "source"
        source.mkdir()
        (source / "VERSION").write_text(f"{version}\n", encoding="utf-8")
        (source / "plugin.json").write_text(
            json.dumps(_manifest(version)),
            encoding="utf-8",
        )
        (source / "LICENSE").write_bytes(b"complete test license\n")
        (source / "core").mkdir()
        (source / "core" / "feature.gd").write_text(
            "extends RefCounted\n",
            encoding="utf-8",
        )
        (source / "core" / "menu.tscn").write_text(
            '[gd_scene format=3]\n',
            encoding="utf-8",
        )
        assets = source / "assets"
        assets.mkdir()
        (assets / "icon.svg").write_text("<svg/>", encoding="utf-8")
        (assets / "icon.svg.import").write_text(
            (
                "[remap]\n\n"
                'importer="texture"\n'
                'type="CompressedTexture2D"\n'
                f'path="{import_path}"\n\n'
                "[deps]\n\n"
                f'source_file="{import_source}"\n'
                f'dest_files=["{import_destination}"]\n'
            ),
            encoding="utf-8",
        )
        return source

    def _package(
        self,
        directory: Path,
        *,
        version: str = "0.1.0",
        extra_entries: tuple[str, ...] = (),
        include_compiled_entrypoint: bool = True,
        include_compiled_dependency: bool = True,
        include_imported_texture: bool = True,
        include_license: bool = True,
        manifest: dict[str, object] | None = None,
    ) -> Path:
        package = directory / "panel-de-control.zip"
        package_manifest = _manifest(version) if manifest is None else manifest
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "plugins/panel-de-control/plugin.json",
                json.dumps(package_manifest),
            )
            if include_license:
                archive.writestr(
                    "plugins/panel-de-control/LICENSE",
                    b"complete test license\n",
                )
            if include_compiled_entrypoint:
                archive.writestr("plugins/panel-de-control/plugin.gdc", b"compiled")
                archive.writestr(
                    "plugins/panel-de-control/plugin.gd.remap",
                    b'[remap]\npath="plugin.gdc"\n',
                )
            if include_compiled_dependency:
                archive.writestr(
                    "plugins/panel-de-control/core/feature.gdc",
                    b"compiled dependency",
                )
                archive.writestr(
                    "plugins/panel-de-control/core/feature.gd.remap",
                    b'[remap]\npath="feature.gdc"\n',
                )
            archive.writestr(
                "plugins/panel-de-control/core/menu.tscn.remap",
                b'[remap]\npath="menu.scn"\n',
            )
            archive.writestr(
                ".godot/exported/42/power_status_menu.scn",
                b"compiled scene",
            )
            archive.writestr("icudt_godot.dat", b"Godot ICU data")
            archive.writestr(
                "plugins/panel-de-control/assets/icon.svg.import",
                (
                    "[remap]\n\n"
                    'importer="texture"\n'
                    'type="CompressedTexture2D"\n'
                    'path="res://.godot/imported/icon.svg-test.ctex"\n'
                    "\0"
                ).encode(),
            )
            if include_imported_texture:
                archive.writestr(
                    ".godot/imported/icon.svg-test.ctex",
                    b"imported texture",
                )
            for entry in extra_entries:
                archive.writestr(entry, b"forbidden")
        return package

    def test_validates_installable_pack_and_writes_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(root)

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            hash_file = root / "panel-de-control.zip.sha256"
            digest, filename = hash_file.read_text(encoding="ascii").split()
            self.assertEqual(filename, "panel-de-control.zip")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertEqual(
                digest,
                hashlib.sha256(package.read_bytes()).hexdigest(),
            )

    def test_rejects_incomplete_manifest_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(
                root,
                manifest={
                    "plugin.id": "panel-de-control",
                    "plugin.version": "0.1.0",
                    "plugin.min-api-version": "2.0.0",
                    "entrypoint": "plugin.gd",
                },
            )

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing manifest fields", result.stderr)

    def test_rejects_package_without_license(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(root, include_license=False)

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("license", result.stderr.lower())

    def test_rejects_package_with_tests_or_private_sources(self) -> None:
        forbidden_entries = (
            "plugins/panel-de-control/tests/unit/test_plugin.gdc",
            "plugins/panel-de-control/.superpowers/report.md",
            "plugins/panel-de-control/.pdc/INDEX.md",
            "plugins/panel-de-control/.agents/private.md",
            "plugins/panel-de-control/.notes/investigation.md",
            "plugins/panel-de-control/AGENTS.md",
            "plugins/panel-de-control/core/uncompiled.gd",
            "plugins/panel-de-control/core/uncompiled.tscn",
            "plugins/panel-de-control/scripts/validate_package.py",
        )
        for forbidden in forbidden_entries:
            with self.subTest(forbidden=forbidden):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = self._source(root)
                    package = self._package(root, extra_entries=(forbidden,))

                    result = _run(
                        "python3",
                        str(VALIDATE_PACKAGE),
                        "--package",
                        str(package),
                        "--source",
                        str(source),
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(forbidden, result.stderr)

    def test_rejects_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root, version="0.1.0")
            package = self._package(root, version="9.9.9")

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("plugin.version must match VERSION", result.stderr)

    def test_rejects_pack_without_compiled_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(root, include_compiled_entrypoint=False)

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("compiled entrypoint", result.stderr.lower())

    def test_rejects_pack_without_a_compiled_production_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(root, include_compiled_dependency=False)

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("compiled script", result.stderr.lower())

    def test_rejects_pack_without_referenced_imported_texture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            package = self._package(root, include_imported_texture=False)

            result = _run(
                "python3",
                str(VALIDATE_PACKAGE),
                "--package",
                str(package),
                "--source",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("imported texture", result.stderr.lower())

    def test_rejects_invalid_icon_import_contract(self) -> None:
        cases = (
            {
                "import_source": "res://assets/wrong.svg",
                "expected": "source_file",
            },
            {
                "import_path": "res://outside/icon.ctex",
                "expected": "path",
            },
            {
                "import_destination": "res://outside/icon.ctex",
                "expected": "dest_files",
            },
        )
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source_args = {
                        key: value
                        for key, value in case.items()
                        if key != "expected"
                    }
                    source = self._source(root, **source_args)
                    package = self._package(root)

                    result = _run(
                        "python3",
                        str(VALIDATE_PACKAGE),
                        "--package",
                        str(package),
                        "--source",
                        str(source),
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(case["expected"], result.stderr)


class InstallScriptTests(unittest.TestCase):
    def _fake_remote_commands(self, root: Path) -> tuple[Path, dict[str, str]]:
        calls = root / "remote-calls"
        fake_bin = root / "bin"
        fake_bin.mkdir()
        for command in ("ssh", "scp"):
            executable = fake_bin / command
            executable.write_text(
                (
                    "#!/bin/sh\n"
                    f"printf '{command}\\n' >> \"$REMOTE_CALLS\"\n"
                    "printf '%s\\n' \"$@\" >> \"$REMOTE_CALLS\"\n"
                ),
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        environment["REMOTE_CALLS"] = str(calls)
        return calls, environment

    def test_creates_plugin_directory_then_copies_only_requested_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "panel-de-control.zip"
            package.write_bytes(b"package")
            calls, environment = self._fake_remote_commands(root)

            result = _run(
                "bash",
                str(INSTALL_TO_DEVICE),
                "--host",
                "192.0.2.10",
                "--user",
                "deck",
                "--package",
                str(package),
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                [
                    "ssh",
                    "deck@192.0.2.10",
                    "mkdir -p .local/share/opengamepadui/plugins",
                    "scp",
                    str(package),
                    "deck@192.0.2.10:.local/share/opengamepadui/plugins/"
                    "panel-de-control.zip",
                ],
            )

    def test_brackets_ipv6_host_for_scp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "panel-de-control.zip"
            package.write_bytes(b"package")
            calls, environment = self._fake_remote_commands(root)

            result = _run(
                "bash",
                str(INSTALL_TO_DEVICE),
                "--host",
                "2001:db8::10",
                "--user",
                "deck",
                "--package",
                str(package),
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                [
                    "ssh",
                    "deck@2001:db8::10",
                    "mkdir -p .local/share/opengamepadui/plugins",
                    "scp",
                    str(package),
                    "deck@[2001:db8::10]:.local/share/opengamepadui/plugins/"
                    "panel-de-control.zip",
                ],
            )


class BuildContractTests(unittest.TestCase):
    def test_icon_import_sidecar_is_reproducible_and_versioned(self) -> None:
        sidecar = PLUGIN_DIR / "assets" / "icon.svg.import"
        contents = sidecar.read_text(encoding="utf-8")
        tracked = _run(
            "git",
            "-c",
            f"safe.directory={REPOSITORY_ROOT}",
            "ls-files",
            "--error-unmatch",
            sidecar.relative_to(REPOSITORY_ROOT).as_posix(),
            cwd=REPOSITORY_ROOT,
        )

        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        self.assertIn('uid="uid://dch0ypnin4gvi"', contents)
        self.assertIn(
            'source_file="res://plugins/panel-de-control/assets/icon.svg"',
            contents,
        )

    def test_dist_invokes_godot_export_pack_for_the_fixed_archive_name(self) -> None:
        result = _run(
            "make",
            "--dry-run",
            "--file",
            str(PLUGIN_DIR / "Makefile"),
            "dist",
            "OGUI_DIR=/tmp/OpenGamepadUI",
            "GODOT=/opt/godot",
            cwd=PLUGIN_DIR,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/opt/godot --headless", result.stdout)
        self.assertIn("--export-pack", result.stdout)
        self.assertIn('"Panel de Control"', result.stdout)
        self.assertIn("dist/panel-de-control.zip", result.stdout)
        self.assertNotRegex(result.stdout, r"(^|\s)zip(\s|$)")

    def test_smoke_target_loads_pack_without_source_symlink(self) -> None:
        result = _run(
            "make",
            "--dry-run",
            "--file",
            str(PLUGIN_DIR / "Makefile"),
            "smoke",
            "OGUI_DIR=/tmp/OpenGamepadUI",
            "GODOT=/opt/godot",
            cwd=PLUGIN_DIR,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("package_smoke.gd", result.stdout)
        self.assertIn("panel-de-control.zip", result.stdout)
        self.assertIn("--log-file", result.stdout)
        self.assertIn("dist/package-smoke.log", result.stdout)
        self.assertIn("unlink", result.stdout)
        self.assertIn("trap", result.stdout)


class WorkflowIsolationTests(unittest.TestCase):
    def test_decky_classifier_routes_platform_and_mixed_changes(self) -> None:
        decky = DECKY_WORKFLOW.read_text(encoding="utf-8")
        ogui = OGUI_WORKFLOW.read_text(encoding="utf-8")
        windows = WINDOWS_WORKFLOW.read_text(encoding="utf-8")
        decky_paths = _filter_paths(decky, "decky")

        self.assertEqual(
            decky_paths,
            [
                "**",
                "!opengamepadui/**",
                "!.github/workflows/opengamepadui-ci.yml",
                "!windows/**",
                "!.github/workflows/windows-ci.yml",
                "!themes/gallery/**",
                "!scripts/package-theme.mjs",
                "!scripts/check-theme-version.mjs",
                "!scripts/build-theme-publication.mjs",
                "!scripts/resolve-theme-panel-minimum.mjs",
                "!scripts/promote-theme-pages.mjs",
                "!scripts/stage-theme-pages.mjs",
                "!scripts/theme-publication-contract.mjs",
                "!scripts/verify-theme-pages.mjs",
                "!scripts/verify-theme-pages-governance.mjs",
                "!tests/themePackaging.test.ts",
                "!tests/themeVersioning.test.ts",
                "!tests/themeWorkflow.test.ts",
                "!tests/galleryPackage.test.ts",
                "!tests/themePagesPromote.test.ts",
                "!tests/themePagesStage.test.ts",
                "!tests/themePagesVerify.test.ts",
                "!tests/themePagesGovernance.test.ts",
                "!tests/themePublicationBuild.test.ts",
                "!tests/themePanelMinimum.test.ts",
                "!tests/themePublicationContract.test.ts",
                "!.github/workflows/_theme-package.yml",
                "!.github/workflows/_theme-promote.yml",
                "!.github/workflows/_theme-stage.yml",
                "!.github/workflows/theme-gallery.yml",
                "!.github/workflows/theme-gallery-promote.yml",
                "!.github/workflows/theme-gallery-stage.yml",
            ],
        )
        self.assertIn("predicate-quantifier: every", decky)

        for event in ("push", "pull_request"):
            ogui_paths = _event_paths(ogui, event)
            windows_paths = _event_paths(windows, event)

            self.assertNotIn("paths:", _event_body(decky, event))
            self.assertTrue(_matches("opengamepadui/plugin.gd", ogui_paths))
            self.assertFalse(_matches("src/index.tsx", ogui_paths))
            self.assertTrue(
                _matches(".github/workflows/opengamepadui-ci.yml", ogui_paths)
            )
            self.assertTrue(_matches("windows/PanelDeControl.sln", windows_paths))
            self.assertTrue(_matches("shared/fixtures/auto_tdp.json", windows_paths))
            self.assertFalse(_matches("src/index.tsx", windows_paths))
            self.assertTrue(
                _matches(".github/workflows/windows-ci.yml", windows_paths)
            )

        self.assertRegex(
            windows,
            r"python -m unittest\s+"
            r"opengamepadui\.tests\.test_package\.WorkflowIsolationTests",
        )

        cases = (
            (["opengamepadui/plugin.gd"], False),
            (["opengamepadui/plugin.json"], False),
            ([".github/workflows/opengamepadui-ci.yml"], False),
            (["windows/PanelDeControl.sln"], False),
            ([".github/workflows/windows-ci.yml"], False),
            (["shared/fixtures/auto_tdp.json"], True),
            (["themes/gallery/theme.json"], False),
            (["themes/bundled/hooandee-gallery/0.7.8/gallery.zip"], True),
            (["scripts/package-theme.mjs"], False),
            (["scripts/check-theme-version.mjs"], False),
            (["scripts/build-theme-publication.mjs"], False),
            (["scripts/resolve-theme-panel-minimum.mjs"], False),
            (["scripts/promote-theme-pages.mjs"], False),
            (["scripts/stage-theme-pages.mjs"], False),
            (["scripts/theme-publication-contract.mjs"], False),
            (["scripts/verify-theme-pages.mjs"], False),
            (["scripts/verify-theme-pages-governance.mjs"], False),
            (["tests/themePackaging.test.ts"], False),
            (["tests/themeVersioning.test.ts"], False),
            (["tests/themeWorkflow.test.ts"], False),
            (["tests/galleryPackage.test.ts"], False),
            (["tests/themePagesPromote.test.ts"], False),
            (["tests/themePagesStage.test.ts"], False),
            (["tests/themePagesVerify.test.ts"], False),
            (["tests/themePagesGovernance.test.ts"], False),
            (["tests/themePublicationBuild.test.ts"], False),
            (["tests/themePanelMinimum.test.ts"], False),
            (["tests/themePublicationContract.test.ts"], False),
            ([".github/workflows/_theme-package.yml"], False),
            ([".github/workflows/_theme-promote.yml"], False),
            ([".github/workflows/_theme-stage.yml"], False),
            ([".github/workflows/theme-gallery.yml"], False),
            ([".github/workflows/theme-gallery-promote.yml"], False),
            ([".github/workflows/theme-gallery-stage.yml"], False),
            (["src/index.tsx"], True),
            (["opengamepadui/plugin.gd", "src/index.tsx"], True),
            (["windows/PanelDeControl.sln", "src/index.tsx"], True),
            (["themes/gallery/theme.json", "src/themes/catalog.ts"], True),
            (["themes/gallery/theme.json", "opengamepadui/plugin.gd"], False),
            (["conftest.py"], True),
            (["plugin.json"], True),
            (["release-please-config.json"], True),
            ([".github/workflows/release-please.yml"], True),
            ([".github/workflows/prerelease.yml"], True),
            (["README.md"], True),
            (["future-root-config.toml"], True),
            ([".github/workflows/ci.yml"], True),
        )
        for changed_paths, expected_decky in cases:
            with self.subTest(changed_paths=changed_paths):
                self.assertEqual(
                    any(_matches_every(path, decky_paths) for path in changed_paths),
                    expected_decky,
                )

    def test_decky_required_jobs_report_without_running_expensive_ogui_steps(
        self,
    ) -> None:
        workflow = DECKY_WORKFLOW.read_text(encoding="utf-8")

        changes = _job_body(workflow, "changes")
        self.assertIn("decky: ${{ steps.filter.outputs.decky }}", changes)

        for job_name in ("backend-tests", "frontend-build"):
            job = _job_body(workflow, job_name)
            header = job.split("steps:", maxsplit=1)[0]
            self.assertIn("needs: changes", header)
            self.assertIn("if: ${{ always() }}", header)

            steps = _job_steps(workflow, job_name)
            guards = [
                step
                for step in steps
                if "Require successful path classification" in step
            ]
            skipped = [step for step in steps if "Decky paths unchanged" in step]
            expensive = [
                step for step in steps if step not in guards and step not in skipped
            ]
            self.assertEqual(len(guards), 1)
            self.assertIn("needs.changes.result != 'success'", guards[0])
            self.assertIn(
                "needs.changes.outputs.decky != 'true'",
                guards[0],
            )
            self.assertIn(
                "needs.changes.outputs.decky != 'false'",
                guards[0],
            )
            self.assertRegex(guards[0], r"(?m)^\s*exit 1$")
            self.assertEqual(len(skipped), 1)
            self.assertIn(
                "if: needs.changes.outputs.decky == 'false'",
                skipped[0],
            )
            self.assertGreater(len(expensive), 0)
            for step in expensive:
                self.assertIn(
                    "if: needs.changes.outputs.decky == 'true'",
                    step,
                )

    def test_decky_classifier_is_pinned_and_read_only(self) -> None:
        workflow = DECKY_WORKFLOW.read_text(encoding="utf-8")
        changes = _job_body(workflow, "changes")
        workflow_permissions = workflow.split("concurrency:", maxsplit=1)[0]

        self.assertIn("contents: read", workflow)
        self.assertNotIn("pull-requests:", workflow_permissions)
        self.assertIn("permissions:", changes)
        self.assertIn("contents: read", changes)
        self.assertIn("pull-requests: read", changes)
        self.assertNotRegex(workflow, r"(?m)^\s+[a-z-]+: write$")
        self.assertRegex(
            changes,
            r"actions/checkout@[0-9a-f]{40}",
        )
        self.assertIn("persist-credentials: false", changes)
        self.assertRegex(
            changes,
            r"(?m)^\s*uses: dorny/paths-filter@[0-9a-f]{40}(?:\s+#.*)?$",
        )
        self.assertNotRegex(workflow, r"(?m)^\s*(release|tags):")

    def test_ogui_ci_is_read_only_pinned_and_artifact_only(self) -> None:
        workflow = OGUI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("contents: read", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("b149644f46b71e175a2ad223e84c18361596691e", workflow)
        self.assertIn(
            "ghcr.io/shadowblip/opengamepadui-builder:4.7.1"
            "@sha256:d1f816502509e00f931e93b60fac570b"
            "c8ab757b694b68d450de7cf191b5e005",
            workflow,
        )
        self.assertIn("apt-get install -y --no-install-recommends python3", workflow)
        self.assertNotIn("repository: bitwes/Gut", workflow)
        self.assertNotIn("gut-source", workflow)
        export_step = workflow.index("Export installable plugin pack")
        smoke_step = workflow.index("Smoke test exported resource pack")
        upload_step = workflow.index("Upload installable plugin")
        self.assertLess(export_step, smoke_step)
        self.assertLess(smoke_step, upload_step)
        self.assertIn("make -C opengamepadui smoke", workflow)
        self.assertRegex(
            workflow,
            r"actions/upload-artifact@[0-9a-f]{40}",
        )
        self.assertIn("if-no-files-found: error", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s*(release|tags):")

    def test_release_please_excludes_unpublished_platforms(self) -> None:
        config = json.loads(RELEASE_PLEASE_CONFIG.read_text(encoding="utf-8"))
        root_package = config["packages"]["."]
        manifest = json.loads(RELEASE_PLEASE_MANIFEST.read_text(encoding="utf-8"))

        self.assertNotIn("separate-pull-requests", config)
        self.assertEqual(
            set(root_package["exclude-paths"]),
            {
                "opengamepadui",
                ".github/workflows/opengamepadui-ci.yml",
                "windows",
                ".github/workflows/windows-ci.yml",
                "themes/gallery",
                "scripts/package-theme.mjs",
                "scripts/check-theme-version.mjs",
                "scripts/build-theme-publication.mjs",
                "scripts/resolve-theme-panel-minimum.mjs",
                "scripts/promote-theme-pages.mjs",
                "scripts/stage-theme-pages.mjs",
                "scripts/theme-publication-contract.mjs",
                "scripts/verify-theme-pages.mjs",
                "scripts/verify-theme-pages-governance.mjs",
                "tests/themePackaging.test.ts",
                "tests/themeVersioning.test.ts",
                "tests/themeWorkflow.test.ts",
                "tests/galleryPackage.test.ts",
                "tests/themePagesPromote.test.ts",
                "tests/themePagesStage.test.ts",
                "tests/themePagesVerify.test.ts",
                "tests/themePagesGovernance.test.ts",
                "tests/themePublicationBuild.test.ts",
                "tests/themePanelMinimum.test.ts",
                "tests/themePublicationContract.test.ts",
                ".github/workflows/_theme-package.yml",
                ".github/workflows/_theme-promote.yml",
                ".github/workflows/_theme-stage.yml",
                ".github/workflows/theme-gallery.yml",
                ".github/workflows/theme-gallery-promote.yml",
                ".github/workflows/theme-gallery-stage.yml",
            },
        )
        self.assertNotIn("opengamepadui", config["packages"])
        self.assertNotIn("windows", config["packages"])
        self.assertEqual(set(manifest), {"."})

    def test_release_workflow_ignores_unpublished_platform_changes(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        release_paths = _event_paths(workflow, "push")

        self.assertIn("branches: [main]", _event_body(workflow, "push"))
        self.assertEqual(
            release_paths,
            [
                ".github/workflows/release-please.yml",
                ".release-please-manifest.json",
                "release-please-config.json",
                "shared/fixtures/**",
                "src/**",
                "py_modules/**",
                "main.py",
                "package.json",
                "pnpm-lock.yaml",
                "tsconfig.json",
                "rollup.config.js",
                "plugin.json",
                "README.md",
                "README.en.md",
                "LICENSE",
                "assets/**",
                "bin/**",
                "scripts/**",
                "themes/bundled/**",
            ],
        )
        for unpublished_platform_path in (
            "opengamepadui/plugin.gd",
            "opengamepadui/plugin.json",
            ".github/workflows/opengamepadui-ci.yml",
            "windows/PanelDeControl.sln",
            ".github/workflows/windows-ci.yml",
        ):
            with self.subTest(unpublished_platform_path=unpublished_platform_path):
                self.assertFalse(_matches(unpublished_platform_path, release_paths))

        for decky_release_path in (
            "shared/fixtures/auto_tdp.json",
            "src/index.tsx",
            "py_modules/tdp/service.py",
            "main.py",
            "plugin.json",
            "README.md",
            "LICENSE",
            "rollup.config.js",
            "tsconfig.json",
            "release-please-config.json",
            ".github/workflows/release-please.yml",
        ):
            with self.subTest(decky_release_path=decky_release_path):
                self.assertTrue(_matches(decky_release_path, release_paths))


if __name__ == "__main__":
    unittest.main()
