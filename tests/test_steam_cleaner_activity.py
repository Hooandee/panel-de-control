import os

from steam_cleaner.activity import process_activity


def process(root, pid, command, environment):
    path = root / str(pid)
    path.mkdir(parents=True)
    (path / "environ").write_bytes(environment)
    (path / "comm").write_text(command)
    return path


def test_steam_open_is_not_a_global_game_block(tmp_path):
    root = tmp_path / "proc"
    process(root, 1, "steam", b"USER=private\0")
    process(root, 2, "steamwebhelper", b"USER=private\0")
    result = process_activity(tmp_path, str(root))
    assert result == {"complete": True, "appids": [], "paths": []}


def test_backend_observes_native_and_shortcut_activity(tmp_path):
    root = tmp_path / "proc"
    process(root, 1, "game", b"SteamAppId=10\0SteamGameId=10\0")
    encoded = (3_000_000_001 << 32) | 0x02000000
    process(root, 2, "wine64", f"SteamGameId={encoded}\0STEAM_COMPAT_DATA_PATH=/library/steamapps/compatdata/3000000001\0".encode())
    result = process_activity(tmp_path, str(root))
    assert result["complete"] is True
    assert result["appids"] == ["10", "3000000001"]
    assert result["paths"] == ["/library/steamapps/compatdata/3000000001"]


def test_unidentified_wine_and_missing_proc_fail_closed(tmp_path):
    assert process_activity(tmp_path, str(tmp_path / "missing"))["complete"] is False
    root = tmp_path / "proc"
    process(root, 1, "wineserver", b"USER=private\0")
    assert process_activity(tmp_path, str(root))["complete"] is False


def test_open_cache_file_detected_even_without_steam_environment(tmp_path):
    root = tmp_path / "proc"
    target = tmp_path / "cache/10"
    target.mkdir(parents=True)
    opened = target / "shader"
    opened.write_text("cache")
    running = process(root, 1, "unidentified", b"USER=private\0")
    (running / "fd").mkdir()
    (running / "fd/8").symlink_to(opened)
    (running / "cwd").symlink_to(tmp_path)
    result = process_activity(tmp_path, str(root), data_roots=[str(target)])
    assert str(opened) in result["paths"]


def test_unreadable_live_process_cannot_be_declared_idle(tmp_path, monkeypatch):
    root = tmp_path / "proc"
    process(root, 1, "game", b"SteamAppId=10\0")
    original = os.stat

    def denied(path, *args, **kwargs):
        if str(path).endswith("/proc/1"):
            raise PermissionError()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", denied)
    assert process_activity(tmp_path, str(root))["complete"] is False
