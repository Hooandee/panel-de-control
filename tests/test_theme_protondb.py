import io
import json
import urllib.error

from theme_protondb import MISSING_TTL_S, ProtonDbLookup


def site(answers):
    calls = []

    def fetch(url):
        calls.append(url)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    fetch.calls = calls
    return fetch


def not_found(url="u"):
    return urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))


def test_reads_the_tier_and_keeps_it(tmp_path):
    fetch = site([{"tier": "platinum", "confidence": "strong", "total": 1886, "score": 0.87}])
    lookup = ProtonDbLookup(str(tmp_path / "c.json"), fetch=fetch, clock=lambda: 10.0)
    answer = lookup.lookup(292030)
    assert answer == {"result": "found", "tier": "platinum", "confidence": "strong", "total": 1886}
    assert fetch.calls == ["https://www.protondb.com/api/v1/reports/summaries/292030.json"]
    again = ProtonDbLookup(str(tmp_path / "c.json"), fetch=site([OSError("offline")]), clock=lambda: 20.0)
    assert again.lookup("292030") == answer


def test_a_game_nobody_reported_is_a_kept_miss_and_a_failure_is_not(tmp_path):
    clock = [0.0]
    fetch = site([not_found(), {"tier": "gold"}])
    lookup = ProtonDbLookup(str(tmp_path / "c.json"), fetch=fetch, clock=lambda: clock[0])
    assert lookup.lookup("1")["result"] == "not_found"
    assert lookup.lookup("1")["result"] == "not_found"
    clock[0] = MISSING_TTL_S + 1
    assert lookup.lookup("1")["tier"] == "gold"
    down = ProtonDbLookup(str(tmp_path / "d.json"), fetch=site([OSError("offline")]))
    assert down.lookup("2")["result"] == "unavailable"
    assert not (tmp_path / "d.json").exists()


def test_pending_or_unknown_tiers_are_misses_and_shortcuts_are_refused(tmp_path):
    lookup = ProtonDbLookup(str(tmp_path / "c.json"), fetch=site([{"tier": "pending"}]))
    assert lookup.lookup("3")["result"] == "not_found"
    assert lookup.lookup("12884901888000000000")["result"] == "invalid"
    assert lookup.lookup("../x")["result"] == "invalid"
