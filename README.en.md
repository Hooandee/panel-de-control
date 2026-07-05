# Panel de Control

[Español](README.md) · **English**

The control center your handheld gaming PC was missing. Tune power, fan curves, battery, display and
controllers from a single panel inside Steam's quick access menu, without leaving your game and
without memorizing sysfs paths.

It's a plugin for [Decky Loader](https://decky.xyz/), built for the Steam Deck, ROG Ally, Legion Go,
MSI Claw and friends. One idea runs through the whole thing: every control should look good, always
show your machine's real model at the top, and never lie to you about what the hardware is actually
doing.

The interface ships in Spanish by default and falls back to English when your system asks for it.

> [!WARNING]
> This plugin runs with **root privileges** and changes low-level power, thermal, and firmware
> settings on your device. It talks only to documented kernel interfaces and is designed to fail
> safe, but you use it **at your own risk**. There is no warranty (see the [LICENSE](LICENSE)).

## What it does

The panel is organized into tabs. Each one covers a part of the machine.

### Power (Potencia)

The heart of the plugin. A visual arc that fills with TDP across your machine's real range (no made
up numbers, it reads them from firmware). You set the watts with a slider, get quick presets, and
can save a global profile or a per-game one.

- **Auto-TDP.** An automatic mode that watches GPU load and raises or lowers power on its own to give
  you the frames you need while spending as little as possible. It learns from how you play and
  self-corrects, no need to touch anything.
- **Advanced modes.** If your firmware allows it, a collapsible section to fine-tune the boost limits
  (SPPT and FPPT) as margins over the base limit.
- **GPU clock.** Set the minimum and maximum graphics clock.

### System (Sistema)

Everything that isn't raw power but is day-to-day management.

- **Battery.** State, health, cycles and capacity, in a card that fills up and changes color. It
  includes a charge limit (cap charging at a percentage to protect the battery), adapted to how each
  vendor exposes it.
- **CPU.** Toggles for multithreading (SMT) and turbo boost, with a cores-and-threads view and the
  base-to-turbo frequency range.
- **Brightness and volume.** Sliders that show the exact number, something Steam's native controls
  hide.
- **Download Mode.** A single button for leaving the machine downloading a game unattended: it drops
  TDP to the minimum, turns off boost and dims the screen while you aren't touching it. Fully
  reversible.
- **RGB lighting.** If you have the sibling plugin [Colores](https://github.com/Hooandee/decky-colores)
  installed, this card opens it; if not, it offers to install it.

### Fans (Ventiladores)

It starts as a live monitor (RPM and CPU/GPU temperatures with sparklines) and, on machines that
allow it, turns into a temperature-to-speed curve editor you can drag with your finger, with presets
(quiet, balanced, performance) and per-game curves.

It also learns. Over time it suggests a curve tuned to how each game behaves on your machine, and you
can apply it with one tap. If your machine doesn't allow writing the curve, the editor hides itself
and tells you exactly why, instead of pretending it works.

### Display (Pantalla)

Panel color calibration through gamescope: per-game saturation, global temperature and contrast, and
a one-tap "OLED look" preset for panels that aren't OLED. It comes with a confirmation timer that
reverts changes only if something looks wrong, so you never get stuck with an unreadable screen.

### Controllers (Mandos)

Button remapping that cooperates with the daemon already controlling your gamepad (Handheld Daemon on
Bazzite, InputPlumber on SteamOS) instead of fighting it. It shows a warning in Settings if it
detects a configuration conflict. This part is still early.

### Settings (Ajustes)

Language (with flags, not a dropdown), the "learn from my usage" switch (telemetry is 100% local and
can be turned off), and a button to erase what has been learned.

## Per-device compatibility

Panel de Control knows nine models and, for anything else, tries to work by probing the real
capabilities of the hardware. This table sums up what you'll find in each family. Differences usually
come from what the vendor lets you touch in firmware, not from the plugin.

Legend: **●** works · **◐** limited, read-only or default values · **○** not available

| Feature | Steam Deck | ROG Ally | Legion Go | MSI Claw 8 AI+ | Other devices |
|---|:---:|:---:|:---:|:---:|:---:|
| TDP limit | ● | ● | ● | ● | ◐ |
| Advanced modes (SPPT/FPPT) | ○ | ● | ● | ○ | ○ |
| Auto-TDP by GPU load | ● [¹](#notes) | ● | ● | ○ [²](#notes) | ◐ |
| GPU clock | ● | ● | ● | ● | ◐ |
| Battery: state, health, cycles | ● | ● | ● | ● | ● |
| Charge limit | ● | ● | ◐ [³](#notes) | ◐ | ◐ |
| CPU: turbo boost | ● | ● | ● | ● | ◐ |
| CPU: multithreading (SMT) | ● | ● | ● | ○ [⁴](#notes) | ◐ |
| CPU: active cores | ● | ● | ● | ● | ● |
| Brightness and volume | ● | ● | ● | ● | ● |
| Download Mode | ● | ● | ● | ● | ● |
| Fan monitor | ● | ● | ● | ● | ● |
| Fan curves | ● | ● | ◐ [⁵](#notes) | ● | ◐ |
| Learned per-game curves | ● | ● | ◐ [⁵](#notes) | ● | ◐ |
| Color calibration | ● | ● | ● | ● [⁶](#notes) | ● |
| "OLED look" preset | ◐ [⁷](#notes) | ● | ◐ [⁷](#notes) | ● | ● |
| Controller remap (beta) | ◐ | ◐ | ◐ | ◐ | ○ |
| RGB lighting (via Colores) | ○ [⁸](#notes) | ● | ● | ● | ◐ |

Each family covers: **Steam Deck** (LCD and OLED), **ROG Ally** (Ally 2023, Ally X, Xbox Ally X),
**Legion Go** (Go, Go S, Go 2). Every other handheld falls under "Other devices", where the plugin
marks itself as experimental and works with whatever it can probe.

### Notes

1. On the Steam Deck the GPU-load reading is instantaneous and very noisy; auto-TDP averages it
   before deciding.
2. Power profiling on Intel (RAPL / i915) isn't implemented yet, so GPU-based auto-TDP isn't
   available on the Claw. The rest of the TDP control is.
3. On Legion, the charge limit is a "conservation mode" toggle with a firmware-fixed percentage, not
   an adjustable value. On the Claw it depends on what each unit exposes.
4. The Claw's Intel Core Ultra has no hyperthreading, so there's no multithreading to enable or
   disable.
5. Legion Go 2 has a full curve; Legion Go S only coarse modes (quiet, balanced, performance); the
   original Legion Go is limited depending on the OS.
6. On Intel the color is only applied while the compositor is active, so that path is forced and the
   small cost is disclosed.
7. The "OLED look" preset is hidden on panels that are already OLED (Steam Deck OLED, Legion Go 2)
   since it makes no sense there.
8. The Steam Deck has no RGB lighting, so this card doesn't appear.

## Installation

Panel de Control is distributed outside the Decky store. Install [Decky Loader](https://decky.xyz/)
first, then:

1. Download `Panel de Control.zip` from the [latest release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. In Decky, use **Developer Mode → Install Plugin from ZIP** (or your preferred manual install
   method).

Once installed, the plugin can update itself from within its settings.

### Verifying a download (recommended)

Every release zip is signed with build provenance. Confirm it really came from this repository's
pipeline before installing:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

## Building from source

Toolchain: **pnpm 10**, **Node 20**, **Python 3.11**.

```sh
pnpm install --frozen-lockfile
pnpm build          # produces dist/index.js
```

Copy the resulting folder to `~/homebrew/plugins/` on your device and restart Decky. The Python
backend needs root (the plugin declares it) to write to sysfs; model detection, on the other hand,
doesn't. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full test gate and development setup.

## How it learns (and why it stays local)

The point of Panel de Control isn't just having nice buttons, it's that it learns from how you play
each game to suggest a better setup: which fan curve keeps you cool without noise, which power gives
you stable frames without draining the battery. All that learning stays on your device, never leaves
it, and you can turn it off or wipe it whenever you want from Settings.

The principle running through the whole project: never fake it. If a reading isn't available it's
hidden instead of showing a fake zero. If the hardware rejects a change, the interface reflects it. A
number on screen is a real number.

## Acknowledgments

This plugin stands on the work of many people in the handheld community. We reference kernel
interfaces (which are facts, not code) freely, and when we adapt ideas or code we credit it here. The
full list with licenses is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- **[SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP)** (BSD-3, Aarron Lee). The primary
  reference for the per-device TDP mechanism: the Lenovo and ASUS firmware-attributes paths, the
  `platform_profile=custom` prestep, and ryzenadj usage.
- **[Handheld Daemon (HHD)](https://github.com/hhd-dev/hhd)** (LGPL-2.1). Reference for the
  per-device strategy, re-applying on resume and on AC/DC changes, and cooperating with the
  controller daemon. We only reference the approach, we don't copy its code.
- **[RyzenAdj](https://github.com/FlyGoat/RyzenAdj)** (LGPL-3.0). Bundled as a binary for the generic
  AMD path when there's no better firmware route.
- **[PowerControl](https://github.com/mengmeet/PowerControl)**. Origin of the Lenovo
  firmware-attributes path that SimpleDeckyTDP inherits.
- **[Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic)** and **[PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools)**.
  Reference for the fan monitor and curve control and for periodic re-apply.
- **[Decky Loader](https://decky.xyz/)** and its plugin template. The base everything runs on.
- **The Linux kernel documentation** (firmware-attributes, powercap, asus-wmi, hwmon, power_supply).
  The source of the sysfs paths we read and write.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? Please report it privately, see the [Security Policy](SECURITY.md). Do not
open a public issue.

## License

[BSD-3-Clause](LICENSE) © Hooandee. The bundled ryzenadj binary keeps its own LGPL-3.0 license.
Third-party attributions are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
