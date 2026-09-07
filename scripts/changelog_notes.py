#!/usr/bin/env python3
"""Validate and render release notes for every supported interface language."""
import pathlib
import re
import sys

_LINK = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\).*$")
_LANGUAGE_LABEL = re.compile(r"^\*\*(?P<language>[A-Z]{2}):\*\*\s*(?P<text>.*)$")
_VERSION_HEADING = re.compile(r"^##\s+(?!Unreleased\s*$).+")
_LANGUAGE_BLOCKS = {
    "### Español": "ES",
    "### English": "EN",
    "### Italiano": "IT",
    "### Deutsch": "DE",
}
_HEADINGS = {
    "ES": "### Novedades",
    "EN": "### What's new",
    "IT": "### Novità",
    "DE": "### Neuigkeiten",
}
_TRANSLATIONS = {
    "ES": ("Spanish", "### Español"),
    "IT": ("Italian", "### Italiano"),
    "DE": ("German", "### Deutsch"),
}
_LANGUAGES = tuple(_HEADINGS)


def _top_section(text):
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if _VERSION_HEADING.match(line)]
    if not headings:
        return []
    end = headings[1] if len(headings) > 1 else len(lines)
    return lines[headings[0]:end]


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


def _validate(entries, unsupported):
    if unsupported:
        labels = ", ".join(sorted(set(unsupported)))
        return f"CHANGELOG.md contains unsupported language label: {labels}"

    english_count = len(entries["EN"])
    if any(entries.values()) and not english_count:
        return "CHANGELOG.md top section has translations but no English (**EN:** or unlabelled) entries."

    for language, (name, heading) in _TRANSLATIONS.items():
        if english_count and len(entries[language]) != english_count:
            return (
                f"CHANGELOG.md top section has incomplete {name} (**{language}:**) translations: "
                f"{english_count} English bullet(s) vs {len(entries[language])} {name} entries. "
                f"Complete the '{heading}' block."
            )
    return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    section = _top_section(pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8"))
    entries, unsupported = _bullets(section)
    if mode == "--check":
        error = _validate(entries, unsupported)
        if error:
            print(f"::error::{error}")
            return 1
        print("CHANGELOG top section is quadrilingual.")
        return 0

    if mode == "--release-body":
        error = _validate(entries, unsupported)
        if error:
            print(f"::error::{error}", file=sys.stderr)
            return 1
        parts = []
        for language in _LANGUAGES:
            if entries[language]:
                parts.extend((_HEADINGS[language], ""))
                parts.extend([f"- {text}" for text in entries[language]])
                parts.append("")
        sys.stdout.write("\n".join(parts).strip() + "\n")
        return 0

    print("usage: changelog_notes.py --check | --release-body", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
