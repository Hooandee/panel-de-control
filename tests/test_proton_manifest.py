import os

import pytest

from launch.proton_caps import detect_capabilities


def _write_proton(root, compat_name, body):
    d = os.path.join(root, ".steam", "steam", "compatibilitytools.d", compat_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)


PROTON_BODY = """
    def config(self):
        self.check_environment("PROTON_NO_NTSYNC", "nontsync")
        self.check_environment("PROTON_ENABLE_HDR", "hdr")
        self.check_environment("PROTON_FSR4_RDNA3_UPGRADE", "fsr4rdna3")
        self.check_environment("PROTON_PREFER_SDL", "sdlinput")
"""

def _manifest_tool(root, folder, tool_id, install_path="."):
    directory = root / ".steam/steam/compatibilitytools.d" / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "compatibilitytool.vdf").write_text(
        '"compatibilitytools" { "compat_tools" { '
        f'"{tool_id}" {{ "install_path" "{install_path}" '
        '"display_name" "Requested-Proton" } } }'
    )
    return directory


@pytest.mark.parametrize("install_path", [".", "files/build"])
def test_manifest_resolves_id_and_install_path(tmp_path, install_path):
    directory = _manifest_tool(tmp_path, "different-folder", "Requested-Proton", install_path)
    install = directory / install_path
    install.mkdir(parents=True, exist_ok=True)
    (install / "proton").write_text(PROTON_BODY)
    (install / "contrib").mkdir()
    (install / "contrib/amdxcffx64.dll").touch()
    caps = detect_capabilities("Requested-Proton", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]
    assert "FSR4_UPGRADE" in caps["envs"]


@pytest.mark.parametrize("tool_id", ["Other-Proton", "Requested-Proton-extra"])
def test_manifest_rejects_folder_and_display_matches(tmp_path, tool_id):
    directory = _manifest_tool(tmp_path, "Requested-Proton", tool_id)
    (directory / "proton").write_text(PROTON_BODY)
    assert detect_capabilities("Requested-Proton", home=str(tmp_path)) == {"envs": [], "found": False}


def test_manifest_missing_install_does_not_use_folder_script(tmp_path):
    directory = _manifest_tool(tmp_path, "Requested-Proton", "Requested-Proton", "missing")
    (directory / "proton").write_text(PROTON_BODY)
    assert detect_capabilities("Requested-Proton", home=str(tmp_path)) == {"envs": [], "found": False}


@pytest.mark.parametrize("manifest", ['"compatibilitytools" {', '"compatibilitytools" "invalid"'])
def test_bad_manifest_does_not_hide_valid_install(tmp_path, manifest):
    directory = _manifest_tool(tmp_path, "Requested-Proton", "Requested-Proton")
    (directory / "compatibilitytool.vdf").write_text(manifest)
    (directory / "proton").write_text('self.check_environment("PROTON_WRONG_BUILD", "wrong")')
    valid = _manifest_tool(tmp_path, "valid-folder", "Requested-Proton")
    (valid / "proton").write_text(PROTON_BODY)
    caps = detect_capabilities("Requested-Proton", home=str(tmp_path))
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]
    assert "PROTON_WRONG_BUILD" not in caps["envs"]


def test_manifest_resolution_in_second_steam_root(tmp_path):
    directory = _manifest_tool(tmp_path, "different-folder", "Requested-Proton")
    (directory / "proton").write_text(PROTON_BODY)
    destination = tmp_path / ".local/share/Steam/compatibilitytools.d/different-folder"
    destination.parent.mkdir(parents=True)
    directory.rename(destination)
    assert detect_capabilities("Requested-Proton", home=str(tmp_path))["found"] is True


def test_exact_folder_keeps_priority_over_scanned_manifests(tmp_path):
    _write_proton(str(tmp_path), "Requested-Proton", PROTON_BODY)
    directory = _manifest_tool(tmp_path, "another-folder", "Requested-Proton")
    (directory / "proton").write_text('self.check_environment("PROTON_WRONG_BUILD", "wrong")')
    caps = detect_capabilities("Requested-Proton", home=str(tmp_path))
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]
    assert "PROTON_WRONG_BUILD" not in caps["envs"]


@pytest.mark.parametrize("install_value", ['{ "path" "." }', '"/missing"'])
def test_invalid_install_path_fails_closed(tmp_path, install_value):
    directory = _manifest_tool(tmp_path, "Requested-Proton", "Requested-Proton")
    manifest = directory / "compatibilitytool.vdf"
    manifest.write_text(manifest.read_text().replace('"install_path" "."', f'"install_path" {install_value}'))
    (directory / "proton").write_text(PROTON_BODY)
    assert detect_capabilities("Requested-Proton", home=str(tmp_path)) == {"envs": [], "found": False}
