import wave

from audio.tone import loop_samples, write_wav


def test_loop_length_and_range():
    s = loop_samples(rate=8000)
    assert len(s) == int(8000 * 0.42 * 8)
    assert all(-1.0 <= x <= 1.0 for x in s)


def test_loop_not_silent():
    assert any(abs(x) > 0.1 for x in loop_samples(rate=8000))


def test_loop_deterministic():
    assert loop_samples(rate=8000) == loop_samples(rate=8000)


def test_write_wav_is_readable_stereo(tmp_path):
    path = str(tmp_path / "t.wav")
    write_wav(path, loop_samples(rate=8000), rate=8000)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 8000
