"""Version choice, frame generation and solution plan cases shared with the Windows port.

`shared/fixtures/upscalers/plan_parity.json` records what `catalog` and `solution_plan` answer for every GPU family,
device, recipe and game the matrix below combines; windows/tests/PanelDeControl.Core.Tests/Upscalers must give the
same answers. Rewrite it after a logic or data change with
`PYTHONPATH=py_modules python tests/test_upscalers_plan_parity.py --write`.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from itertools import product
from pathlib import Path

from upscalers import catalog, solution_plan

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "plan_parity.json"
GPUS = (*catalog.EVERY_GPU, "nvidia")
DEVICES = ("", "steam_deck_lcd", "steam_deck_oled", "rog_ally", "rog_ally_x", "legion_go", "legion_go_s", "msi_claw_8")
INPUT_SETS = {
    "none": {},
    "fsr31": {"fsr31": ["Game/amd_fidelityfx_dx12.dll"]},
    "fsr31-loader": {"fsr31": ["bin/AMD_FidelityFX_Loader_DX12.dll"]},
    "dlss": {"dlss": ["nvngx_dlss.dll"]},
    "dlssg": {"dlss": ["nvngx_dlss.dll"], "dlssg": ["nvngx_dlssg.dll"], "streamline": ["sl.interposer.dll"]},
    "fsrfg": {"fsr31": ["amd_fidelityfx_dx12.dll"], "fsrfg": ["amd_fidelityfx_dx12.dll"]},
    "xefg": {"xess": ["libxess.dll"], "xefg": ["libxess_fg.dll"]},
    "all-fg": {"dlssg": ["a"], "fsrfg": ["b"], "xefg": ["c"], "streamline": ["d"]},
}
API_SETS = ([], ["d3d12"], ["d3d11"], ["vulkan"], ["d3d11", "d3d12"])


@dataclass
class PlanRecipe:
    """The recipe attributes solution_plan reads."""
    args: tuple = ()
    effective_api: str | None = None
    quality_owner: str = "panel"
    recommended_input: str | None = None
    dependencies: tuple = ()
    fg: dict | None = None
    optiscaler_fg: bool = True
    catalog_revision: int | None = None


RECIPES = {
    "none": None,
    "remake": PlanRecipe(args=("-dx11",), effective_api="d3d11", quality_owner="game", recommended_input="dlss",
                         dependencies=("luma-ff7", "vcrun2022", "msvcrt40"), catalog_revision=5),
    "dx12-args": PlanRecipe(args=("-dx12",), catalog_revision=2),
    "conflict": PlanRecipe(args=("-dx11", "-DX12"), catalog_revision=1),
    "vulkan-declared": PlanRecipe(effective_api="vulkan"),
    "recipe-fg": PlanRecipe(fg={"input": "fsrfg"}, recommended_input="fsr31", dependencies=("refw",)),
    "no-optifg": PlanRecipe(optiscaler_fg=False, recommended_input="dlss", dependencies=("x",)),
}
ANALYSES = {
    "unknown": {"apis": [], "inputs": {}},
    "dx12-dlssg": {"apis": ["d3d12", "dxgi"], "inputs": INPUT_SETS["dlssg"], "streamline": 2},
    "dx11-fsrfg": {"apis": ["d3d11"], "inputs": INPUT_SETS["fsrfg"]},
    "both-apis": {"apis": ["d3d11", "d3d12"], "inputs": INPUT_SETS["all-fg"], "streamline": 1},
    "vulkan": {"apis": ["vulkan"], "inputs": INPUT_SETS["dlss"]},
}


def _table(answers: dict) -> dict:
    """Distinct answers once, each case pointing at its answer: most cases repeat a handful of plans."""
    values, index, keys = [], {}, {}
    for key, value in answers.items():
        text = json.dumps(value, sort_keys=True)
        if text not in index:
            index[text] = len(values)
            values.append(value)
        keys[key] = index[text]
    return {"values": values, "cases": keys}


def snapshot() -> dict:
    builds = list(catalog.BUILDS.values())
    describe = {f"{gpu}|{device}": catalog.describe(gpu, device) for gpu, device in product(GPUS, DEVICES)}
    preferred = {f"{gpu}|{rec}": catalog.preferred_build(gpu, PlanRecipeBuild(rec))
                 for gpu, rec in product(GPUS, ["", "unknown-build", *catalog.BUILDS])}
    for_game = {}
    for build, inputs, gpu, deps in product(builds, ("none", "fsr31", "fsr31-loader"), GPUS, ("", "luma")):
        recipe = PlanRecipe(dependencies=("luma-ff7",) if deps else ())
        shaped = catalog.for_game(build, INPUT_SETS[inputs], gpu, recipe)
        for_game[f"{build.id}|{inputs}|{gpu}|{deps}"] = {"archive": shaped.archive, "extra_dir": shaped.extra_dir, "ini": shaped.ini}
    models = {f"{build.id}|{model}": catalog.model_overrides(build, model or None)
              for build in builds for model in ("", "unknown", *(name for name, _ in build.models))}
    routes = {}
    for gpu, inputs, apis, streamline, generation in product(GPUS, INPUT_SETS, range(len(API_SETS)), (None, 1, 2), (9, 10)):
        routes[f"{gpu}|{inputs}|{apis}|{streamline}|{generation}"] = catalog.fg_routes(
            gpu, INPUT_SETS[inputs], API_SETS[apis], streamline, generation)
    plans = {}
    for gpu, inputs, apis, recipe_fg, generation, route in product(
            ("rdna3", "intel", "nvidia"), INPUT_SETS, range(3), ("", "fsrfg"), (9, 10), ("", "game", "bogus")):
        plan = catalog.fg_plan(gpu, INPUT_SETS[inputs], {"input": recipe_fg} if recipe_fg else None, generation,
                               API_SETS[apis], 2, route or None)
        key = f"{gpu}|{inputs}|{apis}|{recipe_fg}|{generation}|{route}"
        plans[key] = {"plan": plan, "overrides_on": catalog.fg_overrides(plan, True), "overrides_off": catalog.fg_overrides(plan, False),
                      "switched": catalog.fg_route_plan(plan, "optiscaler")}
    solutions = {}
    for gpu, recipe, analysis, generation, engine, route, ready in product(
            ("rdna3", "intel", "nvidia"), RECIPES, ANALYSES, (9, 10), ("optiscaler", "dll"), ("", "optiscaler"), (False, True)):
        plan = solution_plan.resolve(gpu, ANALYSES[analysis], RECIPES[recipe], generation, engine, route or None, ready)
        requested = {fg: solution_plan.requested_fg(plan, {"fg": fg, **({"fg_route": route} if route else {})}) for fg in ("on", "off")}
        solutions[f"{gpu}|{recipe}|{analysis}|{generation}|{engine}|{route}|{int(ready)}"] = {"plan": plan, "requested": requested}
    document = {
        "schema_version": 1,
        "gpus": list(GPUS), "devices": list(DEVICES), "input_sets": INPUT_SETS, "api_sets": [list(apis) for apis in API_SETS],
        "recipes": {key: (asdict(value) if value else None) for key, value in RECIPES.items()},
        "analyses": ANALYSES,
        "describe": _table(describe), "preferred": preferred, "for_game": _table(for_game), "models": models,
        "fg_routes": _table(routes), "fg_plans": _table(plans), "solutions": _table(solutions),
    }
    return json.loads(json.dumps(document))


@dataclass
class PlanRecipeBuild:
    recommended_build: str | None = field(default=None)

    def __init__(self, recommended):
        self.recommended_build = recommended or None


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
