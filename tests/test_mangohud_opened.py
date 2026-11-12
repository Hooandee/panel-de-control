import sys

import pytest

import struct

from mangohud.opened import OpenWatch, contains_open


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="inotify is Linux only")
def test_open_watch_sees_a_reader_open_the_file(tmp_path):
    target = tmp_path / "presets.conf"
    target.write_text("[preset 1]\n")

    with OpenWatch(str(target)) as watch:
        assert watch.available
        assert watch.opened(0.05) is False
        target.read_text()
        assert watch.opened(0.5) is True


def test_open_watch_without_inotify_is_unknown(tmp_path):
    with OpenWatch(str(tmp_path / "presets.conf"), libc_loader=lambda: None) as watch:
        assert not watch.available
        assert watch.opened(0.01) is None


def test_only_open_events_count_as_a_reload():
    ignored = struct.pack("iIII", 1, 0x8000, 0, 0)
    overflow = struct.pack("iIII", -1, 0x4000, 0, 0)
    opened = struct.pack("iIII", 1, 0x20, 0, 16) + b"presets.conf\0\0\0\0"

    assert contains_open(ignored + overflow) is False
    assert contains_open(ignored + opened) is True
    assert contains_open(b"") is False
