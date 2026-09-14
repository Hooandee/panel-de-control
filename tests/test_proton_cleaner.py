import pytest

from steam_cleaner import filesystem
from steam_cleaner.proton import ProtonCleanerService
from steam_cleaner.service import SteamCleanerError, SteamCleanerService


def write(path, content=b"data"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    return path


def make_steam(tmp_path):
    home = tmp_path / "home"
    steam = home / ".local/share/Steam"
    (steam / "steamapps").mkdir(parents=True)
    write(steam / "steamapps/libraryfolders.vdf", f'"libraryfolders" {{ "0" {{ "path" "{steam}" }} }}')
    return home, steam


def idle():
    return {"complete": True, "appids": [], "paths": []}


def official(steam, appid, name, directory):
    write(
        steam / "steamapps" / f"appmanifest_{appid}.acf",
        f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{directory}" "type" "Tool" }}',
    )
    write(steam / "steamapps/common" / directory / "toolmanifest.vdf", '"manifest" {}')
    write(steam / "steamapps/common" / directory / "payload.bin", b"official")


def custom(steam, directory, tool_name):
    root = steam / "compatibilitytools.d" / directory
    write(
        root / "compatibilitytool.vdf",
        f'"compatibilitytools" {{ "compat_tools" {{ "{tool_name}" {{ "display_name" "{tool_name}" }} }} }}',
    )
    return write(root / "files/payload.bin", b"custom")


def test_inventory_protects_steam_tools_and_recommends_only_unreferenced_custom_tools(tmp_path):
    home, steam = make_steam(tmp_path)
    official(steam, "100", "Proton 10.0", "Proton 10")
    official(steam, "200", "Steam Linux Runtime 3.0", "SteamLinuxRuntime_sniper")
    custom(steam, "used", "GE-Proton-Used")
    custom(steam, "old", "GE-Proton-Old")
    write(
        steam / "config/config.vdf",
        '"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "10" { "name" "GE-Proton-Used" } } } } } }',
    )

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()
    entries = {entry["name"]: entry for entry in state["entries"]}

    assert entries["Proton 10.0"]["status"] == "managed_by_steam"
    assert entries["Proton 10.0"]["selectable"] is False
    assert entries["Steam Linux Runtime 3.0"]["status"] == "protected"
    assert entries["GE-Proton-Used"]["status"] == "in_use"
    assert entries["GE-Proton-Used"]["selectable"] is False
    assert entries["GE-Proton-Old"]["status"] == "unused"
    assert entries["GE-Proton-Old"]["recommended"] is True
    assert entries["GE-Proton-Old"]["selectable"] is True


def test_official_game_with_proton_in_its_title_is_not_listed_as_a_tool(tmp_path):
    home, steam = make_steam(tmp_path)
    write(
        steam / "steamapps/appmanifest_300.acf",
        '"AppState" { "appid" "300" "name" "Proton Racing" "installdir" "ProtonRacing" "type" "Game" }',
    )
    write(steam / "steamapps/common/ProtonRacing/game.bin")

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()

    assert state["entries"] == []


def test_modern_official_manifest_without_type_uses_steam_tool_marker(tmp_path):
    home, steam = make_steam(tmp_path)
    write(
        steam / "steamapps/appmanifest_100.acf",
        '"AppState" { "appid" "100" "name" "Proton 10.0" "installdir" "Proton 10" }',
    )
    write(steam / "steamapps/common/Proton 10/toolmanifest.vdf", '"manifest" {}')

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()

    assert len(state["entries"]) == 1
    assert state["entries"][0]["status"] == "managed_by_steam"
    assert state["entries"][0]["selectable"] is False
    assert state["coverage_complete"] is True


def test_unreadable_official_manifest_marks_coverage_incomplete(tmp_path):
    home, steam = make_steam(tmp_path)
    official(steam, "100", "Proton 10.0", "Proton 10")
    write(steam / "steamapps/appmanifest_200.acf", '"AppState" { "appid"')

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()

    assert [entry["name"] for entry in state["entries"]] == ["Proton 10.0"]
    assert state["coverage_complete"] is False


def test_structurally_invalid_official_tool_marks_coverage_incomplete(tmp_path):
    home, steam = make_steam(tmp_path)
    write(
        steam / "steamapps/appmanifest_200.acf",
        '"AppState" { "appid" "200" "name" "Proton Broken" "type" "Tool" }',
    )

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()

    assert state["entries"] == []
    assert state["coverage_complete"] is False


def test_execution_deletes_only_the_reviewed_custom_tool(tmp_path):
    home, steam = make_steam(tmp_path)
    payload = custom(steam, "old", "GE-Proton-Old")
    cleaner = ProtonCleanerService(str(home), activity_provider=idle)
    state = cleaner.inventory()
    entry = state["entries"][0]

    plan = cleaner.prepare(state["scan_id"], [entry["id"]])
    result = cleaner.execute(plan["id"])

    assert result["items"] == [{"id": entry["id"], "status": "deleted", "reason": None, "bytes_removed": entry["bytes"]}]
    assert not payload.parent.parent.exists()


def test_referenced_or_steam_managed_tools_cannot_be_prepared(tmp_path):
    home, steam = make_steam(tmp_path)
    official(steam, "100", "Proton 10.0", "Proton 10")
    custom(steam, "used", "GE-Proton-Used")
    write(steam / "config/config.vdf", '"root" { "CompatToolMapping" { "10" { "name" "GE-Proton-Used" } } }')
    cleaner = ProtonCleanerService(str(home), activity_provider=idle)
    state = cleaner.inventory()

    for entry in state["entries"]:
        with pytest.raises(SteamCleanerError, match="protected_tool|tool_in_use"):
            cleaner.prepare(state["scan_id"], [entry["id"]])


def test_changed_custom_tool_is_not_deleted(tmp_path):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    cleaner = ProtonCleanerService(str(home), activity_provider=idle)
    state = cleaner.inventory()
    entry = state["entries"][0]
    plan = cleaner.prepare(state["scan_id"], [entry["id"]])
    write(steam / "compatibilitytools.d/old/files/new.bin", b"changed")

    result = cleaner.execute(plan["id"])

    assert result["items"][0]["status"] == "skipped"
    assert result["items"][0]["reason"] == "path_changed"
    assert (steam / "compatibilitytools.d/old").exists()


def test_partial_deletion_reports_removed_bytes_and_requires_a_new_scan(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    cleaner = ProtonCleanerService(str(home), activity_provider=idle)
    state = cleaner.inventory()
    plan = cleaner.prepare(state["scan_id"], [state["entries"][0]["id"]])

    def fail_after_removal(*_args):
        raise filesystem.DeletionError("io_error", 4, True, OSError("failed"))

    monkeypatch.setattr("steam_cleaner.proton.filesystem.remove_tree", fail_after_removal)
    result = cleaner.execute(plan["id"])

    assert result["items"][0]["status"] == "error"
    assert result["items"][0]["reason"] == "partial_delete"
    assert result["items"][0]["bytes_removed"] == 4
    assert result["estimated_bytes_removed"] == 4
    assert cleaner.get_state()["scan_id"] is None


def test_diagnostics_survive_a_restart_without_storing_paths(tmp_path):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    settings = tmp_path / "settings"
    ProtonCleanerService(str(home), state_dir=settings, activity_provider=idle).inventory()

    diagnostics = ProtonCleanerService(str(home), state_dir=settings, activity_provider=idle).diagnostics()

    assert diagnostics["events"][-1]["event"] == "completed"
    assert diagnostics["persistence_error"] is None
    assert str(home) not in (settings / "proton_cleaner_history.json").read_text()


def test_execution_rechecks_activity_immediately_before_deleting(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    tool = steam / "compatibilitytools.d/old"
    active = False

    def activity():
        return {"complete": True, "appids": [], "paths": [str(tool)] if active else []}

    cleaner = ProtonCleanerService(str(home), activity_provider=activity)
    state = cleaner.inventory()
    plan = cleaner.prepare(state["scan_id"], [state["entries"][0]["id"]])
    inspect = filesystem.inspect_tree

    def inspect_and_start_game(*args):
        nonlocal active
        result = inspect(*args)
        active = True
        return result

    monkeypatch.setattr("steam_cleaner.proton.filesystem.inspect_tree", inspect_and_start_game)
    result = cleaner.execute(plan["id"])

    assert result["items"][0]["status"] == "skipped"
    assert result["items"][0]["reason"] == "active_game"
    assert tool.exists()


def test_parent_service_scopes_activity_detection_to_custom_proton_directories(tmp_path, monkeypatch):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    observed = []

    def capture(_home, data_roots):
        observed.extend(data_roots)
        return idle()

    monkeypatch.setattr("steam_cleaner.proton.process_activity", capture)
    SteamCleanerService(str(home)).inventory_proton()

    assert str(steam / "compatibilitytools.d") in observed


def test_new_profile_reference_after_prepare_prevents_deletion(tmp_path):
    home, steam = make_steam(tmp_path)
    custom(steam, "old", "GE-Proton-Old")
    cleaner = ProtonCleanerService(str(home), activity_provider=idle)
    state = cleaner.inventory()
    plan = cleaner.prepare(state["scan_id"], [state["entries"][0]["id"]])
    write(
        steam / "userdata/123/config/localconfig.vdf",
        '"root" { "CompatToolMapping" { "10" { "name" "GE-Proton-Old" } } }',
    )

    with pytest.raises(SteamCleanerError, match="path_changed"):
        cleaner.execute(plan["id"])
    assert (steam / "compatibilitytools.d/old").exists()


def test_non_proton_compatibility_tools_are_not_presented_as_proton(tmp_path):
    home, steam = make_steam(tmp_path)
    custom(steam, "luxtorpeda", "Luxtorpeda")
    custom(steam, "proton", "GE-Proton-Old")

    state = ProtonCleanerService(str(home), activity_provider=idle).inventory()

    assert [entry["name"] for entry in state["entries"]] == ["GE-Proton-Old"]
