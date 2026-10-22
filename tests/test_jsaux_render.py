from accessories.jsaux_pixel.render import canvas as cv
from accessories.jsaux_pixel.render import fonts

WHITE = (255, 255, 255)


def test_pixels_outside_the_panel_are_ignored():
    c = cv.Canvas()
    c.px(-1, 0, WHITE)
    c.px(64, 10, WHITE)
    c.px(10, 54, WHITE)
    c.rect(60, 50, 10, 10, WHITE)
    assert c.get(63, 53) == WHITE
    assert c.get(0, 0) == (0, 0, 0)


def test_text_width_matches_measure_and_draws_lit_pixels():
    c = cv.Canvas()
    width = c.text(1, 1, "CPU 42%", fonts.SMALL, WHITE)
    assert width == fonts.measure("CPU 42%", fonts.SMALL)
    lit = sum(1 for y in range(54) for x in range(64) if c.get(x, y) == WHITE)
    assert lit > 30
    assert all(c.get(x, y) == (0, 0, 0) for y in range(54) for x in range(width + 1, 64))


def test_every_font_covers_digits_letters_and_clock_symbols():
    for font in (fonts.TINY, fonts.SMALL):
        for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:%.-/ ":
            assert fonts.measure(ch, font) > 0 or ch == " "
        assert fonts.measure("abc", font) == fonts.measure("ABC", font)


def test_big_clock_fits_the_panel_width():
    assert fonts.measure("23:59", fonts.big(18)) <= 62
    c = cv.Canvas()
    c.text(1, 4, "10:57", fonts.big(18), WHITE)
    assert any(c.get(x, 10) == WHITE for x in range(64))


def test_quantize_shares_one_palette_across_frames_under_256_colours():
    frames = []
    for n in range(3):
        c = cv.Canvas()
        for y in range(54):
            for x in range(64):
                c.px(x, y, ((x * 4 + n) % 256, (y * 5) % 256, (x * y + n * 7) % 256))
        frames.append(c)
    palette, indexed = cv.quantize(frames)
    assert len(palette) <= 255
    assert all(len(ix) == 64 * 54 for ix in indexed)
    r, g, b = palette[indexed[0][10 * 64 + 20]]
    assert abs(r - 80) <= 32 and abs(g - 50) <= 32


def test_quantize_keeps_exact_colours_when_few():
    c = cv.Canvas()
    c.px(1, 1, (12, 34, 56))
    palette, indexed = cv.quantize([c])
    assert palette[indexed[0][1 * 64 + 1]] == (12, 34, 56)
    assert palette[indexed[0][0]] == (0, 0, 0)
