<!-- Thanks for contributing! Please fill out the checklist below. -->

## What does this change?

<!-- A short description of the change and why. Link any related issue: Closes #123 -->

## How was it tested?

<!-- Which device(s) did you test on, if any? What did you verify? -->

## Checklist

- [ ] The commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`, …). Only `feat:`/`fix:` trigger a release.
- [ ] `pnpm typecheck`, `pnpm test:fe`, and `pnpm build` pass.
- [ ] `ruff check py_modules main.py tests` and `python -m pytest` pass.
- [ ] No secrets, tokens, or personal data are included.
- [ ] I did not add new third-party dependencies without noting them (and their license) in `THIRD_PARTY_NOTICES.md`.
