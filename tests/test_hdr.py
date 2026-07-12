from display.hdr import HdrBackend


class _Runner:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return (0 if self.ok else 1, "")


def test_backend_toggles_hdr():
    r = _Runner()
    b = HdrBackend(r)
    assert b.set_enabled(True) is True
    assert r.calls[-1] == ["hdr_enabled", "1"]
    b.set_enabled(False)
    assert r.calls[-1] == ["hdr_enabled", "0"]


def test_backend_reports_failure():
    assert HdrBackend(_Runner(ok=False)).set_enabled(True) is False
