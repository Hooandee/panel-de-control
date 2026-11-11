from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

import theme_packages
from test_theme_extensions import THEME_ID, THEME_NAME, package, paths
from test_theme_rpc import theme_rpc  # noqa: F401


RESET_HOME = {
    "id": "reset-home",
    "label": {"es": "Restablecer menú principal", "en": "Reset home screen", "it": "Ripristina il menu principale"},
    "description": {"es": "Vuelve a la disposición original.", "en": "Back to the original layout."},
    "confirm": {"es": "¿Restablecer el menú principal?", "en": "Reset the home screen?"},
    "destructive": True,
}


def install(tmp_path, actions):
    archive, descriptor = package(tmp_path, marker_patch={"actions": actions})
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)
    theme_packages.commit_theme_install(prepared["transaction"], themes, receipts_path=receipts)
    return themes


def test_installs_a_theme_declaring_actions_and_serves_them(tmp_path):
    themes = install(tmp_path, [RESET_HOME])

    assert theme_packages.theme_actions(themes, THEME_ID, THEME_NAME) == [RESET_HOME]
    assert theme_packages.list_theme_extensions(*paths(tmp_path))[0]["catalogId"] == THEME_ID


def test_a_theme_without_actions_serves_none(tmp_path):
    archive, descriptor = package(tmp_path)
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)
    theme_packages.commit_theme_install(prepared["transaction"], themes, receipts_path=receipts)

    assert theme_packages.theme_actions(themes, THEME_ID, THEME_NAME) == []


def test_actions_of_another_catalog_id_or_an_unsafe_name_are_not_served(tmp_path):
    themes = install(tmp_path, [RESET_HOME])

    assert theme_packages.theme_actions(themes, "other-theme", THEME_NAME) == []
    assert theme_packages.theme_actions(themes, THEME_ID, "../Example Theme") == []
    assert theme_packages.theme_actions(themes, THEME_ID, "Missing Theme") == []


@pytest.mark.parametrize("actions", [
    "reset-home",
    {"id": "reset-home"},
    None,
    [{"id": f"action-{index}", "label": {"en": "A"}} for index in range(65)],
])
def test_malformed_actions_never_fail_the_install(tmp_path, actions):
    themes = install(tmp_path, actions)

    served = theme_packages.theme_actions(themes, THEME_ID, THEME_NAME)
    assert len(served) == (8 if isinstance(actions, list) else 0)
    assert theme_packages.list_theme_extensions(*paths(tmp_path))[0]["catalogId"] == THEME_ID


def test_actions_live_beside_labels_and_never_reach_css_loader(tmp_path):
    archive, descriptor = package(tmp_path, marker_patch={
        "actions": [RESET_HOME],
        "labels": {"Estilizar Inicio": {"name": {"en": "Home"}}},
    })
    themes, receipts = paths(tmp_path)
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes, receipts_path=receipts)
    theme_packages.commit_theme_install(prepared["transaction"], themes, receipts_path=receipts)

    assert theme_packages.theme_actions(themes, THEME_ID, THEME_NAME) == [RESET_HOME]
    assert theme_packages.theme_patch_labels(themes, THEME_ID, THEME_NAME) == {"Estilizar Inicio": {"name": {"en": "Home"}}}
    assert "actions" not in json.loads((themes / THEME_NAME / "theme.json").read_text(encoding="utf-8"))


def test_malformed_repeated_and_excess_entries_are_dropped(tmp_path):
    themes = install(tmp_path, [
        {"id": "Bad Id", "label": {"en": "Bad"}},
        {"id": "x" * 41, "label": {"en": "Long id"}},
        {"id": "no-label"},
        {"id": "blank-label", "label": {"en": " "}},
        {"id": "unknown-language", "label": {"ja": "リセット"}},
        "reset-home",
        {
            "id": "good",
            "label": {"en": "Good", "ja": "良い", "es": 3},
            "description": {"en": "x" * 241},
            "confirm": "Sure?",
            "destructive": "yes",
        },
        {"id": "good", "label": {"en": "Duplicate"}},
        *({"id": f"extra-{index}", "label": {"en": f"Extra {index}"}} for index in range(10)),
    ])

    served = theme_packages.theme_actions(themes, THEME_ID, THEME_NAME)
    assert served[0] == {"id": "good", "label": {"en": "Good"}}
    assert [action["id"] for action in served] == ["good", *(f"extra-{index}" for index in range(7))]


def test_actions_rpc_reads_the_installed_theme_and_never_raises(theme_rpc, monkeypatch):  # noqa: F811
    main, plugin, fake = theme_rpc
    themes_root = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes"
    calls = []
    monkeypatch.setattr(
        main.theme_packages,
        "theme_actions",
        lambda root, catalog_id, name: calls.append((root, catalog_id, name)) or [RESET_HOME],
    )

    assert asyncio.run(plugin.get_theme_actions("example-theme", "Example Theme")) == [RESET_HOME]
    assert calls == [(themes_root, "example-theme", "Example Theme")]

    def fail(*_args):
        raise OSError("disk")

    monkeypatch.setattr(main.theme_packages, "theme_actions", fail)
    assert asyncio.run(plugin.get_theme_actions("example-theme", "Example Theme")) == []
