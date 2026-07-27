#!/usr/bin/env python3

import argparse
from pathlib import Path
import re


PLUGIN_ID = "panel-de-control"
PLUGIN_NAME = "Panel de Control"
PRESET_PATTERN = re.compile(
    r"(?ms)^\[preset\.(?P<number>\d+)\]\n.*?(?=^\[preset\.\d+\]\n|\Z)"
)


def configure_export(ogui_dir: Path, template_path: Path) -> bool:
    presets_path = ogui_dir / "export_presets.cfg"
    if not presets_path.is_file():
        raise ValueError(f"OpenGamepadUI export presets not found: {presets_path}")
    if not template_path.is_file():
        raise ValueError(f"Plugin export preset template not found: {template_path}")

    contents = presets_path.read_text(encoding="utf-8")
    matches = list(PRESET_PATTERN.finditer(contents))
    matching = [
        match
        for match in matches
        if f'name="{PLUGIN_NAME}"' in match.group(0)
    ]
    if len(matching) > 1:
        raise ValueError(f"Multiple export presets named {PLUGIN_NAME}")

    if matching:
        preset_number = int(matching[0].group("number"))
    else:
        preset_number = max(
            (int(match.group("number")) for match in matches),
            default=-1,
        ) + 1

    template = template_path.read_text(encoding="utf-8")
    for placeholder in ("PRESET_NUM", "PLUGIN_ID", "PLUGIN_NAME"):
        if placeholder not in template:
            raise ValueError(f"Missing template placeholder: {placeholder}")
    rendered = (
        template.replace("PRESET_NUM", str(preset_number))
        .replace("PLUGIN_ID", PLUGIN_ID)
        .replace("PLUGIN_NAME", PLUGIN_NAME)
        .strip()
        + "\n"
    )

    if matching:
        match = matching[0]
        configured = contents[: match.start()] + rendered + contents[match.end() :]
    else:
        separator = "" if not contents or contents.endswith("\n\n") else "\n"
        configured = contents + separator + rendered

    if configured == contents:
        return False
    presets_path.write_text(configured, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Panel de Control export preset into OpenGamepadUI."
    )
    parser.add_argument("--ogui-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args()
    try:
        changed = configure_export(args.ogui_dir.resolve(), args.template.resolve())
    except ValueError as error:
        parser.error(str(error))
    print("Configured Panel de Control export preset" if changed else "Export preset unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
