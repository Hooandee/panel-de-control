"""HHD tdp_enable read/write helper. The value is confirmed by the echoed state."""
from controllers import hhd


def test_read_state_only_requests_english_action_status_when_explicit(monkeypatch):
    paths = []
    monkeypatch.setattr(hhd, "_token", lambda root="/": "token")
    monkeypatch.setattr(
        hhd,
        "_get",
        lambda path, token, timeout=5: paths.append((path, token, timeout)) or {},
    )

    assert hhd.read_state() == {}
    assert hhd.read_state(language="en", timeout=0.5) == {}
    assert paths == [
        ("/state", "token", 5),
        ("/state?lang=en", "token", 0.5),
    ]


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
    assert hhd.set_tdp_enable(False) is False
    assert fake.state["hhd"]["settings"]["tdp_enable"] is False


def test_set_tdp_enable_true(monkeypatch):
    fake = _FakeHHD()
    fake.state["hhd"]["settings"]["tdp_enable"] = False
    monkeypatch.setattr(hhd, "post_state", fake.post_state)
    assert hhd.set_tdp_enable(True) is True
    assert fake.state["hhd"]["settings"]["tdp_enable"] is True


def test_set_tdp_enable_unreachable(monkeypatch):
    monkeypatch.setattr(hhd, "post_state", lambda payload, root="/": None)
    assert hhd.set_tdp_enable(False) is None            # unreachable → unknown
