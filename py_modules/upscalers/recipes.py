"""What a particular game needs besides OptiScaler, so nobody has to research it.

Each entry is data checked against the OptiScaler wiki and, where marked, a real
install on a handheld. Panel applies it on install and undoes exactly what it added.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Recipe:
    appid: str
    exe: str | None = None
    args: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict)
    native_dlls: tuple[str, ...] = ()
    ini: dict[str, str] = field(default_factory=dict)


RECIPES: dict[str, Recipe] = {
    recipe.appid: recipe
    for recipe in (
        # REDlauncher waits for a click under Proton; DX12 is the build that ships the upscalers.
        Recipe("292030", exe="bin/x64_dx12/witcher3.exe", args=("--launcher-skip", "-dx12")),
        # RE Engine exposes its upscaler to OptiScaler only through REFramework.
        Recipe("2054970", files={"dinput8.dll": "reframework-nightly"}, native_dlls=("dinput8",)),
    )
}


def recipe_for(appid: str) -> Recipe | None:
    return RECIPES.get(str(appid))
