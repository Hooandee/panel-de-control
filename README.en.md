# Panel de Control

[Español](README.md) · **English**

<p align="center">
  <a href="https://github.com/Hooandee/panel-de-control/releases/latest"><img src="https://img.shields.io/github/v/release/Hooandee/panel-de-control?label=latest%20release&color=blue" alt="Latest release"></a>
  <a href="https://github.com/Hooandee/panel-de-control/releases"><img src="https://img.shields.io/github/downloads/Hooandee/panel-de-control/total?label=downloads&color=brightgreen" alt="Downloads"></a>
</p>

<p align="center">
  <a href="https://ko-fi.com/hooandee"><img src="https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi"></a>
  <a href="https://www.patreon.com/hooandee"><img src="https://img.shields.io/badge/Patreon-Support%20me-FF424D?style=for-the-badge&logo=patreon&logoColor=white" alt="Patreon"></a>
  <a href="https://www.youtube.com/channel/UCDsSJByXklp6xc_WwQJI7Lw/join"><img src="https://img.shields.io/badge/YouTube-Become%20a%20member-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://discord.gg/x2ZNARy"><img src="https://img.shields.io/badge/Discord-Join-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://linktr.ee/hooandee"><img src="https://img.shields.io/badge/All%20my%20links-Linktree-43E660?style=for-the-badge&logo=linktree&logoColor=white" alt="Linktree"></a>
</p>

<h3 align="center">The control center your handheld PC was missing.</h3>

Panel de Control lives in Steam's quick access menu and runs everything from there: power, fans,
battery, display, sound, HUD, launch options and themes that completely change how Steam looks. All
without leaving your game or opening a terminal.

I'm Hooandee, I make it, and I test every feature on my own machines. Panel doesn't make up data.
If your device doesn't let it read or change something, it just doesn't show up, and the numbers you
see are the real ones.

It runs on [Decky Loader](https://decky.xyz/) and is available in English, Spanish, Italian,
German and Brazilian Portuguese.

## 🎬 Video guides

The videos are in Spanish, but YouTube's auto-translated subtitles work well.

| [![Panel de Control in depth](https://img.youtube.com/vi/sDpXFTxG7NQ/hqdefault.jpg)](https://youtu.be/sDpXFTxG7NQ) | [![How to install themes](https://img.youtube.com/vi/aENDY4BFcRE/hqdefault.jpg)](https://youtu.be/aENDY4BFcRE) | [![Panel on ARM with Armada](https://img.youtube.com/vi/1BHufGK6nbo/hqdefault.jpg)](https://youtu.be/1BHufGK6nbo) |
|:---:|:---:|:---:|
| **The plugin in depth** | **How to install themes** | **Panel on ARM with Armada** |

## What it does

⚡ **Power.** TDP across your device's real range, presets your way and a separate profile for
each game. Auto-TDP raises or lowers the watts depending on what the game needs, so you get the
FPS you want without wasting battery.

🌀 **Fans.** Live temperatures and RPM, and curves you draw with your finger. Over time it learns
how hot each game runs and suggests a curve made for it.

🎨 **Display.** One-tap color modes (Native, Cinema, Vivid, Comfort) or fine tuning if you like to
tinker, an OLED look for LCD screens, scheduled night mode and HDR where the panel supports it.

🎧 **Sound.** A real system-wide equalizer with presets, ten bands, separate curves for speakers
and headphones, bass boost and volume leveling.

🔋 **System.** Battery health and charge limit, CPU, GPU clock, exact brightness and volume, and a
Download Mode that keeps your device grabbing games while using as little power as possible, with
the screen off until you touch it.

📊 **HUD.** Build your own MangoHud overlay and see how it looks right away. You choose which
metrics show up, where and in what colors.

🚀 **Launch options.** Each game's launch options turned into toggles with a plain explanation.
FSR4, HDR, scaling and more, but only what your Proton version supports.

🧹 **Cleanup.** See how much space your games' Shader Cache and prefixes take up and get it back in
a moment.

✨ **Themes.** Change how Steam looks from top to bottom with themes you install and update right
from Panel.

🎮 **Controllers.** Button remapping that works with Handheld Daemon and InputPlumber. Still
in beta.

🧩 **Your way.** Reorder and hide tabs, build your own views and pick an accent color. Everything
works with the controller, and updates show up on their own in the quick access menu.

## 📱 ARM too

Panel isn't just for PCs. With Armada it also runs on ARM consoles, recognizes the model and chip,
and only shows what that hardware lets it control. The [video](https://youtu.be/1BHufGK6nbo) goes
through the setup step by step.

And if you have an AYN Thor, Panel can use the bottom screen as a touch panel while you play on the
top one.

## 🕹️ Devices

I test everything on the machines I have at home: **Steam Deck LCD and OLED, ROG Ally, ROG Ally X,
ROG Xbox Ally X, Legion Go, Legion Go S, Legion Go 2 and MSI Claw 8 AI+**, and on ARM, **AYN Thor,
AYN Odin 3, AYN Odin 2 Portal, Retroid Pocket 5, Retroid Pocket Nova and Anbernic RG Cube**.

Many more have received support too: OneXFly Apex, GPD Win 5, GPD Win Mini, AOKZOE A1X, MSI Claw A8,
OneXPlayer X2 Mini Pro and quite a few others, even desktop PCs and the Steam Machine. If your
device isn't on the list, Panel looks at what it can control on it and shows you that.

## 📦 Installation

With [Decky Loader](https://decky.xyz/) installed:

1. Download `Panel de Control.zip` from the [latest release](https://github.com/Hooandee/panel-de-control/releases/latest).
2. In Decky, go to **Developer Mode → Install Plugin from ZIP** and pick the file.

That's it. From then on it updates itself, and when a new version is out you'll see a notice in the
quick access menu.

## 💬 Bugs and ideas

If something isn't working or you're missing something, the quickest way to tell me is from Panel
itself, in **Settings → Send a report**. You can send a problem or an idea, and Panel attaches only
the technical info about your device that I need to understand it, nothing personal. You can also
open an [issue](https://github.com/Hooandee/panel-de-control/issues) here on GitHub.

If you have a device I don't, your reports are what help me polish it the most.

## 🔒 Privacy

Panel learns from how you play to fine-tune its suggestions, but all of it stays on your device. You
can turn it off or wipe it anytime from Settings.

> [!WARNING]
> Panel runs with root permissions and changes power, thermal and firmware settings. It's built to
> fail safely, but you use it at your own risk and without warranty.

## ❤️ Thanks

Panel de Control was born after using [SimpleDeckyTDP](https://github.com/aarron-lee/SimpleDeckyTDP)
by Aarron Lee. It's what got me to build something bigger, and Panel has followed its own path ever
since.

Thanks as well to the handheld community for everything it shares, especially
[Handheld Daemon](https://github.com/hhd-dev/hhd), [PowerControl](https://github.com/mengmeet/PowerControl),
[Fantastic](https://git.ngram.ca/NG-SD-Plugins/Fantastic), [PowerTools](https://git.ngni.us/NG-SD-Plugins/PowerTools),
[RyzenAdj](https://github.com/FlyGoat/RyzenAdj), [decky-steamgriddb](https://github.com/SteamGridDB/decky-steamgriddb)
and [Decky Loader](https://decky.xyz/), which is where all of this runs. License details are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

[GPL-3.0](LICENSE) © Hooandee. If you find a security issue, let me know privately through the
[security policy](SECURITY.md).
