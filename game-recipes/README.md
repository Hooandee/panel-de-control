# Game recipes

This directory is the versioned, public catalog used by Panel de Control. Each game has one stable file in `games/<Steam appid>.json`. Runtime implementation lives separately in `py_modules/upscalers/recipe_catalog.py`.

- `catalog.json`: schema and catalog versions.
- `assets.json`: pinned release downloads, exact sizes and SHA-256 hashes.
- `dependencies.json`: reusable file mappings and supported Proton prerequisites.
- `games/`: executable paths, explicit engine/platform/architecture conditions, launch arguments, OptiScaler settings and dependency IDs.
- `schema.json`: document shapes; the loader additionally validates references, dependency cycles, duplicate keys, case-insensitive destinations, source origins and bounded reads.

Increase a game's `revision` when changing its behavior and `catalog_version` when changing any catalog data. Keep sources on each game and release provenance on each asset. Recipes contain data only: scripts, shell commands and arbitrary Winetricks verbs are not accepted. Supported prerequisite verbs are `vcrun2022` and `msvcrt40`.

File mappings use `destination: archive member`, relative to the selected executable directory and archive root respectively. Paths cannot escape those roots. The installer must also reject archive symlinks and reparse points, verify downloads against the pinned hash and size, preserve unrelated files and roll back failed changes. Dependency files are merged first; the selected OptiScaler files take precedence for shared upscaler libraries.

Final Fantasy VII Remake uses the official Luma release `latest-800`. Its `dxgi.dll` is mapped to `ReShade64.dll`, loaded through OptiScaler with `Plugins.LoadReshade=true`. The recipe requests DX11 and disables `Hotfix.CreateD3D12DeviceForLuma`. A matching recipe describes prerequisites; it does not establish that they are installed or active.

## Loader API

`load(directory)` validates the whole catalog and raises `CatalogError` on invalid data. `bundled()` caches the distributed catalog and returns an empty catalog if loading fails. `Catalog.match(appid, engine, platform=None, arch=None)` returns a matching recipe or `None`; omitted platform and architecture use the actual host, with AMD64/ARM64 normalized. `Catalog.dependency_order(ids)` returns prerequisites before dependents, without duplicates. Assets and dependencies are available by ID through `Catalog.assets` and `Catalog.dependencies`.

Validate changes with `python -m pytest tests/test_upscalers_recipe_catalog.py tests/test_upscalers.py`. Include this entire directory when packaging Panel de Control.

## Game updates

The canonical recipe path remains `game-recipes/games/<Steam appid>.json`, independent of runtime refactors. `tested_game_builds` and `tested_at` record observed game builds and the evidence date; they do not guarantee compatibility with every version. An optional `conditions.game_builds` restricts application to listed builds. When that restriction exists, missing or different build IDs do not match. Without it, a game update alone does not disable the recipe. Pass the installed build as `Catalog.match(..., game_build=build_id)`.

After a game update, verify prerequisites and launch behavior, append the observed build and update the evidence date. If changed files or configuration require a different recipe, update its mappings/settings, increment the game revision and catalog version, and re-run the catalog tests. Add a build restriction only when compatibility requires one.

`configuration` applies allowlisted INI keys while preserving unrelated settings. Remake sets `ReShade.ini` → `Luma.SRUserType=2` so Luma supplies DLSS input to OptiScaler even after a previous disabled selection. The installer stages this edit and includes it in its file rollback. A nonempty `INSTALL.BasePath` redirect is unsupported; an existing configuration is never silently replaced.

`recommended_input` is optional game-menu guidance (`dlss`, `fsr31`, `fsr2` or `xess`), separate from the output upscaler selected in Panel. It is offered only for detected game inputs and the matching engine. It does not change game settings or prove the requested rendering quality is active.
