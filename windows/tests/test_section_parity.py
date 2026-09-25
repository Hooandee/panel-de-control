import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "src" / "customize" / "manifest.tsx"
CATALOG = REPO / "windows" / "src" / "PanelDeControl.Core" / "Presentation" / "SectionCatalog.cs"
WINDOWS_ONLY_BLOCKS = {"energy"}


def linux_tabs():
    source = MANIFEST.read_text(encoding="utf-8")
    return re.findall(r'\{ id: "([a-z]+)", labelKey: "nav\.[a-z]+", descriptionKey: "[^"]+", accent: "#([0-9a-f]{6})"', source)


def linux_blocks():
    source = MANIFEST.read_text(encoding="utf-8")
    body = source[source.index("export const SECTION_BLOCKS"):source.index("export function blocksForSection")]
    blocks = {}
    for section, entries in re.findall(r"\n  ([a-z]+): \[(.*?)\n  \],", body, re.S):
        blocks[section] = [
            block for block in re.findall(r'id: "([A-Za-z]+)"', entries)
            if block != "desktopPower"
        ]
    blocks["power"] = ["tdp", *blocks["power"]]
    return blocks


def windows_catalog():
    source = CATALOG.read_text(encoding="utf-8")
    sections = []
    for match in re.finditer(r'new SectionDefinition\("([a-z]+)", "[A-Za-z]+", 0xFF([0-9A-F]{6}), "[^"]+", new\[\](.*?)\}\),', source, re.S):
        blocks = re.findall(r'new BlockDefinition\("([A-Za-z]+)"', match.group(3))
        sections.append((match.group(1), match.group(2).lower(), blocks))
    return sections


class SectionParityTests(unittest.TestCase):
    def test_windows_has_every_linux_section_in_order_with_its_accent(self):
        linux = [(section, accent) for section, accent in linux_tabs()]
        windows = [(section, accent) for section, accent, _ in windows_catalog()]
        self.assertEqual(linux, windows)

    def test_windows_has_every_linux_block(self):
        windows = {section: blocks for section, _, blocks in windows_catalog()}
        for section, blocks in linux_blocks().items():
            self.assertEqual(
                [block for block in windows[section] if block not in WINDOWS_ONLY_BLOCKS],
                blocks,
                section,
            )

    def test_every_block_and_section_has_localized_text(self):
        strings = (REPO / "windows" / "src" / "PanelDeControl.GameBar" / "Strings" / "en-US" / "Resources.resw").read_text(encoding="utf-8")
        source = CATALOG.read_text(encoding="utf-8")
        stems = re.findall(r'new SectionDefinition\("[a-z]+", "([A-Za-z]+)"', source)
        for stem in stems:
            self.assertIn(f'name="Nav{stem}"', strings)
            self.assertIn(f'name="Nav{stem}Desc"', strings)
        for stem in re.findall(r'new BlockDefinition\("[A-Za-z]+", "([A-Za-z]+)"', source):
            self.assertIn(f'name="{stem}Title"', strings)
            self.assertIn(f'name="{stem}Desc"', strings)


if __name__ == "__main__":
    unittest.main()
