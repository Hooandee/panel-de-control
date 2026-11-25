import ast
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pdc_import_paths
from pdc_import_paths import own_top_level_names, prefer_plugin_modules

ROOT = Path(__file__).resolve().parent.parent
PY_MODULES = str(ROOT / "py_modules")

# Top-level names that distro Python packages are known to install in site-packages.
KNOWN_SYSTEM_PACKAGES = {"report"}  # Fedora python3-libreport


def _make_local(tmp_path):
    local = tmp_path / "plugin" / "py_modules"
    (local / "report").mkdir(parents=True)
    (local / "report" / "__init__.py").write_text("")
    (local / "journal.py").write_text("")
    return str(local)


def test_plugin_modules_move_to_the_front_once(tmp_path):
    local = _make_local(tmp_path)
    paths = ["/usr/lib64/python3.14/site-packages", local, "/other", local]

    prefer_plugin_modules(local, paths, {})

    assert paths == [local, "/usr/lib64/python3.14/site-packages", "/other"]


def test_foreign_modules_with_our_names_are_dropped(tmp_path):
    local = _make_local(tmp_path)
    foreign = types.ModuleType("report")
    foreign.__file__ = "/usr/lib64/python3.14/site-packages/report/__init__.py"
    foreign_sub = types.ModuleType("report.accountmanager")
    foreign_sub.__file__ = "/usr/lib64/python3.14/site-packages/report/accountmanager.py"
    ours = types.ModuleType("journal")
    ours.__file__ = os.path.join(local, "journal.py")
    unrelated = types.ModuleType("json")
    unrelated.__file__ = "/usr/lib64/python3.14/json/__init__.py"
    modules = {
        "report": foreign,
        "report.accountmanager": foreign_sub,
        "journal": ours,
        "json": unrelated,
    }

    evicted = prefer_plugin_modules(local, [], modules)

    assert sorted(evicted) == ["report", "report.accountmanager"]
    assert modules == {"journal": ours, "json": unrelated}


def test_missing_plugin_dir_changes_nothing(tmp_path):
    paths = ["/usr/lib/python3/site-packages"]
    modules = {"report": types.ModuleType("report")}

    assert prefer_plugin_modules(str(tmp_path / "nope"), paths, modules) == []
    assert paths == ["/usr/lib/python3/site-packages"]
    assert "report" in modules


def test_every_plugin_package_wins_over_a_same_named_system_package(tmp_path):
    """Decky appends py_modules after site-packages; any same-named system package must lose."""
    site = tmp_path / "site-packages"
    site.mkdir()
    names = sorted(own_top_level_names(PY_MODULES))
    for name in names:
        (site / name).mkdir()
        (site / name / "__init__.py").write_text("SYSTEM = True\n")
    script = textwrap.dedent(
        f"""
        import importlib.util, os, sys
        sys.path[:] = [{str(site)!r}] + [p for p in sys.path if p] + [{PY_MODULES!r}]
        import journal, tdp  # system copies already imported before the plugin starts
        sys.path.insert(0, {PY_MODULES!r})
        import pdc_import_paths
        sys.path.remove({PY_MODULES!r})
        pdc_import_paths.prefer_plugin_modules({PY_MODULES!r}, sys.path, sys.modules)
        bad = []
        for name in {names!r}:
            origin = importlib.util.find_spec(name).origin or ""
            if not os.path.realpath(origin).startswith(os.path.realpath({PY_MODULES!r}) + os.sep):
                bad.append((name, origin))
        print(bad)
        """
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_plugin_names_never_shadow_the_stdlib_or_decky():
    clashes = own_top_level_names(PY_MODULES) & (set(sys.stdlib_module_names) | {"decky"})

    assert clashes == set()


def test_plugin_names_avoid_known_distro_packages():
    assert own_top_level_names(PY_MODULES) & KNOWN_SYSTEM_PACKAGES == set()


def _ancestors(tree, target):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    node = target
    while node in parents:
        node = parents[node]
        yield node


def test_main_fixes_import_order_before_any_plugin_import():
    tree = ast.parse((ROOT / "main.py").read_text())
    own = own_top_level_names(PY_MODULES)
    first_own = None
    module_level = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and not any(isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for parent in _ancestors(tree, node))
    ]
    for node in sorted(module_level, key=lambda n: (n.lineno, n.col_offset)):
        if isinstance(node, ast.Import):
            tops = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            tops = [(node.module or "").split(".")[0]]
        else:
            continue
        mine = [top for top in tops if top in own]
        if mine:
            first_own = mine[0]
            break

    assert first_own == "pdc_import_paths"


def test_module_is_importable_without_other_plugin_modules():
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(Path(pdc_import_paths.__file__).read_text()))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(ast.parse(Path(pdc_import_paths.__file__).read_text()))
        if isinstance(node, ast.ImportFrom)
    }

    assert imports <= set(sys.stdlib_module_names)
