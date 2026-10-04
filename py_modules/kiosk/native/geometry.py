from dataclasses import dataclass

WIDTH, HEIGHT = 620, 540
GRID_X, GRID_Y, GRID_W, GRID_H, GAP = 14, 160, 592, 364, 9

AREAS = {
    "perf": (0, 0, 2, 2), "fps": (2, 0, 1, 1), "fan": (3, 0, 1, 1), "bri": (4, 0, 1, 2), "vol": (5, 0, 1, 2),
    "rgb": (2, 1, 2, 1), "hz": (0, 2, 1, 1), "turbo": (1, 2, 1, 1), "shot": (2, 2, 1, 1), "kbd": (3, 2, 1, 1),
    "qam": (4, 2, 1, 1), "off": (5, 2, 1, 1),
}


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h


def grid_rects() -> dict[str, Rect]:
    col = (GRID_W - 5 * GAP) / 6
    row = (GRID_H - 2 * GAP) / 3
    return {
        name: Rect(GRID_X + c * (col + GAP), GRID_Y + r * (row + GAP), w * col + (w - 1) * GAP, h * row + (h - 1) * GAP)
        for name, (c, r, w, h) in AREAS.items()
    }


def logical_point(panel_x: float, panel_y: float, panel_w: int, panel_h: int) -> tuple[float, float]:
    return panel_y * WIDTH / panel_h, (panel_w - panel_x) * HEIGHT / panel_w


# The panel is mounted a quarter turn clockwise.
def rotation(panel_w: int, panel_h: int) -> tuple[float, float, float, float, float, float]:
    return (0.0, panel_h / WIDTH, -panel_w / HEIGHT, 0.0, float(panel_w), 0.0)
