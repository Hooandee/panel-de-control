import math
from dataclasses import dataclass, field

import cairo

from choices import step_at
from geometry import HEIGHT, WIDTH, Rect
from paint import Icons, Text, fill_rounded, rounded_rect, swatch_pattern, white

RGB = tuple[int, int, int]

PANEL_W = 560
PAD_X, PAD_TOP, PAD_BOTTOM = 24, 22, 24
INNER_W = PANEL_W - 2 * PAD_X
RADIUS = 38
BUBBLE = 70
ORB = 66
ORB_MIN_W = 74
ORB_LABEL_GAP = 8
ORB_ROW_H = ORB + ORB_LABEL_GAP + 15
ORB_ROW_GAP = 12
ORBS_PER_ROW = 6
STEPS_H, STEPS_PAD, KNOB = 30, 11, 26
SWATCH, SWATCH_GAP = 34, 12
CHIP_H, CHIP_PAD_X, CHIP_GAP = 31, 13, 8
BAR_H = 40
CTA_H = 44
DISABLED = 0.4
INK = (0.07, 0.07, 0.07, 1.0)


@dataclass(frozen=True)
class Orb:
    key: object
    label: str
    icon: str | None = None
    text: str | None = None
    on: bool = False
    disabled: bool = False


@dataclass(frozen=True)
class Orbs:
    items: tuple[Orb, ...]
    gap: float = 18


@dataclass(frozen=True)
class Colors:
    items: tuple[tuple[object, RGB, bool], ...]
    gap: float = 14


@dataclass(frozen=True)
class Chips:
    items: tuple[tuple[object, str, bool], ...]
    gap: float = 14


@dataclass(frozen=True)
class Bar:
    key: object
    value: float | None
    icon: str
    gap: float = 14


@dataclass(frozen=True)
class Steps:
    value: int
    low: int
    high: int
    disabled: bool = False
    gap: float = 16


@dataclass(frozen=True)
class Note:
    text: str
    gap: float = 14


@dataclass(frozen=True)
class Cta:
    key: object
    label: str
    disabled: bool = False
    gap: float = 18


Section = Orbs | Colors | Chips | Bar | Steps | Note | Cta


@dataclass(frozen=True)
class DialogModel:
    title: str
    detail: str | None = None
    bubble_icon: str | None = None
    bubble_text: str | None = None
    bubble_fill: tuple[RGB, ...] | None = None
    sections: tuple[Section, ...] = ()


@dataclass
class Placed:
    section: Section
    rect: Rect
    parts: list[tuple[Rect, object]] = field(default_factory=list)


@dataclass
class Layout:
    panel: Rect
    placed: list[Placed] = field(default_factory=list)


_MEASURE = cairo.Context(cairo.ImageSurface(cairo.FORMAT_RGB24, 1, 1))


def _chip_width(label: str) -> float:
    return Text(_MEASURE, label, 12.5, 550).width + 2 * CHIP_PAD_X


def _orb_rows(items: tuple[Orb, ...]) -> list[tuple[Orb, ...]]:
    if len(items) <= ORBS_PER_ROW:
        return [items]
    rows = math.ceil(len(items) / ORBS_PER_ROW)
    per_row = math.ceil(len(items) / rows)
    return [items[i:i + per_row] for i in range(0, len(items), per_row)]


def _section_height(section: Section) -> float:
    if isinstance(section, Orbs):
        rows = len(_orb_rows(section.items))
        return rows * ORB_ROW_H + (rows - 1) * ORB_ROW_GAP
    if isinstance(section, Colors):
        return SWATCH
    if isinstance(section, Chips):
        rows, line = 1, 0.0
        for _, label, _ in section.items:
            width = _chip_width(label)
            if line and line + CHIP_GAP + width > INNER_W:
                rows, line = rows + 1, width
            else:
                line += (CHIP_GAP if line else 0) + width
        return rows * CHIP_H + (rows - 1) * CHIP_GAP
    if isinstance(section, Bar):
        return BAR_H
    if isinstance(section, Steps):
        return STEPS_H
    if isinstance(section, Note):
        return Text(_MEASURE, section.text, 12, 400, wrap_width=INNER_W).height
    return CTA_H


def _place(section: Section, x: float, y: float) -> Placed:
    height = _section_height(section)
    placed = Placed(section, Rect(x, y, INNER_W, height))
    if isinstance(section, Orbs) and section.items:
        for row_index, row in enumerate(_orb_rows(section.items)):
            width = max(ORB_MIN_W, INNER_W / len(row))
            start = x + (INNER_W - width * len(row)) / 2
            top = y + row_index * (ORB_ROW_H + ORB_ROW_GAP)
            placed.parts += [(Rect(start + i * width, top, width, ORB_ROW_H), orb) for i, orb in enumerate(row)]
    elif isinstance(section, Colors) and section.items:
        total = len(section.items) * SWATCH + (len(section.items) - 1) * SWATCH_GAP
        start = x + (INNER_W - total) / 2
        placed.parts = [(Rect(start + i * (SWATCH + SWATCH_GAP), y, SWATCH, SWATCH), item) for i, item in enumerate(section.items)]
    elif isinstance(section, Chips):
        cx, cy = x, y
        for item in section.items:
            width = _chip_width(item[1])
            if cx > x and cx + width > x + INNER_W:
                cx, cy = x, cy + CHIP_H + CHIP_GAP
            placed.parts.append((Rect(cx, cy, width, CHIP_H), item))
            cx += width + CHIP_GAP
    elif isinstance(section, Steps):
        placed.rect = Rect(x + 6, y, INNER_W - 12, STEPS_H)
    elif isinstance(section, Cta):
        width = Text(_MEASURE, section.label, 15, 650).width + 52
        placed.rect = Rect(x + (INNER_W - width) / 2, y, width, CTA_H)
    return placed


def layout(model: DialogModel) -> Layout:
    height = PAD_TOP + BUBBLE + PAD_BOTTOM + sum(s.gap + _section_height(s) for s in model.sections)
    panel = Rect((WIDTH - PANEL_W) / 2, (HEIGHT - height) / 2, PANEL_W, height)
    result = Layout(panel)
    y = panel.y + PAD_TOP + BUBBLE
    for section in model.sections:
        y += section.gap
        result.placed.append(_place(section, panel.x + PAD_X, y))
        y += _section_height(section)
    return result


def hit(model: DialogModel, x: float, y: float) -> tuple[str, object, object]:
    placed = layout(model)
    for item in placed.placed:
        section = item.section
        if isinstance(section, (Orbs, Colors, Chips)):
            for rect, part in item.parts:
                if rect.contains(x, y):
                    if isinstance(part, Orb):
                        return ("inside", None, None) if part.disabled else ("orb", part.key, None)
                    kind = "color" if isinstance(section, Colors) else "chip"
                    return kind, part[0], None
        elif isinstance(section, Bar) and section.value is not None and item.rect.contains(x, y):
            return "bar", section.key, bar_value(item.rect, x)
        elif isinstance(section, Steps) and not section.disabled and item.rect.contains(x, y):
            return "steps", None, step_at(x - item.rect.x, item.rect.w, STEPS_PAD, section.low, section.high)
        elif isinstance(section, Cta) and not section.disabled and item.rect.contains(x, y):
            return "cta", section.key, None
    return ("inside", None, None) if placed.panel.contains(x, y) else ("outside", None, None)


def drag_value(model: DialogModel, kind: str, key: object, x: float) -> object:
    for item in layout(model).placed:
        section = item.section
        if kind == "bar" and isinstance(section, Bar) and section.key == key:
            return bar_value(item.rect, x)
        if kind == "steps" and isinstance(section, Steps):
            return step_at(x - item.rect.x, item.rect.w, STEPS_PAD, section.low, section.high)
    return None


def bar_value(rect: Rect, x: float) -> float:
    return round(min(1.0, max(0.0, (x - rect.x) / rect.w)), 3)


def _resample(source: cairo.ImageSurface, width: int, height: int, smooth: cairo.Filter) -> cairo.ImageSurface:
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, max(1, width), max(1, height))
    ctx = cairo.Context(out)
    ctx.scale(out.get_width() / source.get_width(), out.get_height() / source.get_height())
    ctx.set_source_surface(source, 0, 0)
    ctx.get_source().set_filter(smooth)
    ctx.get_source().set_extend(cairo.EXTEND_PAD)
    ctx.paint()
    return out


def frosted(scene: cairo.ImageSurface) -> cairo.ImageSurface:
    width, height = scene.get_width(), scene.get_height()
    current = scene
    for factor in (4, 4, 2):
        current = _resample(current, current.get_width() // factor, current.get_height() // factor, cairo.FILTER_GOOD)
    for factor in (2, 4):
        current = _resample(current, current.get_width() * factor, current.get_height() * factor, cairo.FILTER_BILINEAR)
    return _resample(current, width, height, cairo.FILTER_BILINEAR)


def paint(ctx: cairo.Context, model: DialogModel, icons: Icons, backdrop: cairo.ImageSurface | None,
          device_scale: tuple[float, float], drag: tuple[str, object, object] | None = None) -> None:
    placed = layout(model)
    p = placed.panel
    ctx.save()
    ctx.set_source_rgba(0, 0, 0, 0.3)
    ctx.paint()
    _glass(ctx, p, backdrop, device_scale)
    _hero(ctx, model, icons, p.x + PAD_X, p.y + PAD_TOP)
    for item in placed.placed:
        section = item.section
        if isinstance(section, Orbs):
            for rect, orb in item.parts:
                _orb(ctx, orb, icons, rect)
        elif isinstance(section, Colors):
            for rect, (_, color, on) in item.parts:
                if on:
                    fill_rounded(ctx, rect.x - 3, rect.y - 3, rect.w + 6, rect.h + 6, rect.w / 2 + 3, white(0.95))
                fill_rounded(ctx, rect.x, rect.y, rect.w, rect.h, rect.w / 2, (*(c / 255 for c in color), 1.0))
        elif isinstance(section, Chips):
            for rect, (_, label, on) in item.parts:
                fill_rounded(ctx, rect.x, rect.y, rect.w, rect.h, 16, white(0.95) if on else white(0.12))
                text = Text(ctx, label, 12.5, 550)
                text.draw(ctx, rect.x + (rect.w - text.width) / 2, rect.y + (rect.h - text.height) / 2, INK if on else white(1))
        elif isinstance(section, Bar):
            value = drag[2] if drag and drag[0] == "bar" and drag[1] == section.key else section.value
            _bar(ctx, section, value, item.rect, icons)
        elif isinstance(section, Steps):
            value = drag[2] if drag and drag[0] == "steps" else section.value
            _steps(ctx, section, value, item.rect)
        elif isinstance(section, Note):
            note = Text(ctx, section.text, 12, 400, wrap_width=INNER_W)
            note.draw_centered(ctx, item.rect.x, item.rect.y, INNER_W, white(0.6))
        elif isinstance(section, Cta):
            fill_rounded(ctx, item.rect.x, item.rect.y, item.rect.w, item.rect.h, 22, (1, 1, 1, 0.6 if section.disabled else 1))
            label = Text(ctx, section.label, 15, 650)
            label.draw(ctx, item.rect.x + (item.rect.w - label.width) / 2, item.rect.y + (item.rect.h - label.height) / 2, INK)
    ctx.restore()


def _glass(ctx: cairo.Context, p: Rect, backdrop: cairo.ImageSurface | None, device_scale: tuple[float, float]) -> None:
    rounded_rect(ctx, p.x, p.y, p.w, p.h, RADIUS)
    ctx.save()
    ctx.clip()
    if backdrop is not None:
        ctx.save()
        ctx.scale(1 / device_scale[0], 1 / device_scale[1])
        ctx.set_source_surface(backdrop, 0, 0)
        ctx.paint()
        ctx.restore()
        ctx.set_source_rgba(0, 0, 0, 0.3)
        ctx.paint()
    angle = math.radians(145 - 90)
    dx, dy = math.cos(angle) * p.w / 2, math.sin(angle) * p.h / 2
    sheen = cairo.LinearGradient(p.x + p.w / 2 - dx, p.y + p.h / 2 - dy, p.x + p.w / 2 + dx, p.y + p.h / 2 + dy)
    sheen.add_color_stop_rgba(0, 1, 1, 1, 0.20)
    sheen.add_color_stop_rgba(0.42, 1, 1, 1, 0.06)
    sheen.add_color_stop_rgba(1, 1, 1, 1, 0.10)
    ctx.set_source(sheen)
    ctx.paint()
    glow = cairo.RadialGradient(p.x + p.w * 0.15, p.y, 0, p.x + p.w * 0.15, p.y, p.w * 0.66)
    glow.add_color_stop_rgba(0, 1, 1, 1, 0.22)
    glow.add_color_stop_rgba(0.55, 1, 1, 1, 0)
    ctx.set_source(glow)
    ctx.paint()
    for rgba, rect in (
        (white(0.55), (p.x, p.y, p.w, 1)), (white(0.08), (p.x, p.y + p.h - 1, p.w, 1)),
        (white(0.18), (p.x, p.y, 1, p.h)), (white(0.10), (p.x + p.w - 1, p.y, 1, p.h)),
    ):
        ctx.set_source_rgba(*rgba)
        ctx.rectangle(*rect)
        ctx.fill()
    ctx.restore()


def _hero(ctx: cairo.Context, model: DialogModel, icons: Icons, x: float, y: float) -> None:
    if model.bubble_fill:
        rounded_rect(ctx, x, y, BUBBLE, BUBBLE, BUBBLE / 2)
        ctx.set_source(swatch_pattern(model.bubble_fill, x, BUBBLE))
        ctx.fill()
    else:
        fill_rounded(ctx, x, y, BUBBLE, BUBBLE, BUBBLE / 2, white(0.14))
    ctx.save()
    rounded_rect(ctx, x, y, BUBBLE, BUBBLE, BUBBLE / 2)
    ctx.clip()
    ctx.set_source_rgba(1, 1, 1, 0.4)
    ctx.rectangle(x, y, BUBBLE, 1)
    ctx.fill()
    ctx.restore()
    if model.bubble_icon:
        icons.draw(ctx, model.bubble_icon, x + BUBBLE / 2, y + BUBBLE / 2, 38, white(1), 1.3)
    elif model.bubble_text:
        number = Text(ctx, model.bubble_text, 36, 250, spacing=-0.04)
        number.draw(ctx, x + (BUBBLE - number.width) / 2, y + (BUBBLE - number.height) / 2)
    width = INNER_W - BUBBLE - 18
    title = Text(ctx, model.title, 38, 220, spacing=-0.05, max_width=width)
    detail = Text(ctx, model.detail, 12.5, 400, max_width=width) if model.detail else None
    block = title.height + (5 + detail.height if detail else 0)
    top = y + (BUBBLE - block) / 2
    title.draw(ctx, x + BUBBLE + 18, top)
    if detail:
        detail.draw(ctx, x + BUBBLE + 18, top + title.height + 5, white(0.7))


def _orb(ctx: cairo.Context, orb: Orb, icons: Icons, rect: Rect) -> None:
    if orb.disabled:
        ctx.push_group()
    cx = rect.x + rect.w / 2
    size = ORB
    top = rect.y
    fill_rounded(ctx, cx - size / 2, top, size, size, size / 2, (1, 1, 1, 0.95) if orb.on else white(0.12))
    ctx.save()
    rounded_rect(ctx, cx - size / 2, top, size, size, size / 2)
    ctx.clip()
    ctx.set_source_rgba(1, 1, 1, 0.45)
    ctx.rectangle(cx - size / 2, top, size, 1)
    ctx.fill()
    ctx.restore()
    ink = INK if orb.on else white(1)
    if orb.icon:
        icons.draw(ctx, orb.icon, cx, top + size / 2, 28, ink, 1.6)
    elif orb.text:
        text = Text(ctx, orb.text, 22, 450)
        text.draw(ctx, cx - text.width / 2, top + (size - text.height) / 2, ink)
    label = Text(ctx, orb.label, 12, 550, max_width=rect.w - 2)
    label.draw(ctx, cx - label.width / 2, rect.y + ORB + ORB_LABEL_GAP, white(0.85))
    if orb.disabled:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(DISABLED)


def _bar(ctx: cairo.Context, bar: Bar, value: float | None, rect: Rect, icons: Icons) -> None:
    if value is None:
        ctx.push_group()
    fill_rounded(ctx, rect.x, rect.y, rect.w, rect.h, 13, white(0.14))
    fraction = value or 0.0
    if fraction > 0:
        ctx.save()
        rounded_rect(ctx, rect.x, rect.y, rect.w, rect.h, 13)
        ctx.clip()
        ctx.set_source_rgba(1, 1, 1, 0.95)
        ctx.rectangle(rect.x, rect.y, rect.w * fraction, rect.h)
        ctx.fill()
        ctx.restore()
    icons.draw(ctx, bar.icon, rect.x + 13 + 10, rect.y + rect.h / 2, 20, (0x1C / 255, 0x1C / 255, 0x1E / 255, 1), 1.9)
    pct = Text(ctx, f"{round(fraction * 100)} %", 13, 600)
    pct_x = rect.x + rect.w - 13 - pct.width
    over_fill = pct_x + pct.width / 2 < rect.x + rect.w * fraction
    pct.draw(ctx, pct_x, rect.y + (rect.h - pct.height) / 2, (0.11, 0.11, 0.12, 0.85) if over_fill else white(0.75))
    if value is None:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(0.45)


def _steps(ctx: cairo.Context, steps: Steps, value: int, rect: Rect) -> None:
    if steps.disabled:
        ctx.push_group()
    span = rect.w - 2 * STEPS_PAD
    fraction = (value - steps.low) / (steps.high - steps.low) if steps.high > steps.low else 0.0
    fill_rounded(ctx, rect.x + STEPS_PAD, rect.y + 9, span, 8, 4, white(0.16))
    fill_rounded(ctx, rect.x + STEPS_PAD, rect.y + 9, span * fraction, 8, 4, white(0.95))
    knob_x = rect.x + STEPS_PAD + span * fraction
    fill_rounded(ctx, knob_x - KNOB / 2, rect.y + 2, KNOB, KNOB, KNOB / 2, (0, 0, 0, 0.25))
    fill_rounded(ctx, knob_x - KNOB / 2, rect.y, KNOB, KNOB, KNOB / 2, (1, 1, 1, 1))
    if steps.disabled:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(DISABLED)
