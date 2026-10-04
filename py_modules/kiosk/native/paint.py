import functools
import io
import math
import re

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Rsvg", "2.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Pango, PangoCairo, Rsvg  # noqa: E402

FONT_FAMILY = "Inter, Noto Sans, sans-serif"
WHITE = (1.0, 1.0, 1.0, 1.0)

RGBA = tuple[float, float, float, float]


def white(alpha: float) -> RGBA:
    return (1.0, 1.0, 1.0, alpha)


def rounded_rect(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float) -> None:
    r = max(0.0, min(r, w / 2, h / 2))
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def glass(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float = 24) -> None:
    angle = math.radians(160 - 90)
    dx, dy = math.cos(angle) * w / 2, math.sin(angle) * h / 2
    sheen = cairo.LinearGradient(x + w / 2 - dx, y + h / 2 - dy, x + w / 2 + dx, y + h / 2 + dy)
    sheen.add_color_stop_rgba(0, 1, 1, 1, 0.13)
    sheen.add_color_stop_rgba(1, 1, 1, 1, 0.05)
    rounded_rect(ctx, x, y, w, h, r)
    ctx.set_source(sheen)
    ctx.fill_preserve()
    ctx.save()
    ctx.clip()
    ctx.set_source_rgba(1, 1, 1, 0.22)
    ctx.rectangle(x, y, w, 1)
    ctx.fill()
    ctx.restore()
    rounded_rect(ctx, x + 0.25, y + 0.25, w - 0.5, h - 0.5, r)
    ctx.set_source_rgba(1, 1, 1, 0.08)
    ctx.set_line_width(0.5)
    ctx.stroke()


def fill_rounded(ctx: cairo.Context, x: float, y: float, w: float, h: float, r: float, rgba: RGBA) -> None:
    rounded_rect(ctx, x, y, w, h, r)
    ctx.set_source_rgba(*rgba)
    ctx.fill()


@functools.lru_cache(maxsize=64)
def _font(size: float, weight: int) -> Pango.FontDescription:
    desc = Pango.FontDescription.from_string(FONT_FAMILY)
    desc.set_absolute_size(size * Pango.SCALE)
    # GI accepts only named weights; the variable font gets the exact one as a variation.
    desc.set_weight(min(Pango.Weight.__enum_values__.values(), key=lambda named: abs(int(named) - weight)))
    desc.set_variations(f"wght={weight}")
    return desc


class Text:
    def __init__(self, ctx: cairo.Context, value: str, size: float, weight: int = 400, spacing: float = 0.0,
                 max_width: float | None = None, wrap_width: float | None = None):
        self.layout = PangoCairo.create_layout(ctx)
        self.layout.set_font_description(_font(size, weight))
        if spacing:
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_letter_spacing_new(int(spacing * size * Pango.SCALE)))
            self.layout.set_attributes(attrs)
        if max_width is not None:
            self.layout.set_width(int(max_width * Pango.SCALE))
            self.layout.set_ellipsize(Pango.EllipsizeMode.END)
        elif wrap_width is not None:
            self.layout.set_width(int(wrap_width * Pango.SCALE))
            self.layout.set_wrap(Pango.WrapMode.WORD)
            self.layout.set_alignment(Pango.Alignment.CENTER)
        self.layout.set_text(value, -1)
        _, logical = self.layout.get_pixel_extents()
        self.width = logical.width
        self.height = logical.height
        self.baseline = self.layout.get_baseline() / Pango.SCALE

    def draw(self, ctx: cairo.Context, x: float, y: float, rgba: RGBA = WHITE) -> None:
        ctx.move_to(x, y)
        ctx.set_source_rgba(*rgba)
        PangoCairo.show_layout(ctx, self.layout)

    def draw_centered(self, ctx: cairo.Context, x: float, y: float, width: float, rgba: RGBA = WHITE) -> None:
        self.draw(ctx, x + (width - self.layout.get_width() / Pango.SCALE) / 2, y, rgba)

    def draw_baseline(self, ctx: cairo.Context, x: float, baseline: float, rgba: RGBA = WHITE) -> None:
        self.draw(ctx, x, baseline - self.baseline, rgba)


_SVG_INNER = re.compile(r"^<svg[^>]*>(.*)</svg>$", re.S)


class Icons:
    def __init__(self, markup: dict[str, str]):
        self._markup = markup
        self._handles: dict[tuple[str, RGBA, float], Rsvg.Handle] = {}

    def draw(self, ctx: cairo.Context, name: str, cx: float, cy: float, size: float, rgba: RGBA = WHITE,
             stroke: float = 1.7) -> None:
        handle = self._handle(name, rgba, stroke)
        if handle is None:
            return
        rect = Rsvg.Rectangle()
        rect.x, rect.y, rect.width, rect.height = cx - size / 2, cy - size / 2, size, size
        handle.render_document(ctx, rect)

    def _handle(self, name: str, rgba: RGBA, stroke: float) -> Rsvg.Handle | None:
        key = (name, rgba, stroke)
        if key in self._handles:
            return self._handles[key]
        raw = self._markup.get(name)
        match = _SVG_INNER.match(raw.strip()) if raw else None
        if match is None:
            return None
        color = "rgba({},{},{},{})".format(*(round(c * 255) for c in rgba[:3]), rgba[3])
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'style="color:{color}" fill="none" stroke="currentColor" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-linejoin="round">{match.group(1)}</svg>'
        )
        handle = Rsvg.Handle.new_from_data(svg.encode())
        self._handles[key] = handle
        return handle


def decode_image(data: bytes, max_width: int) -> cairo.ImageSurface | None:
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf is None:
            return None
        if pixbuf.get_width() > max_width:
            height = max(1, round(pixbuf.get_height() * max_width / pixbuf.get_width()))
            pixbuf = pixbuf.scale_simple(max_width, height, GdkPixbuf.InterpType.BILINEAR)
        ok, png = pixbuf.save_to_bufferv("png", [], [])
        return cairo.ImageSurface.create_from_png(io.BytesIO(png)) if ok else None
    except Exception:  # noqa: BLE001
        return None


def cover(ctx: cairo.Context, image: cairo.ImageSurface, x: float, y: float, w: float, h: float,
          focus_y: float = 0.5, alpha: float = 1.0) -> None:
    scale = max(w / image.get_width(), h / image.get_height())
    drawn_w, drawn_h = image.get_width() * scale, image.get_height() * scale
    ctx.save()
    ctx.rectangle(x, y, w, h)
    ctx.clip()
    ctx.translate(x + (w - drawn_w) / 2, y + (h - drawn_h) * focus_y)
    ctx.scale(scale, scale)
    ctx.set_source_surface(image, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_GOOD)
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def contain(ctx: cairo.Context, image: cairo.ImageSurface, x: float, bottom: float, max_w: float, max_h: float) -> float:
    scale = min(max_w / image.get_width(), max_h / image.get_height())
    drawn_h = image.get_height() * scale
    ctx.save()
    ctx.translate(x, bottom - drawn_h)
    ctx.scale(scale, scale)
    ctx.set_source_surface(image, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_GOOD)
    ctx.paint()
    ctx.restore()
    return drawn_h


def swatch_pattern(stops: tuple[tuple[int, int, int], ...], x: float, w: float) -> cairo.Pattern:
    if len(stops) == 1:
        return cairo.SolidPattern(*(c / 255 for c in stops[0]))
    pattern = cairo.LinearGradient(x, 0, x + w, 0)
    for index, (r, g, b) in enumerate(stops):
        pattern.add_color_stop_rgb(index / (len(stops) - 1), r / 255, g / 255, b / 255)
    return pattern
