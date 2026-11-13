import json
import shutil

import pytest

from py_modules.upscalers import recipe_catalog as rc, recipes


@pytest.fixture
def catalog_dir(tmp_path):
    destination = tmp_path / 'recipes'
    shutil.copytree(rc.CATALOG_PATH, destination)
    return destination


def edit(directory, filename, change):
    path = directory / filename
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def test_pinned_remake_and_dependency_order():
    catalog = rc.load()
    game = catalog.match('1462040', 'optiscaler', 'linux', 'amd64')
    assert game.exe == 'End/Binaries/Win64/ff7remake_.exe'
    assert game.args == ('-dx11',)
    assert game.ini == {'Plugins.LoadReshade': 'true', 'Hotfix.CreateD3D12DeviceForLuma': 'false'}
    assert [d.id for d in catalog.dependency_order(game.dependencies, 'linux')] == ['vcrun2022', 'msvcrt40', 'luma-ff7']
    asset = catalog.assets['luma-ff7-800']
    assert asset.sha256 == 'eb5186525da7af03951a2fd681e857c7191c9f5d7dcb5e40bb4c8372be222cfd'
    assert asset.size == 136693836
    files = catalog.dependencies['luma-ff7'].files
    assert len(files) == 147
    assert files['ReShade64.dll'] == 'dxgi.dll'
    assert 'dxgi.dll' not in files


def test_conditions_use_actual_host(monkeypatch):
    monkeypatch.setattr(rc.host_platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(rc.host_platform, 'machine', lambda: 'AMD64')
    catalog = rc.load()
    assert catalog.match('1462040', 'optiscaler')
    for engine, platform, arch in [('dll', 'linux', 'x86_64'), ('optiscaler', 'darwin', 'x86_64'), ('optiscaler', 'linux', 'aarch64')]:
        assert catalog.match('1462040', engine, platform, arch) is None
    assert catalog.match('292030', 'optiscaler', 'windows', 'x86_64') is None
    assert catalog.match('99999', 'optiscaler') is None


def test_recipe_preserves_wiki_and_existing_rules():
    recipe = recipes.recipe_for('1462040', platform='linux', arch='x86_64')
    assert recipe.dependencies == ('luma-ff7', 'vcrun2022', 'msvcrt40')
    assert 'luma' in recipe.needs
    assert recipe.catalog_revision == 5
    assert recipe.catalog_version == 12
    assert '-dx11' in recipe.args
    assert not recipes.recipe_for('1462040', engine='dll', platform='linux', arch='x86_64').dependencies
    assert recipes.recipe_for('292030').exe == 'bin/x64_dx12/witcher3.exe'
    assert recipes.recipe_for('870780').ini['Spoofing.Dxgi'] == 'false'


@pytest.mark.parametrize('filename,change', [
    ('catalog.json', lambda d: d.update(schema_version=True)),
    ('catalog.json', lambda d: d.update(script='echo bad')),
    ('dependencies.json', lambda d: d['vcrun2022'].update(verb='run')),
    ('dependencies.json', lambda d: d['vcrun2022'].update(verb=[])),
    ('dependencies.json', lambda d: d['luma-ff7'].update(asset=[])),
    ('dependencies.json', lambda d: d['luma-ff7'].update(requires=['missing'])),
    ('dependencies.json', lambda d: d['vcrun2022'].update(requires=['luma-ff7'])),
    ('dependencies.json', lambda d: d['luma-ff7'].update(files={'../evil':'dxgi.dll'})),
    ('dependencies.json', lambda d: d['luma-ff7'].update(files={'foo':'/evil'})),
    ('dependencies.json', lambda d: d['luma-ff7'].update(files={'foo':'a\\b'})),
    ('dependencies.json', lambda d: d['luma-ff7'].update(files={'A.dll':'a','a.dll':'b'})),
    ('assets.json', lambda d: d['luma-ff7-800'].update(url='https://github.com:wrong/a')),
    ('assets.json', lambda d: d['luma-ff7-800'].update(url='https://user@github.com/a')),
    ('assets.json', lambda d: d['luma-ff7-800'].update(url='http://localhost/a')),
    ('assets.json', lambda d: d['luma-ff7-800'].update(sha256='no')),
    ('assets.json', lambda d: d['luma-ff7-800'].update(size=True)),
    ('games/1462040.json', lambda d: d['linux'].update(args=['-dx11;echo'])),
    ('games/1462040.json', lambda d: d['linux'].update(dependencies=['luma-ff7','luma-ff7'])),
])
def test_invalid_catalog_rejected(catalog_dir, filename, change):
    edit(catalog_dir, filename, change)
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_duplicate_json_key_rejected(catalog_dir):
    (catalog_dir / 'catalog.json').write_text('{"schema_version":2,"schema_version":2,"catalog_version":1}')
    with pytest.raises(rc.CatalogError, match='duplicate_key'):
        rc.load(catalog_dir)


def test_symlink_rejected(catalog_dir, tmp_path):
    path = catalog_dir / 'games/1462040.json'
    moved = tmp_path / 'game.json'
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_oversized_file_rejected(catalog_dir):
    (catalog_dir / 'catalog.json').write_text(' ' * (2 * 1024 * 1024 + 1))
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_bundled_fails_closed(monkeypatch):
    rc.bundled.cache_clear()
    def fail():
        raise rc.CatalogError('broken')
    monkeypatch.setattr(rc, 'load', fail)
    try:
        assert not rc.bundled().games
    finally:
        rc.bundled.cache_clear()


def test_tested_builds_are_informational():
    catalog = rc.load()
    entry = catalog.match('1462040', 'optiscaler', 'linux', 'x86_64', game_build='999')
    assert entry.tested_game_builds == ('21888968',)
    assert catalog.match('1462040', 'optiscaler', 'linux', 'x86_64')


def test_optional_build_condition_requires_observed_match(catalog_dir):
    edit(catalog_dir, 'games/1462040.json', lambda d: d['linux']['conditions'].update(game_builds=['21888968']))
    catalog = rc.load(catalog_dir)
    assert catalog.match('1462040', 'optiscaler', 'linux', 'x86_64', game_build='21888968')
    assert catalog.match('1462040', 'optiscaler', 'linux', 'x86_64', game_build='999') is None
    assert catalog.match('1462040', 'optiscaler', 'linux', 'x86_64') is None


@pytest.mark.parametrize('change', [
    lambda d: d['linux'].update(tested_game_builds=[21888968]),
    lambda d: d['linux'].update(tested_game_builds=['21888968', '21888968']),
    lambda d: d['linux'].update(tested_at='2026-02-30'),
    lambda d: d['linux'].update(tested_at='20261107'),
    lambda d: d['linux'].update(tested_at='2026-11-07', tested_game_builds=[]),
    lambda d: d['linux']['conditions'].update(game_builds=[]),
    lambda d: d['linux']['conditions'].update(game_builds=['../1']),
])
def test_invalid_build_evidence_rejected(catalog_dir, change):
    edit(catalog_dir, 'games/1462040.json', change)
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_recipe_for_forwards_build_condition(catalog_dir, monkeypatch):
    edit(catalog_dir, 'games/1462040.json', lambda d: d['linux']['conditions'].update(game_builds=['21888968']))
    catalog = rc.load(catalog_dir)
    monkeypatch.setattr(rc, 'bundled', lambda: catalog)
    assert recipes.recipe_for('1462040', platform='linux', arch='x86_64', game_build='21888968').dependencies
    assert not recipes.recipe_for('1462040', platform='linux', arch='x86_64', game_build='999').dependencies


@pytest.mark.parametrize('configuration', [
    {'../ReShade.ini': {'Luma.SRUserType': '2'}},
    {'ReShade.ini': {'INSTALL.BasePath': '/outside'}},
    {'ReShade.ini': {'Luma.SRUserType': '2\nOther=3'}},
    {'ReShade.ini': {'Luma.SRUserType': 2}},
])
def test_configuration_allowlist(catalog_dir, configuration):
    edit(catalog_dir, 'games/1462040.json', lambda d: d['linux'].update(configuration=configuration))
    with pytest.raises(rc.CatalogError, match='unsupported_configuration'):
        rc.load(catalog_dir)


def test_witcher_input_guidance_preserves_existing_rules_and_wiki():
    live = recipes.Recipe('292030', inputs=('FSR2', 'XeSS'), status='works')
    recipe = recipes.recipe_for('292030', live, platform='linux', arch='x86_64')
    assert recipe.recommended_input == 'xess'
    assert recipe.exe == 'bin/x64_dx12/witcher3.exe'
    assert recipe.args == ('--launcher-skip', '-dx12')
    assert recipe.fg_note == 'reflexOff'
    assert recipe.inputs == ('FSR2', 'XeSS')
    assert recipe.dependencies == ()
    assert recipes.recipe_for('292030', engine='dll', platform='linux', arch='x86_64').recommended_input is None
    assert recipes.recipe_for('292030', platform='windows', arch='x86_64').recommended_input is None
    assert recipes.recipe_for('870780', platform='linux', arch='x86_64').recommended_input is None


@pytest.mark.parametrize('value', ['fsr4', '', True, None, ['xess']])
def test_invalid_recommended_input_rejected(catalog_dir, value):
    edit(catalog_dir, 'games/292030.json', lambda data: data['linux'].update(recommended_input=value))
    with pytest.raises(rc.CatalogError, match='invalid_recommended_input'):
        rc.load(catalog_dir)

@pytest.mark.parametrize('key,value', [('effective_api', 'dx99'), ('effective_api', None), ('quality_owner', 'luma'), ('quality_owner', [])])
def test_solution_metadata_rejects_unknown_values(catalog_dir, key, value):
    edit(catalog_dir, 'games/1462040.json', lambda data: data['linux'].update({key: value}))
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


@pytest.mark.parametrize('value', ['', True, None, [], '../fsr-4.1.2-beta'])
def test_invalid_recommended_build_rejected(catalog_dir, value):
    edit(catalog_dir, 'games/1462040.json', lambda data: data['linux'].update(recommended_build=value))
    with pytest.raises(rc.CatalogError, match='invalid_recommended_build'):
        rc.load(catalog_dir)


def test_remake_recommends_supported_build_without_changing_global_default():
    from py_modules.upscalers import catalog
    recipe = recipes.recipe_for('1462040', platform='linux', arch='x86_64')
    assert recipe.recommended_build == 'fsr-4.1.2-beta'
    for gpu in ('rdna2', 'rdna3', 'rdna35'):
        assert catalog.preferred_build(gpu, recipe) == 'fsr-4.1.2-beta'
    assert catalog.BUILDS[recipe.recommended_build].models[0][0] == 'lite'
    assert catalog.preferred_build('intel', recipe) == 'xess'
    assert catalog.preferred_build('rdna4', recipe) == 'fsr-4.1.1'
    assert catalog.preferred_build('rdna3') == 'fsr-4.1.1'
    windows = recipes.recipe_for('1462040', platform='darwin', arch='x86_64')
    assert catalog.preferred_build('rdna3', windows) == 'fsr-4.1.1'


def test_luma_411_uses_new_engine_and_preserves_driver_provider():
    from py_modules.upscalers import catalog
    recipe = recipes.recipe_for('1462040', platform='linux', arch='x86_64')
    original = catalog.BUILDS['fsr-4.1.1']
    variant = catalog.for_game(original, {}, 'rdna3', recipe)
    assert variant.id == original.id
    assert variant.version == '4.1.1'
    assert variant.assets == ('amdxcffx64-4.1.1',)
    assert variant.archive == catalog.OPTISCALER_BETA
    assert variant.extra_dir == 'OptiScaler'
    assert variant.ini == {
        'Upscalers.Dx12Upscaler': 'ffx', 'Upscalers.Dx11Upscaler': 'ffx_12',
        'Upscalers.VulkanUpscaler': 'ffx_12', 'FSR.Fsr4GpuSupport': '2', 'FSR.UpscalerIndex': '1',
    }
    assert catalog.for_game(original, {}, 'rdna3') is original
    windows = recipes.recipe_for('1462040', platform='darwin', arch='x86_64')
    assert catalog.for_game(original, {}, 'rdna3', windows) is original
    other = catalog.BUILDS['fsr-4.1.2-beta']
    assert catalog.for_game(other, {}, 'rdna3', recipe) is other


def test_hidden_files_beside_the_recipes_are_ignored(catalog_dir):
    (catalog_dir / 'games' / '.DS_Store').write_bytes(b'\x00')
    assert rc.load(catalog_dir).match('1462040', 'optiscaler', 'linux', 'amd64') is not None


def _user_dependency(data):
    data['puredark-test'] = {
        'kind': 'user_files', 'name': 'UpscalerBasePlugin', 'page_url': 'https://www.nexusmods.com/site/mods/502',
        'version': '1.1.2', 'avoid_versions': ['1.2.0'], 'files': {'PDPerfPlugin.dll': 'PDPerfPlugin.dll'},
    }


def test_user_files_dependency_names_what_the_user_brings(catalog_dir):
    edit(catalog_dir, 'dependencies.json', _user_dependency)
    dependency = rc.load(catalog_dir).dependencies['puredark-test']
    assert dependency.kind == 'user_files' and dependency.asset is None
    assert dependency.name == 'UpscalerBasePlugin' and dependency.version == '1.1.2'
    assert dependency.avoid_versions == ('1.2.0',)
    assert dependency.page_url == 'https://www.nexusmods.com/site/mods/502'
    assert dependency.files == {'PDPerfPlugin.dll': 'PDPerfPlugin.dll'}
    assert dependency.download_url is None
    assert rc.load().dependencies['puredark-upscaler-base'].download_url.endswith('?tab=files&file_id=2293')


@pytest.mark.parametrize('change', [
    lambda d: d['puredark-test'].update(page_url='https://evil.example/mod'),
    lambda d: d['puredark-test'].update(files={'PDPerfPlugin.dll': 'sub/PDPerfPlugin.dll'}),
    lambda d: d['puredark-test'].update(files={}),
    lambda d: d['puredark-test'].pop('name'),
])
def test_user_files_dependency_rejects_unsafe_data(catalog_dir, change):
    edit(catalog_dir, 'dependencies.json', lambda d: (_user_dependency(d), change(d)))
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_re4_brings_its_own_reframework_and_asks_the_user_only_for_puredark(tmp_path):
    from pathlib import Path
    from py_modules.upscalers import auto_recipes, user_deps
    catalog = rc.load()
    game = catalog.match('2050650', 'optiscaler', 'linux', 'x86_64')
    order = catalog.dependency_order(game.dependencies)
    assert [(d.id, d.kind) for d in order] == [('refw-pdup-re4', 'game_files'), ('puredark-upscaler-base', 'user_files')]
    recipe = recipes.recipe_for('2050650', platform='linux', arch='x86_64')
    root = tmp_path / 'RE4'
    root.mkdir()
    (root / 're_chunk_000.pak').write_bytes(b'')
    composed = recipes.with_engine(recipe, '2050650', root)
    assert 'reframework-nightly' not in composed.files.values()
    assert composed.menu_key == 'home' and 'dinput8' in composed.native_dlls
    assert not auto_recipes.unresolved(composed, {'inputs': {}}, game)
    assert [a.id for a in auto_recipes.assets(game)] == ['refw-pdup-re4']
    store = user_deps.Store(tmp_path / 'store')
    framework = tmp_path / 'refw'
    framework.mkdir()
    (framework / 'dinput8.dll').write_bytes(b'MZ')
    assert set(auto_recipes.sources(game, {'refw-pdup-re4': framework}, store)) == {'dinput8.dll'}
    assert [s['state'] for s in auto_recipes.user_files(game, store)] == ['missing']
    plugin = tmp_path / 'PDPerfPlugin.dll'
    plugin.write_bytes(b'MZ')
    store.adopt(catalog.dependencies['puredark-upscaler-base'], plugin)
    assert set(auto_recipes.sources(game, {'refw-pdup-re4': framework}, store)) == {'dinput8.dll', 'PDPerfPlugin.dll'}


def test_standard_reframework_still_composes_for_other_re_engine_games(tmp_path):
    root = tmp_path / 'game'
    root.mkdir()
    (root / 're_chunk_000.pak').write_bytes(b'')
    composed = recipes.with_engine(recipes.Recipe('3764200'), '3764200', root)
    assert composed.files == {'dinput8.dll': 'reframework-nightly'}



def test_re4_keeps_optiscalers_libxess_beside_the_exe():
    game = rc.load().match('2050650', 'optiscaler', 'linux', 'x86_64')
    assert game.optiscaler_root_files == ('libxess.dll',)
    assert recipes.recipe_for('2050650', platform='linux', arch='x86_64').optiscaler_root_files == ('libxess.dll',)


@pytest.mark.parametrize('value', [['sub/libxess.dll'], ['libxess.exe'], 'libxess.dll'])
def test_root_files_must_be_plain_dll_names(catalog_dir, value):
    edit(catalog_dir, 'games/2050650.json', lambda d: d['linux'].update(optiscaler_root_files=value))
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_re4_recipe_drives_reframeworks_upscaler_and_names_the_game_setting():
    game = rc.load().match('2050650', 'optiscaler', 'linux', 'x86_64')
    assert game.reframework_upscaler is True and game.optiscaler_fg is False
    assert game.game_settings == (('FidelityFX Super Resolution 2', 'No'),)
    recipe = recipes.recipe_for('2050650', platform='linux', arch='x86_64')
    assert recipe.reframework_upscaler and not recipe.optiscaler_fg
    assert recipe.game_settings == (('FidelityFX Super Resolution 2', 'No'),)


def test_recipe_without_optiscaler_fg_neither_offers_nor_applies_it():
    from py_modules.upscalers import solution_plan
    recipe = recipes.Recipe('1', optiscaler_fg=False)
    plan = solution_plan.resolve('rdna2', {'apis': ['d3d12'], 'inputs': {'fsrfg': True}}, recipe)
    assert plan['fg_plan'] is None and plan['offered_fg_plan'] is None
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'optiscaler'}) is None
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'game'}) is None


def test_baldurs_gate_3_skips_its_launcher_into_d3d11_and_asks_for_dlss():
    recipe = recipes.recipe_for('1086940', platform='linux', arch='x86_64')
    assert (recipe.exe, recipe.args, recipe.recommended_input) == ('bin/bg3_dx11.exe', ('--skip-launcher',), 'dlss')
    assert recipe.dependencies == () and not recipe.needs


def test_every_reframework_recipe_runs_optiscalers_overlay_menu():
    for appid in ('2050650', '883710', '952060', '418370', '601150'):
        assert recipes.recipe_for(appid, platform='linux', arch='x86_64').ini['Menu.OverlayMenu'] == 'true', appid


def _windows_block(d, **changes):
    block = {key: value for key, value in d['linux'].items() if key != 'dependencies'}
    d['windows'] = {**block, 'dependencies': [], 'status': 'untested', 'exe': 'game.exe', **changes}


def test_every_recipe_has_a_block_per_os_and_linux_keeps_its_recipe():
    catalog = rc.load()
    assert catalog.schema_version == 2
    for appid, game in catalog.games.items():
        assert set(game.statuses) == {'linux', 'windows'}, appid
        assert game.recipes['linux'].platform == 'linux'
        assert catalog.match(appid, 'optiscaler', 'linux', 'x86_64') is game.recipes['linux']
        windows = catalog.match(appid, 'optiscaler', 'windows', 'x86_64')
        assert (windows is not None) == (game.statuses['windows'] in ('tested', 'untested')), appid


def test_each_os_gets_only_its_own_block(catalog_dir):
    edit(catalog_dir, 'games/1462040.json', _windows_block)
    catalog = rc.load(catalog_dir)
    linux = catalog.match('1462040', 'optiscaler', 'linux', 'x86_64')
    windows = catalog.match('1462040', 'optiscaler', 'windows', 'amd64')
    assert linux.exe == 'End/Binaries/Win64/ff7remake_.exe' and linux.dependencies == ('luma-ff7', 'vcrun2022', 'msvcrt40')
    assert (windows.exe, windows.dependencies, windows.status, windows.platform) == ('game.exe', (), 'untested', 'windows')
    assert catalog.games['1462040'].statuses == {'linux': 'tested', 'windows': 'untested'}
    assert catalog.match('1462040', 'optiscaler', 'darwin', 'x86_64') is None


def test_not_applicable_block_matches_nothing(catalog_dir):
    edit(catalog_dir, 'games/1462040.json', lambda d: d.update(linux={'status': 'not_applicable'}))
    catalog = rc.load(catalog_dir)
    assert catalog.match('1462040', 'optiscaler', 'linux', 'x86_64') is None
    assert catalog.games['1462040'].statuses['linux'] == 'not_applicable'


@pytest.mark.parametrize('change', [
    lambda d: d.pop('windows'),
    lambda d: d.update(android={'status': 'unknown'}),
    lambda d: d.update(windows={'status': 'unknown', 'exe': 'game.exe'}),
    lambda d: d.update(windows={'status': 'works'}),
    lambda d: d.update(windows={}),
    lambda d: d['linux'].pop('status'),
    lambda d: d['linux']['conditions'].update(platform=['linux']),
    lambda d: _windows_block(d, exe='../game.exe'),
    lambda d: _windows_block(d, dependencies=['vcrun2022']),
    lambda d: _windows_block(d, args=['-dx11;echo']),
])
def test_both_os_blocks_are_validated_strictly(catalog_dir, change):
    edit(catalog_dir, 'games/1462040.json', change)
    with pytest.raises(rc.CatalogError):
        rc.load(catalog_dir)


def test_shared_dependency_follows_only_its_own_systems_runtimes(catalog_dir):
    edit(catalog_dir, 'games/1462040.json', lambda d: _windows_block(d, dependencies=['refw-pdup-re4']))
    edit(catalog_dir, 'dependencies.json', lambda d: d['refw-pdup-re4'].update(requires=['vcrun2022', 'vc-redist-x64']))
    catalog = rc.load(catalog_dir)
    windows = catalog.match('1462040', 'optiscaler', 'windows', 'x86_64')
    assert [d.id for d in catalog.dependency_order(windows.dependencies, 'windows')] == ['vc-redist-x64', 'refw-pdup-re4']
    assert [d.id for d in catalog.dependency_order(('refw-pdup-re4',), 'linux')] == ['vcrun2022', 'refw-pdup-re4']


def test_previous_schema_is_rejected(catalog_dir):
    edit(catalog_dir, 'catalog.json', lambda d: d.update(schema_version=1))
    with pytest.raises(rc.CatalogError, match='unsupported_schema'):
        rc.load(catalog_dir)


def test_remake_windows_block_needs_the_visual_cpp_runtime_not_proton_verbs():
    catalog = rc.load()
    game = catalog.match('1462040', 'optiscaler', 'windows', 'amd64')
    assert game.status == 'untested'
    assert game.exe == 'End/Binaries/Win64/ff7remake_.exe'
    assert [d.id for d in catalog.dependency_order(game.dependencies, 'windows')] == ['vc-redist-x64', 'luma-ff7']
    runtime = catalog.dependencies['vc-redist-x64']
    assert (runtime.kind, runtime.verb, runtime.version) == ('windows_redist', 'vc14_x64', '14.40.33810.0')


def test_linux_automatic_dependencies_skip_windows_runtimes():
    from py_modules.upscalers import auto_recipes
    game = rc.load().match('1462040', 'optiscaler', 'linux', 'amd64')
    assert [d.id for d in auto_recipes.dependencies(game)] == ['vcrun2022', 'msvcrt40', 'luma-ff7']


@pytest.mark.parametrize('platform, foreign', [('linux', 'vc-redist-x64'), ('windows', 'vcrun2022')])
def test_block_cannot_list_another_systems_dependency(catalog_dir, platform, foreign):
    def change(data):
        if data[platform].get('status') == 'unknown':
            data[platform] = dict(data['linux' if platform == 'windows' else 'windows'])
        data[platform]['dependencies'] = ['luma-ff7', foreign]
    edit(catalog_dir, 'games/1462040.json', change)
    with pytest.raises(rc.CatalogError, match='dependency_not_for_platform'):
        rc.load(catalog_dir)


@pytest.mark.parametrize('field, value, error', [
    ('page_url', 'https://example.com/vc_redist', 'untrusted_origin'),
    ('component', 'vc14_arm64', 'unsupported_dependency'),
    ('provider', 'winget', 'unsupported_dependency'),
    ('min_version', 'latest', 'invalid_version'),
])
def test_windows_runtime_is_validated(catalog_dir, field, value, error):
    edit(catalog_dir, 'dependencies.json', lambda data: data['vc-redist-x64'].__setitem__(field, value))
    with pytest.raises(rc.CatalogError, match=error):
        rc.load(catalog_dir)
