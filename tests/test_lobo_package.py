import hashlib
import json
import struct
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1] / "windows/native/keyboard/themes/lobo-blanco"


def font_table(path, tag):
    data = path.read_bytes()
    for index in range(struct.unpack_from(">H", data, 4)[0]):
        name, _, offset, length = struct.unpack_from(">4sIII", data, 12 + index * 16)
        if name == tag.encode("ascii"):
            return data[offset:offset + length]
    raise AssertionError(f"Missing {tag} table: {path.name}")


def font_coverage(path):
    data = font_table(path, "cmap")
    for index in range(struct.unpack_from(">H", data, 2)[0]):
        platform, encoding, offset = struct.unpack_from(">HHI", data, 4 + index * 8)
        if (platform, encoding) != (3, 1):
            continue
        assert struct.unpack_from(">H", data, offset)[0] == 4
        count = struct.unpack_from(">H", data, offset + 6)[0] // 2
        end_base = offset + 14
        start_base = end_base + count * 2 + 2
        delta_base = start_base + count * 2
        range_base = delta_base + count * 2
        codes = set()
        for segment in range(count):
            end = struct.unpack_from(">H", data, end_base + 2 * segment)[0]
            start = struct.unpack_from(">H", data, start_base + 2 * segment)[0]
            delta = struct.unpack_from(">h", data, delta_base + 2 * segment)[0]
            word = range_base + 2 * segment
            distance = struct.unpack_from(">H", data, word)[0]
            for code in range(start, min(end + 1, 0xFFFF)):
                if distance:
                    glyph = struct.unpack_from(">H", data, word + distance + 2 * (code - start))[0]
                    glyph = (glyph + delta) & 0xFFFF if glyph else 0
                else:
                    glyph = (code + delta) & 0xFFFF
                if glyph:
                    codes.add(code)
        return codes
    raise AssertionError(f"Missing Windows Unicode cmap: {path.name}")


def manifest():
    path = PACKAGE / "theme.json"
    assert path.is_file(), "Lobo Blanco needs its own resource manifest"
    return json.loads(path.read_text())


def test_lobo_resources_are_complete_and_match_their_hashes():
    theme = manifest()
    paths = set()
    for item in theme["assets"]:
        path = PACKAGE / item["path"]
        assert path.resolve().is_relative_to(PACKAGE.resolve())
        assert item["path"] not in paths
        paths.add(item["path"])
        data = path.read_bytes()
        assert len(data) == item["bytes"], item["path"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
    resources = {
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*")
        if path.suffix in {".png", ".webp", ".woff2", ".ttf"}
    }
    assert resources == paths


def test_lobo_roles_and_effects_only_reference_packaged_resources():
    theme = manifest()
    paths = {item["path"] for item in theme["assets"]}
    references = {theme["plate"]["asset"], *theme["keyFaces"]["states"].values()}
    references.update(sign["asset"] for sign in theme["signs"].values())
    references.update(font["path"] for font in theme["fonts"].values())
    references.update(effect["asset"] for effect in theme["effects"].values() if "asset" in effect)
    assert references <= paths
    assert set(theme["keyRoles"].values()) == set(theme["signs"])
    assert len(theme["keyRoles"]) == 5
    assert len(set(theme["keyFaces"]["states"].values())) == 7
    assert theme["fonts"]["letters"]["family"] == "Lobo Blanco Letras"
    assert theme["fonts"]["letters"]["unicodeRanges"] == ["0041-005A", "0061-007A", "00C0-00FF", "0152-0153"]
    assert theme["fonts"]["symbols"]["family"] == "Cinzel"


def test_lobo_scope_and_licensing_do_not_claim_windows_validation():
    theme = manifest()
    assert theme["schemaVersion"] == 1
    assert theme["id"] == "lobo-blanco"
    assert theme["target"] == "TextInputHost.exe"
    assert theme["experimental"] is True
    assert theme["scope"]["validatedWindowsBuilds"] == []
    assert theme["licensing"]["artwork"]["catalogAuthor"] == "Hooandee"
    assert theme["licensing"]["artwork"]["separateLicense"] is None
    for name in ("OFL-cinzel.txt", "OFL-marcellus.txt"):
        assert "SIL OPEN FONT LICENSE Version 1.1" in (PACKAGE / "fonts" / name).read_text()


def test_letter_font_exposes_only_original_css_ranges_for_native_fallback():
    wanted = set()
    for first, last in ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0xFF), (0x152, 0x153)):
        wanted.update(range(first, last + 1))
    full = font_coverage(PACKAGE / "fonts/Marcellus.ttf")
    letters = font_coverage(PACKAGE / "fonts/LoboBlancoLetras.ttf")
    symbols = font_coverage(PACKAGE / "fonts/Cinzel.ttf")
    assert len(full) == 214
    assert len(symbols) == 220
    assert letters == wanted.intersection(full)
    assert not letters.intersection(map(ord, " 0123456789.,!?"))
    assert set(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzñÑéÉ×÷")) <= letters


if __name__ == "__main__":
    tests = [test for name, test in globals().copy().items() if name.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} Lobo Blanco package checks passed")
