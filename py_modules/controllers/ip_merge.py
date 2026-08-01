"""Merge remap overrides into InputPlumber's profile YAML.

Decky's frozen (PyInstaller) backend may not bundle PyYAML, so the YAML load/dump
runs in the SYSTEM python via subprocess; the actual merge is the pure, unit-tested
`ip_profile.apply_overrides_to_profile`. Env is scrubbed (see detect.clean_env) so
the system python isn't poisoned by the bundle's LD_LIBRARY_PATH.
"""
import json
import os
import subprocess

from controllers.detect import clean_env, resolve_bin

# .../py_modules — so the system python can import `controllers.ip_profile`.
_PYMODS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SCRIPT = (
    "import sys,json,yaml;"
    "sys.path.insert(0, sys.argv[1]);"
    "from controllers.ip_profile import apply_overrides_to_profile;"
    "prof=yaml.safe_load(sys.stdin.read()) or {};"
    "ov=json.loads(sys.argv[2]);"
    "sys.stdout.write(yaml.safe_dump(apply_overrides_to_profile(prof, ov),"
    " sort_keys=False, default_flow_style=False))"
)

_COMPARE_SCRIPT = (
    "import sys,json,yaml;"
    "docs=json.load(sys.stdin);"
    "print('true' if yaml.safe_load(docs[0]) == yaml.safe_load(docs[1]) "
    "else 'false')"
)


def merge_profile(baseline_yaml: str, overrides: dict):
    """Return the baseline profile YAML with overrides applied, or None on failure."""
    try:
        r = subprocess.run(
            [resolve_bin("python3"), "-c", _SCRIPT, _PYMODS, json.dumps(overrides)],
            input=baseline_yaml, capture_output=True, text=True, timeout=8,
            env=clean_env(),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    except Exception:
        pass
    return None


def profiles_equal(left: str, right: str) -> bool:
    """Compare profile contents without relying on YAML formatting stability."""
    if left == right:
        return True
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        result = subprocess.run(
            [resolve_bin("python3"), "-c", _COMPARE_SCRIPT],
            input=json.dumps([left, right]), capture_output=True, text=True,
            timeout=8, env=clean_env(),
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except Exception:
        return False
