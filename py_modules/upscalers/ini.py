"""In-place OptiScaler.ini edits that keep comments, order and line endings."""

import re

_SECTION = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")


def apply(text: str, overrides: dict[str, str]) -> str:
    """Set `Section.Key=value` pairs, appending keys or sections that are missing."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    for dotted, value in overrides.items():
        section, key = dotted.split(".", 1)
        key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        inside = False
        insert_at = None
        for index, line in enumerate(lines):
            match = _SECTION.match(line)
            if match:
                if inside:
                    insert_at = index
                    break
                inside = match.group("name") == section
                continue
            if inside and key_pattern.match(line):
                ending = line[len(line.rstrip("\r\n")):] or newline
                lines[index] = f"{key}={value}{ending}"
                break
        else:
            if inside:
                insert_at = len(lines)
            elif insert_at is None:
                if lines and not lines[-1].endswith(("\n", "\r")):
                    lines[-1] += newline
                lines.append(f"[{section}]{newline}")
                insert_at = len(lines)
            if lines and insert_at > 0 and not lines[insert_at - 1].endswith(("\n", "\r")):
                lines[insert_at - 1] += newline
            lines.insert(insert_at, f"{key}={value}{newline}")
            continue
        if insert_at is not None:
            lines.insert(insert_at, f"{key}={value}{newline}")
    return "".join(lines)


def read(text: str, dotted: str) -> str | None:
    section, key = dotted.split(".", 1)
    inside = False
    for line in text.splitlines():
        match = _SECTION.match(line)
        if match:
            inside = match.group("name") == section
            continue
        if inside:
            name, sep, value = line.partition("=")
            if sep and name.strip() == key:
                return value.strip()
    return None
