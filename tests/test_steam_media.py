import json
import threading

from steam_cleaner import media_diagnostics
from steam_cleaner.media import measure_screenshot_paths
from steam_cleaner.service import SteamCleanerService


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


def test_media_diagnostics_are_bounded_private_and_survive_restart(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings"
    cleaner = SteamCleanerService(str(home), state_dir=settings)
    operation_id = "abcd-1234-abcd-1234-abcd-1234-abcd-1234"
    record = getattr(cleaner, "record_media_event", None)
    assert callable(record)

    assert record("cleanup_started", operation_id, 2, 0, "none", "none") is True
    assert record("cleanup_failed", operation_id, 2, 1, "clips", "steam_api_error") is True
    assert record("cleanup_completed", operation_id, 2, 1, "none", "none") is True

    restored = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]
    assert restored["phase"] == "idle"
    assert restored["interrupted"] is False
    assert restored["events"][-2] == {
        "event": "cleanup_failed", "operation_id": operation_id, "phase": "cleanup",
        "at": restored["events"][-2]["at"], "source": "clips", "reason": "steam_api_error",
        "count": 2, "errors": 1,
    }
    assert restored["events"][-1]["count"] == 2
    assert restored["events"][-1]["errors"] == 1
    assert restored["events"][-1]["deleted"] == 1
    assert str(home) not in json.dumps(restored)


def test_media_diagnostics_reject_unbounded_or_private_values(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cleaner = SteamCleanerService(str(home), state_dir=tmp_path / "settings")
    record = getattr(cleaner, "record_media_event", None)
    assert callable(record)

    assert record("cleanup_failed", "/home/deck/private", 1, 1, "clips", "steam_api_error") is False
    assert record("cleanup_failed", "abcd-1234-abcd-1234-abcd-1234-abcd-1234", 100_001, 1, "clips", "steam_api_error") is False
    assert record("cleanup_failed", "abcd-1234-abcd-1234-abcd-1234-abcd-1234", 1, 2, "clips", "steam_api_error") is False
    assert cleaner.diagnostics()["media"]["events"] == []


def test_media_diagnostics_report_an_interrupted_cleanup_once(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings"
    operation_id = "abcd-1234-abcd-1234-abcd-1234-abcd-1234"
    cleaner = SteamCleanerService(str(home), state_dir=settings)
    record = getattr(cleaner, "record_media_event", None)
    assert callable(record)
    assert record("cleanup_started", operation_id, 1, 0, "none", "none") is True

    first = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]
    second = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]

    assert first["interrupted"] is True
    assert first["events"][-1]["event"] == "interrupted"
    assert sum(event["event"] == "interrupted" for event in second["events"]) == 1


def test_media_diagnostics_treat_a_total_scan_failure_as_finished(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings"
    operation_id = "abcd-1234-abcd-1234-abcd-1234-abcd-1234"
    cleaner = SteamCleanerService(str(home), state_dir=settings)
    cleaner.record_media_event("scan_started", operation_id, 0, 0, "none", "none")
    cleaner.record_media_event("scan_failed", operation_id, 0, 1, "none", "steam_api_error")

    restored = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]

    assert restored["phase"] == "idle"
    assert restored["interrupted"] is False


def test_late_media_event_does_not_close_a_new_operation(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cleaner = SteamCleanerService(str(home), state_dir=tmp_path / "settings")
    first = "1111-1111-1111-1111-1111-1111-1111-1111"
    second = "2222-2222-2222-2222-2222-2222-2222-2222"

    cleaner.record_media_event("scan_started", first)
    cleaner.record_media_event("scan_started", second)
    cleaner.record_media_event("scan_cancelled", first, reason="section_closed")

    current = cleaner.diagnostics()["media"]
    assert current["phase"] == "scan"
    assert current["last_operation_id"] == second


def test_late_media_event_does_not_replace_active_operation_after_restart(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings"
    cleaner = SteamCleanerService(str(home), state_dir=settings)
    first = "1111-1111-1111-1111-1111-1111-1111-1111"
    second = "2222-2222-2222-2222-2222-2222-2222-2222"

    cleaner.record_media_event("scan_started", first)
    cleaner.record_media_event("scan_started", second)
    cleaner.record_media_event("scan_cancelled", first, reason="section_closed")

    restored = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]

    assert restored["phase"] == "idle"
    assert restored["last_operation_id"] == second
    assert restored["events"][-1]["event"] == "interrupted"
    assert restored["events"][-1]["operation_id"] == second


def test_partial_media_scan_failure_keeps_the_operation_active(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    cleaner = SteamCleanerService(str(home), state_dir=tmp_path / "settings")
    operation_id = "abcd-1234-abcd-1234-abcd-1234-abcd-1234"

    cleaner.record_media_event("scan_started", operation_id)
    cleaner.record_media_event("scan_failed", operation_id, 3, 1, "screenshots", "steam_api_error")

    assert cleaner.diagnostics()["media"]["phase"] == "scan"


def test_media_journal_keeps_the_newest_concurrent_event(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    settings = tmp_path / "settings"
    cleaner = SteamCleanerService(str(home), state_dir=settings)
    first = "1111-1111-1111-1111-1111-1111-1111-1111"
    second = "2222-2222-2222-2222-2222-2222-2222-2222"
    first_dump_started = threading.Event()
    second_dump_started = threading.Event()
    original_dump = media_diagnostics.json.dump

    def delayed_dump(document, output, *args, **kwargs):
        if document.get("last_operation_id") == first:
            first_dump_started.set()
            second_dump_started.wait(0.2)
        else:
            second_dump_started.set()
        return original_dump(document, output, *args, **kwargs)

    monkeypatch.setattr(media_diagnostics.json, "dump", delayed_dump)
    first_thread = threading.Thread(target=cleaner.record_media_event, args=("cleanup_started", first))
    second_thread = threading.Thread(target=cleaner.record_media_event, args=("cleanup_started", second))
    first_thread.start()
    assert first_dump_started.wait(1)
    second_thread.start()
    first_thread.join(1)
    second_thread.join(1)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()

    restored = SteamCleanerService(str(home), state_dir=settings).diagnostics()["media"]
    operation_ids = {event["operation_id"] for event in restored["events"]}
    assert {first, second} <= operation_ids
