from ambient.core.m3u import MAX_CHANNELS, parse_m3u

PLAYLIST = """﻿#EXTM3U x-tvg-url="https://epg.test/guide.xml"
#EXTINF:-1 tvg-id="la1" tvg-logo="https://logo.test/la1.png" group-title="Generalistas",La 1
https://tv.test/la1/main.m3u8
#EXTINF:-1 tvg-name="Radio Test" tvg-logo="http://insecure.test/logo.png",
#EXTGRP:Radios
https://radio.test/stream.mp3
#EXTINF:-1,Local file
/home/deck/video.mp4
#EXTINF:-1 group-title="Generalistas",La 1 again
https://tv.test/la1/main.m3u8
https://tv.test/bare/channel.m3u8
"""


def test_reads_names_logos_groups_and_urls():
    channels = parse_m3u(PLAYLIST)
    assert [c["name"] for c in channels] == ["La 1", "Radio Test", "channel.m3u8"]
    assert channels[0] == {
        "id": channels[0]["id"],
        "name": "La 1",
        "url": "https://tv.test/la1/main.m3u8",
        "logo": "https://logo.test/la1.png",
        "group": "Generalistas",
    }
    assert channels[1]["logo"] == ""
    assert channels[1]["group"] == "Radios"
    assert channels[0]["id"].startswith("ch.") and len({c["id"] for c in channels}) == 3


def test_ignores_non_http_entries_and_caps_size():
    text = "#EXTM3U\n" + "".join(f"#EXTINF:-1,C{i}\nhttps://s.test/{i}\n" for i in range(MAX_CHANNELS + 5))
    assert len(parse_m3u(text)) == MAX_CHANNELS
    assert parse_m3u("file:///etc/passwd\nrtmp://x/y\n") == []
