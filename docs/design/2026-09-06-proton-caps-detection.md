# Plan: Detect Proton-CachyOS launch-option capabilities

## Problem
On ASUS ROG Ally X (Z1 Extreme = RDNA3) + CachyOS, the FSR4/OptiScaler pills
(`fsr4`, `fsr4Rdna3`, `fsr4Official`, `optiscaler`) never show.

Root cause: `py_modules/launch/proton_caps.py` only recognizes capabilities
declared via `check_environment("PROTON_...")` in the `proton` script, plus
`FSR4_UPGRADE` only when `contrib/amdxcffx64.dll` is bundled. Modern
Proton-CachyOS (10.0-20251222+) moved upscaler handling into **protonfixes**
(runtime), downloads the FSR4 DLL at runtime (not bundled), and 11.0-20260702
removed `PROTON_FSR4_RDNA3_UPGRADE`. So `detect_capabilities()` returns an
envs list missing all four → `pillVisible()` hides them.

`fsr4` (PROTON_FSR4_UPGRADE) is rdna4-only → correctly hidden on RDNA3 (no change).

## User-confirmed finding (2026-09-06)
- "ProtonCachyOS Latest" → OptiScaler pill APPEARS. So the current
  `check_environment` regex DOES match Proton-CachyOS's `proton` script for
  `PROTON_USE_OPTISCALER` (folder was found).
- "proton-cachyos-11.0-2026-07-03 (steam linux runtime)" → does NOT appear.
  The "(steam linux runtime)" is the DISPLAY name; matching uses the internal
  id (`strCompatToolName`) against the EXACT folder name in
  `compatibilitytools.d/<compat_name>/proton` (no normalization/substring/case).
- User's actual `compatibilitytools.d` folders:
  `LegacyRuntime`, `Proton-CachyOS Latest`, `Proton-CachyOS Latest-x86_64_v3`,
  `Proton-GE Latest`.
- KEY (user-confirmed): the versioned entry's id `proton-cachyos-11.0-2026-07-03`
  maps to the folder `Proton-CachyOS Latest-x86_64_v3` — the v3 variant of
  "Proton-CachyOS Latest" installed via **ProtonPlus** into the user's own
  `~/.steam/steam/compatibilitytools.d`. ProtonPlus names the folder with the
  alias + variant suffix but writes the versioned id into `toolmanifest.vdf`
  (`compat_tool_name`). The folder IS in the user's roots, but its name ≠ the
  id, so the exact-match in `_find_proton_script()` fails → `found: false` → no
  Proton-gated pills. THIS is the primary cause for the user's case. Fix:
  resolve the id via the folder's `toolmanifest.vdf` `compat_tool_name`
  (Phase 1). Workaround: select "Proton-CachyOS Latest" (its id matches its
  folder → works).
- NEW (2026-09-07): user removed "Proton-CachyOS Latest", kept only
  `Proton-CachyOS Latest-x86_64_v3` → NO optiscaler/fsr4 options (confirms
  Phase 1 bug: folder name ≠ id → `found: false`). Selecting "Proton-GE Latest"
  shows `PROTON_FSR4_RDNA3_UPGRADE` + OptiScaler — GE-Proton still supports
  RDNA3_UPGRADE (unlike CachyOS 11.0), so that is CORRECT per-build behavior.
  Expectation check: CachyOS v3 + CachyOS Latest = same build → identical
  options (after Phase 1). GE = different build → different options (shows
  `fsr4Rdna3`; CachyOS 11.0 shows `fsr4Official` instead). "Same options across
  all three" is NOT the goal — correct options per build is.
- CONFIRMED via changelog (11.0-20260702): `PROTON_FSR4_RDNA3_UPGRADE` was
  REMOVED ("setting DXIL_SPIRV_CONFIG=wmma_rdna3_workaround is not required any
  more in most cases"). So on "Latest" (11.0-20260703) the `fsr4Rdna3` pill
  SHOULD NOT appear — current behavior is CORRECT for that build. The correct
  FSR4 pill on RDNA3 + 11.0 is `fsr4Official` (`FSR4_UPGRADE` short name), which
  works because the DLL is now always present (copied automatically at runtime,
  NOT bundled) — so detection must add `FSR4_UPGRADE` from protonfixes, not from
  a bundled DLL. `fsr4Rdna3` remains correct for 10.x builds only.

## Approach (recommended)
1. PRIMARY (user's explicit request): resolve the game's compat-tool id to its
   folder via `toolmanifest.vdf` `compat_tool_name` — makes
   `Proton-CachyOS Latest-x86_64_v3` (id `proton-cachyos-11.0-2026-07-03`) show
   the same options as `Proton-CachyOS Latest`. Also scan system-wide roots for
   robustness.
2. PRIMARY (11.0 detection): broaden env-var detection to scan the build's
   Python files (protonfixes) for `PROTON_*` tokens + upscaler short names
   (`FSR4_UPGRADE`, …), self-updating per version. Unlocks `fsr4Official` on
   11.0 (DLL now runtime-copied, not bundled). Keep `_CORE` + bundled-DLL checks
   + retired-var guard.

## Development setup (per CONTRIBUTING.md)
- Backend: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt`
- Frontend (only if Phase 3 UI change is included): `pnpm install --frozen-lockfile`
- Toolchain: pnpm 10, Node 20, Python 3.11.

## Steps

### Phase 1 — Robust compat-tool resolution (PRIMARY — user's explicit request)
1. Build an id→folder map: for every `compatibilitytools.d` folder found, read
   its `toolmanifest.vdf` and extract `compat_tool_name` (the authoritative id
   Steam uses — handles `-slr`/`-native`/`-x86_64_v3` variant folders and
   space/hyphen differences); fall back to the folder name when no manifest.
   This makes `Proton-CachyOS Latest-x86_64_v3` (id
   `proton-cachyos-11.0-2026-07-03`) resolve exactly like `Proton-CachyOS Latest`
   does.
2. Resolve the game's `compat_name` through that map first; if still missing,
   try case-insensitive + known-suffix/substring fallbacks against folder names.
3. Expand `_steam_roots()` to also scan system-wide compat-tool dirs that Steam
   registers on distros like CachyOS:
   `/usr/share/steam/compatibilitytools.d`, `/usr/local/share/steam/compatibilitytools.d`
   (plus the existing `~/.steam/steam` + `~/.local/share/Steam`).
4. Keep `found` semantics: still False when no script located.

### Phase 2 — Broaden env-var detection (needed for `fsr4Official` on 11.0)
5. Add `_scan_build_envs(build_dir)` that walks the build's `.py` files (incl.
   `protonfixes/`) + the `proton` script, matching:
   - `PROTON_[A-Z0-9_]+` tokens (covers `os.environ.get("PROTON_...")`, bare
     string literals in protonfixes, and existing `check_environment` calls)
   - upscaler short names: `FSR4_UPGRADE`, `FSR3_UPGRADE`, `XESS_UPGRADE`,
     `DLSS_UPGRADE`
6. In `detect_capabilities()`: union `_CORE` + `_ENV_RE` (proton script) +
   `_scan_build_envs(build_dir)` + bundled-DLL `FSR4_UPGRADE`.
7. **NO global `_RETIRED` list.** The scan reports what each build actually
   references, which is the correct per-build behavior: CachyOS 11.0 removed
   `PROTON_ENABLE_HDR` (11.0-20260506 → `DXVK_HDR`) and
   `PROTON_FSR4_RDNA3_UPGRADE` (11.0-20260702), so those builds no longer
   reference them → pills stay hidden; GE-Proton still references them → pills
   show (correct, and keeps the existing GE test green). A global exclusion
   would wrongly hide HDR/RDNA3 on GE-Proton. (If a future build resurrects a
   var, add a targeted `_RETIRED` then.)

### Phase 3 — (optional) UX
8. Surface `found: false` in the editor UI (e.g. a muted "no Proton build
   found" hint) so users understand why Proton-gated pills are missing.

### Phase 4 — Tests in `tests/test_proton_caps.py`
8. Add test: exact folder match still works (existing behavior).
9. Add test: `toolmanifest.vdf` with `compat_tool_name` resolving the real
   CachyOS pair — folder `Proton-CachyOS Latest-x86_64_v3` → id
   `proton-cachyos-11.0-2026-07-03` — is found for that `compat_name`.
10. Add test: system-wide root (`/usr/share/steam/compatibilitytools.d`) is
    scanned (injectable root for tests).
11. Add test: a build with a `protonfixes/` dir referencing
    `PROTON_USE_OPTISCALER` + `FSR4_UPGRADE` → both reported (covers 11.0).
12. Add test: a 10.x-style build referencing `PROTON_FSR4_RDNA3_UPGRADE` →
    reported (so `fsr4Rdna3` shows on 10.x only).
13. Add test: retired var (`PROTON_ENABLE_HDR`) excluded.
14. Keep existing official/GE tests green (behavior unchanged).

## Relevant files
- `py_modules/launch/proton_caps.py` — `_ENV_RE`, `_CORE`, `_OFFICIAL_FSR4_DLL`,
  `_steam_roots`, `_find_proton_script`, `detect_capabilities`; add
  `_scan_build_envs`, `_compat_roots`/`_compat_id_to_folder` (toolmanifest.vdf
  id→folder map), system-wide roots, variant-suffix fallbacks.
- `tests/test_proton_caps.py` — extend with manifest/variant-root/protonfixes
  fixtures (reuse `_write_proton`/`_write_builtin_proton` helpers).
- NO changes to `src/launch/catalog.ts` — per-GPU/per-var gating already correct;
  `fsr4Official`/`optiscaler` will show once `supportedEnvs` is right; `fsr4Rdna3`
  correctly hidden on 11.0 (var removed upstream).

## Verification
1. Backend quality gate (per CONTRIBUTING.md):
   - `ruff check py_modules main.py tests`
   - `python -m pytest` (full suite — new + existing tests)
2. Frontend gate (only if Phase 3 UI change is included):
   - `pnpm typecheck`, `pnpm test:fe`, `pnpm build` (must produce `dist/index.js`)
3. Manual on Ally X + Proton-CachyOS "Latest" (11.0): open launch editor →
   `fsr4Official` (FSR4_UPGRADE) + `optiscaler` appear; `fsr4Rdna3` does NOT
   (correct — removed in 11.0); `fsr4` stays hidden (RDNA3).
4. Manual on the versioned entry (`proton-cachyos-11.0-2026-07-03`, folder
   `Proton-CachyOS Latest-x86_64_v3`): shows the SAME options as "Latest"
   (manifest resolution).
5. Manual on a 10.x build (if available): `fsr4Rdna3` appears.
6. Manual regression: official Proton without bundled DLL → still no FSR4 pills.

## Decisions
- Scan-based env-var detection (self-updating) over static name→vars map:
  avoids stale pills as Proton-CachyOS versions churn (RDNA3_UPGRADE removed in
  11.0, FSR3_UPGRADE renamed to FFX3_UPGRADE).
- Resolve compat tools via `toolmanifest.vdf` (authoritative id) + expanded
  roots, rather than guessing folder names — handles CachyOS's system-wide
  versioned installs and variant suffixes.
- No global retired-var guard: the scan reports what each build references, so
  removed vars (HDR, RDNA3_UPGRADE on CachyOS 11.0) naturally disappear while
  GE-Proton keeps them. Keeps existing GE tests green and honors "correct
  options per build".
- UX hint for `found: false` optional (Phase 3) — include if cheap.
- Commit as `fix:` (Conventional Commits → patch release via release-please); no
  new third-party deps, so no `THIRD_PARTY_NOTICES.md` update needed.
- Follow CONTRIBUTING principles: never fake success (keep `found: false` honest —
  only report envs confirmed against a real build), degrade gracefully
  (`detect_capabilities` never raises — keep the try/except), test pure logic
  (`_scan_build_envs` + manifest parsing are unit-tested).
- Version-agnostic by design: the id→folder map reads the CURRENT
  `toolmanifest.vdf` `compat_tool_name` at runtime, and `_scan_build_envs` reads
  the CURRENT build's files — so when CachyOS bumps to a new version (e.g.
  `proton-cachyos-11.0-2026-09-10`), the folder's manifest id and the game's
  `compat_name` update together and resolution keeps working. The test fixture
  id is a synthetic representative (it tests the mechanism, not a pinned
  version). The only manual-maintenance spot is the small `_RETIRED` list (only
  if a future build resurrects a var).