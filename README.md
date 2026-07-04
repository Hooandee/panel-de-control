# Panel de Control

The ultimate control center for handheld gaming PCs — configure TDP, fan curves, the
display, the battery and controllers from a beautiful, easy-to-use
[Decky Loader](https://decky.xyz/) panel. Spanish-first, with English support.

> [!WARNING]
> This plugin runs with **root privileges** and changes low-level power, thermal, and
> firmware settings on your device. It talks only to documented kernel interfaces and
> is designed to fail safe, but you use it **at your own risk**. There is no warranty
> (see the [LICENSE](LICENSE)).

## Features

- **Potencia** — per-device TDP control with a live power gauge, per-game profiles,
  advanced PL1/SPPT/FPPT boost, and an optional GPU-driven auto-TDP.
- **Ventiladores** — live fan/temperature monitor plus a temp→fan curve editor with
  presets and learned suggestions (per device; honestly hidden where the firmware
  doesn't allow it).
- **Sistema** — brightness, volume, battery (health, cycles, charge limit), CPU
  (SMT / turbo), a low-power "download" mode, and RGB via the companion Colores plugin.
- **Pantalla** — panel color calibration (saturation / temperature / contrast).
- **Mandos** — cooperative controller remapping that works alongside the device's
  resident controller daemon.

## Supported devices

Steam Deck (LCD / OLED), ROG Ally · Ally X · Xbox Ally X, Legion Go · Go S · Go 2,
and the MSI Claw 8 AI+. Unrecognized hardware falls back to a generic profile, and
each control is hidden when the device doesn't support it.

## Installation

Panel de Control is distributed outside the Decky store. Install [Decky Loader](https://decky.xyz/)
first, then:

1. Download `Panel de Control.zip` from the [latest release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. In Decky, use **Developer Mode → Install Plugin from ZIP** (or your preferred manual
   install method).

Once installed, the plugin can update itself from within its settings.

### Verifying a download (recommended)

Every release zip is signed with build provenance. Confirm it really came from this
repository's pipeline before installing:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

## Building from source

Toolchain: **pnpm 10**, **Node 20**, **Python 3.11**.

```sh
pnpm install --frozen-lockfile
pnpm build          # produces dist/index.js
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full test gate and development setup.

## Contributing

Contributions are welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? Please report it privately — see the
[Security Policy](SECURITY.md). Do not open a public issue.

## License

[BSD-3-Clause](LICENSE) © Hooandee. Third-party attributions are listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
