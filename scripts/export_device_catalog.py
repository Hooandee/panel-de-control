#!/usr/bin/env python3
"""Export the Linux device table as the shared catalog consumed by Windows.

    python3 scripts/export_device_catalog.py          # rewrite shared/devices/catalog.json
    python3 scripts/export_device_catalog.py --check  # exit 1 when the file is stale
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py_modules"))

from device_profiles import DEVICE_TABLE, GENERIC  # noqa: E402

CATALOG_PATH = ROOT / "shared" / "devices" / "catalog.json"
SCHEMA_VERSION = 1


def _limits(profile):
    return {
        "tdp_min": profile.tdp_min,
        "tdp_default": profile.tdp_default,
        "tdp_max": profile.tdp_max,
        "tdp_max_charger": profile.tdp_max_charger,
        "tdp_presets": list(profile.tdp_presets),
        "charger_only_extra": profile.charger_only_extra,
        "cooler_max": profile.cooler_max,
        "experimental_tdp_max_ac": profile.experimental_tdp_max_ac,
    }


def _profile(profile):
    return {
        "key": profile.key,
        "display_name": profile.display_name,
        "vendor": profile.vendor,
        "chip": profile.chip,
        "experimental": profile.experimental,
        "match_names": list(profile.match_names),
        "dmi_matches": [
            {
                "product_name": match.product_name,
                "sys_vendor": match.sys_vendor,
                "board_names": list(match.board_names),
            }
            for match in profile.dmi_matches
        ],
        "limits": _limits(profile),
    }


def build_catalog():
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "py_modules/device_profiles.py",
        "generic": _profile(GENERIC),
        "profiles": [_profile(profile) for profile in DEVICE_TABLE],
    }


def render_catalog():
    return json.dumps(build_catalog(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rendered = render_catalog()
    if args.check:
        current = CATALOG_PATH.read_text(encoding="utf-8") if CATALOG_PATH.exists() else ""
        if current != rendered:
            print(f"{CATALOG_PATH.relative_to(ROOT)} is stale; run {Path(__file__).name}", file=sys.stderr)
            return 1
        return 0
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
