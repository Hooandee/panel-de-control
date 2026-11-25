from ambient.adapters.game_media import pick_album, pick_trailer, pick_track


def _albums(*names):
    return {"results": [{"collectionId": i + 1, "collectionName": n} for i, n in enumerate(names)]}


def test_official_soundtrack_beats_covers_sequels_and_dlc():
    assert pick_album(_albums("Hades - Single", "Hades II (Original Soundtrack)", "Hades: Original Soundtrack"), "Hades") == 3
    assert pick_album(_albums("Elden Ring Shadow of the Erdtree (Original Soundtrack)", "Elden Ring (Main Theme) [Metal Version]"), "ELDEN RING") is None
    assert pick_album(_albums("Portal 2: Songs to Test By (Original Soundtrack)"), "Portal") is None
    assert pick_album(_albums("Celeste (Original Soundtrack) Vol. 2"), "Celeste") == 1
    assert pick_album(_albums("Hollow Knight (Piano Collections, Vol. 1) - EP"), "Hollow Knight") is None


def test_trailer_prefers_the_highlight_and_only_steam_video():
    details = {"10": {"success": True, "data": {"movies": [
        {"name": "b", "hls_h264": "https://video.akamai.steamstatic.com/b.m3u8"},
        {"name": "a", "highlight": True, "hls_h264": "https://video.akamai.steamstatic.com/a.m3u8", "thumbnail": "t"},
        {"name": "x", "highlight": True, "hls_h264": "https://evil.test/x.m3u8"},
    ]}}}
    assert pick_trailer(details, "10") == {"url": "https://video.akamai.steamstatic.com/a.m3u8", "poster": "t", "title": "a"}
    assert pick_trailer({"10": {"success": False}}, "10") is None


def test_track_needs_an_https_preview():
    lookup = {"results": [{"wrapperType": "collection"}, {"wrapperType": "track", "previewUrl": "http://x"}, {"wrapperType": "track", "previewUrl": "https://a.test/p.m4a", "trackName": "Main", "artistName": "Me"}]}
    assert pick_track(lookup) == {"url": "https://a.test/p.m4a", "title": "Main", "artist": "Me"}
