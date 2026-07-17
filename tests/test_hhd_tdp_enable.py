"""HHD tdp_enable read/write helper — the cooperative handshake that hands the
power rails between HHD and us. The value is confirmed by the echoed state
(never a fabricated success)."""
from controllers import hhd


class _FakeHHD:
    def __init__(self):
        self.state = {"hhd": {"settings": {"tdp_enable": True}}}

    def read_state(self, root="/"):
        return self.state

    def post_state(self, payload, root="/"):
        self.state["hhd"]["settings"]["tdp_enable"] = (
            payload["hhd"]["settings"]["tdp_enable"]
        )
        return self.state


def test_current_tdp_enable_reads_bool(monkeypatch):
    fake = _FakeHHD()
    monkeypatch.setattr(hhd, "read_state", fake.read_state)
    assert hhd.current_tdp_enable() is True


def test_current_tdp_enable_unreachable(monkeypatch):
    monkeypatch.setattr(hhd, "read_state", lambda root="/": None)
    assert hhd.current_tdp_enable() is None


def test_set_tdp_enable_false(monkeypatch):
    fake = _FakeHHD()
    monkeypatch.setattr(hhd, "read_state", fake.read_state)
    monkeypatch.setattr(hhd, "post_state", fake.post_state)
    assert hhd.set_tdp_enable(False) is False          # echoed value
    assert fake.state["hhd"]["settings"]["tdp_enable"] is False


def test_set_tdp_enable_true(monkeypatch):
    fake = _FakeHHD()
    fake.state["hhd"]["settings"]["tdp_enable"] = False
    monkeypatch.setattr(hhd, "post_state", fake.post_state)
    assert hhd.set_tdp_enable(True) is True
    assert fake.state["hhd"]["settings"]["tdp_enable"] is True


def test_set_tdp_enable_unreachable(monkeypatch):
    monkeypatch.setattr(hhd, "post_state", lambda payload, root="/": None)
    assert hhd.set_tdp_enable(False) is None            # honest: unknown
