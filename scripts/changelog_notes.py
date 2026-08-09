#!/usr/bin/env python3
"""Derive multilingual release notes from the newest CHANGELOG.md section.

Modes:
  --check         validate Spanish, English and optional Italian entries in the newest
                  release section.
  --release-body  print clean release notes in Spanish, English and Italian, with the
                  PR/commit links stripped, for the in-app updater to render.

The preferred format groups entries below `### Español`, `### English` and
`### Italiano` headings. Explicit `**ES:**`, `**EN:**` and `**IT:**` labels remain
supported, as do Release Please's unlabelled English entries. Only the top (newest)
section is considered.
"""
import pathlib
import re
import sys

_LINK = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\).*$")
_LANGUAGE_LABEL = re.compile(r"^\*\*(?P<language>[A-Z]{2}):\*\*\s*(?P<text>.*)$")
_LANGUAGES = ("ES", "EN", "IT")
_LANGUAGE_BLOCKS = {
    "### Español": "ES",
    "### English": "EN",
    "### Italiano": "IT",
}
_HEADINGS = {
    "ES": "### Novedades",
    "EN": "### What's new",
    "IT": "### Novità",
}


def _top_section(text):
    lines = text.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("## [")]
    if not heads:
        return []
    end = heads[1] if len(heads) > 1 else len(lines)
    return lines[heads[0]:end]


def _bullets(section):
    entries = {language: [] for language in _LANGUAGES}
    unsupported = []
    current_language = "EN"
    for line in section:
        if line.startswith("### "):
            current_language = _LANGUAGE_BLOCKS.get(line.strip(), "EN")
            continue
        if not line.startswith("* "):
            continue
        body = line[2:].strip()
        label = _LANGUAGE_LABEL.match(body)
        if label:
            language = label.group("language")
            if language not in entries:
                unsupported.append(language)
                continue
            body = label.group("text")
        else:
            language = current_language
        entries[language].append(_LINK.sub("", body).strip())
    return entries, unsupported


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    section = _top_section(pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8"))
    entries, unsupported = _bullets(section)
    spanish = entries["ES"]
    english = entries["EN"]
    italian = entries["IT"]

    if mode == "--check":
        if unsupported:
            labels = ", ".join(sorted(set(unsupported)))
            print(f"::error::CHANGELOG.md contains unsupported language label: {labels}")
            return 1
        if english and len(spanish) != len(english):
            print("::error::CHANGELOG.md top section is not bilingual: "
                  f"{len(english)} English bullet(s) vs {len(spanish)} Spanish "
                  "entry or entries below '### Español'.")
            return 1
        if (spanish or italian) and not english:
            print("::error::CHANGELOG.md top section has translations but no English "
                  "(**EN:** or unlabelled) entries.")
            return 1
        if italian and len(italian) != len(english):
            print("::error::CHANGELOG.md top section is not trilingual: "
                  f"{len(english)} English bullet(s) vs {len(italian)} Italian (**IT:**) "
                  "entries. Complete the '### Italiano' block.")
            return 1
        kind = "trilingual" if italian else "bilingual"
        print(f"CHANGELOG top section is {kind}.")
        return 0

    if mode == "--release-body":
        parts = []
        for language in _LANGUAGES:
            if entries[language]:
                parts += [_HEADINGS[language], ""]
                parts += [f"- {text}" for text in entries[language]] + [""]
        sys.stdout.write("\n".join(parts).strip() + "\n")
        return 0

    print("usage: changelog_notes.py --check | --release-body", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
