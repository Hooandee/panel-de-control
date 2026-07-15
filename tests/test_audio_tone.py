import wave

from audio.tone import arpeggio_samples, write_wav


def test_arpeggio_length_and_range():
    s = arpeggio_samples(rate=8000, seconds=1.0)
    assert len(s) == 8000
    assert all(-1.0 <= x <= 1.0 for x in s)


def test_arpeggio_not_silent():
    assert any(abs(x) > 0.1 for x in arpeggio_samples(rate=8000, seconds=1.0))


def test_arpeggio_deterministic():
    assert arpeggio_samples(rate=8000, seconds=1.0) == arpeggio_samples(rate=8000, seconds=1.0)


def test_write_wav_is_readable_stereo(tmp_path):
    path = str(tmp_path / "t.wav")
    write_wav(path, arpeggio_samples(rate=8000, seconds=1.0), rate=8000)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 2
        assert w.getframerate() == 8000
        assert w.getnframes() == 8000
