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

Toolchain: **pnpm 10**, **Node 20**, **Python 3.11**.

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
pnpm test:fe
pnpm build            # must produce dist/index.js

# Backend
ruff check py_modules main.py tests
python -m pytest
```

CI runs the same checks on every push and pull request.

### Principles

- **Never fake success.** If a hardware write, daemon call, or sysfs read fails, the
  UI must reflect that honestly — do not show a value the hardware never accepted.
- **Degrade gracefully.** Code that talks to hardware or system daemons should never
  raise into the UI; return a safe/empty result instead.
- **Test the logic.** Pure logic (curve math, parsing, decision loops) is unit-tested;
  hardware access is behind small, injectable seams so it can be tested with fakes.

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
[BSD-3-Clause License](LICENSE).
