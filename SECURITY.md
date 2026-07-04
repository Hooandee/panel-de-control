# Security Policy

Panel de Control is a Decky Loader plugin that runs with **root privileges** on the
device (it reads and writes kernel `sysfs` interfaces to control TDP, fans, the
display, the battery and controllers). Because of that, security is taken seriously.
Thank you for helping keep users safe.

## Supported versions

Only the **latest released version** receives security fixes. Please update before
reporting — the issue may already be fixed.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately through GitHub's built-in advisory flow:

- Go to the repository's **Security** tab → **Report a vulnerability**, or
- Open <https://github.com/Hooandee/panel-de-control/security/advisories/new>

Please include:

- A description of the vulnerability and its impact.
- Steps to reproduce (proof-of-concept if possible).
- The affected version, device, and OS.

### What to expect

- Acknowledgement within 7 days.
- An initial assessment and, where applicable, a target fix timeline.
- Credit in the release notes when a fix ships, unless you prefer to remain anonymous.
- Please allow a reasonable window to release a fix before any public disclosure
  (coordinated disclosure).

## Verifying release integrity

Every release artifact (`Panel de Control.zip`) is built by the pinned
`release-please` workflow and signed with **build provenance** (Sigstore, via GitHub
Artifact Attestations). Before trusting a downloaded release you can verify it came
from this repository's pipeline and was not tampered with:

```sh
gh attestation verify "Panel de Control.zip" --repo Hooandee/panel-de-control
```

A zip published outside the official pipeline will not have valid provenance.

## Security model & notes

- **Runs as root.** The plugin's Python backend runs as `root` under Decky. It only
  touches documented kernel interfaces and never grabs input devices directly.
- **Self-update.** The plugin can update itself by downloading the latest GitHub
  release over TLS (certificate-verified) from this repository only, then installing
  it in place. User settings are stored separately and are not overwritten.
- **No telemetry leaves the device.** Usage learning ("Aprender de mi uso") is stored
  locally, is opt-out, and is never transmitted.
- **External processes** (`systemctl`, `busctl`, `python3`, …) are invoked with
  absolute paths, argument lists (never a shell), and a scrubbed environment.
