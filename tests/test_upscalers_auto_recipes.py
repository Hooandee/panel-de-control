import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_upscalers import steam as steam, fake_catalog as fake_catalog, dll_catalog as dll_catalog, proc as proc, _service, APPID
from upscalers import auto_recipes, prefix_dependencies, recipes
from upscalers.service import UpscalerError


@pytest.fixture
def automatic(steam, fake_catalog, proc, monkeypatch, tmp_path):
    service = _service(steam, fake_catalog, proc)
    selected = SimpleNamespace(revision=1, dependencies=('luma-test',))
    monkeypatch.setattr(auto_recipes, 'plan', lambda recipe, installed: selected)
    monkeypatch.setattr(auto_recipes, 'assets', lambda selected: [])
    addon = tmp_path / 'addon'
    addon.write_bytes(b'addon')
    monkeypatch.setattr(auto_recipes, 'sources', lambda selected, paths, store=None: {'Luma-test.addon': addon})
    monkeypatch.setattr(auto_recipes, 'verbs', lambda selected: ('vcrun2022',))
    calls = []
    receipt = {'state': 'prepared'}
    monkeypatch.setattr(prefix_dependencies, 'prepare', lambda *args: receipt)
    monkeypatch.setattr(prefix_dependencies, 'publish', lambda *args: (calls.append('publish'), receipt.update(state='published')))
    monkeypatch.setattr(prefix_dependencies, 'rollback', lambda *args: (calls.append('rollback'), receipt.update(state='rolled_back')))
    monkeypatch.setattr(prefix_dependencies, 'finish', lambda *args: calls.append('finish'))
    monkeypatch.setattr(prefix_dependencies, 'recover_pending', lambda *args: receipt)
    return service, calls, receipt


def test_requires_checkpoint_before_changing_files(automatic, steam):
    service, calls, _ = automatic
    with pytest.raises(UpscalerError, match='recipe_transaction_required'):
        service.install(APPID, {'build': 'fsr-test'})
    assert calls == []
    assert not list(steam[1].rglob('Luma-test.addon'))


def test_recipe_files_and_prefix_committed_after_launch(automatic, steam):
    service, calls, _ = automatic
    checkpoint = service.begin_scaler_transition(APPID)
    result = service.install(APPID, {'build': 'fsr-test'})
    assert result['overrides']
    assert calls == ['publish']
    assert list(steam[1].rglob('Luma-test.addon'))
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert calls == ['publish', 'finish']
    assert service._game_state(APPID)['install']['recipe_dependencies'] == ['luma-test']


def test_failed_launch_restores_files_prefix_and_cleans_on_confirmation(automatic, steam):
    service, calls, receipt = automatic
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert calls == ['publish', 'rollback']
    assert not list(steam[1].rglob('Luma-test.addon'))
    assert service._game_state(APPID).get('install') is None
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert calls == ['publish', 'rollback', 'finish']


def test_existing_verified_prefix_needs_no_transaction(automatic, monkeypatch):
    service, calls, _ = automatic
    monkeypatch.setattr(prefix_dependencies, 'prepare', lambda *args: None)
    monkeypatch.setattr(prefix_dependencies, 'recover_pending', lambda *args: None)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert calls == []


def test_a_missing_mod_warns_but_never_blocks_the_install(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    monkeypatch.setitem(recipes.RECIPES, APPID, recipes.Recipe(APPID, needs=('mod',)))
    service.install(APPID, {'build': 'fsr-test'})
    assert service._game_state(APPID)['install']['build'] == 'fsr-test'
    info = service.game(APPID)['recipe_info']
    assert 'mod' in info['needs'] and info['blocked'] is False


def test_report_distinguishes_applied_and_current_game_build(steam, fake_catalog, proc, monkeypatch):
    from dataclasses import replace
    service = _service(steam, fake_catalog, proc)
    original = service._find(APPID)
    current = replace(original, build_id='100')
    monkeypatch.setattr(service, '_find', lambda appid: current)
    service.install(APPID, {'build': 'fsr-test'})
    current = replace(original, build_id='200')
    report = service.diagnose(APPID)
    assert report['build_id'] == '200'
    assert report['install']['game_build'] == '100'
    assert report['history'][-1]['game_build'] == '100'


def test_report_preserves_luma_dependency_id_without_raw_configuration():
    from upscalers import diagnostics
    report = diagnostics._report_install({'recipe_dependencies': ['luma-ff7', 'vcrun2022', '../private'],
                                          'env': {'TOKEN': 'private'}, 'edited': {'Secret': 'value'}})
    assert report['recipe_dependencies'] == ['luma-ff7', 'vcrun2022']
    assert 'env' not in report and 'edited' not in report


@pytest.fixture
def configured(automatic, monkeypatch):
    service, _, _ = automatic
    selected = SimpleNamespace(revision=1, dependencies=('luma-test',),
                               configuration={'ReShade.ini': {'Luma.SRUserType': '2'}})
    monkeypatch.setattr(auto_recipes, 'plan', lambda recipe, installed: selected)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    service.finish_scaler_transition(APPID, checkpoint['token'])
    target = Path(service._game_state(APPID)['install']['target'])
    return service, target


def test_runtime_config_survives_legacy_upgrade_and_rollback(configured, monkeypatch):
    import json
    from test_upscalers_scaler_transition import files
    service, target = configured
    manifest = target / '.pdc-upscaler' / 'manifest.json'
    data = json.loads(manifest.read_text())
    data.pop('configuration')
    install = service._game_state(APPID)['install']
    configuration = install.pop('recipe_configuration')
    selected = SimpleNamespace(revision=3, configuration=configuration, dependencies=('luma-test',))
    assert data['files']['ReShade.ini'] == '954a89a301786d4491f1c8795effd46f137a212410034262b9487833f930ce35'
    catalog = auto_recipes.recipe_catalog.bundled()
    original_match = catalog.match
    monkeypatch.setattr(type(catalog), 'match', lambda self, *args, **kwargs: selected if len(args) == 2 else original_match(*args, **kwargs))
    manifest.write_text(json.dumps(data))
    runtime = '[Luma]\nSRUserType=2\n[Luma Advanced]\nShader#008DE6E3=1\n'
    (target / 'ReShade.ini').write_text(runtime)
    before = files(target)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test', 'quality': 'balanced'})
    assert (target / 'ReShade.ini').read_text() == runtime
    service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert files(target) == before
    service.finish_scaler_transition(APPID, checkpoint['token'])


def test_runtime_config_released_without_erasing_other_keys(configured):
    service, target = configured
    (target / 'ReShade.ini').write_text('[Luma]\nSRUserType=2\nOther=7\n[Luma Advanced]\nShader#ABC=1\n')
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    assert (target / 'ReShade.ini').read_text() == '[Luma]\nOther=7\n[Luma Advanced]\nShader#ABC=1\n'
    assert not (target / '.pdc-upscaler').exists()
    service.finish_scaler_transition(APPID, checkpoint['token'])


def test_modified_dll_still_blocks_mutable_config_transition(configured):
    service, target = configured
    (target / 'ReShade.ini').write_text('[Luma]\nSRUserType=2\nShader=1\n')
    (target / 'dxgi.dll').write_bytes(b'external dll')
    with pytest.raises(UpscalerError, match='transition_conflict'):
        service.begin_scaler_transition(APPID)
    assert (target / 'dxgi.dll').read_bytes() == b'external dll'


def test_config_the_game_rewrote_after_checkpoint_never_blocks(configured):
    service, target = configured
    checkpoint = service.begin_scaler_transition(APPID)
    (target / 'ReShade.ini').write_text('[Luma]\nSRUserType=1\n')
    service.uninstall(APPID)
    assert (target / 'ReShade.ini').read_text() == '[Luma]\nSRUserType=1\n'
    assert service.scaler_transitions.pending(APPID)['token'] == checkpoint['token']
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert not service.scaler_transitions.pending(APPID)


def test_user_owned_value_is_not_reset_on_removal(configured):
    service, target = configured
    text = '[Luma]\nSRUserType=1\nOther=5\n'
    (target / 'ReShade.ini').write_text(text)
    checkpoint = service.begin_scaler_transition(APPID)
    service.uninstall(APPID)
    assert (target / 'ReShade.ini').read_text() == text
    service.finish_scaler_transition(APPID, checkpoint['token'])



def test_switch_to_dll_preserves_runtime_keys_and_rollback(configured, dll_catalog):
    from test_upscalers_scaler_transition import files
    service, target = configured
    runtime = '[Luma]\nSRUserType=2\n[Luma Advanced]\nShader#ABC=1\n'
    (target / 'ReShade.ini').write_text(runtime)
    root = service._find(APPID).root
    before = files(root)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'dll-test'})
    assert (target / 'ReShade.ini').read_text() == '[Luma]\n[Luma Advanced]\nShader#ABC=1\n'
    service.finish_scaler_transition(APPID, checkpoint['token'], True)
    assert files(root) == before
    service.finish_scaler_transition(APPID, checkpoint['token'])



def test_remake_marks_reshade_tutorial_done_and_takes_it_back(tmp_path):
    from types import SimpleNamespace
    from upscalers import auto_recipes, recipe_catalog
    selected = recipe_catalog.bundled().match('1462040', 'optiscaler', 'linux', 'amd64')
    changes = selected.configuration['ReShade.ini']
    assert changes == {'Luma.SRUserType': '2', 'OVERLAY.TutorialProgress': '4'}
    game, staging = tmp_path / 'game', tmp_path / 'staging'
    game.mkdir(), staging.mkdir()
    original = '[Luma]\nSRUserType=0\n'
    (game / 'ReShade.ini').write_text(original)
    (game / 'backup.ini').write_text(original)
    prepared = auto_recipes.configured_sources(SimpleNamespace(configuration={'ReShade.ini': changes}), game, staging)
    configured = prepared['ReShade.ini'].read_text()
    assert 'TutorialProgress=4' in configured and 'SRUserType=2' in configured
    (game / 'ReShade.ini').write_text(configured)
    auto_recipes.restore_configuration(game / 'ReShade.ini', game / 'backup.ini', changes)
    restored = (game / 'ReShade.ini').read_text()
    assert 'TutorialProgress' not in restored and 'SRUserType=0' in restored


def test_recipe_without_proton_prerequisites_never_touches_the_prefix(automatic, steam, monkeypatch):
    service, calls, _ = automatic
    monkeypatch.setattr(auto_recipes, 'verbs', lambda selected: ())
    monkeypatch.setattr(prefix_dependencies, 'prepare', lambda *args: (_ for _ in ()).throw(AssertionError('no prefix')))
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    assert list(steam[1].rglob('Luma-test.addon'))
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert calls == []


def test_windows_components_that_fail_do_not_stop_the_install(automatic, steam, monkeypatch):
    service, calls, _ = automatic

    def failing(*args):
        raise prefix_dependencies.DependencyError('prefix_install_failed')

    monkeypatch.setattr(prefix_dependencies, 'prepare', failing)
    monkeypatch.setattr(prefix_dependencies, 'abandon', lambda *args: calls.append('abandon'))
    monkeypatch.setattr(prefix_dependencies, 'status', lambda *args: {'state': 'missing', 'dependencies': []})
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {'build': 'fsr-test'})
    assert list(steam[1].rglob('Luma-test.addon'))
    assert service._game_state(APPID)['install']['windows_components_error'] == 'prefix_install_failed'
    assert service.game(APPID)['recipe_info']['windows_components'] == 'missing'
    service.finish_scaler_transition(APPID, checkpoint['token'])
    assert calls == ['abandon']


def test_a_game_that_starts_mid_install_still_stops_it(automatic, monkeypatch):
    service, _, _ = automatic

    def running(*args):
        raise prefix_dependencies.DependencyError('running')

    monkeypatch.setattr(prefix_dependencies, 'prepare', running)
    service.begin_scaler_transition(APPID)
    with pytest.raises(UpscalerError, match='running'):
        service.install(APPID, {'build': 'fsr-test'})


def test_an_abandoned_staging_is_removed_and_one_in_use_is_left(tmp_path, monkeypatch):
    from upscalers.games import Installed
    library = tmp_path / 'Steam'
    root = library / 'steamapps/common/Game'
    root.mkdir(parents=True)
    compat = library / 'steamapps/compatdata/1462040'
    (compat / 'pfx').mkdir(parents=True)
    transaction = compat.parent / '.pdc-dependencies-1462040'
    (transaction / 'compat/pfx').mkdir(parents=True)
    (transaction / 'receipt.json').write_text(json.dumps({'appid': '1462040', 'compatdata': str(compat), 'transaction': str(transaction),
                                                          'dependencies': ['vcrun2022'], 'state': 'failed', 'verified': False}))
    game = Installed('1462040', 'Game', root, 4)
    monkeypatch.setattr(prefix_dependencies.games, 'library_paths', lambda home: [library])
    monkeypatch.setattr(prefix_dependencies.games, 'running_under', lambda *args: False)
    proc = tmp_path / 'proc'
    proc.mkdir()

    def busy(*args):
        raise prefix_dependencies.DependencyError('prefix_process_running')

    with monkeypatch.context() as patched:
        patched.setattr(prefix_dependencies, '_guard_transaction', busy)
        prefix_dependencies.abandon(str(tmp_path), game, str(proc))
        assert transaction.exists()
    prefix_dependencies.abandon(str(tmp_path), game, str(proc))
    assert not transaction.exists() and (compat / 'pfx').is_dir()
