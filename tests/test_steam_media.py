from steam_cleaner.media import measure_screenshot_paths


def write(path, content=b"image"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_measurement_accepts_only_regular_screenshots_from_steam_userdata(tmp_path):
    home = tmp_path / "home"
    screenshot = write(home / ".local/share/Steam/userdata/1/760/remote/10/screenshots/shot.jpg")
    thumbnail = write(home / ".local/share/Steam/userdata/1/760/remote/10/screenshots/thumbnails/shot.jpg", b"thumb")
    outside = write(tmp_path / "private/save.jpg", b"secret")

    result = measure_screenshot_paths(str(home), [str(screenshot), str(thumbnail), str(outside), "relative.jpg"])

    assert result[str(screenshot)] == 5
    assert result[str(thumbnail)] is None
    assert result[str(outside)] is None
    assert result["relative.jpg"] is None


def test_measurement_never_follows_a_screenshot_symlink(tmp_path):
    home = tmp_path / "home"
    outside = write(tmp_path / "private/save.jpg", b"secret")
    link = home / ".local/share/Steam/userdata/1/760/remote/10/screenshots/link.jpg"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    assert measure_screenshot_paths(str(home), [str(link)]) == {str(link): None}


def test_measurement_is_bounded(tmp_path):
    home = tmp_path / "home"
    paths = [str(write(home / f".local/share/Steam/userdata/1/760/remote/10/screenshots/{index}.jpg")) for index in range(501)]

    result = measure_screenshot_paths(str(home), paths)

    assert len(result) == 500
