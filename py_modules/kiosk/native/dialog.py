"""The glass dialog of the bottom screen: a hero line, a row of orbs and an optional step slider."""

import math
from dataclasses import dataclass, field

import cairo

from choices import step_at
from geometry import HEIGHT, WIDTH, Rect
from paint import Icons, Text, fill_rounded, rounded_rect, white

PANEL_W = 560
PAD_X, PAD_TOP, PAD_BOTTOM = 24, 22, 24
RADIUS = 38
BUBBLE = 70
HERO_GAP = 18
ORB = 66
ORB_MIN_W = 74
ORB_LABEL_GAP = 8
ORB_ROW_H = ORB + ORB_LABEL_GAP + 15
STEPS_TOP, STEPS_H, STEPS_PAD, KNOB = 16, 30, 11, 26
NOTE_TOP = 14
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
class Steps:
    value: int
    low: int
    high: int
    disabled: bool = False


@dataclass(frozen=True)
class DialogModel:
    title: str
    detail: str | None = None
    bubble_icon: str | None = None
    bubble_text: str | None = None
    orbs: tuple[Orb, ...] = ()
    steps: Steps | None = None
    note: str | None = None


@dataclass
class Layout:
    panel: Rect
    orbs: list[tuple[Rect, Orb]] = field(default_factory=list)
    steps: Rect | None = None


def layout(model: DialogModel) -> Layout:
    height = PAD_TOP + BUBBLE + PAD_BOTTOM
    if model.orbs:
        height += HERO_GAP + ORB_ROW_H
    if model.steps:
        height += STEPS_TOP + STEPS_H
    if model.note:
        height += NOTE_TOP + 17
    panel = Rect((WIDTH - PANEL_W) / 2, (HEIGHT - height) / 2, PANEL_W, height)
    result = Layout(panel)
    y = panel.y + PAD_TOP + BUBBLE
    if model.orbs:
        y += HERO_GAP
        inner = PANEL_W - 2 * PAD_X
        width = max(ORB_MIN_W, inner / len(model.orbs))
        start = panel.x + PAD_X + (inner - width * len(model.orbs)) / 2
        result.orbs = [(Rect(start + i * width, y, width, ORB_ROW_H), orb) for i, orb in enumerate(model.orbs)]
        y += ORB_ROW_H
    if model.steps:
        result.steps = Rect(panel.x + PAD_X + 6, y + STEPS_TOP, PANEL_W - 2 * PAD_X - 12, STEPS_H)
    return result


def hit(model: DialogModel, x: float, y: float) -> tuple[str, object]:
    """('orb', key) | ('steps', value) | ('inside', None) | ('outside', None)."""
    placed = layout(model)
    for rect, orb in placed.orbs:
        if rect.contains(x, y):
            return ("inside", None) if orb.disabled else ("orb", orb.key)
    if placed.steps and model.steps and not model.steps.disabled and placed.steps.contains(x, y):
        return "steps", steps_value(model, x)
    return ("inside", None) if placed.panel.contains(x, y) else ("outside", None)


def steps_value(model: DialogModel, x: float) -> int:
    rect = layout(model).steps
    if rect is None or model.steps is None:
        return 0
    return step_at(x - rect.x, rect.w, STEPS_PAD, model.steps.low, model.steps.high)


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
    """A soft blur of what is behind the glass, made once when the dialog opens: shrink in box-filtered
    steps, then grow back in bilinear steps so no blocks show."""
    width, height = scene.get_width(), scene.get_height()
    current = scene
    for factor in (4, 4, 2):
        current = _resample(current, current.get_width() // factor, current.get_height() // factor, cairo.FILTER_GOOD)
    for factor in (2, 4):
        current = _resample(current, current.get_width() * factor, current.get_height() * factor, cairo.FILTER_BILINEAR)
    return _resample(current, width, height, cairo.FILTER_BILINEAR)


def paint(ctx: cairo.Context, model: DialogModel, icons: Icons, backdrop: cairo.ImageSurface | None,
          device_scale: tuple[float, float], drag_value: int | None = None) -> None:
    placed = layout(model)
    p = placed.panel
    ctx.save()
    ctx.set_source_rgba(0, 0, 0, 0.3)
    ctx.paint()

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

    _hero(ctx, model, icons, p.x + PAD_X, p.y + PAD_TOP)
    for rect, orb in placed.orbs:
        _orb(ctx, orb, icons, rect)
    if placed.steps and model.steps:
        value = model.steps.value if drag_value is None else drag_value
        _steps(ctx, model.steps, value, placed.steps)
    if model.note:
        note = Text(ctx, model.note, 12, 400, max_width=p.w - 2 * PAD_X)
        note.draw(ctx, p.x + (p.w - note.width) / 2, p.y + p.h - PAD_BOTTOM - 17, white(0.6))
    ctx.restore()


def _hero(ctx: cairo.Context, model: DialogModel, icons: Icons, x: float, y: float) -> None:
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
    title = Text(ctx, model.title, 38, 220, spacing=-0.05, max_width=PANEL_W - 2 * PAD_X - BUBBLE - 18)
    detail = Text(ctx, model.detail, 12.5, 400, max_width=PANEL_W - 2 * PAD_X - BUBBLE - 18) if model.detail else None
    block = title.height + (5 + detail.height if detail else 0)
    top = y + (BUBBLE - block) / 2
    title.draw(ctx, x + BUBBLE + 18, top)
    if detail:
        detail.draw(ctx, x + BUBBLE + 18, top + title.height + 5, white(0.7))


def _orb(ctx: cairo.Context, orb: Orb, icons: Icons, rect: Rect) -> None:
    if orb.disabled:
        ctx.push_group()
    cx = rect.x + rect.w / 2
    top = rect.y
    fill_rounded(ctx, cx - ORB / 2, top, ORB, ORB, ORB / 2, (1, 1, 1, 0.95) if orb.on else white(0.12))
    ctx.save()
    rounded_rect(ctx, cx - ORB / 2, top, ORB, ORB, ORB / 2)
    ctx.clip()
    ctx.set_source_rgba(1, 1, 1, 0.45)
    ctx.rectangle(cx - ORB / 2, top, ORB, 1)
    ctx.fill()
    ctx.restore()
    ink = INK if orb.on else white(1)
    if orb.icon:
        icons.draw(ctx, orb.icon, cx, top + ORB / 2, 28, ink, 1.6)
    elif orb.text:
        text = Text(ctx, orb.text, 22, 450)
        text.draw(ctx, cx - text.width / 2, top + (ORB - text.height) / 2, ink)
    label = Text(ctx, orb.label, 12, 550, max_width=rect.w)
    label.draw(ctx, cx - label.width / 2, top + ORB + ORB_LABEL_GAP, white(0.85))
    if orb.disabled:
        ctx.pop_group_to_source()
        ctx.paint_with_alpha(DISABLED)


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
