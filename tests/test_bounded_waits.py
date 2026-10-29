"""Every blocking wait in the backend carries a limit, so no shutdown, RPC or loop can hang."""
import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WAIT_METHODS = {"result", "join", "wait", "communicate"}
_SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output"}

# (file, enclosing function, call) -> why it cannot hang.
_ALLOWED = {
    ("main.py", "_finish_offered_pdc_refresh", "future.result()"):
        "done callback: the future has already completed",
    ("py_modules/decky_socket_guard.py", "_", "task.result()"):
        "done callback: the task has already completed",
    ("py_modules/remote_access.py", "_run_once", "self._process.wait()"):
        "supervisor task for a long-lived server; cancelled on shutdown",
}


def _sources():
    yield _ROOT / "main.py"
    yield from sorted((_ROOT / "py_modules").rglob("*.py"))


def _keyword(call, name):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _is_wait_for(node):
    func = getattr(node, "func", None)
    return isinstance(func, ast.Attribute) and func.attr == "wait_for" or (
        isinstance(func, ast.Name) and func.id == "wait_for"
    )


def _unbounded(call, parent):
    if not isinstance(call.func, ast.Attribute):
        return None
    method = call.func.attr
    owner = ast.unparse(call.func.value)
    if _is_wait_for(parent) and parent.args and parent.args[0] is call:
        return None
    if method in _WAIT_METHODS and not call.args and _keyword(call, "timeout") is None:
        return method
    if method == "shutdown" and not call.args:
        wait = _keyword(call, "wait")
        if not (isinstance(wait, ast.Constant) and wait.value is False):
            return "shutdown without wait=False"
    if owner == "subprocess" and method in _SUBPROCESS_CALLS and _keyword(call, "timeout") is None:
        return f"subprocess.{method} without timeout"
    if method == "wait_for" and len(call.args) < 2 and _keyword(call, "timeout") is None:
        return "wait_for without timeout"
    if method == "wait_for" and len(call.args) >= 2 and (
        isinstance(call.args[1], ast.Constant) and call.args[1].value is None
    ):
        return "wait_for with timeout=None"
    return None


def _findings():
    found = []
    for path in _sources():
        relative = path.relative_to(_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            problem = _unbounded(node, parents.get(node))
            if problem is None:
                continue
            scope = parents.get(node)
            while scope is not None and not isinstance(
                scope, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                scope = parents.get(scope)
            key = (relative, scope.name if scope else "<module>", ast.unparse(node))
            if key not in _ALLOWED:
                found.append(f"{relative}:{node.lineno}: {problem}: {key[2]}")
    return found


def test_no_wait_without_a_limit():
    assert _findings() == []


def test_allowlist_has_no_stale_entries():
    present = set()
    for path in _sources():
        relative = path.relative_to(_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for call in ast.walk(node):
                    if isinstance(call, ast.Call):
                        present.add((relative, node.name, ast.unparse(call)))
    assert set(_ALLOWED) <= present
