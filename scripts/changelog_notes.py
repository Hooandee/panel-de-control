#!/usr/bin/env python3
"""Derive release notes from the newest CHANGELOG.md section.

Modes:
  --check         exit non-zero unless every entry in the newest release section has
                  both an English bullet and a matching Spanish (**ES:**) bullet.
  --release-body  print a clean bilingual release body (Spanish first, then English,
                  with the PR/commit links stripped) for the in-app updater to render.

The changelog uses release-please's format: a section per version, each entry a
`* <English> ([#N](...)) ([sha](...))` bullet followed by a `* **ES:** <Spanish> ...`
bullet. Only the top (newest) section is considered.
"""
import pathlib
import re
import sys

_LINK = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\).*$")


def _top_section(text):
    lines = text.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("## [")]
    if not heads:
        return []
    end = heads[1] if len(heads) > 1 else len(lines)
    return lines[heads[0]:end]


def _bullets(section):
    """(is_es, text) for each `* ` bullet, with trailing PR/commit links stripped."""
    out = []
    for line in section:
        if not line.startswith("* "):
            continue
        body = line[2:].strip()
        is_es = body.startswith("**ES:**")
        if is_es:
            body = body[len("**ES:**"):].strip()
        out.append((is_es, _LINK.sub("", body).strip()))
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    section = _top_section(pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8"))
    bullets = _bullets(section)
    english = [b for is_es, b in bullets if not is_es]
    spanish = [b for is_es, b in bullets if is_es]

    if mode == "--check":
        if english and len(spanish) != len(english):
            print("::error::CHANGELOG.md top section is not bilingual: "
                  f"{len(english)} English bullet(s) vs {len(spanish)} Spanish "
                  "(**ES:**) one(s). Add a '* **ES:** ...' line for each entry.")
            return 1
        print("CHANGELOG top section is bilingual.")
        return 0

    if mode == "--release-body":
        parts = []
        if spanish:
            parts += ["### Novedades", ""] + [f"- {b}" for b in spanish] + [""]
        if english:
            parts += ["### What's new", ""] + [f"- {b}" for b in english]
        sys.stdout.write("\n".join(parts).strip() + "\n")
        return 0

    print("usage: changelog_notes.py --check | --release-body", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
