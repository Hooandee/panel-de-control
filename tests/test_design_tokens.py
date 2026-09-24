import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_design_tokens  # noqa: E402


def test_generated_design_files_are_current():
    assert export_design_tokens.main(["--check"]) == 0


def test_tokens_mirror_the_linux_theme_and_accents():
    tokens = json.loads((ROOT / "shared" / "design" / "tokens.json").read_text(encoding="utf-8"))
    accents = re.findall(r'\{ id: "(\w+)", hex: "#([0-9a-fA-F]{6})" \}', (ROOT / "src" / "system" / "accentColor.ts").read_text())

    assert tokens["color"]["surface"] == "#FF060608"
    assert tokens["color"]["surfaceRaised"] == "#FF0C0C10"
    assert tokens["color"]["hairline"] == "#0FFFFFFF"
    assert [(item["id"], item["color"]) for item in tokens["accents"]] == [
        (accent_id, "#FF" + hex_value.upper()) for accent_id, hex_value in accents
    ]
    assert tokens["default_accent"] == "blue"
    assert tokens["font"] == {"caption": 11, "body": 13, "value": 28}
