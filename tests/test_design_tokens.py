import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_design_tokens  # noqa: E402


def test_generated_design_files_are_current():
    assert export_design_tokens.main(["--check"]) == 0


def test_font_export_rejects_missing_defaults():
    source = export_design_tokens.THEME.read_text(encoding="utf-8")
    source = source.replace('themeSizeOverride("fontBody") ?? 13', 'themeSizeOverride("fontBody")')
    with pytest.raises(SystemExit, match="font defaults not found"):
        export_design_tokens._font_defaults(source)
