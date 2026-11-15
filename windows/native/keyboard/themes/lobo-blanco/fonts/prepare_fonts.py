"""Rebuild native font containers and the CSS letter-range derivative."""

import hashlib
from pathlib import Path

from fontTools import subset
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parent
ORIGINAL_HASHES = {
    "cinzel-latin.woff2": "8efa224fe70fef188a39c095e218b81fd31061809f2752537e33a9ec7b9c2263",
    "marcellus-latin.woff2": "8a539799d12e3a144273288055490f57e1eee84da7a9145f085bc522e80719c3",
}
LETTER_RANGES = ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x00FF), (0x0152, 0x0153))


def original(name):
    path = ROOT / "originals" / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != ORIGINAL_HASHES[name]:
        raise ValueError(f"Original font hash mismatch: {name}")
    return TTFont(path, recalcTimestamp=False)


def outlines(font):
    glyphs = font.getGlyphSet()
    result = {}
    for name in font.getGlyphOrder():
        pen = DecomposingRecordingPen(glyphs)
        glyphs[name].draw(pen)
        result[name] = pen.value
    return result


def save_full(source, destination):
    font = original(source)
    font.flavor = None
    font.save(ROOT / destination)
    rebuilt = TTFont(ROOT / destination, recalcTimestamp=False)
    baseline = original(source)
    assert rebuilt.getGlyphOrder() == baseline.getGlyphOrder()
    assert rebuilt.getBestCmap() == baseline.getBestCmap()
    assert rebuilt["hmtx"].metrics == baseline["hmtx"].metrics
    assert outlines(rebuilt) == outlines(baseline)
    assert rebuilt["name"].compile(rebuilt) == baseline["name"].compile(baseline)
    return rebuilt


def rename_letters(font):
    replacements = {
        1: "Lobo Blanco Letras",
        2: "Regular",
        3: "Hooandee:LoboBlancoLetras:1.0",
        4: "Lobo Blanco Letras Regular",
        6: "LoboBlancoLetras-Regular",
        16: "Lobo Blanco Letras",
        17: "Regular",
        21: "Lobo Blanco Letras",
        22: "Regular",
    }
    for record in list(font["name"].names):
        if record.nameID in replacements:
            font["name"].setName(
                replacements[record.nameID], record.nameID,
                record.platformID, record.platEncID, record.langID,
            )
    for name_id, value in replacements.items():
        font["name"].setName(value, name_id, 3, 1, 0x409)


def save_letters():
    baseline = original("marcellus-latin.woff2")
    font = original("marcellus-latin.woff2")
    wanted = {code for first, last in LETTER_RANGES for code in range(first, last + 1)}
    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.recalc_timestamp = False
    options.canonical_order = True
    options.glyph_names = True
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=wanted)
    subsetter.subset(font)
    rename_letters(font)
    font.flavor = None
    font.save(ROOT / "LoboBlancoLetras.ttf")
    rebuilt = TTFont(ROOT / "LoboBlancoLetras.ttf", recalcTimestamp=False)
    source_cmap = baseline.getBestCmap()
    result_cmap = rebuilt.getBestCmap()
    assert set(result_cmap) == wanted.intersection(source_cmap)
    source_outlines = outlines(baseline)
    result_outlines = outlines(rebuilt)
    for code, name in result_cmap.items():
        source_name = source_cmap[code]
        assert result_outlines[name] == source_outlines[source_name]
        assert rebuilt["hmtx"][name] == baseline["hmtx"][source_name]
    for record in rebuilt["name"].names:
        if record.nameID in {1, 3, 4, 6, 16, 21}:
            assert "Marcellus" not in record.toUnicode()


if __name__ == "__main__":
    save_full("cinzel-latin.woff2", "Cinzel.ttf")
    save_full("marcellus-latin.woff2", "Marcellus.ttf")
    save_letters()
    print("Verified full font coverage, outlines, metrics and letter-range derivative.")
