import wave

from audio.tone import pink_samples, write_wav


def test_pink_samples_count_and_range():
    s = pink_samples(2000, seed=1)
    assert len(s) == 2000
    assert all(-1.0 <= x <= 1.0 for x in s)


def test_pink_samples_deterministic():
    assert pink_samples(500, seed=7) == pink_samples(500, seed=7)


def test_pink_samples_not_silent():
    assert any(abs(x) > 0.01 for x in pink_samples(1000, seed=1))


def test_write_wav_is_readable_stereo(tmp_path):
    path = str(tmp_path / "t.wav")
    write_wav(path, pink_samples(4800, seed=1), rate=48000)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 48000
        assert w.getnframes() == 4800
