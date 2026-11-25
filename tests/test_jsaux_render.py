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


def test_plain_text_makes_names_drawable():
    from accessories.jsaux_pixel.render.text import plain_text

    assert plain_text("Pokémon™ Legends: Z-A") == "POKEMON LEGENDS: Z-A"
    assert plain_text("Zürich") == "ZURICH"
    assert plain_text("OLÁ") == "OLA"
    assert plain_text("Ratchet & Clank") == "RATCHET + CLANK"
    assert plain_text("Straße Œuvre Ø  \u4e2d") == "STRASSE OEUVRE O"
    assert plain_text("Hello, World®") == "HELLO. WORLD"


def test_fit_cuts_at_a_space_then_at_chars_and_adds_a_dot():
    from accessories.jsaux_pixel.render.text import fit

    assert fit("SHORT", fonts.SMALL, 62) == "SHORT"
    cut = fit("RATCHET AND CLANK RIFT APART", fonts.SMALL, 62)
    assert cut.endswith(".") and fonts.measure(cut, fonts.SMALL) <= 62
    assert cut == "RATCHET."
    chars = fit("SUPERCALIFRAGILISTIC", fonts.TINY, 40)
    assert chars.endswith(".") and fonts.measure(chars, fonts.TINY) <= 40


def test_big_minus_lights_pixels_at_mid_height_and_measures_wider_than_nothing():
    glyph = fonts.big(14).glyph("-")
    lit_rows = [y for y, row in enumerate(glyph) if "#" in row]
    assert lit_rows and all(abs(y - 6.5) <= 1.5 for y in lit_rows)
    c = cv.Canvas()
    c.text(1, 1, "-5", fonts.big(14), WHITE)
    assert any(c.get(x, 7) == WHITE for x in range(1, 7))
    assert fonts.measure("--", fonts.big(14)) > fonts.measure("", fonts.big(14))
