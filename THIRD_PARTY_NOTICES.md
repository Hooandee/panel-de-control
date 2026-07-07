# Third-Party Notices

Panel de Control is licensed under the [BSD-3-Clause License](LICENSE).

This file lists the third-party work the project builds on. Two categories:

1. **Referenced projects** — we studied their approach or use documented, public
   hardware interfaces (kernel `sysfs` paths, daemon APIs). Interfaces and facts are
   not copyrightable; attribution here is given as courtesy and for transparency. No
   source code from these projects is copied into this repository.
2. **Bundled dependencies** — code that is redistributed inside the built plugin.

If you believe attribution is missing or incorrect, please open an issue.

## Referenced projects (approach / hardware interfaces)

| Project | License | What we reference |
| --- | --- | --- |
| [SteamDeckHomebrew/decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) | BSD-3-Clause | Project scaffold. |
| [SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP) | BSD-3-Clause | TDP mechanism reference (firmware-attributes paths, per-device approach). |
| [Handheld Daemon (hhd)](https://github.com/hhd-dev/hhd) | LGPL-2.1 | Per-device strategy, resume/AC re-apply concepts; its localhost REST API for cooperative control. Approach/interface only — no LGPL code copied. |
| [RyzenAdj](https://github.com/FlyGoat/RyzenAdj) | LGPL-3.0 | Generic AMD TDP fallback. Invoked as an external subprocess (never linked into our code). See the bundled-dependencies section below — release builds ship a prebuilt binary. |
| [PowerControl](https://github.com/mengmeet/PowerControl) | See project | Upstream of the Lenovo firmware-attributes path (chain credit). |
| [LegionGoRemapper](https://github.com/aarron-lee/LegionGoRemapper) | See project | Controller/remap reference for Legion devices. |
| [InputPlumber](https://github.com/ShadowBlip/InputPlumber) | See project | SteamOS controller daemon. We cooperate with it over its D-Bus interface; no code copied. |
| [PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools) | See project | Resume/re-apply concepts (idea only). |
| [Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic) | See project | Fan monitor/curve approach. Fans/temps read via the kernel `hwmon` ABI (facts). |
| Linux kernel ABI docs | Documentation | `sysfs` interfaces: `firmware-attributes`, `powercap`, `hwmon`, `power_supply`, `cpufreq`, and vendor WMI paths. |

## Bundled runtime dependencies

The built plugin (`dist/index.js`) bundles the following runtime packages:

| Package | License |
| --- | --- |
| [@decky/api](https://github.com/SteamDeckHomebrew/decky-frontend-lib) | BSD-3-Clause |
| [react-icons](https://github.com/react-icons/react-icons) | MIT |
| [tslib](https://github.com/microsoft/tslib) | 0BSD |
| React / React-DOM (provided by the Decky runtime) | MIT |

### Bundled binary (release builds only)

Release builds also include a prebuilt [RyzenAdj](https://github.com/FlyGoat/RyzenAdj)
CLI binary at `bin/ryzenadj` (built from source at a pinned tag during the release
pipeline; not committed to this repository). It is used only as a last-resort generic
AMD power fallback and is invoked as a standalone subprocess — it is **not** linked
into the plugin's code. RyzenAdj is licensed under the **LGPL-3.0**; its full license
text ships alongside the binary as `bin/ryzenadj-LICENSE.txt`. RyzenAdj's
corresponding source is available at its upstream repository at the pinned tag. Dev
and prerelease builds omit the binary; the fallback simply reports as unsupported.

Development-only tooling (TypeScript, Rollup, Vitest, Ruff, pytest, `@decky/ui`,
`@decky/rollup`, type stubs) is not redistributed and is listed in `package.json`
and `requirements-dev.txt`.
