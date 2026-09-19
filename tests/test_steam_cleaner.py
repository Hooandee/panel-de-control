import json
import os
import struct
import threading

import pytest

from steam_cleaner import SteamCleanerError, SteamCleanerService


def write(path, content=b"data"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    return path


def make_steam(tmp_path):
    home = tmp_path / "home"
    steam = home / ".local/share/Steam"
    (steam / "steamapps").mkdir(parents=True)
    write(steam / "steamapps/libraryfolders.vdf", '"libraryfolders" { "0" { "path" "' + str(steam) + '" } }')
    return home, steam


def idle():
    return {"complete": True, "appids": [], "paths": []}


def service(home, **kwargs):
    return SteamCleanerService(str(home), activity_provider=kwargs.pop("activity_provider", idle), **kwargs)


def data(steam, kind="shadercache", appid="10"):
    return write(steam / "steamapps" / kind / appid / "data.bin")


def manifest(steam, appid="10", name="Example", install_dir="Example"):
    return write(steam / "steamapps" / f"appmanifest_{appid}.acf", f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{install_dir}" }}')


def prepare_all(cleaner):
    state = cleaner.inventory()
    return cleaner.prepare(state["scan_id"], [entry["id"] for entry in state["entries"]])


def test_empty_home_is_honestly_unavailable(tmp_path):
    cleaner = service(tmp_path)
    assert cleaner.get_state()["status"] == "idle"
    state = cleaner.inventory()
    assert state["available"] is False
    assert state["entries"] == []
    assert state["coverage_complete"] is False


def test_flatpak_only_home_is_outside_native_steam_scope(tmp_path):
    payload = data(tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
    cleaner = service(tmp_path)
    state = cleaner.inventory()
    assert state["available"] is False
    assert state["entries"] == []
    assert payload.read_bytes() == b"data"


def test_unexpected_scan_failure_leaves_recoverable_state_and_safe_diagnostic(tmp_path, monkeypatch):
    home, _ = make_steam(tmp_path)
    cleaner = service(home)
    discover = cleaner._discover

    def fail():
        raise RuntimeError("private user data must not reach the report")

    monkeypatch.setattr(cleaner, "_discover", fail)
    with pytest.raises(SteamCleanerError, match="^internal_error$"):
        cleaner.inventory()
    assert cleaner.get_state()["status"] == "error"
    diagnostic = cleaner.diagnostics()
    assert diagnostic["phase"] == "idle"
    assert diagnostic["events"][-1]["reason"] == "internal_error"
    assert "private user data" not in json.dumps(diagnostic)
    monkeypatch.setattr(cleaner, "_discover", discover)
    assert cleaner.inventory()["status"] == "ready"


@pytest.mark.parametrize("modern", [True, False])
def test_cross_library_installation_and_numeric_unknowns_remain_visible(tmp_path, modern):
    home, steam = make_steam(tmp_path)
    sd = tmp_path / "card"
    manifest(sd)
    data(steam, "compatdata")
    data(sd, appid="99")
    entry = f'"1" {{ "path" "{sd}" }}' if modern else f'"1" "{sd}"'
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ {entry} }}')
    state = service(home).inventory()
    installed = next(e for e in state["entries"] if e["appid"] == "10")
    unknown = next(e for e in state["entries"] if e["appid"] == "99")
    assert installed["name"] == "Example"
    assert installed["installation"] == "installed"
    assert unknown["name"] is None
    assert unknown["installation"] == "not_installed"
    assert len(state["libraries"]) == 2


def test_missing_library_prevents_orphan_claims(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "1" {{ "path" "{tmp_path / "absent"}" }} }}')
    state = service(home).inventory()
    assert state["coverage_complete"] is False
    assert state["entries"][0]["installation"] == "unknown"


def test_malformed_library_index_remains_read_only(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    write(steam / "steamapps/libraryfolders.vdf", '"libraryfolders" { "1"')
    state = service(home).inventory()
    assert state["coverage_complete"] is False
    assert state["entries"][0]["blocked_reason"] == "coverage_incomplete"


def test_all_shortcut_profiles_are_read_without_inventing_high_appids(tmp_path):
    home, steam = make_steam(tmp_path)
    for user, appid, name in [("1", 3_000_000_001, "First"), ("2", 3_000_000_002, "Second")]:
        blob = b"\x00shortcuts\x00\x000\x00\x02appid\x00" + struct.pack("<I", appid) + b"\x01appname\x00" + name.encode() + b"\x00\x08\x08\x08"
        write(steam / "userdata" / user / "config/shortcuts.vdf", blob)
        data(steam, "compatdata", str(appid))
    data(steam, "compatdata", "3999999999")
    entries = service(home).inventory()["entries"]
    assert {e["name"] for e in entries if e["installation"] == "non_steam"} == {"First", "Second"}
    assert next(e for e in entries if e["appid"] == "3999999999")["installation"] == "unknown"


@pytest.mark.parametrize("names", [("First", "Second"), ("First", "Second", "")])
def test_conflicting_shortcuts_remain_unknown_and_protected(tmp_path, names):
    home, steam = make_steam(tmp_path)
    appid = 3_000_000_001
    target = data(steam, "compatdata", str(appid))
    for profile, name in enumerate(names, 1):
        blob = b"\x00shortcuts\x00\x000\x00\x02appid\x00" + struct.pack("<I", appid) + b"\x01appname\x00" + name.encode() + b"\x00\x08\x08\x08"
        write(steam / "userdata" / str(profile) / "config/shortcuts.vdf", blob)
    cleaner = service(home)
    state = cleaner.inventory()
    entry = state["entries"][0]
    assert entry["installation"] == "unknown"
    assert entry["name"] is None
    assert entry["blocked_reason"] == "unknown_identity"
    with pytest.raises(SteamCleanerError, match="unknown_identity"):
        cleaner.prepare(state["scan_id"], [entry["id"]])
    assert target.exists()


def test_unreadable_manifest_listing_never_claims_complete_coverage(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    manifest(steam)
    original = os.scandir

    def denied(path):
        if not isinstance(path, int) and os.path.normpath(path) == str(steam / "steamapps"):
            raise PermissionError(13, "private directory")
        return original(path)

    monkeypatch.setattr(os, "scandir", denied)
    cleaner = service(home)
    state = cleaner.inventory()
    assert state["coverage_complete"] is False
    entry = state["entries"][0]
    assert entry["installation"] == "unknown"
    assert entry["blocked_reason"] == "coverage_incomplete"
    with pytest.raises(SteamCleanerError, match="coverage_incomplete"):
        cleaner.prepare(state["scan_id"], [entry["id"]])
    assert target.exists()
    issues = [event for event in cleaner.diagnostics()["events"] if event.get("source") == "manifest"]
    assert issues[0]["system_error"] == "permission_denied"
    assert "private directory" not in json.dumps(cleaner.diagnostics())


def test_selection_ids_are_distinct_for_same_game_and_category_in_two_libraries(tmp_path):
    home, steam = make_steam(tmp_path)
    sd = tmp_path / "sd"
    data(steam)
    data(sd)
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "1" "{sd}" }}')
    entries = service(home).inventory()["entries"]
    assert len({e["id"] for e in entries}) == 2
    assert len({e["game_id"] for e in entries}) == 1


def test_explicit_mixed_selection_deletes_only_reviewed_locations(tmp_path):
    home, steam = make_steam(tmp_path)
    cache = data(steam)
    prefix = data(steam, "compatdata")
    outside = write(tmp_path / "unrelated/save")
    other = data(steam, appid="20")
    cleaner = service(home)
    state = cleaner.inventory()
    ids = [e["id"] for e in state["entries"] if e["appid"] == "10"]
    plan = cleaner.prepare(state["scan_id"], ids)
    assert plan["requires_prefix_confirmation"] is True
    with pytest.raises(SteamCleanerError, match="prefix_confirmation_required"):
        cleaner.execute(plan["id"])
    assert cache.exists() and prefix.exists()
    # Missing confirmation does not authorize work or consume the review.
    result = cleaner.execute(plan["id"], confirm_compatdata=True)
    assert {item["status"] for item in result["items"]} == {"deleted"}
    assert result["estimated_bytes_removed"] == 8
    assert not cache.exists() and not prefix.exists()
    assert outside.exists() and other.exists()
    with pytest.raises(SteamCleanerError, match="invalid_plan"):
        cleaner.execute(plan["id"], True)


@pytest.mark.parametrize("bad", [[], ["../../unrelated"], [3], "entry", None])
def test_invalid_selection_never_accepts_frontend_paths(tmp_path, bad):
    home, steam = make_steam(tmp_path)
    data(steam)
    cleaner = service(home)
    state = cleaner.inventory()
    with pytest.raises(SteamCleanerError, match="invalid_selection"):
        cleaner.prepare(state["scan_id"], bad)


def test_new_scan_invalidates_old_scan_and_plans(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    cleaner = service(home)
    plan = prepare_all(cleaner)
    cleaner.inventory()
    with pytest.raises(SteamCleanerError, match="stale_scan"):
        cleaner.prepare(plan["scan_id"], [e["id"] for e in plan["entries"]])
    with pytest.raises(SteamCleanerError, match="invalid_plan"):
        cleaner.execute(plan["id"])


def test_expired_plan_is_not_executable(tmp_path, monkeypatch):
    import steam_cleaner.service as module
    home, steam = make_steam(tmp_path)
    target = data(steam)
    cleaner = service(home)
    plan = prepare_all(cleaner)
    monkeypatch.setattr(module.time, "monotonic", lambda: 10**15)
    with pytest.raises(SteamCleanerError, match="expired_plan"):
        cleaner.execute(plan["id"])
    assert target.exists()


@pytest.mark.parametrize("kind", ["entry", "category"])
def test_symlink_destinations_are_visible_and_protected(tmp_path, kind):
    home, steam = make_steam(tmp_path)
    outside = write(tmp_path / "outside/10/save")
    category = steam / "steamapps/compatdata"
    if kind == "entry":
        category.mkdir()
        (category / "10").symlink_to(outside.parent, target_is_directory=True)
    else:
        category.symlink_to(outside.parent.parent, target_is_directory=True)
    cleaner = service(home)
    state = cleaner.inventory()
    assert state["entries"]
    assert state["entries"][0]["blocked_reason"] == "symlink"
    with pytest.raises(SteamCleanerError):
        cleaner.prepare(state["scan_id"], [state["entries"][0]["id"]])
    assert outside.exists()


def test_internal_wine_links_are_unlinked_without_following_targets(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam, "compatdata")
    outside = write(tmp_path / "outside/save")
    (target.parent / "dosdevices").mkdir()
    (target.parent / "dosdevices/z:").symlink_to(outside.parent, target_is_directory=True)
    cleaner = service(home)
    plan = prepare_all(cleaner)
    result = cleaner.execute(plan["id"], True)
    assert result["items"][0]["status"] == "deleted"
    assert outside.exists()


def test_replaced_directory_after_review_is_never_deleted(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    cleaner = service(home)
    plan = prepare_all(cleaner)
    target.parent.rename(target.parent.with_name("old"))
    replacement = data(steam)
    result = cleaner.execute(plan["id"])
    assert result["items"][0]["status"] == "skipped"
    assert result["items"][0]["reason"] == "path_changed"
    assert replacement.exists()


@pytest.mark.parametrize("snapshot,reason", [({"complete": False, "appids": [], "paths": []}, "activity_unknown"), ({"complete": True, "appids": ["10"], "paths": []}, "active_game")])
def test_fresh_activity_at_execute_blocks_previously_idle_game(tmp_path, snapshot, reason):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    activity = [idle()]
    cleaner = service(home, activity_provider=lambda: activity[0])
    plan = prepare_all(cleaner)
    activity[0] = snapshot
    result = cleaner.execute(plan["id"])
    assert result["items"][0]["reason"] == reason
    assert target.exists()


def test_runtime_manifest_is_visible_but_protected(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    manifest(steam)
    write(steam / "steamapps/common/Example/toolmanifest.vdf", '"manifest" {}')
    entry = service(home).inventory()["entries"][0]
    assert entry["blocked_reason"] == "runtime"


def test_cancellation_between_entries_preserves_remaining_data(tmp_path):
    home, steam = make_steam(tmp_path)
    first = data(steam)
    second = data(steam, appid="20")
    cleaner = service(home)
    plan = prepare_all(cleaner)
    def active():
        if not first.exists():
            cleaner.cancel()
        return idle()

    cleaner._activity_provider = active
    result = cleaner.execute(plan["id"])
    assert result["cancelled"] is True
    assert not first.exists()
    assert second.exists()


def test_busy_close_drains_scan_and_prevents_new_work(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    entered = threading.Event()
    release = threading.Event()

    def activity():
        entered.set()
        release.wait(3)
        return idle()

    cleaner = service(home, activity_provider=activity)
    worker = threading.Thread(target=cleaner.inventory)
    worker.start()
    assert entered.wait(2)
    with pytest.raises(SteamCleanerError, match="busy"):
        cleaner.inventory()
    closer = threading.Thread(target=cleaner.close)
    closer.start()
    assert closer.is_alive()
    release.set()
    worker.join(3)
    closer.join(3)
    assert not closer.is_alive()
    with pytest.raises(SteamCleanerError, match="closed"):
        cleaner.inventory()


def test_diagnostics_are_bounded_private_and_survive_restart(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    settings = tmp_path / "settings"
    cleaner = service(home, state_dir=str(settings))
    plan = prepare_all(cleaner)
    cleaner.execute(plan["id"])
    diagnostic = cleaner.diagnostics()
    assert diagnostic["events"]
    assert str(home) not in json.dumps(diagnostic)
    assert "Example" not in json.dumps(diagnostic)
    assert len(diagnostic["events"]) <= 120
    files = list(settings.glob("*.json"))
    assert len(files) == 1
    restored = service(home, state_dir=str(settings))
    restored.inventory()
    assert any(e["event"] == "deleted" for e in restored.diagnostics()["events"])
    assert "plans" not in files[0].read_text()


def test_corrupt_diagnostics_cannot_inject_private_content(tmp_path):
    home, _ = make_steam(tmp_path)
    settings = tmp_path / "settings"
    write(settings / "steam_cleaner_history.json", json.dumps({"events": [{"event": "secret/path", "private": "secret"}]}))
    cleaner = service(home, state_dir=str(settings))
    cleaner.inventory()
    assert "secret" not in json.dumps(cleaner.diagnostics())


def test_unknown_shortcut_identity_is_not_a_cleanup_candidate(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam, "compatdata", "3999999999")
    cleaner = service(home)
    state = cleaner.inventory()
    assert state["entries"][0]["blocked_reason"] == "unknown_identity"
    with pytest.raises(SteamCleanerError, match="unknown_identity"):
        cleaner.prepare(state["scan_id"], [state["entries"][0]["id"]])
    assert target.exists()


def test_execute_removes_confirmed_entries_and_requires_fresh_inventory(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    data(steam, appid="20")
    cleaner = service(home)
    scan = cleaner.inventory()
    plan = cleaner.prepare(scan["scan_id"], [scan["entries"][0]["id"]])
    cleaner.execute(plan["id"])
    state = cleaner.get_state()
    assert state["scan_id"] is None
    assert [entry["appid"] for entry in state["entries"]] == ["20"]
    assert state["totals"]["shadercache"] == 4


def test_partial_failure_reports_changed_data_and_unknown_remaining_size(tmp_path, monkeypatch):
    import steam_cleaner.filesystem as module
    home, steam = make_steam(tmp_path)
    first = write(steam / "steamapps/compatdata/10/a", "first")
    second = write(first.parent / "b", "second")
    cleaner = service(home)
    plan = prepare_all(cleaner)
    original = module.os.unlink

    def fail_second(path, *args, **kwargs):
        if path == "b":
            raise PermissionError(13, "private username")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "unlink", fail_second)
    result = cleaner.execute(plan["id"], True)
    assert not first.exists() and second.exists()
    assert result["items"][0]["reason"] == "partial_delete"
    assert result["items"][0]["bytes_removed"] == 5
    assert result["estimated_bytes_removed"] == 5
    entry = cleaner.get_state()["entries"][0]
    assert entry["bytes"] is None
    assert entry["blocked_reason"] == "path_changed"
    assert "private username" not in json.dumps(cleaner.diagnostics())


def test_changed_category_ancestor_is_not_followed(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    outside = write(tmp_path / "outside/10/data.bin")
    cleaner = service(home)
    plan = prepare_all(cleaner)
    category = target.parent.parent
    category.rename(category.with_name("old-cache"))
    category.symlink_to(outside.parent.parent)
    result = cleaner.execute(plan["id"])
    assert result["items"][0]["status"] == "skipped"
    assert outside.exists()


def test_nested_mount_is_blocked_before_deleting_any_contents(tmp_path, monkeypatch):
    import steam_cleaner.filesystem as module
    home, steam = make_steam(tmp_path)
    target = data(steam)
    mounted = write(target.parent / "mounted/sentinel")
    monkeypatch.setattr(module, "mount_points", lambda: {str(mounted.parent)})
    entry = service(home).inventory()["entries"][0]
    assert entry["blocked_reason"] == "mount_point"
    assert mounted.exists()


def test_interrupted_journal_available_before_scan_and_never_resumes(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    settings = tmp_path / "settings"
    cleaner = service(home, state_dir=str(settings))
    plan = prepare_all(cleaner)
    saved = json.loads((settings / "steam_cleaner_history.json").read_text())
    saved["phase"] = "execute"
    write(settings / "steam_cleaner_history.json", json.dumps(saved))
    restarted = service(home, state_dir=str(settings))
    assert restarted.diagnostics()["interrupted"] is True
    assert restarted.get_state()["status"] == "idle"
    with pytest.raises(SteamCleanerError, match="invalid_plan"):
        restarted.execute(plan["id"])
    assert target.exists()


def test_diagnostic_ids_survive_report_redaction(tmp_path):
    from report.collector import redact_text
    home, steam = make_steam(tmp_path)
    data(steam)
    cleaner = service(home)
    cleaner.execute(prepare_all(cleaner)["id"])
    for event in cleaner.diagnostics()["events"]:
        for key in ("operation_id", "entry_id", "library_id"):
            if key in event:
                assert redact_text(event[key]) == event[key]


def test_secondary_library_symlink_is_visible_but_not_followed(tmp_path):
    home, steam = make_steam(tmp_path)
    sd = tmp_path / "sd"
    external = data(sd)
    alias = tmp_path / "linked-card"
    alias.symlink_to(sd)
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "1" "{alias}" }}')
    state = service(home).inventory()
    assert len(state["libraries"]) == 2
    assert state["libraries"][1]["reason"] == "symlink"
    assert state["coverage_complete"] is False
    assert state["entries"] == []
    assert external.exists()


def test_download_in_other_library_protects_the_game_cache(tmp_path):
    home, steam = make_steam(tmp_path)
    sd = tmp_path / "sd"
    target = data(steam)
    write(sd / "steamapps/downloading/10/chunk")
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "1" "{sd}" }}')
    entry = service(home).inventory()["entries"][0]
    assert entry["blocked_reason"] == "active_download"
    assert target.exists()


def test_download_starting_after_review_blocks_execution(tmp_path):
    home, steam = make_steam(tmp_path)
    target = data(steam)
    (steam / "steamapps/downloading").mkdir()
    cleaner = service(home)
    plan = prepare_all(cleaner)
    write(steam / "steamapps/downloading/10/chunk")
    result = cleaner.execute(plan["id"])
    assert result["items"][0]["reason"] == "active_download"
    assert target.exists()


def test_result_keeps_display_labels_after_removing_inventory_entry(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    manifest(steam)
    cleaner = service(home)
    result = cleaner.execute(prepare_all(cleaner)["id"])
    assert result["items"][0]["entry"]["name"] == "Example"
    assert "Example" not in json.dumps(cleaner.diagnostics())


@pytest.mark.parametrize("content", [b"x" * (128 * 1024 + 1), b'{"schema_version":2}', b'{"schema_version":1,"events":{}}', b'{"schema_version":1,"events":[{"event":"secret"}]}'], ids=["oversized", "schema", "events_shape", "invalid_event"])
def test_invalid_history_reports_safe_diagnostic_failure(tmp_path, content):
    home, _ = make_steam(tmp_path)
    settings = tmp_path / "settings"
    write(settings / "steam_cleaner_history.json", content)
    restarted = service(home, state_dir=str(settings))
    assert restarted.diagnostics()["persistence_error"] == "io_error"
    assert "secret" not in json.dumps(restarted.diagnostics())


def test_interruption_retains_operation_id_without_duplicate_on_clean_restart(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    settings = tmp_path / "settings"
    cleaner = service(home, state_dir=str(settings))
    cleaner.inventory()
    history = settings / "steam_cleaner_history.json"
    saved = json.loads(history.read_text())
    saved["phase"] = "execute"
    previous_id = saved["last_operation_id"]
    write(history, json.dumps(saved))
    restarted = service(home, state_dir=str(settings))
    interruption = restarted.diagnostics()["events"][-1]
    assert interruption["event"] == "interrupted"
    assert interruption["operation_id"] == previous_id
    restarted.inventory()
    third = service(home, state_dir=str(settings))
    assert sum(item["event"] == "interrupted" for item in third.diagnostics()["events"]) == 1


def test_library_labels_identify_actual_directory_without_paths(tmp_path):
    home, steam = make_steam(tmp_path)
    second = tmp_path / "GamesCard"
    data(second)
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "1" "{second}" }}')
    state = service(home).inventory()
    assert state["libraries"][1]["label"] == "GamesCard"
    assert state["entries"][0]["library_label"] == "GamesCard"
    assert state["entries"][0]["library_internal"] is False


def test_native_home_library_has_localizable_internal_storage_label(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    data(steam)
    monkeypatch.setattr("steam_cleaner.filesystem.mount_points", lambda: {"/", str(home)})
    state = service(home).inventory()
    assert state["entries"][0]["library_internal"] is True


def test_library_mounted_inside_home_is_not_presented_as_internal(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    data(steam)
    monkeypatch.setattr("steam_cleaner.filesystem.mount_points", lambda: {"/", str(steam.parent)})
    state = service(home).inventory()
    assert state["entries"][0]["library_internal"] is False


def test_partial_scan_diagnostic_names_source_and_safe_cause(tmp_path):
    home, steam = make_steam(tmp_path)
    data(steam)
    write(steam / "steamapps/appmanifest_10.acf", '"AppState" { "broken"')
    cleaner = service(home)
    cleaner.inventory()
    issues = [event for event in cleaner.diagnostics()["events"] if event.get("source") == "manifest"]
    assert issues
    assert issues[0]["reason"] == "coverage_incomplete"
    assert issues[0]["system_error"] == "malformed_data"
    assert str(home) not in json.dumps(issues)


def test_inventory_limit_is_incomplete_and_never_authorizes_partial_coverage(tmp_path, monkeypatch):
    import steam_cleaner.service as module
    home, steam = make_steam(tmp_path)
    for appid in ("10", "20", "30"):
        data(steam, appid=appid)
    monkeypatch.setattr(module, "MAX_ENTRIES", 2)
    state = service(home).inventory()
    assert len(state["entries"]) == 2
    assert state["coverage_complete"] is False
    assert {entry["blocked_reason"] for entry in state["entries"]} == {"coverage_incomplete"}
