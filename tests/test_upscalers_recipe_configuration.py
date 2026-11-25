from types import SimpleNamespace

import pytest
from upscalers import auto_recipes


@pytest.fixture
def config(tmp_path):
    target = tmp_path / 'game'
    staging = tmp_path / 'staging'
    target.mkdir()
    staging.mkdir()
    selected = SimpleNamespace(configuration={'ReShade.ini': {'Luma.SRUserType': '2'}})
    return selected, target, staging


def test_new_configuration_staged_without_mutating_game(config):
    selected, target, staging = config
    result = auto_recipes.configured_sources(selected, target, staging)
    assert result['ReShade.ini'].read_text() == '[Luma]\nSRUserType=2\n'
    assert not (target / 'ReShade.ini').exists()


def test_preserves_other_keys_comments_bom_and_crlf(config):
    selected, target, staging = config
    original = '\ufeff;keep\r\n[Luma]\r\nSRUserType=0\r\nOther=4\r\n[GENERAL]\r\nValue=mine\r\n'
    path = target / 'ReShade.ini'
    path.write_bytes(original.encode())
    result = auto_recipes.configured_sources(selected, target, staging)
    assert result['ReShade.ini'].read_bytes() == original.replace('SRUserType=0', 'SRUserType=2').encode()
    assert path.read_bytes() == original.encode()


@pytest.mark.parametrize('content', ['[INSTALL]\nBasePath=/elsewhere\n', '[install]\nbasepath=elsewhere\n', '[Luma]\nSRUserType=0\nSRUserType=1\n', '[Luma]\nOther=1\n[Luma]\nSRUserType=0\n'])
def test_unsupported_config_never_written(config, content):
    selected, target, staging = config
    (target / 'ReShade.ini').write_text(content)
    with pytest.raises(auto_recipes.RecipeError, match='recipe_unsupported'):
        auto_recipes.configured_sources(selected, target, staging)
    assert not list(staging.iterdir())
    assert (target / 'ReShade.ini').read_text() == content


def test_symlink_and_oversize_rejected(config):
    selected, target, staging = config
    outside = target.parent / 'outside'
    outside.write_text('[Luma]\nSRUserType=0\n')
    path = target / 'ReShade.ini'
    path.symlink_to(outside)
    with pytest.raises(auto_recipes.RecipeError, match='recipe_files_invalid'):
        auto_recipes.configured_sources(selected, target, staging)
    path.unlink()
    path.write_bytes(b' ' * (1024 * 1024 + 1))
    with pytest.raises(auto_recipes.RecipeError, match='recipe_files_invalid'):
        auto_recipes.configured_sources(selected, target, staging)
    assert not list(staging.iterdir())


def test_no_recipe_and_untrusted_path(config):
    selected, target, staging = config
    assert auto_recipes.configured_sources(None, target, staging) == {}
    selected.configuration = {'../escape.ini': {'Luma.SRUserType': '2'}}
    with pytest.raises(auto_recipes.RecipeError, match='recipe_unsupported'):
        auto_recipes.configured_sources(selected, target, staging)



def test_restore_owned_keys_keeps_runtime_bom_crlf_and_original_value(config):
    _, target, _ = config
    path, backup = target / 'ReShade.ini', target / 'original.ini'
    backup.write_bytes(b'[Luma]\r\nSRUserType=0\r\n')
    path.write_bytes('\ufeff[Luma]\r\nSRUserType=2\r\n[Luma Advanced]\r\nShader#ABC=1\r\n'.encode())
    auto_recipes.restore_configuration(path, backup, {'Luma.SRUserType': '2'})
    assert path.read_bytes() == '\ufeff[Luma]\r\nSRUserType=0\r\n[Luma Advanced]\r\nShader#ABC=1\r\n'.encode()


def test_restore_rejects_ambiguous_user_configuration(config):
    _, target, _ = config
    path = target / 'ReShade.ini'
    text = '[Luma]\nSRUserType=2\nSRUserType=1\n'
    path.write_text(text)
    with pytest.raises(auto_recipes.RecipeError, match='recipe_unsupported'):
        auto_recipes.restore_configuration(path, target / 'absent', {'Luma.SRUserType': '2'})
    assert path.read_text() == text


@pytest.fixture
def legacy(config, monkeypatch):
    import hashlib
    import json
    selected, target, staging = config
    selected.dependencies = ('test',)
    selected.revision = 3
    monkeypatch.setattr(auto_recipes.recipe_catalog, 'bundled', lambda: SimpleNamespace(match=lambda *args, **kwargs: selected))
    meta = target / '.pdc-upscaler'
    meta.mkdir()
    installed = '[Luma]\nSRUserType=2\n'
    manifest = {'files': {'ReShade.ini': hashlib.sha256(installed.encode()).hexdigest()}, 'backups': [], 'dirs': []}
    (meta / 'manifest.json').write_text(json.dumps(manifest))
    install = {'target': str(target), 'recipe_revision': 1, 'recipe_dependencies': ['test'], 'game_build': '123'}
    return selected, target, meta, manifest, install


def test_legacy_ownership_proven_across_recipe_revisions(legacy):
    selected, _, _, _, install = legacy
    assert auto_recipes.installed_configuration(install, '123') == selected.configuration


def test_legacy_changed_recipe_values_do_not_gain_ownership(legacy):
    selected, _, _, _, install = legacy
    selected.configuration = {'ReShade.ini': {'Luma.SRUserType': '1'}}
    assert auto_recipes.installed_configuration(install, '123') == {}


@pytest.mark.parametrize('failure', ['missing-backup', 'null-digest', 'wrong-digest', 'absent-file'])
def test_legacy_requires_complete_manifest_proof(legacy, failure):
    import json
    _, _, meta, manifest, install = legacy
    if failure == 'missing-backup':
        manifest['backups'] = ['ReShade.ini']
    elif failure == 'absent-file':
        manifest['files'] = {}
    else:
        manifest['files']['ReShade.ini'] = None if failure == 'null-digest' else '0' * 64
    (meta / 'manifest.json').write_text(json.dumps(manifest))
    assert auto_recipes.installed_configuration(install, '123') == {}


def test_legacy_reconstructs_original_backup_preserving_bom_crlf(legacy):
    import hashlib
    import json
    selected, _, meta, manifest, install = legacy
    original = '\ufeff[Luma]\r\nSRUserType=0\r\nOther=7\r\n'
    (meta / 'backup').mkdir()
    (meta / 'backup/ReShade.ini').write_bytes(original.encode())
    manifest['backups'] = ['ReShade.ini']
    manifest['files']['ReShade.ini'] = hashlib.sha256(original.replace('SRUserType=0', 'SRUserType=2').encode()).hexdigest()
    (meta / 'manifest.json').write_text(json.dumps(manifest))
    assert auto_recipes.installed_configuration(install, '123') == selected.configuration
    (meta / 'backup/ReShade.ini').unlink()
    (meta / 'backup/ReShade.ini').symlink_to(meta / 'manifest.json')
    assert auto_recipes.installed_configuration(install, '123') == {}
