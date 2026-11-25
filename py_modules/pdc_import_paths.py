"""Make the plugin's own py_modules win over same-named system packages.

Decky appends py_modules to sys.path, so a distro package with a generic name
(Fedora's libreport ships a top-level ``report``) is found first and the plugin
imports the wrong module.
"""
import os
import sys


def own_top_level_names(local_modules: str) -> set[str]:
    names = set()
    for entry in os.listdir(local_modules):
        path = os.path.join(local_modules, entry)
        if entry.endswith(".py"):
            names.add(entry[:-3])
        elif os.path.isfile(os.path.join(path, "__init__.py")):
            names.add(entry)
    return names


def _is_inside(path: str | None, root: str) -> bool:
    if not path:
        return False
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def prefer_plugin_modules(local_modules: str, paths: list, modules: dict) -> list[str]:
    """Put local_modules first on paths and drop foreign modules that shadow ours.

    Returns the names evicted from ``modules``.
    """
    if not os.path.isdir(local_modules):
        return []
    real = os.path.realpath(local_modules)
    paths[:] = [p for p in paths if not (isinstance(p, str) and p and os.path.realpath(p) == real)]
    paths.insert(0, local_modules)

    own = own_top_level_names(local_modules)
    evicted = []
    for name in list(modules):
        top = name.split(".")[0]
        if top not in own:
            continue
        module = modules.get(name)
        location = getattr(module, "__file__", None)
        if _is_inside(location, local_modules):
            continue
        del modules[name]
        evicted.append(name)
    return evicted


prefer_plugin_modules(os.path.dirname(os.path.abspath(__file__)), sys.path, sys.modules)
