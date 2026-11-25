import io
import json
import urllib.error

import theme_hltb
from theme_hltb import HltbLookup, best_match, normalise


def entry(name, main=36000, plus=72000, full=108000, game_id=1, alias=""):
    return {"game_name": name, "game_alias": alias, "comp_main": main, "comp_plus": plus, "comp_100": full, "game_id": game_id}


class FakeSite:
    """howlongtobeat.com: a token from init, results for whoever presents it."""

    def __init__(self, results=None, fail=None):
        self.results = results or []
        self.fail = fail
        self.tokens = 0
        self.searches = []
        self.refuse_next = False

    def __call__(self, url, body, headers):
        if self.fail:
            raise self.fail
        if "/init" in url:
            self.tokens += 1
            return json.dumps({"token": f"t{self.tokens}"}).encode()
        if self.refuse_next:
            self.refuse_next = False
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(b""))
        assert headers["x-auth-token"] == f"t{self.tokens}"
        self.searches.append(json.loads(body))
        return json.dumps({"data": self.results}).encode()


def test_normalise_drops_marks_editions_and_punctuation():
    assert normalise("Sekiro™: Shadows Die Twice - GOTY Edition") == "sekiro shadows die twice"
    assert normalise("The Witcher 3: Wild Hunt — Remastered") == "the witcher 3 wild hunt"
    assert normalise("Baldur's Gate 3") == "baldur s gate 3"


def test_best_match_prefers_the_same_name_and_rejects_strangers():
    results = [entry("Hollow Knight: Silksong", game_id=2), entry("Hollow Knight", game_id=1)]
    assert best_match("Hollow Knight", results)["game_id"] == 1
    assert best_match("The Witcher 3: Wild Hunt — Remastered", [entry("The Witcher 3: Wild Hunt", game_id=3)])["game_id"] == 3
    assert best_match("Celeste", [entry("Stardew Valley")]) is None


def test_lookup_answers_in_hours_and_keeps_the_answer(tmp_path):
    site = FakeSite([entry("Hollow Knight", main=97154, plus=149877, full=236214, game_id=26286)])
    hltb = HltbLookup(str(tmp_path / "cache.json"), fetch=site, clock=lambda: 1000.0)
    answer = hltb.lookup("367520", "Hollow Knight")
    assert answer == {"result": "found", "main": 27.0, "plus": 41.6, "complete": 65.6, "title": "Hollow Knight", "id": 26286}
    assert site.searches[0]["searchTerms"] == ["hollow", "knight"]
    again = HltbLookup(str(tmp_path / "cache.json"), fetch=FakeSite(fail=OSError("offline")), clock=lambda: 2000.0)
    assert again.lookup(367520, "Hollow Knight") == answer


def test_a_miss_is_kept_for_days_and_a_network_failure_never(tmp_path):
    clock = [0.0]
    site = FakeSite([entry("Something Else")])
    hltb = HltbLookup(str(tmp_path / "cache.json"), fetch=site, clock=lambda: clock[0])
    assert hltb.lookup("1", "Celeste") == {"result": "not_found"}
    assert hltb.lookup("1", "Celeste") == {"result": "not_found"}
    assert len(site.searches) == 1
    clock[0] = theme_hltb.MISSING_TTL_S + 1
    hltb.lookup("1", "Celeste")
    assert len(site.searches) == 2

    down = HltbLookup(str(tmp_path / "other.json"), fetch=FakeSite(fail=OSError("offline")))
    assert down.lookup("2", "Portal 2")["result"] == "unavailable"
    assert not (tmp_path / "other.json").exists()


def test_a_refused_token_is_renewed_once(tmp_path):
    site = FakeSite([entry("Portal 2")])
    hltb = HltbLookup(str(tmp_path / "cache.json"), fetch=site)
    hltb.lookup("620", "Portal 2")
    site.refuse_next = True
    assert hltb.lookup("400", "Portal 2")["result"] == "found"
    assert site.tokens == 2


def test_a_renamed_game_is_looked_up_again(tmp_path):
    site = FakeSite([entry("Portal 2")])
    hltb = HltbLookup(str(tmp_path / "cache.json"), fetch=site)
    hltb.lookup("620", "Portal 2")
    site.results = [entry("Portal")]
    assert hltb.lookup("620", "Portal")["title"] == "Portal"


def test_rejects_bad_input_without_asking_the_site(tmp_path):
    site = FakeSite()
    hltb = HltbLookup(str(tmp_path / "cache.json"), fetch=site)
    assert hltb.lookup("../x", "Portal")["result"] == "invalid"
    assert hltb.lookup("620", "  ")["result"] == "invalid"
    assert site.tokens == 0
