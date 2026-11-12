import sys

import pytest

from mangohud.opened import OpenWatch


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
