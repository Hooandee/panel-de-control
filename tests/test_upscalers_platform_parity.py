"""Every upscaler RPC Linux exposes says what Windows does about it, so neither side drifts unnoticed."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARITY = json.loads((ROOT / "shared/upscalers/parity.json").read_text(encoding="utf-8"))
NAMES = ("upscaler", "lsfg", "mako")


def _rpcs() -> set[str]:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Plugin")
    return {node.name for node in plugin.body if isinstance(node, ast.AsyncFunctionDef)
            and not node.name.startswith("_") and any(name in node.name for name in NAMES)}


def test_every_linux_upscaler_rpc_has_a_windows_status():
    listed = set(PARITY["rpcs"])
    assert _rpcs() - listed == set(), "add the new RPC to shared/upscalers/parity.json with its Windows status"
    assert listed - _rpcs() == set(), "remove RPCs Linux no longer has from shared/upscalers/parity.json"


def test_statuses_are_known():
    for name, entry in PARITY["rpcs"].items():
        assert entry["windows"] in PARITY["statuses"], name
