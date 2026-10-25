"""A reel of the most striking scenes with made-up data, for filming the panel.

Every shot is one finished GIF: each press of the demo button costs a single upload.
"""

import dataclasses
from collections.abc import Callable
from datetime import tzinfo

from .scenes import pet as pet_scene
from .scenes.base import Scene, SceneContext, Segment
from .scenes.fit import fits

SEVILLE = {"name": "Sevilla", "detail": "Andalucía, España", "lat": 37.39, "lon": -5.98}
_LAYOUT = [
    {"type": "pill", "x": 2, "y": 2, "text": "GG WP", "color": "sunset", "font": "small"},
    {"type": "clock", "x": 2, "y": 14, "size": "l", "color": "aurora"},
    {"type": "sticker", "x": 48, "y": 1, "sticker": "fire", "size": "m"},
    {"type": "text", "x": 2, "y": 37, "text": "HOOANDEE", "font": "outline", "color": "mint"},
    {"type": "sticker", "x": 52, "y": 44, "sticker": "pacman", "size": "s"},
    {"type": "sticker", "x": 44, "y": 45, "sticker": "coin", "size": "s"},
    {"type": "text", "x": 2, "y": 47, "text": "PIXEL", "font": "shadow", "color": "aurora"},
]
_PET_SHOTS = {
    "pet_happy": ("idle", ("dance", "hearts", "butterfly", "ball", "stars")),
    "pet_sad": ("idle", ("hungry", "sulk", "call")),
    "pet_scared": ("idle", ("scared", "shiver", "flinch")),
    "pet_windy": ("idle", ("blown", "hold")),
}


@dataclasses.dataclass(frozen=True)
class Shot:
    id: str
    render: Callable[[dict[str, Scene], float, tzinfo], Segment]


def _context(now: float, tz: tzinfo, options: dict, game: dict | None = None, events: dict | None = None) -> SceneContext:
    return SceneContext(now=now, tz=tz, options=options, game=game, events=events or {})


def _scene_shot(scene_id: str, options: dict | None = None) -> Callable:
    def render(scenes, now, tz):
        scene = scenes[scene_id]
        ctx = _context(now, tz, dict(options or {}))
        scene.key(ctx)
        return scene.render(ctx)
    return render


def _pet_shot(mood: str, episodes: tuple[str, ...]) -> Callable:
    def render(scenes, now, tz):
        frames = []
        for name in episodes:
            frames += [canvas for canvas, _ in pet_scene.episode_frames(name, mood, {})]
        while True:
            segment = Segment(frames, [6] * len(frames))
            if fits(segment):
                return segment
            frames = frames[: len(frames) * 3 // 4]
    return render


def _weather_shot(group: str, temp: float, high: float, low: float) -> Callable:
    from .weather import SAMPLE_CODES

    def render(scenes, now, tz):
        reading = {"temp": temp, "code": SAMPLE_CODES[group], "day": True, "high": high, "low": low}
        return scenes["weather"].render_reading(reading, {"city": SEVILLE, "style": "sky"})
    return render


def _cover_shot(art: dict, layout: str) -> Callable:
    def render(scenes, now, tz):
        game = {"appid": art["appid"], "name": art["name"], "started_at": now - 2700}
        info = {"appid": art["appid"], "tags": [], "playtime_min": art.get("playtime_min"),
                "achievements": art.get("achievements"), "sent_at": now}
        if art.get("portrait"):
            info["portrait"] = art["portrait"]
        events = {"game_art": {"appid": art["appid"], "rgb": art["rgb"]}, "game_info": info}
        scene = scenes["game_cover"]
        ctx = _context(now, tz, {"layout": layout}, game, events)
        scene.key(ctx)
        return scene.render(ctx)
    return render


def _speedrun_shot(scenes, now, tz):
    scene = scenes["speedrun"]
    ctx = _context(now, tz, {}, {"appid": "504230", "name": "Celeste", "started_at": now - 754})
    scene.key(ctx)
    return scene.render(ctx)


def reel(art: dict | None) -> list[Shot]:
    shots = [Shot("hooandee", _scene_shot("hooandee"))]
    shots += [Shot(shot_id, _pet_shot(*spec)) for shot_id, spec in _PET_SHOTS.items()]
    shots += [Shot("weather_sun", _weather_shot("clear", 27, 31, 17)), Shot("weather_storm", _weather_shot("storm", 19, 22, 14))]
    if art:
        shots += [Shot("cover_full", _cover_shot(art, "full")), Shot("cover_side", _cover_shot(art, "side"))]
    shots += [
        Shot("speedrun", _speedrun_shot),
        Shot("layout", _scene_shot("composed", {"layout": {"blocks": _LAYOUT}})),
        Shot("clock_tetris", _scene_shot("clock_tetris")),
        Shot("art_aquarium", _scene_shot("art_aquarium")),
    ]
    return shots

