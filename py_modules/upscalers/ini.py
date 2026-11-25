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


_DEFAULT = re.compile(r"Default \(auto\) is ([^\s,;]+)|Default is ([^\s,;]+)", re.I)
_CHOICE_TOKEN = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _choices(help_lines: list[str]) -> list[str] | None:
    """Allowed values from OptiScaler's own comment: `a, b, c - Default (auto) is a` or `true or false`."""
    for line in reversed(help_lines):
        listed, sep, _ = line.partition(" - Default")
        if not sep:
            continue
        if listed.strip().lower() == "true or false":
            return ["auto", "true", "false"]
        listed = re.sub(r"\([^)]*\)", "", listed)
        tokens = [part.strip().split(" ")[0] for part in listed.split(",")]
        if len(tokens) > 1 and all(_CHOICE_TOKEN.match(t) for t in tokens) and not any(t[0].isdigit() for t in tokens):
            return ["auto", *[t for t in tokens if t != "auto"]]
    return None


def schema(text: str, managed: set[str] = frozenset()) -> list[dict]:
    """Every section and key with the help OptiScaler writes above it, its allowed values and default."""
    sections: list[dict] = []
    help_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        match = _SECTION.match(line)
        if match:
            sections.append({"name": match.group("name"), "keys": []})
            help_lines = []
        elif stripped.startswith(";"):
            body = stripped.lstrip(";").strip()
            if body and set(body) != {"-"}:
                help_lines.append(body[:300])
        elif "=" in stripped and sections:
            key, _, value = stripped.partition("=")
            dotted = f"{sections[-1]['name']}.{key.strip()}"
            default = next((m.group(1) or m.group(2) for line_ in help_lines if (m := _DEFAULT.search(line_))), None)
            choices = _choices(help_lines)
            if choices and value.strip() and value.strip() not in choices:
                choices.append(value.strip())
            sections[-1]["keys"].append({
                "key": key.strip(), "value": value.strip(), "help": help_lines[:12],
                "choices": choices, "default": default, "managed": dotted in managed,
            })
            help_lines = []
        elif not stripped:
            help_lines = []
    return [s for s in sections if s["keys"]]
