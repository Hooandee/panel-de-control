import wave

from audio.tone import render, sample_ids, write_wav


def test_loop_length_and_range():
    s = render("full", rate=8000)
    assert abs(len(s) / 8000 - 4.0) < 0.1  # a ~4 s loop
    assert all(-1.0 <= x <= 1.0 for x in s)


def test_loop_edges_are_faded_for_a_seamless_join():
    s = render("full", rate=8000)
    assert abs(s[0]) < 0.05 and abs(s[-1]) < 0.05  # edges fade to near-silence


def test_loop_not_silent():
    assert any(abs(x) > 0.1 for x in render("full", rate=8000))


def test_loop_deterministic():
    assert render("full", rate=8000) == render("full", rate=8000)


def test_write_wav_is_readable_stereo(tmp_path):
    path = str(tmp_path / "t.wav")
    write_wav(path, render("full", rate=8000), rate=8000)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 8000


def test_sample_ids_are_the_four_focuses():
    assert sample_ids() == ["bass", "voice", "treble", "full"]


def test_every_sample_renders_audible_and_bounded():
    for sid in sample_ids():
        s = render(sid, rate=8000)
        assert len(s) > 0
        assert all(-1.0 <= x <= 1.0 for x in s)
        assert any(abs(x) > 0.1 for x in s)  # not silent


def test_unknown_sample_falls_back_to_full():
    assert render("nope", rate=8000) == render("full", rate=8000)


def test_bass_has_more_low_energy_than_treble():
    # crude spectral check: consecutive-sample differences are small for a low-frequency
    # signal and large for a high-frequency one, so the mean |Δ| ranks treble above bass.
    def roughness(s):
        return sum(abs(s[i] - s[i - 1]) for i in range(1, len(s))) / len(s)
    assert roughness(render("treble", rate=8000)) > roughness(render("bass", rate=8000))
