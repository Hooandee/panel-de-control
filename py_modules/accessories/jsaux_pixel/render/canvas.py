"""RGB drawing surface the size of the panel, and quantisation to one shared GIF palette."""

from .. import codec
from .fonts import Font

Rgb = tuple[int, int, int]
BLACK: Rgb = (0, 0, 0)
_MAX_COLOURS = 255


class Canvas:
    def __init__(self, width: int = codec.WIDTH, height: int = codec.HEIGHT, background: Rgb = BLACK):
        self.width, self.height = width, height
        self._pixels: list[Rgb] = [background] * (width * height)

    def px(self, x: int, y: int, rgb: Rgb) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = rgb

    def get(self, x: int, y: int) -> Rgb:
        return self._pixels[y * self.width + x]

    def fill(self, rgb: Rgb) -> None:
        self._pixels = [rgb] * (self.width * self.height)

    def rect(self, x: int, y: int, w: int, h: int, rgb: Rgb) -> None:
        for row in range(max(0, y), min(self.height, y + h)):
            for col in range(max(0, x), min(self.width, x + w)):
                self._pixels[row * self.width + col] = rgb

    def line(self, x0: int, y0: int, x1: int, y1: int, rgb: Rgb) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.px(x0, y0, rgb)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx: int, cy: int, r: int, rgb: Rgb, filled: bool = False) -> None:
        for y in range(-r, r + 1):
            for x in range(-r, r + 1):
                d = x * x + y * y
                if d <= r * r + r and (filled or d >= (r - 1) * (r - 1) + (r - 1)):
                    self.px(cx + x, cy + y, rgb)

    def text(self, x: int, y: int, text: str, font: Font, rgb: Rgb) -> int:
        cursor = x
        for index, ch in enumerate(text):
            rows = font.glyph(ch)
            for dy, row in enumerate(rows):
                for dx, cell in enumerate(row):
                    if cell == "#":
                        self.px(cursor + dx, y + dy, rgb)
            cursor += (len(rows[0]) if rows else 0) + (font.spacing if index < len(text) - 1 else 0)
        return cursor - x

    def blit(self, sprite: "Canvas", x: int, y: int, transparent: Rgb | None = BLACK) -> None:
        for row in range(sprite.height):
            for col in range(sprite.width):
                rgb = sprite.get(col, row)
                if rgb != transparent:
                    self.px(x + col, y + row, rgb)

    def copy(self) -> "Canvas":
        twin = Canvas(self.width, self.height)
        twin._pixels = list(self._pixels)
        return twin

    def pixels(self) -> list[Rgb]:
        return list(self._pixels)


def quantize(frames: list[Canvas]) -> tuple[list[Rgb], list[bytes]]:
    """One palette for every frame of a segment; colours are posterised only when needed."""
    shift = 0
    while True:
        def reduce(rgb: Rgb) -> Rgb:
            if not shift:
                return rgb
            half = (1 << shift) >> 1
            return tuple(min(255, ((c >> shift) << shift) + half) for c in rgb)

        palette: dict[Rgb, int] = {BLACK: 0}
        for frame in frames:
            for rgb in frame._pixels:
                key = BLACK if rgb == BLACK else reduce(rgb)
                if key not in palette:
                    palette[key] = len(palette)
        if len(palette) <= _MAX_COLOURS:
            break
        shift += 1
    indexed = [bytes(palette[BLACK if rgb == BLACK else reduce(rgb)] for rgb in frame._pixels) for frame in frames]
    return list(palette), indexed
