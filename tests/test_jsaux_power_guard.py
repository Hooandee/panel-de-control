from accessories.jsaux_pixel import codec, power_guard
from accessories.jsaux_pixel.codec import HEIGHT, WIDTH
from accessories.jsaux_pixel.gif import Frame


def test_brightness_maps_linearly_to_the_supply_ceiling():
    assert power_guard.pwm_for(100, strong=True) == 80
    assert power_guard.pwm_for(100, strong=False) == 30
    assert power_guard.pwm_for(50, strong=True) == 40
    assert power_guard.pwm_for(1, strong=False) == 1
    assert power_guard.pwm_for(0, strong=True) == 0
    assert power_guard.pwm_for(250, strong=True) == 80
    assert power_guard.pwm_for(-5, strong=True) == 0


def test_mostly_white_frames_are_dimmed_under_the_light_budget():
    palette = [(0, 0, 0), (255, 255, 255)]
    white = Frame(bytes([1]) * (WIDTH * HEIGHT), 100)
    limited = power_guard.limit_palette(palette, [white])
    assert power_guard.frame_load(limited, white) <= power_guard.LIGHT_BUDGET + 1e-6
    assert limited[0] == (0, 0, 0)


def test_dark_scenes_keep_their_colours():
    palette = [(0, 0, 0), (255, 255, 255)]
    sparse = bytearray(WIDTH * HEIGHT)
    sparse[:200] = bytes([1]) * 200
    assert power_guard.limit_palette(palette, [Frame(bytes(sparse), 100)]) == palette


def test_the_brightest_frame_of_an_animation_sets_the_dimming():
    palette = [(0, 0, 0), (255, 0, 0)]
    dark = Frame(bytes(WIDTH * HEIGHT), 100)
    full = Frame(bytes([1]) * (WIDTH * HEIGHT), 100)
    limited = power_guard.limit_palette(palette, [dark, full])
    assert power_guard.frame_load(limited, full) <= power_guard.LIGHT_BUDGET + 1e-6


def test_white_and_cycling_factory_patterns_are_never_sent():
    assert not power_guard.allowed(codec.frame(1, codec.Cmd.TEST, b"\x04"))
    assert not power_guard.allowed(codec.frame(1, codec.Cmd.TEST, b"\xff"))
    assert power_guard.allowed(codec.frame(1, codec.Cmd.TEST, b"\x00"))
    assert not power_guard.allowed(codec.frame(1, codec.Cmd.BRIGHTNESS, b"\x51"))
    assert power_guard.allowed(codec.frame(1, codec.Cmd.BRIGHTNESS, b"\x50"))
