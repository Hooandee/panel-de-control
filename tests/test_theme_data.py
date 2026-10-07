from __future__ import annotations

import json
import os
import stat

import pytest

import theme_data


def test_round_trips_a_record_with_its_summary(tmp_path):
    record = theme_data.write(tmp_path, "hooandee-bubble", "7 páginas · 3 carpetas", {"pages": [1, 2]}, now=1000)

    assert record == {"summary": "7 páginas · 3 carpetas", "value": {"pages": [1, 2]}, "updatedAt": 1000, "bytes": record["bytes"]}
    assert record["bytes"] > 0
    assert theme_data.read(tmp_path, "hooandee-bubble") == record


def test_reads_nothing_before_the_first_write(tmp_path):
    assert theme_data.read(tmp_path, "hooandee-bubble") is None
    assert theme_data.list_records(tmp_path) == []


def test_writes_are_private_and_leave_no_temporary_files(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "", {"a": 1}, now=1)
    folder = tmp_path / "theme-data"

    assert [path.name for path in folder.iterdir()] == ["hooandee-bubble.json"]
    assert stat.S_IMODE(os.stat(folder / "hooandee-bubble.json").st_mode) == 0o600


def test_overwrites_in_place(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "one", {"v": 1}, now=1)
    theme_data.write(tmp_path, "hooandee-bubble", "two", {"v": 2}, now=2)

    assert theme_data.read(tmp_path, "hooandee-bubble")["value"] == {"v": 2}


@pytest.mark.parametrize("catalog_id", ["", "Bubble", "../x", "a/b", "x" * 80, "a--b", None])
def test_rejects_unsafe_catalog_ids(tmp_path, catalog_id):
    with pytest.raises(theme_data.ThemeDataError) as error:
        theme_data.write(tmp_path, catalog_id, "", {}, now=1)
    assert error.value.code == "invalid_catalog"


def test_rejects_oversized_values(tmp_path):
    with pytest.raises(theme_data.ThemeDataError) as error:
        theme_data.write(tmp_path, "hooandee-bubble", "", {"blob": "x" * (theme_data.MAX_VALUE_BYTES + 1)}, now=1)
    assert error.value.code == "too_large"
    assert theme_data.read(tmp_path, "hooandee-bubble") is None


def test_rejects_values_nested_too_deep(tmp_path):
    value: object = 1
    for _ in range(theme_data.MAX_DEPTH + 2):
        value = [value]
    with pytest.raises(theme_data.ThemeDataError) as error:
        theme_data.write(tmp_path, "hooandee-bubble", "", value, now=1)
    assert error.value.code == "invalid_value"


@pytest.mark.parametrize("summary", ["x" * 121, "line\nbreak", 5])
def test_rejects_bad_summaries(tmp_path, summary):
    with pytest.raises(theme_data.ThemeDataError) as error:
        theme_data.write(tmp_path, "hooandee-bubble", summary, {}, now=1)
    assert error.value.code == "invalid_summary"


def test_rejects_values_json_cannot_represent(tmp_path):
    with pytest.raises(theme_data.ThemeDataError) as error:
        theme_data.write(tmp_path, "hooandee-bubble", "", {"n": float("nan")}, now=1)
    assert error.value.code == "invalid_value"


def test_lists_every_theme_without_its_content(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "2 páginas", {"big": "x" * 50}, now=10)
    theme_data.write(tmp_path, "hooandee-gallery", "", {}, now=20)

    listed = theme_data.list_records(tmp_path)

    assert [item["catalogId"] for item in listed] == ["hooandee-bubble", "hooandee-gallery"]
    assert listed[0]["summary"] == "2 páginas"
    assert "value" not in listed[0]


def test_skips_corrupt_files_when_listing_and_reading(tmp_path):
    folder = tmp_path / "theme-data"
    folder.mkdir()
    (folder / "hooandee-bubble.json").write_text("{not json")
    (folder / "notes.txt").write_text("x")

    assert theme_data.list_records(tmp_path) == []
    assert theme_data.read(tmp_path, "hooandee-bubble") is None


def test_delete_removes_one_theme(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "", {}, now=1)
    theme_data.write(tmp_path, "hooandee-gallery", "", {}, now=1)

    assert theme_data.delete(tmp_path, "hooandee-bubble") is True
    assert theme_data.delete(tmp_path, "hooandee-bubble") is False
    assert [item["catalogId"] for item in theme_data.list_records(tmp_path)] == ["hooandee-gallery"]


def test_stored_file_carries_its_identity(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "s", {"v": 1}, now=3)
    stored = json.loads((tmp_path / "theme-data" / "hooandee-bubble.json").read_text())

    assert stored["schemaVersion"] == 1
    assert stored["catalogId"] == "hooandee-bubble"


def test_a_file_renamed_to_another_theme_is_not_served(tmp_path):
    theme_data.write(tmp_path, "hooandee-bubble", "", {"v": 1}, now=1)
    folder = tmp_path / "theme-data"
    (folder / "hooandee-bubble.json").rename(folder / "hooandee-gallery.json")

    assert theme_data.read(tmp_path, "hooandee-gallery") is None


def test_adopts_records_left_in_the_old_folder_once(tmp_path):
    legacy = tmp_path / "panel-settings"
    shared = tmp_path / "shared"
    theme_data.write(legacy, "hooandee-bubble", "3 páginas", {"pages": 3}, now=1.0)

    assert theme_data.adopt_legacy(shared, legacy) == ["hooandee-bubble"]
    assert theme_data.read(shared, "hooandee-bubble")["value"] == {"pages": 3}
    assert theme_data.read(legacy, "hooandee-bubble") is None
    assert theme_data.adopt_legacy(shared, legacy) == []


def test_adoption_never_overwrites_newer_shared_data(tmp_path):
    legacy = tmp_path / "panel-settings"
    shared = tmp_path / "shared"
    theme_data.write(legacy, "hooandee-bubble", "viejo", {"pages": 1}, now=1.0)
    theme_data.write(shared, "hooandee-bubble", "nuevo", {"pages": 9}, now=2.0)

    assert theme_data.adopt_legacy(shared, legacy) == []
    assert theme_data.read(shared, "hooandee-bubble")["value"] == {"pages": 9}


def test_adoption_copies_when_the_folders_live_on_different_disks(tmp_path, monkeypatch):
    legacy = tmp_path / "panel-settings"
    shared = tmp_path / "shared"
    theme_data.write(legacy, "hooandee-bubble", "3 páginas", {"pages": 3}, now=5.0)
    real_replace = os.replace

    def cross_device(source, target):
        if str(source).startswith(str(legacy)):
            raise OSError(18, "Invalid cross-device link")
        return real_replace(source, target)

    monkeypatch.setattr(theme_data.os, "replace", cross_device)

    assert theme_data.adopt_legacy(shared, legacy) == ["hooandee-bubble"]
    assert theme_data.read(shared, "hooandee-bubble")["value"] == {"pages": 3}
    assert theme_data.read(shared, "hooandee-bubble")["updatedAt"] == 5
    assert not (legacy / "theme-data" / "hooandee-bubble.json").exists()


def test_adoption_that_cannot_move_a_record_says_so_and_keeps_it(tmp_path, monkeypatch):
    legacy = tmp_path / "panel-settings"
    shared = tmp_path / "shared"
    theme_data.write(legacy, "hooandee-bubble", "", {"pages": 3}, now=1.0)
    monkeypatch.setattr(theme_data, "write", lambda *args, **kwargs: (_ for _ in ()).throw(OSError(28, "No space")))
    monkeypatch.setattr(theme_data.os, "replace", lambda *args: (_ for _ in ()).throw(OSError(18, "cross-device")))

    with pytest.raises(theme_data.ThemeDataError) as raised:
        theme_data.adopt_legacy(shared, legacy)

    assert raised.value.code == "adoption_incomplete"
    assert (legacy / "theme-data" / "hooandee-bubble.json").exists()


def test_refuses_a_data_folder_that_is_a_link(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "theme-data").symlink_to(elsewhere)

    with pytest.raises(theme_data.ThemeDataError) as raised:
        theme_data.write(shared, "hooandee-bubble", "", {}, now=1.0)

    assert raised.value.code == "unsafe_folder"
    assert list(elsewhere.iterdir()) == []
