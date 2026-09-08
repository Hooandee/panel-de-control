# Contributing to Panel de Control

Thanks for your interest in improving Panel de Control! This document explains how to
set up the project, the quality bar for changes, and how releases work.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- For **bugs** and **feature ideas**, open an issue first so we can discuss scope.
- For **security vulnerabilities**, do **not** open a public issue — follow the
  [Security Policy](SECURITY.md).
- Small fixes (typos, obvious bugs) are welcome as direct PRs.

## Project layout

- `src/` — TypeScript + React frontend (Decky standard).
- `py_modules/` + `main.py` — Python backend, exposed to the frontend via Decky RPC.
- `tests/` — Python tests (pytest). Frontend logic tests live next to the code
  (`*.test.ts`, run with vitest).

## Development setup

Toolchain: **pnpm 10**, **Node 20**, **Python 3.11**. Versions are pinned in the
repo: Node via `.node-version` (fnm/nvm), Python via `.python-version`
(pyenv/uv), and pnpm via the `packageManager` field in `package.json` (Corepack
picks it up automatically — `corepack enable` if your shell doesn't).

```sh
# Frontend deps
pnpm install --frozen-lockfile

# Backend dev deps (into a virtualenv is recommended)
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

## The quality gate

Every change must pass the full gate before it can be merged. Run it locally:

```sh
# Frontend
pnpm typecheck
pnpm test:i18n       # translation keys, placeholders and reviewed terminology
pnpm test:fe
pnpm build            # must produce dist/index.js

# Backend
ruff check py_modules main.py tests
python -m pytest
```

CI runs the same checks on every push and pull request.

### Localization quality

Spanish, English, Italian, and German are product copy, not literal translation
targets. New or changed strings must read naturally to a native speaker, use the
established gaming and hardware terminology, and preserve the intent and tone of
the original. Avoid machine-translation phrasing and editorial tics such as em
dashes. `pnpm test:i18n` checks keys, placeholders, banned punctuation, and
reviewed terminology; a human content review is still required for meaning and
naturalness.

### Principles

- **Never fake success.** If a hardware write, daemon call, or sysfs read fails, the
  UI must reflect that honestly — do not show a value the hardware never accepted.
- **Degrade gracefully.** Code that talks to hardware or system daemons should never
  raise into the UI; return a safe/empty result instead.
- **Test the logic.** Pure logic (curve math, parsing, decision loops) is unit-tested;
  hardware access is behind small, injectable seams so it can be tested with fakes.

## Building a local plugin zip for testing

To test a build on a device without waiting for a release, produce the same zip the
release pipeline ships. Decky's "Install from zip" expects the archive to contain a
**single top-level folder named after the plugin** (`Panel de Control/…`), so stage
the payload into that folder before zipping:

```sh
pnpm build                       # must produce dist/index.js
node scripts/copy-plugin-payload.mjs . "$HOME/Downloads/Panel de Control"
cd "$HOME/Downloads"; zip -r "Panel de Control.zip" "Panel de Control"; cd -
```

Then install it on the device via **Decky → Settings → Install from zip**. The zip
lands in `~/homebrew/plugins/Panel de Control`; restart the loader if the plugin does
not appear.  

> **Gotcha:** zipping the payload files at the archive root (without the
> `Panel de Control/` wrapper) makes Decky's zip installer fail — the top-level
> folder is required.
>
> **pnpm ≥ 10 note:** if `pnpm install` refuses to run esbuild's postinstall
> ("Ignored build scripts"), allow it with `pnpm approve-builds` (or a local
> `pnpm-workspace.yaml` with `allowBuilds.esbuild: true`) before building.

## Commit messages & releases

This project uses [Conventional Commits](https://www.conventionalcommits.org/) with
[release-please](https://github.com/googleapis/release-please). The commit prefix
drives versioning:

- `feat:` → minor release
- `fix:` → patch release
- `feat!:` or a `BREAKING CHANGE:` footer → major release
- `chore:`, `docs:`, `ci:`, `refactor:`, `test:`, `style:` → **no release**

Merging to `main` automatically maintains a release PR; merging that PR tags the
version, builds the plugin zip, signs it with build provenance, and attaches it to the
GitHub release.

## Pull request checklist

- The full gate above passes.
- Commit messages follow Conventional Commits.
- No secrets or personal data are included.
- New third-party dependencies are recorded in
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) with their license.
- If you can, note which device(s) you tested on.

## License

By contributing, you agree that your contributions are licensed under the
[GNU General Public License v3.0](LICENSE) (`GPL-3.0-only`).
