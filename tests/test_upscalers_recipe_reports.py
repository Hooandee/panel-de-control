import json
import pytest
from upscalers import diagnostics, games, prefix_dependencies


def test_launch_report_omits_secrets_paths_and_unknown_env():
    value = 'TOKEN=private-token /home/alice/mangohud WINEDLLOVERRIDES="dxgi=n,b;vcruntime140=n;secretname=n" %command% -dx11 --password hidden-value https://secret.invalid/?key=credential'
    result = diagnostics.launch_diagnostics(value)
    serialized = json.dumps(result)
    for secret in ('private-token', 'alice', 'secretname', 'password', 'hidden-value', 'secret.invalid', 'credential', 'TOKEN'):
        assert secret not in serialized
    assert result['command_placeholder'] is True
    assert result['render_flags'] == ['dx11']
    assert result['wrappers'] == ['mangohud']
    assert result['dll_overrides'] == [{'name': 'dxgi', 'mode': 'n,b'}, {'name': 'vcruntime140', 'mode': 'n'}]
    assert result['omitted_count'] == 5


def test_malformed_launch_is_safe_and_unknown():
    result = diagnostics.launch_diagnostics('TOKEN="secret-missing-quote')
    assert result['omitted_count'] == 1
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('shortcut,launcher,store,source', [
    (False, None, 'steam', 'steam_manifest'),
    (True, ('heroic', 'key', 'legendary'), 'epic', 'launcher_config'),
    (True, ('heroic', 'key', 'gog'), 'gog', 'launcher_config'),
    (True, ('heroic', 'key', 'nile'), 'amazon', 'launcher_config'),
    (True, ('lutris', 'key', None), 'unknown', 'launcher_config'),
    (True, None, 'unknown', 'external_shortcut'),
])
def test_game_provenance_never_asserts_license(tmp_path, shortcut, launcher, store, source):
    game = games.Installed('1462040', 'Game crack legit official', tmp_path, 4, shortcut=shortcut,
                           launcher=launcher, build_id='987654')
    report = diagnostics.game_report(str(tmp_path), game.appid, {}, game)
    assert report['build_id'] == '987654'
    assert report['provenance']['store'] == store
    assert report['provenance']['source'] == source
    assert report['provenance']['license'] == 'unknown'
    assert report['provenance']['authenticity'] == 'unknown'


def test_snapshot_keeps_recipe_version_and_dependencies():
    report = diagnostics.snapshot({'engine': 'dll', 'recipe': 'ff7-remake', 'recipe_revision': '2',
                                   'game_build': '987654', 'recipe_dependencies': ['vcrun2022', 'msvcrt40']})
    assert report['applied']['recipe_revision'] == '2'
    assert report['applied']['game_build'] == '987654'
    assert report['applied']['recipe_dependencies'] == ['vcrun2022', 'msvcrt40']


@pytest.mark.parametrize('scenario,expected', [('missing', 'missing'), ('ready', 'ready'), ('pending', 'pending'), ('ambiguous', 'unknown')])
def test_dependency_status_is_readonly_and_path_free(tmp_path, monkeypatch, scenario, expected):
    library = tmp_path / 'PrivateUser/Steam'
    game = games.Installed('1462040', 'Game', library / 'steamapps/common/Game', 4)
    compat = library / 'steamapps/compatdata/1462040'
    if scenario != 'missing':
        pfx = compat / 'pfx'
        dll = pfx / 'drive_c/windows/syswow64/msvcrt40.dll'
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b'MZruntime')
        (pfx / 'winetricks.log').write_text('msvcrt40\n')
    libraries = [library]
    if scenario == 'ambiguous':
        extra = tmp_path / 'SecondSteam'
        (extra / 'steamapps/compatdata/1462040/pfx').mkdir(parents=True)
        libraries.append(extra)
    monkeypatch.setattr(prefix_dependencies.games, 'library_paths', lambda home: libraries)
    monkeypatch.setattr(prefix_dependencies, 'recover_pending', lambda *a: {'state': 'prepared'} if scenario == 'pending' else None)
    def forbidden(*args, **kwargs):
        raise AssertionError('status must never execute tools')
    monkeypatch.setattr(prefix_dependencies, '_execute', forbidden)
    result = prefix_dependencies.status(str(tmp_path), game, ('msvcrt40',))
    assert result == {'state': expected, 'dependencies': [{'id': 'msvcrt40', 'state': expected}]}
    assert 'PrivateUser' not in json.dumps(result)


def test_complete_report_drops_raw_install_history_and_launch_options(tmp_path, monkeypatch):
    root = tmp_path / 'Steam'
    (root / 'userdata/123/config').mkdir(parents=True)
    monkeypatch.setattr(diagnostics.games, 'steam_roots', lambda home: [root])
    def read(path):
        if path.name == 'localconfig.vdf':
            return {'userlocalconfigstore': {'software': {'valve': {'steam': {'apps': {
                '1462040': {'launchoptions': 'TOKEN=private-launch-secret %command% -dx11'}
            }}}}}}
        return {}
    monkeypatch.setattr(diagnostics.vdf, 'read_text', read)
    game = games.Installed('1462040', 'Game', tmp_path, 4, build_id='123')
    entry = {'exe': '/private-user/path/game.exe', 'install': {
        'engine': 'dll', 'target': str(tmp_path), 'env': {'TOKEN': 'private-env-secret'},
        'args': '--password private-args-secret', 'edited': {'unknown': 'private-edited-secret'},
        'options': {'quality': 'quality', 'env': 'private-options-secret'},
    }, 'history': [{'at': 1, 'result': 'loaded', 'args': 'private-history-secret',
                   'facts': {'version': '1.2.3', 'env': 'private-facts-secret'}}]}
    report = diagnostics.game_report(str(tmp_path), game.appid, entry, game)
    serialized = json.dumps(report)
    assert 'private-' not in serialized
    assert 'launch_options' not in report['steam']
    assert report['steam']['launch_diagnostics']['render_flags'] == ['dx11']
    assert report['install']['options'] == {'quality': 'quality'}
    assert report['history'][0]['facts'] == {'version': '1.2.3'}
    assert report['manual_exe_selected'] is True


def test_reshade_redirect_is_reported_without_the_private_path():
    result = diagnostics.launch_diagnostics('RESHADE_BASE_PATH_OVERRIDE=/private/user-config %command%')
    assert result['reshade_redirected'] is True
    assert 'private' not in json.dumps(result)
