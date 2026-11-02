import json
import os

import pytest

import theme_storage
from theme_storage import ThemeStorage, ThemeStorageError


def test_reads_back_what_was_written(tmp_path):
    store = ThemeStorage(tmp_path / "theme-storage")
    assert store.get("hooandee-duo", "pdc.hybrid.dock.v1") is None
    store.set("hooandee-duo", "pdc.hybrid.dock.v1", '{"size":3}')
    store.set("hooandee-duo", "pdc-hyb-library-view", "grid")

    reopened = ThemeStorage(tmp_path / "theme-storage")
    assert reopened.get("hooandee-duo", "pdc.hybrid.dock.v1") == '{"size":3}'
    assert reopened.get("hooandee-duo", "pdc-hyb-library-view") == "grid"
    assert (tmp_path / "theme-storage" / "hooandee-duo.json").stat().st_mode & 0o777 == 0o600


def test_themes_are_isolated(tmp_path):
    store = ThemeStorage(tmp_path)
    store.set("hooandee-duo", "layout", "duo")
    store.set("hooandee-bubble", "layout", "bubble")
    assert store.get("hooandee-duo", "layout") == "duo"
    assert store.get("hooandee-bubble", "layout") == "bubble"
    assert store.get("hooandee-eclipse", "layout") is None


@pytest.mark.parametrize("catalog_id", ["../duo", "Duo", "", "a/b", None])
def test_rejects_unsafe_theme_ids(tmp_path, catalog_id):
    with pytest.raises(ThemeStorageError) as error:
        ThemeStorage(tmp_path).set(catalog_id, "key", "value")
    assert error.value.code == "invalid_theme"


@pytest.mark.parametrize("key", ["", "../x", "a b", "x" * 129, 3])
def test_rejects_invalid_keys(tmp_path, key):
    with pytest.raises(ThemeStorageError) as error:
        ThemeStorage(tmp_path).get("hooandee-duo", key)
    assert error.value.code == "invalid_key"


def test_rejects_oversized_values_and_keeps_the_previous_one(tmp_path):
    store = ThemeStorage(tmp_path)
    store.set("hooandee-duo", "groups", "kept")
    with pytest.raises(ThemeStorageError) as error:
        store.set("hooandee-duo", "groups", "x" * (theme_storage.MAX_VALUE_BYTES + 1))
    assert error.value.code == "too_large"
    assert store.get("hooandee-duo", "groups") == "kept"


def test_rejects_a_theme_over_its_total_budget(tmp_path):
    store = ThemeStorage(tmp_path)
    chunk = "x" * (theme_storage.MAX_VALUE_BYTES - 64)
    for index in range(theme_storage.MAX_THEME_BYTES // theme_storage.MAX_VALUE_BYTES - 1):
        store.set("hooandee-duo", f"k{index}", chunk)
    with pytest.raises(ThemeStorageError) as error:
        store.set("hooandee-duo", "one-more", chunk + "x" * 64)
        store.set("hooandee-duo", "and-another", chunk)
    assert error.value.code == "too_large"


def test_rejects_more_keys_than_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_storage, "MAX_KEYS", 2)
    store = ThemeStorage(tmp_path)
    store.set("hooandee-duo", "a", "1")
    store.set("hooandee-duo", "b", "2")
    store.set("hooandee-duo", "a", "3")
    with pytest.raises(ThemeStorageError) as error:
        store.set("hooandee-duo", "c", "4")
    assert error.value.code == "too_many_keys"


def test_unreadable_storage_is_an_error_not_an_empty_value(tmp_path):
    (tmp_path / "hooandee-duo.json").write_text("{broken", encoding="utf-8")
    store = ThemeStorage(tmp_path)
    with pytest.raises(ThemeStorageError) as error:
        store.get("hooandee-duo", "layout")
    assert error.value.code == "corrupt"


def test_a_corrupt_file_is_kept_aside_and_the_next_save_starts_fresh(tmp_path):
    (tmp_path / "hooandee-duo.json").write_text("{broken", encoding="utf-8")
    store = ThemeStorage(tmp_path)
    store.set("hooandee-duo", "layout", "grid")
    assert store.get("hooandee-duo", "layout") == "grid"
    assert (tmp_path / "hooandee-duo.json.corrupt").read_text(encoding="utf-8") == "{broken"


def test_a_failed_write_is_reported(tmp_path, monkeypatch):
    store = ThemeStorage(tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(theme_storage.os, "replace", fail)
    with pytest.raises(ThemeStorageError) as error:
        store.set("hooandee-duo", "layout", "grid")
    assert error.value.code == "write_failed"
    assert not any(name.endswith(".tmp") for name in os.listdir(tmp_path))


def test_refuses_a_symlinked_folder(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    with pytest.raises(ThemeStorageError) as error:
        ThemeStorage(tmp_path / "link").get("hooandee-duo", "layout")
    assert error.value.code == "unsafe_path"


def test_summary_lists_keys_and_size_but_never_values(tmp_path):
    store = ThemeStorage(tmp_path)
    store.set("hooandee-duo", "groups", "secret-name")
    (tmp_path / "hooandee-bubble.json").write_text("nope", encoding="utf-8")
    summary = store.summary()
    assert "secret-name" not in json.dumps(summary)
    assert summary == [
        {"catalogId": "hooandee-bubble", "error": "corrupt"},
        {"catalogId": "hooandee-duo", "keys": ["groups"], "bytes": (tmp_path / "hooandee-duo.json").stat().st_size},
    ]
