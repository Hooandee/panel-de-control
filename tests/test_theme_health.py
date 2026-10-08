import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

import theme_health  # noqa: E402


def _theme(root, folder, manifest=None, *, active=False, marker=False, files=()):
    path = root / folder
    path.mkdir(parents=True)
    if manifest is not None:
        (path / "theme.json").write_text(
            manifest if isinstance(manifest, str) else json.dumps(manifest), encoding="utf-8"
        )
    if marker:
        (path / "panel-theme.json").write_text("{}", encoding="utf-8")
    if active:
        (path / "config_USER.json").write_text(json.dumps({"active": True}), encoding="utf-8")
    for name in files:
        (path / name).write_text("body{}", encoding="utf-8")
    return path


@pytest.fixture
def themes(tmp_path):
    root = tmp_path / "homebrew" / "themes"
    root.mkdir(parents=True)
    return root


def test_scan_classifies_every_folder_css_loader_can_load(themes):
    _theme(themes, "Eclipse", {"name": "Eclipse"}, active=True, marker=True)
    _theme(themes, "Other", {"name": "Other"}, active=True)
    _theme(themes, "Mine.profile", {"name": "Mine.profile", "flags": ["Preset"]}, active=True)
    _theme(themes, "OldCss", files=("theme.css",), active=True)
    _theme(themes, "Sfp", files=("bigpicture.custom.css",))
    _theme(themes, "Broken", "{not json")
    _theme(themes, "TooNew", {"name": "TooNew", "manifest_version": 99})
    _theme(themes, "Residue", active=True)
    _theme(themes, "Eclipse copy", {"name": "Eclipse"})

    by_folder = {item["folder"]: item for item in theme_health.scan(themes)}

    assert {folder: item["kind"] for folder, item in by_folder.items()} == {
        "Eclipse": "hooandee",
        "Other": "third_party",
        "Mine.profile": "profile",
        "OldCss": "legacy",
        "Sfp": "legacy",
        "Broken": "broken",
        "TooNew": "broken",
        "Residue": "leftover",
        "Eclipse copy": "duplicate",
    }
    assert by_folder["Other"]["active"] is True
    assert by_folder["Sfp"]["active"] is False


def test_summary_counts_without_names(themes):
    _theme(themes, "Eclipse", {"name": "Eclipse"}, active=True, marker=True)
    _theme(themes, "Private name", {"name": "Private name"}, active=True)
    _theme(themes, "Residue")

    counts = theme_health.summary(theme_health.scan(themes))

    assert counts == {
        "hooandee": 1,
        "hooandee_active": 1,
        "third_party": 1,
        "other_active": 1,
        "leftover": 1,
    }
    assert "Private name" not in json.dumps(counts)


def test_set_aside_moves_only_scanned_kinds_and_restore_brings_them_back(themes):
    _theme(themes, "Eclipse", {"name": "Eclipse"}, marker=True)
    _theme(themes, "Other", {"name": "Other"}, active=True)
    _theme(themes, "OldCss", files=("theme.css",), active=True)
    _theme(themes, "Residue")

    result = theme_health.set_aside(themes, ["Other"])

    assert sorted(result["moved"]) == ["OldCss", "Residue"]
    assert result["failed"] == []
    assert sorted(path.name for path in themes.iterdir()) == ["Eclipse", "Other"]
    assert theme_health.undo_state(themes) == {"available": True, "moved": 2, "disabled": 1}

    restored = theme_health.restore(themes)

    assert sorted(restored["restored"]) == ["OldCss", "Residue"]
    assert restored["kept"] == []
    assert restored["reenable"] == ["Other"]
    assert (themes / "OldCss" / "config_USER.json").is_file()
    assert theme_health.undo_state(themes) == {"available": True, "moved": 0, "disabled": 1}

    theme_health.forget_reenabled(themes)

    assert not (themes.parent / theme_health.CLEANUP_DIRECTORY).exists()
    assert theme_health.undo_state(themes)["available"] is False


def test_repeated_cleanups_accumulate_and_never_overwrite_a_stored_folder(themes):
    _theme(themes, "Residue")
    theme_health.set_aside(themes, ["A"])
    _theme(themes, "Residue", files=("theme.css",))
    theme_health.set_aside(themes, ["A", "B"])

    stored = sorted(path.name for path in (themes.parent / theme_health.CLEANUP_DIRECTORY).iterdir())
    assert stored == ["Residue", "Residue.1", "record.json"]
    assert theme_health.undo_state(themes) == {"available": True, "moved": 2, "disabled": 2}


def test_restore_keeps_a_folder_whose_name_was_taken_again(themes):
    _theme(themes, "Residue")
    theme_health.set_aside(themes, [])
    _theme(themes, "Residue", {"name": "Residue"})

    restored = theme_health.restore(themes)

    assert restored["restored"] == []
    assert restored["kept"] == ["Residue"]
    assert theme_health.undo_state(themes) == {"available": True, "moved": 1, "disabled": 0}


def test_set_aside_rejects_invalid_names_before_touching_disk(themes):
    _theme(themes, "Residue")

    with pytest.raises(theme_health.ThemeHealthError) as error:
        theme_health.set_aside(themes, [42])

    assert error.value.code == "invalid_request"
    assert (themes / "Residue").is_dir()


def test_a_damaged_record_is_rebuilt_from_what_is_stored(themes):
    cleanup = themes.parent / theme_health.CLEANUP_DIRECTORY
    (cleanup / "Residue").mkdir(parents=True)
    (cleanup / "record.json").write_text("[]", encoding="utf-8")

    assert theme_health.undo_state(themes) == {"available": True, "moved": 1, "disabled": 0, "damaged": True}

    restored = theme_health.restore(themes)

    assert restored["restored"] == ["Residue"]
    assert (themes / "Residue").is_dir()
    assert not cleanup.exists()


def test_restore_ignores_record_entries_that_escape_the_cleanup_folder(themes):
    cleanup = themes.parent / theme_health.CLEANUP_DIRECTORY
    cleanup.mkdir()
    (themes.parent / "outside").mkdir()
    (cleanup / "record.json").write_text(json.dumps({
        "schema": 1,
        "moved": [{"folder": "../escape", "stored": "../outside"}],
        "disabled": [],
    }), encoding="utf-8")

    restored = theme_health.restore(themes)

    assert restored["restored"] == []
    assert (themes.parent / "outside").is_dir()


def test_internal_panel_mode_reads_the_connected_built_in_screen(tmp_path):
    drm = tmp_path / "sys" / "class" / "drm"
    for name, status, modes in (
        ("card0-DP-1", "connected", "3840x2160\n"),
        ("card0-eDP-1", "connected", "800x1280\n1280x800\n"),
    ):
        (drm / name).mkdir(parents=True)
        (drm / name / "status").write_text(status)
        (drm / name / "modes").write_text(modes)

    assert theme_health.internal_panel_mode(str(tmp_path)) == {"width": 800, "height": 1280}


def test_internal_panel_mode_is_unknown_without_a_connected_built_in_screen(tmp_path):
    connector = tmp_path / "sys" / "class" / "drm" / "card1-eDP-1"
    connector.mkdir(parents=True)
    (connector / "status").write_text("disconnected")
    (connector / "modes").write_text("1920x1080\n")

    assert theme_health.internal_panel_mode(str(tmp_path)) is None


def test_set_aside_leaves_no_trace_when_there_is_nothing_to_do(themes):
    _theme(themes, "Eclipse", {"name": "Eclipse"}, marker=True)

    assert theme_health.set_aside(themes, []) == {"moved": [], "failed": []}
    assert not (themes.parent / theme_health.CLEANUP_DIRECTORY).exists()


def test_symlinks_are_moved_as_links_and_restored_even_when_dangling(themes):
    _theme(themes, "Old", files=("theme.css",))
    (themes / "OldLink").symlink_to("Old")
    (themes / "Alias").symlink_to("/nonexistent/theme")

    moved = theme_health.set_aside(themes, [])["moved"]
    restored = theme_health.restore(themes)

    assert sorted(moved) == ["Old", "OldLink"]
    assert sorted(restored["restored"]) == ["Old", "OldLink"]
    assert restored["kept"] == []
    assert (themes / "OldLink").is_symlink() and (themes / "OldLink" / "theme.css").is_file()


def test_a_dangling_stored_link_is_not_overwritten_by_a_later_cleanup(themes):
    cleanup = themes.parent / theme_health.CLEANUP_DIRECTORY
    cleanup.mkdir()
    (cleanup / "Old").symlink_to("/nonexistent")
    (cleanup / "record.json").write_text(json.dumps({
        "schema": 1, "moved": [{"folder": "Old", "stored": "Old"}], "disabled": [],
    }), encoding="utf-8")
    _theme(themes, "Old", files=("theme.css",))

    theme_health.set_aside(themes, [])

    assert (cleanup / "Old").is_symlink()
    assert (cleanup / "Old.1" / "theme.css").is_file()


def test_restore_finishes_a_move_back_interrupted_before_the_record_was_saved(themes):
    _theme(themes, "Residue")
    theme_health.set_aside(themes, [])
    cleanup = themes.parent / theme_health.CLEANUP_DIRECTORY
    (cleanup / "Residue").rename(themes / "Residue")

    restored = theme_health.restore(themes)

    assert restored == {"restored": [], "kept": [], "reenable": []}
    assert not cleanup.exists()


def test_hidden_folders_without_theme_files_are_left_alone(themes):
    (themes / ".git" / "objects").mkdir(parents=True)
    _theme(themes, ".hidden-css", files=("theme.css",))

    kinds = {item["folder"]: item["kind"] for item in theme_health.scan(themes)}

    assert kinds == {".hidden-css": "legacy"}
