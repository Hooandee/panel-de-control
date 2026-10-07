import asyncio

import pytest

from test_theme_rpc import theme_rpc  # noqa: F401


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def installed(theme_rpc, monkeypatch):  # noqa: F811
    main, plugin, fake = theme_rpc
    monkeypatch.setattr(
        main.theme_packages,
        "list_theme_extensions",
        lambda themes_root, receipts_path: [{"catalogId": "hooandee-bubble"}],
    )
    return main, plugin, fake


def test_saves_and_reads_back_an_installed_theme_data(installed):
    _, plugin, _ = installed

    saved = run(plugin.save_theme_data("hooandee-bubble", "3 páginas", {"pages": 3}))

    assert saved["ok"] is True
    assert saved["record"]["summary"] == "3 páginas"
    assert run(plugin.get_theme_data("hooandee-bubble"))["value"] == {"pages": 3}


def test_refuses_to_save_for_a_theme_without_an_installed_runtime(installed):
    _, plugin, _ = installed

    assert run(plugin.save_theme_data("hooandee-gallery", "", {})) == {"ok": False, "code": "not_installed"}
    assert run(plugin.list_theme_data()) == []


def test_reports_invalid_identities_and_values_without_raising(installed):
    _, plugin, _ = installed

    assert run(plugin.save_theme_data("../etc", "", {})) == {"ok": False, "code": "not_installed"}
    assert run(plugin.save_theme_data("hooandee-bubble", "x" * 500, {}))["code"] == "invalid_summary"
    assert run(plugin.get_theme_data("../etc")) is None


def test_lists_and_resets_even_after_the_theme_is_gone(installed, monkeypatch):
    main, plugin, _ = installed
    run(plugin.save_theme_data("hooandee-bubble", "s", {"v": 1}))
    monkeypatch.setattr(main.theme_packages, "list_theme_extensions", lambda *_: [])

    assert [item["catalogId"] for item in run(plugin.list_theme_data())] == ["hooandee-bubble"]
    assert run(plugin.reset_theme_data("hooandee-bubble")) == {"ok": True, "deleted": True}
    assert run(plugin.get_theme_data("hooandee-bubble")) is None


def test_support_logs_name_the_themes_without_their_content(installed):
    _, plugin, _ = installed
    run(plugin.save_theme_data("hooandee-bubble", "secret summary", {"v": 1}))

    support = plugin._support_theme_data()

    assert support["theme_data"][0]["catalogId"] == "hooandee-bubble"
    assert "summary" not in support["theme_data"][0]
    assert "value" not in support["theme_data"][0]


def test_theme_data_lives_outside_panel_settings(installed):
    main, plugin, fake = installed

    run(plugin.save_theme_data("hooandee-bubble", "", {"pages": 1}))

    shared = main.Path(fake.DECKY_USER_HOME) / "homebrew" / "data" / "hooandee-themes" / "theme-data"
    assert (shared / "hooandee-bubble.json").is_file()
    assert not (main.Path(fake.DECKY_PLUGIN_SETTINGS_DIR) / "theme-data").exists()


def test_old_panel_records_move_to_the_shared_folder(installed):
    main, plugin, fake = installed
    main.theme_data.write(main.Path(fake.DECKY_PLUGIN_SETTINGS_DIR), "hooandee-bubble", "", {"pages": 4}, now=1.0)

    assert run(plugin.get_theme_data("hooandee-bubble"))["value"] == {"pages": 4}
