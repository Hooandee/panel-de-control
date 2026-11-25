from dataclasses import replace
from pathlib import Path

import pytest
from test_upscalers import steam, fake_catalog, proc, _service, APPID
from upscalers import recipes, solution_plan, ini, catalog
from upscalers.service import UpscalerError


@pytest.mark.parametrize('apis', [[], ['d3d12'], ['d3d11', 'd3d12']])
def test_recipe_api_recommends_but_allows_explicit_optifg(apis):
    recipe = recipes.Recipe('1', args=('-dx11',), effective_api='d3d11', quality_owner='game')
    plan = solution_plan.resolve('rdna2', {'inputs': {}, 'apis': apis}, recipe)
    assert plan['effective_api'] == 'd3d11' and plan['api_source'] == 'recipe'
    assert plan['fg_plan'] is None
    assert plan['quality']['owner'] == 'game'
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'optiscaler'})['input'] == 'upscaler'
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'game'}) is None


def test_detected_dx12_and_unknown_have_distinct_recommendations_same_offer():
    assert solution_plan.resolve('rdna2', {'apis': ['d3d12']})['fg_plan']['route'] == 'optiscaler'
    for apis in ([], ['d3d11', 'd3d12']):
        plan = solution_plan.resolve('rdna2', {'apis': apis})
        assert plan['effective_api'] is None and plan['fg_plan'] is None
        assert plan['offered_fg_plan']['route'] == 'optiscaler'


def test_conflicting_recipe_arguments_warn_without_blocking():
    plan = solution_plan.resolve('rdna2', {}, recipes.Recipe('1', args=('-dx11', '-dx12')))
    assert plan['warning_reason'] == 'recipe_api_conflict'
    assert plan['blocked_reason'] is None
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'optiscaler'})


def test_install_configure_and_detail_preserve_experimental_choices(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    recipe = recipes.Recipe(APPID, args=('-dx11',), effective_api='d3d11', quality_owner='game')
    monkeypatch.setattr(service, '_recipe', lambda *args: recipe)
    detail = service.game(APPID)['solutions']['fsr-test']
    assert detail['fg_plan'] is None
    service.install(APPID, {'build': 'fsr-test', 'quality': 'balanced', 'fg': 'on', 'fg_route': 'optiscaler'})
    installed = service._game_state(APPID)['install']
    assert installed['solution'] == detail
    assert installed['options']['quality'] == 'balanced'
    assert installed['fg_plan']['route'] == 'optiscaler'
    path = Path(installed['target']) / 'OptiScaler.ini'
    assert ini.read(path.read_text(), 'QualityOverrides.QualityRatioOverrideEnabled') == 'true'
    assert ini.read(path.read_text(), 'FrameGen.FGInput') == 'upscaler'
    service.configure(APPID, {'quality': 'performance', 'fg': 'on', 'fg_route': 'optiscaler'})
    assert installed['options']['quality'] == 'performance'
    assert installed['solution']['fg_plan'] is None
    assert service.game(APPID)['solution'] == installed['solution']


def test_new_recipe_advice_does_not_block_existing_fg_choice(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe(APPID, args=('-dx11', '-dx12')))
    service.configure(APPID, {'fg': 'on', 'fg_route': 'optiscaler'})
    installed = service._game_state(APPID)['install']
    assert installed['options']['fg'] == 'on'
    assert installed['solution']['warning_reason'] == 'recipe_api_conflict'


def test_reconciled_input_is_planned_only_for_declared_dependency_entry():
    recipe = recipes.Recipe('1', dependencies=('luma-ff7',), recommended_input='dlss')
    assert solution_plan.resolve('rdna2', {}, recipe)['input_reconciled'] is False
    assert solution_plan.resolve('rdna2', {}, recipe, dependencies_ready=True)['input_reconciled'] is True
    assert solution_plan.resolve('rdna2', {}, replace(recipe, recommended_input=None), dependencies_ready=True)['input_reconciled'] is False
    assert solution_plan.resolve('rdna2', {}, recipe, engine='dll', dependencies_ready=True)['input_reconciled'] is False


def test_running_quality_choice_is_saved_even_when_game_owns_quality(steam, fake_catalog, proc, monkeypatch):
    from upscalers import games
    service = _service(steam, fake_catalog, proc)
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe(APPID, args=('-dx11',), quality_owner='game'))
    service.install(APPID, {'build': 'fsr-test'})
    monkeypatch.setattr(games, 'running_under', lambda *args: True)
    service.configure(APPID, {'quality': 'performance'})
    installed = service._game_state(APPID)['install']
    assert installed['options']['quality'] == 'performance'
    assert ini.read((Path(installed['target']) / 'OptiScaler.ini').read_text(), 'QualityOverrides.QualityRatioOverrideEnabled') == 'true'


def test_a_missing_mod_never_locks_the_settings_of_an_install(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test', 'fg': 'off', 'quality': 'balanced'})
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe(APPID, needs=('mod',)))
    service.configure(APPID, {'quality': 'performance'})
    assert service._game_state(APPID)['install']['options']['quality'] == 'performance'


@pytest.mark.parametrize('route', ['invented', 'game'])
def test_nonexistent_fg_route_never_reports_success(steam, fake_catalog, proc, monkeypatch, route):
    from upscalers import games
    service = _service(steam, fake_catalog, proc)
    analyze = games.analyze
    monkeypatch.setattr(games, 'analyze', lambda *args, **kwargs: {**analyze(*args, **kwargs), 'inputs': {}})
    with pytest.raises(UpscalerError, match='fg_route_unavailable'):
        service.install(APPID, {'build': 'fsr-test', 'fg': 'on', 'fg_route': route})
    assert not service._game_state(APPID).get('install')
    service.install(APPID, {'build': 'fsr-test'})
    installed = service._game_state(APPID)['install']
    before = (Path(installed['target']) / 'OptiScaler.ini').read_bytes()
    with pytest.raises(UpscalerError, match='fg_route_unavailable'):
        service.configure(APPID, {'fg': 'on', 'fg_route': route})
    assert (Path(installed['target']) / 'OptiScaler.ini').read_bytes() == before


def test_dx11_game_never_gets_optifg_without_the_user_choosing_it():
    recipe = recipes.Recipe('1', args=('-dx11',), effective_api='d3d11', quality_owner='game')
    plan = solution_plan.resolve('rdna2', {'inputs': {}, 'apis': ['d3d11']}, recipe)
    assert solution_plan.requested_fg(plan, {'fg': 'on'}) is None
    assert solution_plan.requested_fg(plan, {'fg': 'on', 'fg_route': 'optiscaler'})['route'] == 'optiscaler'


def test_unknown_api_still_follows_the_offered_route():
    plan = solution_plan.resolve('rdna2', {'apis': []})
    assert solution_plan.requested_fg(plan, {'fg': 'on'})['route'] == 'optiscaler'
