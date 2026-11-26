"""Pixel fonts drawn for the 64x54 panel, plus a stroke-built big numeral face for clocks."""

from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Font:
    height: int
    glyphs: dict[str, tuple[str, ...]] = field(repr=False)
    spacing: int = 1

    def glyph(self, ch: str) -> tuple[str, ...]:
        return self.glyphs.get(ch.upper(), self.glyphs.get("?", ()))


def _parse(table: str, height: int) -> dict[str, tuple[str, ...]]:
    glyphs: dict[str, tuple[str, ...]] = {}
    lines = [line for line in table.strip("\n").split("\n")]
    for start in range(0, len(lines), height + 1):
        header, rows = lines[start], lines[start + 1:start + 1 + height]
        glyphs[header.strip()[0] if header.strip() != "space" else " "] = tuple(rows)
    return glyphs


_TINY = """
0
###
#.#
#.#
#.#
###
1
.#.
##.
.#.
.#.
###
2
###
..#
###
#..
###
3
###
..#
.##
..#
###
4
#.#
#.#
###
..#
..#
5
###
#..
###
..#
###
6
###
#..
###
#.#
###
7
###
..#
.#.
.#.
.#.
8
###
#.#
###
#.#
###
9
###
#.#
###
..#
###
A
.#.
#.#
###
#.#
#.#
B
##.
#.#
##.
#.#
##.
C
.##
#..
#..
#..
.##
D
##.
#.#
#.#
#.#
##.
E
###
#..
##.
#..
###
F
###
#..
##.
#..
#..
G
.##
#..
#.#
#.#
.##
H
#.#
#.#
###
#.#
#.#
I
###
.#.
.#.
.#.
###
J
..#
..#
..#
#.#
.#.
K
#.#
#.#
##.
#.#
#.#
L
#..
#..
#..
#..
###
M
#...#
##.##
#.#.#
#...#
#...#
N
##.
#.#
#.#
#.#
#.#
O
.#.
#.#
#.#
#.#
.#.
P
##.
#.#
##.
#..
#..
Q
.#.
#.#
#.#
##.
.##
R
##.
#.#
##.
#.#
#.#
S
.##
#..
.#.
..#
##.
T
###
.#.
.#.
.#.
.#.
U
#.#
#.#
#.#
#.#
###
V
#.#
#.#
#.#
#.#
.#.
W
#...#
#...#
#.#.#
#.#.#
.#.#.
X
#.#
#.#
.#.
#.#
#.#
Y
#.#
#.#
.#.
.#.
.#.
Z
###
..#
.#.
#..
###
:
.
#
.
#
.
%
#.#
..#
.#.
#..
#.#
.
.
.
.
.
#
-
...
...
###
...
...
/
..#
..#
.#.
#..
#..
+
...
.#.
###
.#.
...
?
###
..#
.#.
...
.#.
!
#
#
#
.
#
'
#
#
.
.
.
°
###
#.#
###
...
...
space
..
..
..
..
..
"""

_SMALL = """
0
.###.
#...#
#..##
#.#.#
##..#
#...#
.###.
1
..#..
.##..
..#..
..#..
..#..
..#..
.###.
2
.###.
#...#
....#
...#.
..#..
.#...
#####
3
#####
...#.
..#..
...#.
....#
#...#
.###.
4
...#.
..##.
.#.#.
#..#.
#####
...#.
...#.
5
#####
#....
####.
....#
....#
#...#
.###.
6
..##.
.#...
#....
####.
#...#
#...#
.###.
7
#####
....#
...#.
..#..
.#...
.#...
.#...
8
.###.
#...#
#...#
.###.
#...#
#...#
.###.
9
.###.
#...#
#...#
.####
....#
...#.
.##..
A
.###.
#...#
#...#
#####
#...#
#...#
#...#
B
####.
#...#
#...#
####.
#...#
#...#
####.
C
.###.
#...#
#....
#....
#....
#...#
.###.
D
###..
#..#.
#...#
#...#
#...#
#..#.
###..
E
#####
#....
#....
####.
#....
#....
#####
F
#####
#....
#....
####.
#....
#....
#....
G
.###.
#...#
#....
#.###
#...#
#...#
.####
H
#...#
#...#
#...#
#####
#...#
#...#
#...#
I
.###.
..#..
..#..
..#..
..#..
..#..
.###.
J
..###
...#.
...#.
...#.
...#.
#..#.
.##..
K
#...#
#..#.
#.#..
##...
#.#..
#..#.
#...#
L
#....
#....
#....
#....
#....
#....
#####
M
#...#
##.##
#.#.#
#.#.#
#...#
#...#
#...#
N
#...#
#...#
##..#
#.#.#
#..##
#...#
#...#
O
.###.
#...#
#...#
#...#
#...#
#...#
.###.
P
####.
#...#
#...#
####.
#....
#....
#....
Q
.###.
#...#
#...#
#...#
#.#.#
#..#.
.##.#
R
####.
#...#
#...#
####.
#.#..
#..#.
#...#
S
.####
#....
#....
.###.
....#
....#
####.
T
#####
..#..
..#..
..#..
..#..
..#..
..#..
U
#...#
#...#
#...#
#...#
#...#
#...#
.###.
V
#...#
#...#
#...#
#...#
#...#
.#.#.
..#..
W
#...#
#...#
#...#
#.#.#
#.#.#
#.#.#
.#.#.
X
#...#
#...#
.#.#.
..#..
.#.#.
#...#
#...#
Y
#...#
#...#
.#.#.
..#..
..#..
..#..
..#..
Z
#####
....#
...#.
..#..
.#...
#....
#####
:
.
.
#
.
#
.
.
%
##..#
##..#
...#.
..#..
.#...
#..##
#..##
.
.
.
.
.
.
.
#
-
.....
.....
.....
####.
.....
.....
.....
/
....#
....#
...#.
..#..
.#...
#....
#....
+
.....
..#..
..#..
#####
..#..
..#..
.....
?
.###.
#...#
....#
...#.
..#..
.....
..#..
!
#
#
#
#
#
.
#
'
#
#
.
.
.
.
.
°
.##.
#..#
#..#
.##.
....
....
....
space
...
...
...
...
...
...
...
"""

TINY = Font(5, _parse(_TINY, 5))
SMALL = Font(7, _parse(_SMALL, 7))

# Big numerals: each digit is a set of segments on a 0..1 grid, rasterised at the requested
# height with rounded joints. Colons are two dots, the minus a single bar.
_SEGMENTS = {
    "a": ((0.0, 0.0), (1.0, 0.0)), "b": ((1.0, 0.0), (1.0, 0.5)), "c": ((1.0, 0.5), (1.0, 1.0)),
    "d": ((0.0, 1.0), (1.0, 1.0)), "e": ((0.0, 0.5), (0.0, 1.0)), "f": ((0.0, 0.0), (0.0, 0.5)),
    "g": ((0.0, 0.5), (1.0, 0.5)),
}
_DIGITS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
    "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def _stroke_glyph(segments: str, width: int, height: int, thickness: int) -> tuple[str, ...]:
    grid = [[False] * width for _ in range(height)]
    span_x, span_y = width - thickness, height - thickness
    for name in segments:
        (x0, y0), (x1, y1) = _SEGMENTS[name]
        ax, ay = round(x0 * span_x), round(y0 * span_y)
        bx, by = round(x1 * span_x), round(y1 * span_y)
        for y in range(min(ay, by), max(ay, by) + thickness):
            for x in range(min(ax, bx), max(ax, bx) + thickness):
                grid[y][x] = True
    return _rounded(grid)


def _one_glyph(width: int, height: int, thickness: int) -> tuple[str, ...]:
    """Stem right of centre plus a diagonal flag of the same weight, so the 1 is not a thin bar."""
    grid = [[False] * width for _ in range(height)]
    stem = width - thickness - 1
    for y in range(height):
        for x in range(stem, stem + thickness):
            grid[y][x] = True
    rows = [list(row) for row in _rounded(grid)]
    flag = min(stem, max(2, round(height * 0.26)))
    for k in range(1, flag + 1):
        for dy in range(thickness):
            y = k + dy - 1
            if y < height:
                rows[y][stem - k] = "#"
    for x in range(stem - 1, stem + thickness - 1):
        rows[0][x] = "#"
    return tuple("".join(row) for row in rows)


def _run(grid: list[list[bool]], x: int, y: int, dx: int, dy: int) -> int:
    height, width = len(grid), len(grid[0])
    count = 1
    for sign in (1, -1):
        cx, cy = x + sign * dx, y + sign * dy
        while 0 <= cx < width and 0 <= cy < height and grid[cy][cx]:
            count += 1
            cx, cy = cx + sign * dx, cy + sign * dy
    return count


def _rounded(grid: list[list[bool]]) -> tuple[str, ...]:
    height, width = len(grid), len(grid[0])

    def lit(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height and grid[y][x]

    corners = [
        (x, y) for y in range(height) for x in range(width)
        if grid[y][x] and any(not lit(x + dx, y) and not lit(x, y + dy) and not lit(x + dx, y + dy)
                              for dx in (-1, 1) for dy in (-1, 1))
        and sum(lit(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) == 2
        and _run(grid, x, y, 1, 0) >= 4 and _run(grid, x, y, 0, 1) >= 4
    ]
    for x, y in corners:
        grid[y][x] = False
    return tuple("".join("#" if cell else "." for cell in row) for row in grid)


@lru_cache(maxsize=8)
def big(height: int) -> Font:
    thickness = max(2, height // 6)
    width = max(thickness * 2 + 2, round(height * 0.6))
    glyphs = {d: _stroke_glyph(s, width, height, thickness) for d, s in _DIGITS.items()}
    glyphs["1"] = _one_glyph(width, height, thickness)
    colon = ["." * thickness] * height
    for top in (round(height * 0.28), round(height * 0.62)):
        for y in range(top, min(height, top + thickness)):
            colon[y] = "#" * thickness
    glyphs[":"] = tuple(colon)
    bar = round((height - thickness) / 2)
    bar_width = max(thickness * 2, width - thickness)
    glyphs["-"] = tuple("#" * bar_width if bar <= y < bar + thickness else "." * bar_width for y in range(height))
    glyphs[" "] = tuple("." * (width // 2) for _ in range(height))
    return Font(height, glyphs, spacing=max(1, thickness // 2 + 1))


def measure(text: str, font: Font) -> int:
    widths = [len(font.glyph(ch)[0]) if font.glyph(ch) else 0 for ch in text]
    if not widths:
        return 0
    return sum(widths) + font.spacing * (len(widths) - 1)
