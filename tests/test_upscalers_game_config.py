import os
from pathlib import Path

from test_upscalers import APPID, _service, steam, fake_catalog, proc  # noqa: F401
from upscalers import recipes

SYSTEM_XML = Path(__file__).parent / 'fixtures/upscalers/rdr2_system.xml'
SETTINGS = 'Documents/Rockstar Games/Red Dead Redemption 2/Settings/system.xml'


def _prefix_settings(steam, text):
    home, game = steam
    library = game.parents[2]
    path = library / 'steamapps/compatdata' / APPID / 'pfx/drive_c/users/steamuser' / SETTINGS
    path.parent.mkdir(parents=True)
    path.write_text(text)
    return path


def _rdr2_recipe(monkeypatch):
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, game_config=((SETTINGS, 'API', 'kSettingAPI_DX12'),)))


def test_install_switches_red_dead_to_directx12_and_uninstall_puts_vulkan_back(steam, fake_catalog, proc, monkeypatch):
    # PDC-Z63N (#1470): RDR2 starts in Vulkan, where FSR 2 with OptiScaler quits the game; DirectX 12 runs.
    _rdr2_recipe(monkeypatch)
    original = SYSTEM_XML.read_text()
    path = _prefix_settings(steam, original)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    text = path.read_text()
    assert '<API>kSettingAPI_DX12</API>' in text and text.replace('kSettingAPI_DX12', 'kSettingAPI_Vulkan') == original
    assert [entry['state'] for entry in service.game(APPID)['install']['game_config']] == ['set']
    service.install(APPID, {'build': 'fsr-test'})
    service.uninstall(APPID)
    assert path.read_text() == original


def test_a_setting_the_user_changed_since_stays_theirs(steam, fake_catalog, proc, monkeypatch):
    _rdr2_recipe(monkeypatch)
    path = _prefix_settings(steam, SYSTEM_XML.read_text())
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    path.write_text(path.read_text().replace('kSettingAPI_DX12', 'kSettingAPI_Vulkan').replace('value="40"', 'value="41"'))
    service.uninstall(APPID)
    assert '<API>kSettingAPI_Vulkan</API>' in path.read_text() and 'value="41"' in path.read_text()


def test_without_the_games_settings_yet_nothing_is_written(steam, fake_catalog, proc, monkeypatch):
    # The game writes system.xml on its first launch: before that the page still says how to switch.
    _rdr2_recipe(monkeypatch)
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    assert [entry['state'] for entry in service.game(APPID)['install']['game_config']] == ['missing']
    home, game = steam
    assert not (game.parents[2] / 'steamapps/compatdata').exists()
    service.uninstall(APPID)
