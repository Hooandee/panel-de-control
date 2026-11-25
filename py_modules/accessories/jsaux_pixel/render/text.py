"""Text clean-up and fitting shared by every scene that draws free-form names."""

import re
import unicodedata

from . import fonts

# What TINY and SMALL can draw; anything else would come out as "?".
_DRAWABLE = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!%'+-./:?° ")
_MAPPED = {"Æ": "AE", "Œ": "OE", "Ø": "O", "&": "+", ",": "."}
_TRADEMARKS = str.maketrans("", "", "™®©")


def plain_text(text: str) -> str:
    """Upper-case ASCII-ish text the pixel fonts can draw: accents dropped, "&" as "+"."""
    upper = text.translate(_TRADEMARKS).upper()
    upper = "".join(_MAPPED.get(ch, ch) for ch in upper)
    decomposed = unicodedata.normalize("NFKD", upper)
    kept = "".join(ch if ch in _DRAWABLE else " " for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", kept).strip()


def fit(text: str, font: fonts.Font, max_w: int) -> str:
    """The text itself, or its longest prefix ending in "." that fits, cut at a space when one does."""
    if fonts.measure(text, font) <= max_w:
        return text

    def shown(cut: int) -> str:
        return text[:cut].rstrip(" :-") + "."

    fitting = [cut for cut in range(len(text), 0, -1) if fonts.measure(shown(cut), font) <= max_w]
    if not fitting:
        return ""
    spaced = [cut for cut in fitting if cut < len(text) and text[cut] == " "]
    return shown((spaced or fitting)[0])


def big_fitting(text: str, sizes: tuple[int, ...], max_w: int) -> fonts.Font:
    """The first (largest) big numeral size whose text fits, else the smallest."""
    for size in sizes:
        font = fonts.big(size)
        if fonts.measure(text, font) <= max_w:
            return font
    return fonts.big(sizes[-1])
