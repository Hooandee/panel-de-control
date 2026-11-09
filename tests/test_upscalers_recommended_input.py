from dataclasses import replace

import pytest

from test_upscalers import _service, _write, fake_catalog, proc, steam
from upscalers import recipe_catalog


@pytest.mark.parametrize('native, detected, expected', [
    (False, True, 'xess'), (False, False, None), (True, True, None),
])
def test_game_input_recommendation_requires_detected_input(steam, fake_catalog, proc, monkeypatch, native, detected, expected):
    monkeypatch.setattr(recipe_catalog.host_platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(recipe_catalog.host_platform, 'machine', lambda: 'x86_64')
    service = _service(steam, fake_catalog, proc)
    if detected:
        _write(steam[1] / 'bin/x64_dx12/libxess.dll')
    if native:
        installed = replace(service._find('292030'), native=True)
        monkeypatch.setattr(service, '_find', lambda appid: installed)
    detail = service.game('292030')
    assert detail['recipe_info']['recommended_input'] == expected
    assert detail['fg_note'] == 'reflexOff'


@pytest.mark.parametrize('eligible', [True, False])
def test_game_and_bulk_share_recipe_build_recommendation(steam, fake_catalog, proc, monkeypatch, eligible):
    from upscalers import auto_recipes, recipes, catalog
    from types import SimpleNamespace
    service = _service(steam, fake_catalog, proc)
    recipe = recipes.Recipe('292030', recommended_build='fsr-test')
    monkeypatch.setattr(service, '_recipe', lambda *args: recipe)
    def plan(*args):
        if not eligible:
            raise auto_recipes.RecipeError('recipe_unsupported')
        return SimpleNamespace(recommended_build='fsr-test')
    monkeypatch.setattr(auto_recipes, 'plan', plan)
    expected = 'fsr-test' if eligible else catalog.preferred_build('rdna2')
    assert service.game('292030')['preferred'] == expected
    assert service.compatibility(['292030'])['292030']['preferred'] == expected
