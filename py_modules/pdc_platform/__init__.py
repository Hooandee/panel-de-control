import os
import sys

from osinfo import read_os_id


_FIRST_CLASS = frozenset({"anatase", "bazzite", "cachyos", "steamos"})


def plugin_root_from_platform_file(path: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path))))


def activate_import_paths(
    os_id: str | None,
    plugin_root: str,
    paths: list[str],
) -> None:
    if os_id != "anatase":
        return
    local_modules = os.path.join(plugin_root, "py_modules")
    if not os.path.isdir(local_modules):
        return
    paths[:] = [path for path in paths if path != local_modules]
    paths.insert(0, local_modules)


activate_import_paths(
    read_os_id(),
    plugin_root_from_platform_file(__file__),
    sys.path,
)

from . import anatase_hhd  # noqa: E402


def describe(os_id: str | None) -> dict:
    return {
        "id": os_id,
        "support_tier": "first-class" if os_id in _FIRST_CLASS else "capability",
    }


def select_hhd_tdp_client(os_id: str | None, default_client):
    return anatase_hhd if os_id == "anatase" else default_client
