from __future__ import annotations

import pytest

import theme_packages
from test_theme_extensions import THEME_ID, THEME_NAME, package, paths


LABELS = {
    "Posición de la parrilla": {
        "name": {"en": "Grid position", "de": "Rasterposition", "pt-BR": "Posição da grade"},
        "values": {"Alta": {"en": "Top", "it": "Alta"}},
    },
    "Estilizar Inicio": {"name": {"es": "Inicio", "en": "Home"}},
}


def install(tmp_path, labels):
    archive, descriptor = package(tmp_path, marker_patch={"labels": labels})
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)
    theme_packages.commit_theme_install(prepared["transaction"], themes, receipts_path=receipts)
    return themes


def test_installs_a_marker_with_patch_labels_and_serves_them(tmp_path):
    themes = install(tmp_path, LABELS)

    assert theme_packages.theme_patch_labels(themes, THEME_ID, THEME_NAME) == LABELS


def test_a_theme_without_labels_serves_none(tmp_path):
    archive, descriptor = package(tmp_path)
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)
    theme_packages.commit_theme_install(prepared["transaction"], themes, receipts_path=receipts)

    assert theme_packages.theme_patch_labels(themes, THEME_ID, THEME_NAME) == {}


def test_labels_of_another_catalog_id_or_an_unsafe_name_are_not_served(tmp_path):
    themes = install(tmp_path, LABELS)

    assert theme_packages.theme_patch_labels(themes, "other-theme", THEME_NAME) == {}
    assert theme_packages.theme_patch_labels(themes, THEME_ID, "../Example Theme") == {}
    assert theme_packages.theme_patch_labels(themes, THEME_ID, "Missing Theme") == {}


@pytest.mark.parametrize("labels", [
    [],
    "labels",
    {f"Patch {index}": {"name": {"en": "Name"}} for index in range(65)},
])
def test_prepare_rejects_labels_that_are_not_a_bounded_object(tmp_path, labels):
    archive, descriptor = package(tmp_path, marker_patch={"labels": labels})
    themes, receipts = paths(tmp_path)

    with pytest.raises(theme_packages.ThemePackageError):
        theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)


def test_malformed_entries_and_unknown_languages_are_dropped_without_blocking_the_theme(tmp_path):
    themes = install(tmp_path, {
        "Good": {"name": {"en": "Good", "fr": "Bon"}, "values": {"A": {"de": "a", "xx": "?"}, "B": {"fr": "b"}}},
        "Blank": {"name": {"en": ""}},
        "Long": {"name": {"en": "x" * 121}},
        "Number": {"name": {"en": 3}},
        "Control": {"name": {"en": "\u0000"}},
        "Other": {"title": {"en": "Name"}},
        "List": [],
        "": {"name": {"en": "Name"}},
    })

    assert theme_packages.theme_patch_labels(themes, THEME_ID, THEME_NAME) == {
        "Good": {"name": {"en": "Good"}, "values": {"A": {"de": "a"}}},
    }
    assert theme_packages.list_theme_extensions(*paths(tmp_path))[0]["catalogId"] == THEME_ID
