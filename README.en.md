# Panel de Control

[Español](README.md) · **English**

<p align="center">
  <a href="https://ko-fi.com/hooandee"><img src="https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
  <a href="https://www.patreon.com/hooandee"><img src="https://img.shields.io/badge/Patreon-Support%20me-FF424D?style=for-the-badge&logo=patreon&logoColor=white" alt="Patreon"></a>
  <a href="https://www.youtube.com/channel/UCDsSJByXklp6xc_WwQJI7Lw/join"><img src="https://img.shields.io/badge/YouTube-Become%20a%20member-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://discord.gg/x2ZNARy"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://linktr.ee/hooandee"><img src="https://img.shields.io/badge/All%20my%20links-Linktree-43E660?style=for-the-badge&logo=linktree&logoColor=white" alt="Linktree"></a>
</p>

<p align="center">
  <a href="https://github.com/Hooandee/panel-de-control/actions/workflows/ci.yml"><img src="https://github.com/Hooandee/panel-de-control/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/Hooandee/panel-de-control/releases/latest"><img src="https://img.shields.io/github/v/release/Hooandee/panel-de-control?label=latest%20release&color=blue" alt="Latest release"></a>
</p>

The control center your handheld gaming PC was missing. Tune power, fan curves, battery, display and
controllers from a single panel inside Steam's quick access menu, without leaving your game and
without memorizing sysfs paths.

It's a plugin for [Decky Loader](https://decky.xyz/), built for the Steam Deck, ROG Ally, Legion Go,
MSI Claw and friends. One idea runs through the whole thing: every control should look good, always
show your machine's real model at the top, and never lie to you about what the hardware is actually
doing.

The interface ships in Spanish by default and falls back to English when your system asks for it.

## Video

In this video I show and explain the plugin in depth:

[![Panel de Control in action](https://img.youtube.com/vi/sDpXFTxG7NQ/maxresdefault.jpg)](https://youtu.be/sDpXFTxG7NQ)

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
- **Boost.** If your firmware allows it, you choose how the SPPT and FPPT rails behave: Stable
  (what you set is what it draws, the default), Auto (a managed boost margin) or Custom (tune the
  margins by hand).
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

Panel color calibration through gamescope, turned into a small lab: one-tap looks (Native, Cinema,
Vivid, Comfort) tuned per panel type, per-game saturation, and an advanced mode with temperature,
contrast, gamma, hue, black level, vibrance and manual white balance (RGB). It adds a night mode that
warms the screen, always or on a schedule you pick, plus a one-tap "OLED look" preset for panels that
aren't OLED. A confirmation timer reverts changes only if something looks wrong, so you never get
stuck with an unreadable screen. On HDR panels (Steam Deck OLED and Legion Go 2) there's also an HDR
toggle.

### Sound (Sonido)

A system equalizer with curated presets and a per-machine correction curve as a starting point,
three simple controls (bass, voice, treble) and a full 10-band advanced EQ with a fullscreen view.
Independent curve for speaker and headphones, per game or global. Includes a bass enhancer, volume
leveling, left/right balance, test samples to hear the effect, and a guard that caps how far you can
boost bass and treble so the speakers aren't overdriven (can be turned off).

### Controllers (Mandos)

Button remapping that cooperates with the daemon already controlling your gamepad (Handheld Daemon on
Bazzite, InputPlumber on SteamOS) instead of fighting it. It shows a warning in Settings if it
detects a configuration conflict. This part is still early.

### Parameters (Parámetros)

Manage each game's launch options without wrestling Steam's syntax. The list shows your games with
their cover art (Steam and non‑Steam, including any artwork you've set), sorted by recent play, with
search and other sort orders. Each option is a row with a plain‑language explanation and a toggle: turn
on Proton variables (FSR4, sync tweaks, HDR, upscaling…) and wrappers like MangoHud, and it only offers
the ones your Proton build actually supports, checked against the game itself. It keeps whatever you
already had (EmuDeck, launchers, your manual tweaks). You can define your own variables to reuse across
games, hide the ones you don't use (tools like Proton versions hide themselves), and jump straight to
the game you're playing. It also adds an entry to the game's library context menu.

### Settings (Ajustes)

Language (with flags, not a dropdown), the "learn from my usage" switch (telemetry is 100% local and
can be turned off), and a button to erase what has been learned. Under "Customize interface" you can
reorder and hide tabs and blocks, turn whole modules on or off (disabling stops that feature across
the panel; hiding just stops showing it here), build your own tabs (custom views) from whichever
blocks you want across categories and place them anywhere in the tab order, and pick the panel's
accent color from a palette.

The whole panel is fully controller-navigable: whatever the cursor is on gets a clear accent outline,
so you never need the touchscreen.

## Per-device compatibility

Panel de Control knows nine models and, for anything else, tries to work by probing the real
capabilities of the hardware. This table is honest about what's **verified on each device** and what
isn't yet: I'd rather show you "unconfirmed" than a false "yes". Differences come from what each
vendor lets you touch in firmware and from each distro's kernel.

Legend: **✅** verified on that device · **⚠️** limited or default only · **❌** not available · **❔**
supported in code but not confirmed on that device yet

| Feature | Steam Deck LCD | Steam Deck OLED | ROG Ally | ROG Ally X | ROG Xbox Ally X | Legion Go | Legion Go S | Legion Go 2 | MSI Claw 8 AI+ |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| TDP limit | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Boost (SPPT/FPPT) | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹](#notes) |
| Auto-TDP by GPU load | ✅ [²](#notes) | ✅ [²](#notes) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [³](#notes) |
| GPU clock | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) | ❔ [⁴](#notes) |
| Battery: state and health | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Battery cycle count | ❌ [⁵](#notes) | ❌ [⁵](#notes) | ❌ [⁵](#notes) | ❌ [⁵](#notes) | ❌ [⁵](#notes) | ✅ | ✅ | ✅ | ❌ [⁵](#notes) |
| Charge limit | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [⁶](#notes) | ❔ | ⚠️ [⁷](#notes) | ✅ |
| CPU: turbo boost | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CPU: multithreading (SMT) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [⁸](#notes) |
| CPU: active cores | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Brightness and volume | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Sound equalizer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [¹⁷](#notes) |
| Download Mode | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Temperature monitor | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [⁹](#notes) |
| Fan RPM monitor | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹⁰](#notes) | ✅ [⁹](#notes) |
| Fan curves | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ [¹¹](#notes) | ⚠️ [¹²](#notes) | ❔ [¹⁰](#notes) | ⚠️ [⁹](#notes) |
| Learned per-game curves | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ [¹¹](#notes) | ❌ [¹²](#notes) | ❔ [¹⁰](#notes) | ❌ [⁹](#notes) |
| Firmware modes (profiles) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ [¹¹](#notes) | ❌ | ❌ | ❌ |
| Color calibration | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [¹³](#notes) |
| "OLED look" preset | ✅ | ❌ [¹⁴](#notes) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ [¹⁴](#notes) | ✅ |
| Controller remap (beta) | ❌ | ❌ | ⚠️ [¹⁵](#notes) | ⚠️ [¹⁵](#notes) | ❌ [¹⁵](#notes) | ⚠️ [¹⁵](#notes) | ❌ [¹⁵](#notes) | ⚠️ [¹⁵](#notes) | ⚠️ [¹⁵](#notes) |
| RGB lighting (via Colores) | ❌ [¹⁶](#notes) | ❌ [¹⁶](#notes) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Any other handheld falls under an **experimental generic** profile: the plugin probes the real
capabilities and shows what it can, honestly hiding the rest.

The **OneXPlayer OneXFly Apex** (Ryzen AI Max+ 395) is now recognised by name and comes in as
experimental. TDP control goes through the generic AMD path, so it should work; fans and the
charge limit only light up if the device exposes the nodes, and until someone runs it in person
we would rather not assume anything. If you own one, reports from the Settings tab help a lot to
dial it in.

The **AOKZOE A1X** (Ryzen AI 9 HX 370) is also recognised by name and comes in as experimental. Its
TDP runs through the same generic AMD path (ryzenadj), but with a 30 W ceiling instead of being
capped at the generic profile's 15 W. As with the OneXFly we do not own one, so reports from the
Settings tab are gold for confirming what actually responds.

The **GPD Win Mini 2025** (Ryzen AI 9 HX 370/365) and the **MSI Claw A8** (Ryzen Z2 Extreme) are now
recognised by name and come in as experimental too. They used to show up as generic with TDP stuck
at 15 W; now they go up to a safe 35 W ceiling (the manufacturer-rated peak, well below the chip's
theoretical cTDP) with three tuned presets. Both run through the same generic AMD path (ryzenadj),
and we do not own either, so reports from the Settings tab help confirm it.

The same batch recognises a few more, all experimental and each with a safe manufacturer-rated
ceiling: the **OneXPlayer F1 Pro** (Ryzen AI 9 HX 370, up to 30 W), the **GPD Win 5** (Ryzen AI Max
385 "Strix Halo", up to 55 W), the **GPD Win Max 2** (Ryzen 7 8840U, up to 35 W) and the **ROG Xbox
Ally** with the Ryzen Z2 A (the white one), which also reported a bogus 100 W firmware ceiling and is
now capped to the real 20 W ASUS rates it at. The **Legion Go 2** with the plain Ryzen Z2 (not
Extreme) is now detected by name instead of as a generic device. For anything we do not own, reports
from the Settings tab are what confirm how it really behaves.

### Notes

1. The Claw controls TDP through `intel-rapl`, which only exposes the base limit (PL1); there are no
   separate boost rails to tune.
2. On the Steam Deck the GPU-load reading is instantaneous and very noisy; auto-TDP averages it
   before deciding.
3. Power profiling on Intel (RAPL / i915) isn't implemented yet, so GPU-based auto-TDP isn't
   available on the Claw. The rest of the TDP control works.
4. GPU-clock writing is implemented per device, but it hasn't been confirmed with a live change on
   any machine yet. Marked as unconfirmed until validated.
5. The cycle counter is only populated by Lenovo firmware; on ASUS, Steam Deck and MSI the node
   reports a fake 0, so it's hidden instead of showing an invented zero.
6. The original Legion Go (83E1) doesn't expose `conservation_mode`, so it offers no charge limit.
7. On Legion the charge limit is a "conservation mode" toggle with a firmware-fixed percentage, not
   an adjustable value.
8. The Claw's Intel Core Ultra has no hyperthreading, so there's no multithreading to enable or
   disable.
9. On the MSI Claw the fan chip (`msi_wmi_platform`) exposes fan RPM (the monitor does show both fans;
   at low temperatures they sit at 0 in silent mode), but its kernel can't write the curve. The curve
   the firmware applies is read over the EC and shown read-only; editing is in progress (fan-speed
   control will be enabled safely).
10. The Legion Go 2 exposes no writable hwmon fan; RPM would have to be read over the EC, and on the
    current build it isn't showing up in the monitor. Marked as not available / unconfirmed until I
    can review it.
11. The original Legion Go drives its fan curve through the `legion_wmi_fan` kernel driver, which ships
    on some kernels and turns on by itself when present. Where it's absent (current SteamOS and some
    kernels), the fan is governed by the **firmware modes** (Quiet/Balanced/Performance) from the Power
    arc, which set power and fan together. The speed monitor always works: if the driver publishes no
    hwmon node, RPM is read over the EC.
12. The Legion Go S drives its fan over an unofficial embedded-controller (EC) path, so it's an
    optional experimental control: you enable it by hand, with a safety speed cap. Left off, it stays
    monitor-only.
13. On Intel the color is only applied while the compositor is active, so that path is forced and the
    small cost is disclosed.
14. The "OLED look" preset is hidden on panels that are already OLED (Steam Deck OLED, Legion Go 2)
    since it makes no sense there.
15. Remapping cooperates with the system daemon (HHD on Bazzite, InputPlumber on SteamOS) and is
    early. It doesn't appear on the Steam Deck; on the Legion Go S and ROG Xbox Ally X the app says
    there's no remapping for that controller yet. On Legion some back buttons aren't detected well yet.
16. The Steam Deck has no RGB lighting, so this card doesn't appear.
17. The equalizer uses PipeWire's filter-chain (available on SteamOS and Bazzite). The bass enhancer
    and volume leveling need the system's CAPS plugin; if it isn't installed the equalizer still
    works, just without those two extras.

> Cells marked **❔** are the ones I haven't confirmed on that specific device. If you have the
> hardware in front of you and see something works (or doesn't), tell me and I'll fix it: this table
> should reflect reality, not what the code tries to do.

## Installation

Panel de Control is distributed outside the Decky store. Install [Decky Loader](https://decky.xyz/)
first, then:

1. Download `Panel de Control.zip` from the [latest release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. In Decky, use **Developer Mode → Install Plugin from ZIP** (or your preferred manual install
   method).

Once installed, the plugin can update itself from within its settings.

### Verifying a download (recommended)

Releases published once the repository is public are signed with build provenance. When the signature
is available, you can confirm the zip really came from this repository's pipeline:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

## How it learns (and why it stays local)

The point of Panel de Control isn't just having nice buttons, it's that it learns from how you play
each game to suggest a better setup: which fan curve keeps you cool without noise, which power gives
you stable frames without draining the battery. All that learning stays on your device, never leaves
it, and you can turn it off or wipe it whenever you want from Settings.

The principle running through the whole project: never fake it. If a reading isn't available it's
hidden instead of showing a fake zero. If the hardware rejects a change, the interface reflects it. A
number on screen is a real number.

## Acknowledgments

This plugin stands on the work of many people in the handheld community. I reference kernel
interfaces (which are facts, not code) freely, and when I adapt an idea or a bit of code I credit it
here. The full list with licenses is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

- **[SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP)** (BSD-3, Aarron Lee). The primary
  reference for the per-device TDP mechanism: the Lenovo and ASUS firmware-attributes paths, the
  `platform_profile=custom` prestep, and ryzenadj usage.
- **[Handheld Daemon (HHD)](https://github.com/hhd-dev/hhd)** (LGPL-2.1). Reference for the
  per-device strategy, re-applying on resume and on AC/DC changes, and cooperating with the
  controller daemon. I only looked at the approach, I didn't copy its code.
- **[RyzenAdj](https://github.com/FlyGoat/RyzenAdj)** (LGPL-3.0). Invoked as an external process for
  the generic AMD path when there's no better firmware route; not bundled inside the plugin.
- **[PowerControl](https://github.com/mengmeet/PowerControl)**. Origin of the Lenovo
  firmware-attributes path that SimpleDeckyTDP inherits.
- **[Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic)** and **[PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools)**.
  Reference for the fan monitor and curve control and for periodic re-apply.
- **[Decky Loader](https://decky.xyz/)** and its plugin template. The base everything runs on.
- **[decky-steamgriddb](https://github.com/SteamGridDB/decky-steamgriddb)** (GPL-3.0). I adapted its
  technique for adding the Parameters entry to a game's library context menu. That adaptation is why
  this plugin is GPL-3.0.
- **The Linux kernel documentation** (firmware-attributes, powercap, asus-wmi, hwmon, power_supply).
  The source of the sysfs paths I read and write.

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? Please report it privately, see the [Security Policy](SECURITY.md). Do not
open a public issue.

## License

[GPL-3.0](LICENSE) © Hooandee. Free software for the community: anyone can use, study, and modify it,
and anyone who distributes it (with or without changes) must do so under the GPL too, with the source
available. Third-party attributions and license details (including decky-steamgriddb, whose context-menu
technique this adapts, and ryzenadj, which is invoked as an external process and not bundled) are listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
