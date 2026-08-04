# Third-Party Notices

Panel de Control is licensed under the [GNU General Public License v3.0](LICENSE)
(`GPL-3.0-only`).

This file lists the third-party work the project builds on. Three categories:

1. **Derived code** — source adapted from another project. This is why Panel de
   Control is GPL-3.0: it incorporates code from a GPL-3.0 project.
2. **Referenced projects** — we studied their approach or use documented, public
   hardware interfaces (kernel `sysfs` paths, daemon APIs). Interfaces and facts are
   not copyrightable; attribution here is given as courtesy and for transparency. No
   source code from these projects is copied into this repository.
3. **Bundled dependencies** — code that is redistributed inside the built plugin.

If you believe attribution is missing or incorrect, please open an issue.

## Derived code

| Project | License | What we adapt |
| --- | --- | --- |
| [decky-steamgriddb](https://github.com/SteamGridDB/decky-steamgriddb) | GPL-3.0 | The library context-menu patch technique (`src/launch/gameContextMenu.tsx` is adapted from its `contextMenuPatch`: locating Steam's `LibraryContextMenu` and inserting a menu item). This derivation is why the whole plugin is GPL-3.0. |

## Referenced projects (approach / hardware interfaces)

| Project | License | What we reference |
| --- | --- | --- |
| [SteamDeckHomebrew/decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template) | BSD-3-Clause | Project scaffold. |
| [SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP) | BSD-3-Clause | TDP mechanism reference (firmware-attributes paths, per-device approach). |
| [Handheld Daemon (hhd)](https://github.com/hhd-dev/hhd) | LGPL-2.1 | Per-device strategy, resume/AC re-apply concepts; its localhost REST API for cooperative control. Approach/interface only — no LGPL code copied. |
| [RyzenAdj](https://github.com/FlyGoat/RyzenAdj) | LGPL-3.0 | Generic AMD TDP fallback. Invoked as an external subprocess (never linked into our code). See the bundled-dependencies section below — release builds ship a prebuilt binary. |
| [PowerControl](https://github.com/mengmeet/PowerControl) | See project | Upstream of the Lenovo firmware-attributes path (chain credit). |
| [LegionGoRemapper](https://github.com/aarron-lee/LegionGoRemapper) | See project | Controller/remap reference for Legion devices. |
| [InputPlumber](https://github.com/ShadowBlip/InputPlumber) | GPL-3.0-or-later | SteamOS controller daemon. We normally cooperate over D-Bus; the exact Xbox Ally X extension described below is redistributed as a modified binary. |
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

The Xbox Ally X HD haptics extension redistributes a modified
[InputPlumber](https://github.com/ShadowBlip/InputPlumber) executable. It is
built from commit
`bb7424fd6fc097d123850950aaf1e6988f2093f3` with
`assets/inputplumber/v0.77.4-xbox-hd.patch` and is activated only when the
device, installed InputPlumber version and stock executable hash all match.
InputPlumber is licensed under **GPL-3.0-or-later**. The pinned upstream commit,
bundled patch and `scripts/build-inputplumber-xbox-hd.sh` constitute the
reproducible corresponding-source recipe for the redistributed executable; the
GPL text is included in this repository's [LICENSE](LICENSE).

### Windows Xbox Game Bar package

The experimental Windows package redistributes these runtime dependencies:

| Package | License |
| --- | --- |
| [Microsoft.Gaming.XboxGameBar](https://www.nuget.org/packages/Microsoft.Gaming.XboxGameBar) | Microsoft Software License Terms |
| [Microsoft.NETCore.UniversalWindowsPlatform](https://www.nuget.org/packages/Microsoft.NETCore.UniversalWindowsPlatform) | Microsoft Software License Terms |
| [LibreHardwareMonitorLib](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | MPL-2.0 |
| [.NET runtime, System.Management and System.IO.Pipes.AccessControl](https://github.com/dotnet/runtime) | MIT |
| [System.IO.Pipes](https://www.nuget.org/packages/System.IO.Pipes) | MIT |
| [DiskInfoToolkit](https://github.com/Blacktempel/DiskInfoToolkit), [BlackSharp.Core](https://github.com/Blacktempel/BlackSharp), and [RAMSPDToolkit-NDD](https://github.com/Blacktempel/RAMSPDToolkit) | MPL-2.0 |
| [HidSharp](https://www.nuget.org/packages/HidSharp) | Apache-2.0 |
| [Mono.Posix.NETStandard](https://www.nuget.org/packages/Mono.Posix.NETStandard) | See package license terms |

The package includes this notice plus the license files supplied by dependencies
that require redistribution. Source for MPL-covered components is available from
the linked upstream projects. Exact resolved versions are recorded in
`windows/src/PanelDeControl.Hardware/packages.lock.json`.

Development-only tooling (TypeScript, Rollup, Vitest, Ruff, pytest, `@decky/ui`,
`@decky/rollup`, type stubs) is not redistributed and is listed in `package.json`
and `requirements-dev.txt`.
