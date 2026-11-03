import io
import json
import urllib.error

from upscalers import wiki

TABLE = """| Game | Compatibility | Upscaler <br>Inputs | OptiPatcher <br>Support | Notes | Images |
| ---- | :-----------: | :-----------------: | :---: | ----- | :----: |
| [Stellar Blade](Stellar-Blade) | ✅ | DLSS, FSR3.1 |  | Launch with -dx12 and use OptiScaler as `winmm.dll`. | |
| Some Racer | ❌ | FSR2 |  | EAC blocks it | |
| Quiet Game | ✅ | DLSS | ✨ |  | |
"""


class Response(io.BytesIO):
    def __init__(self, body, etag='"v1"'):
        super().__init__(body)
        self.headers = {"ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_rows_are_matched_by_name_ignoring_marks_and_demo():
    rows = wiki.parse(TABLE)
    cache = wiki.WikiCache.__new__(wiki.WikiCache)
    cache._rows = rows
    assert cache.lookup("Stellar Blade™ Demo") == {"args": ["-dx12"], "proxy": "winmm.dll"}
    assert cache.lookup(None, "Some Racer") == {"status": "broken"}
    assert cache.lookup("Unknown") is None


def test_refresh_downloads_once_then_keeps_the_copy_when_offline(tmp_path):
    cache = wiki.WikiCache(tmp_path)
    clock = [1000.0]
    assert cache.refresh(fetch=lambda *a, **k: Response(TABLE.encode()), now=lambda: clock[0]) == {"updated": True, "fresh": True}
    assert cache.refresh(fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("too soon")), now=lambda: clock[0]) == {
        "updated": False, "fresh": True}
    clock[0] += wiki.MAX_AGE_S + 1

    def offline(*a, **k):
        raise OSError("no network")

    assert cache.refresh(fetch=offline, now=lambda: clock[0]) == {"updated": False, "fresh": False}
    assert wiki.WikiCache(tmp_path).lookup("Stellar Blade") is not None

    def unchanged(request, **k):
        assert request.get_header("If-none-match") == '"v1"'
        raise urllib.error.HTTPError(request.full_url, 304, "Not Modified", {}, None)

    assert cache.refresh(fetch=unchanged, now=lambda: clock[0]) == {"updated": False, "fresh": True}
    assert json.loads((tmp_path / "optiscaler-wiki.json").read_text())["fetched_at"] == clock[0]
