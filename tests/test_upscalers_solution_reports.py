from upscalers import diagnostics, solution_plan, recipes


def test_report_preserves_decision_without_promoting_it_to_observed():
    recipe = recipes.Recipe("1", args=("-dx11",), quality_owner="game")
    plan = solution_plan.resolve("rdna3", {"apis": ["d3d12"], "inputs": {}}, recipe)
    report = diagnostics.snapshot({"engine": "dll", "solution": plan})
    assert report["applied"]["solution"]["effective_api"] == "d3d11"
    assert report["applied"]["solution"]["quality"]["owner"] == "game"
    assert report["applied"]["solution"]["fg_plan"] is None
    assert report["observed"].get("active") is not True
    assert diagnostics._report_install({"solution": plan})["solution"] == report["applied"]["solution"]


def test_report_solution_drops_private_or_unbounded_data():
    report = diagnostics.solution({
        "effective_api": "/home/private", "api_source": "https://private", "quality": {"owner": "game", "reason": "token=secret"},
        "dependencies": ["vcrun2022", "/home/private", "https://private"] + ["safe"] * 50,
        "recipe_revision": True, "blocked_reason": "password=private", "recommended_input": "/home/private",
        "input_reconciled": "true", "path": "/home/private",
        "fg_plan": {"input": "private", "output": "fsrfg", "source": "optiscaler", "route": "optiscaler",
                    "path": "/home/private", "routes": {"optiscaler": {"input": "upscaler", "path": "/home/private"}, "private": {}}},
    })
    assert "private" not in str(report)
    assert len(report["dependencies"]) <= 16
    assert report["recipe_revision"] is None
    assert report["input_reconciled"] is False
    assert report["fg_plan"]["routes"]["optiscaler"]["input"] == "upscaler"


def test_report_solution_handles_old_and_malformed_state():
    assert diagnostics.solution(None) is None
    report = diagnostics.solution({"quality": [], "dependencies": {}, "fg_plan": {"routes": []}})
    assert report["dependencies"] == []
    assert report["quality"]["owner"] is None
    assert report["fg_plan"]["routes"] == {}


from copy import deepcopy  # noqa: E402
from test_upscalers import steam, fake_catalog, proc, _service, APPID  # noqa: E402


def test_diagnose_separates_applied_from_current_without_mutation(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    applied = diagnostics.solution(service._game_state(APPID)['install']['solution'])
    monkeypatch.setattr(service, '_recipe', lambda *args: recipes.Recipe(APPID, args=('-dx11',), quality_owner='game'))
    expected = diagnostics.solution(service.game(APPID)['solution'])
    before = deepcopy(service.state)
    report = service.diagnose(APPID)
    assert report['solution'] == applied
    assert report['current_solution'] == expected
    assert report['solution'] != report['current_solution']
    assert service.state == before


def test_diagnose_legacy_install_has_no_invented_applied_plan(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    service._game_state(APPID)['install'].pop('solution')
    before = deepcopy(service.state)
    report = service.diagnose(APPID)
    assert report['solution'] is None
    assert report['current_solution'] is not None
    assert service.state == before


def test_report_separates_recommended_and_explicitly_applied_fg():
    plan = solution_plan.resolve("rdna3", {"apis": ["d3d12"]}, recipes.Recipe("1", args=("-dx11",)))
    offered = plan["offered_fg_plan"]
    report = diagnostics.snapshot({"engine": "dll", "solution": plan, "fg_plan": offered})
    assert report["applied"]["solution"]["fg_plan"] is None
    assert report["applied"]["fg_plan"]["route"] == "optiscaler"
    assert report["observed"].get("active") is not True
