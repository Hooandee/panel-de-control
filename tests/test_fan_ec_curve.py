"""Tests for the MSI Claw firmware fan-curve reader (read-only EC parse).

The MSI Claw's msi_wmi_platform driver is read-only RPM on the current kernel
(no writable pwm), but the firmware's active fan curve IS legible in the EC.
These tests cover the pure parser and the reader's caching + honest-degradation
contract. No hardware is touched (byte source is injectable).
"""

from fans.ec_curve import CPU_PCT_OFFSET, CPU_TEMP_OFFSET, EcFanCurveReader, parse_curve

# Example Claw EC layout: 6-point CPU curve, temps @ 0x6A, duty% @ 0x73.
#   temps: 32 3c 46 50 58 58  = 50 60 70 80 88 88 °C
#   pcts:  28 31 3a 43 4b 4b  = 40 49 58 67 75 75 %
SAMPLE_TEMPS = [0x32, 0x3C, 0x46, 0x50, 0x58, 0x58]
SAMPLE_PCTS = [0x28, 0x31, 0x3A, 0x43, 0x4B, 0x4B]
EXPECTED_CURVE = [(50, 40), (60, 49), (70, 58), (80, 67), (88, 75), (88, 75)]


def _dump(temps=SAMPLE_TEMPS, pcts=SAMPLE_PCTS, size=256) -> bytes:
    buf = bytearray(size)
    buf[CPU_TEMP_OFFSET:CPU_TEMP_OFFSET + len(temps)] = bytes(temps)
    buf[CPU_PCT_OFFSET:CPU_PCT_OFFSET + len(pcts)] = bytes(pcts)
    return bytes(buf)


class TestParseCurve:
    def test_parses_sample_dump(self):
        assert parse_curve(_dump()) == EXPECTED_CURVE

    def test_offsets_are_the_known_ec_positions(self):
        assert CPU_TEMP_OFFSET == 0x6A
        assert CPU_PCT_OFFSET == 0x73

    def test_short_buffer_returns_none(self):
        assert parse_curve(bytes(0x50)) is None

    def test_empty_returns_none(self):
        assert parse_curve(b"") is None

    def test_none_returns_none(self):
        assert parse_curve(None) is None

    def test_decreasing_temps_returns_none(self):
        assert parse_curve(_dump(temps=[0x50, 0x46, 0x3C, 0x32, 0x28, 0x1E])) is None

    def test_temp_out_of_range_returns_none(self):
        # 0xF0 = 240 °C — implausible sensor value.
        assert parse_curve(_dump(temps=[0x32, 0x3C, 0x46, 0x50, 0x58, 0xF0])) is None

    def test_percent_over_100_returns_none(self):
        assert parse_curve(_dump(pcts=[0x28, 0x31, 0x3A, 0x43, 0x4B, 0x65])) is None  # 0x65 = 101

    def test_all_zero_returns_none(self):
        # A blank/failed EC read is not a plausible curve.
        assert parse_curve(bytes(256)) is None

    def test_zero_temps_nonzero_pcts_returns_none(self):
        # A misaligned read (temp region zeroed, pct region garbage) isn't a curve.
        assert parse_curve(_dump(temps=[0, 0, 0, 0, 0, 0], pcts=[40, 49, 58, 67, 75, 75])) is None

    def test_non_monotonic_pcts_returns_none(self):
        # Duty must rise with temp; a jagged pct sequence is implausible.
        assert parse_curve(_dump(pcts=[40, 10, 80, 5, 75, 75])) is None

    def test_flat_nonzero_curve_is_valid(self):
        data = _dump(temps=[40, 50, 60, 70, 80, 88], pcts=[30, 30, 30, 30, 30, 30])
        assert parse_curve(data) == [(40, 30), (50, 30), (60, 30), (70, 30), (80, 30), (88, 30)]


class TestEcFanCurveReader:
    def test_reads_and_parses_via_injected_source(self):
        r = EcFanCurveReader(read_bytes=lambda: _dump())
        assert r.read_curve() == EXPECTED_CURVE

    def test_caches_after_first_read(self):
        calls = {"n": 0}

        def src():
            calls["n"] += 1
            return _dump()

        r = EcFanCurveReader(read_bytes=src)
        assert r.read_curve() == EXPECTED_CURVE
        assert r.read_curve() == EXPECTED_CURVE
        assert calls["n"] == 1  # cached — the firmware curve is static

    def test_none_source_degrades_to_none(self):
        r = EcFanCurveReader(read_bytes=lambda: None)
        assert r.read_curve() is None

    def test_raising_source_degrades_to_none(self):
        def boom():
            raise OSError("no debugfs")

        assert EcFanCurveReader(read_bytes=boom).read_curve() is None

    def test_implausible_bytes_degrade_to_none(self):
        r = EcFanCurveReader(read_bytes=lambda: bytes(256))
        assert r.read_curve() is None

    def test_none_result_is_not_cached_as_success(self):
        # A transient failure should be retried, not latched as "no curve".
        seq = [None, _dump()]

        def src():
            return seq.pop(0)

        r = EcFanCurveReader(read_bytes=src)
        assert r.read_curve() is None
        assert r.read_curve() == EXPECTED_CURVE
