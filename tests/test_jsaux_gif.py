import pytest

from accessories.jsaux_pixel import gif
from accessories.jsaux_pixel.codec import HEIGHT, WIDTH
from gif_decode import decode

PALETTE = [(0, 0, 0), (255, 0, 0), (0, 255, 0)]


def _frame(fill=0, dots=(), delay=100):
    pixels = bytearray([fill] * (WIDTH * HEIGHT))
    for x, y, value in dots:
        pixels[y * WIDTH + x] = value
    return gif.Frame(bytes(pixels), delay)


def test_single_frame_round_trips():
    frame = _frame(dots=[(0, 0, 1), (63, 53, 2), (10, 20, 1)])
    decoded = decode(gif.encode([frame], PALETTE))
    assert (decoded["width"], decoded["height"]) == (64, 54)
    assert decoded["palette"][:3] == PALETTE
    assert decoded["frames"] == [(frame.pixels, 100)]


def test_animation_round_trips_with_delays_and_infinite_loop():
    frames = [_frame(dots=[(i, i, 1 + i % 2)], delay=6000) for i in range(30)]
    decoded = decode(gif.encode(frames, PALETTE))
    assert decoded["loop"] == 0
    assert [d for _, d in decoded["frames"]] == [6000] * 30
    for want, (got, _) in zip(frames, decoded["frames"]):
        assert got == want.pixels


def test_small_change_frames_cost_far_less_than_full_frames():
    noisy = [_frame(dots=[(x, y, 1 + (x * y + i) % 2) for x in range(0, 64, 3) for y in range(0, 54, 3)]) for i in range(2)]
    base = noisy[0].pixels
    tweak = bytearray(base)
    tweak[5] = 2 if tweak[5] != 2 else 1
    full = len(gif.encode([noisy[0], noisy[1]], PALETTE))
    delta = len(gif.encode([noisy[0], gif.Frame(bytes(tweak), 100)], PALETTE))
    assert delta < full - 50


def test_identical_consecutive_frames_merge_their_delay():
    frame = _frame(dots=[(3, 3, 1)])
    decoded = decode(gif.encode([frame, gif.Frame(frame.pixels, 250)], PALETTE))
    assert decoded["frames"] == [(frame.pixels, 350)]


def test_delays_beyond_gif_limit_are_split():
    decoded = decode(gif.encode([_frame(delay=100_000)], PALETTE))
    assert sum(d for _, d in decoded["frames"]) == 100_000
    assert all(d <= 65535 for _, d in decoded["frames"])


def test_rejects_palettes_over_256_colours_and_wrong_sizes():
    with pytest.raises(ValueError):
        gif.encode([_frame()], [(i, i, i) for i in range(257)])
    with pytest.raises(ValueError):
        gif.encode([gif.Frame(b"\0" * 10, 1)], PALETTE)
    with pytest.raises(ValueError):
        gif.encode([], PALETTE)
