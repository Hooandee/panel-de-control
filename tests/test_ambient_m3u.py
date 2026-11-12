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


def test_a_channel_list_with_an_m3u8_name_is_told_apart_from_an_hls_playlist():
    from ambient.core.m3u import is_channel_list

    assert is_channel_list(PLAYLIST)
    media = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n#EXTINF:6.0,\nseg1.ts\n#EXTINF:6.0,\nseg2.ts\n"
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=2000000\nhigh.m3u8\n"
    single = "#EXTM3U\n#EXTINF:-1,Only one\nhttps://tv.test/one.m3u8\n"
    assert not is_channel_list(media)
    assert not is_channel_list(master)
    assert not is_channel_list(single)
    assert not is_channel_list("<html>not found</html>")
