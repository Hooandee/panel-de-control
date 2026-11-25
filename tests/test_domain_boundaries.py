"""Domains import only themselves and shared infrastructure (decision: domain modules)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_DOMAINS = ("ambient",)
PY_SHARED = {"pdc_platform", "json_store", "http_util", "version", "decky"}
TS_DOMAINS = ("ambient",)
TS_SHARED_PREFIXES = ("@decky/", "react", "react-icons", "../../platform/", "../../theme", "../../i18n", "../../components/", "../platform/", "../theme", "../i18n", "../components/")
TS_IMPORT = re.compile(r"""(?:import|export)[^'"]*?from\s+['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)""")


def _py_imports(path: Path):
    tree = ast.parse(path.read_text(), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.level


def _is_stdlib(name: str) -> bool:
    import sys
    return name.split(".")[0] in sys.stdlib_module_names or name == "__future__"


def test_python_domains_import_only_themselves_and_shared():
    offenders = []
    for domain in PY_DOMAINS:
        for path in (ROOT / "py_modules" / domain).rglob("*.py"):
            for module, level in _py_imports(path):
                top = module.split(".")[0]
                if level > 0 or top == domain or _is_stdlib(module) or top in PY_SHARED:
                    continue
                offenders.append(f"{path.relative_to(ROOT)} -> {module}")
    assert offenders == []


def test_python_core_is_pure():
    offenders = []
    for domain in PY_DOMAINS:
        for path in (ROOT / "py_modules" / domain / "core").rglob("*.py"):
            for module, level in _py_imports(path):
                if "adapters" in module or module.split(".")[0] in PY_SHARED or module in ("service", "rpc"):
                    offenders.append(f"{path.relative_to(ROOT)} -> {module}")
    assert offenders == []


def _own_contract(target: Path, domain: str) -> bool:
    return str(target).startswith(str((ROOT / "shared" / "contracts" / domain).resolve()))


def _ts_files(domain: str):
    base = ROOT / "src" / domain
    if not base.exists():
        return []
    return [p for p in base.rglob("*") if p.suffix in (".ts", ".tsx") and ".test." not in p.name]


def test_typescript_domains_import_only_themselves_and_shared():
    offenders = []
    for domain in TS_DOMAINS:
        base = (ROOT / "src" / domain).resolve()
        for path in _ts_files(domain):
            for match in TS_IMPORT.finditer(path.read_text()):
                spec = match.group(1) or match.group(2)
                if spec.startswith(TS_SHARED_PREFIXES) and not spec.startswith("."):
                    continue
                if spec.startswith("."):
                    target = (path.parent / spec).resolve()
                    if str(target).startswith(str(base)) or _own_contract(target, domain):
                        continue
                    rel = target.relative_to((ROOT / "src").resolve()).parts[0]
                    if rel in ("platform", "theme", "i18n", "components", "theme.ts"):
                        continue
                offenders.append(f"{path.relative_to(ROOT)} -> {spec}")
    assert offenders == []


def test_typescript_core_is_pure():
    offenders = []
    for domain in TS_DOMAINS:
        for path in (p for p in _ts_files(domain) if p.parent.name == "core"):
            for match in TS_IMPORT.finditer(path.read_text()):
                spec = match.group(1) or match.group(2)
                if not spec.startswith("./") and not _own_contract((path.parent / spec).resolve(), domain):
                    offenders.append(f"{path.relative_to(ROOT)} -> {spec}")
    assert offenders == []
