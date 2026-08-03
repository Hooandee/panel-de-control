import json
import os

import pytest

from mangohud import apply
from mangohud import detect as detection
from mangohud import ownership
from mangohud.apply import apply_hud, clear_presets, read_presets
from mangohud.config import build_presets_conf, coerce_model
from mangohud.detect import presets_path, presets_supported


# ---- detect: pure decision from a process environ ----

def test_presets_supported_flag():
    assert presets_supported({"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"}) is True
    assert presets_supported({"STEAM_MANGOAPP_PRESETS_SUPPORTED": "0"}) is False
    assert presets_supported({}) is False


def test_presets_path_prefers_safe_explicit_env():
    p = presets_path(
        {"MANGOHUD_PRESETSFILE": "/home/deck/.local/share/MangoHud/presets.conf"},
        home="/home/deck",
    )
    assert p == "/home/deck/.local/share/MangoHud/presets.conf"


def test_presets_path_rejects_explicit_path_outside_user_home():
    p = presets_path({"MANGOHUD_PRESETSFILE": "/etc/presets.conf"}, home="/home/deck")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


def test_presets_path_uses_xdg_config_home():
    p = presets_path({"XDG_CONFIG_HOME": "/home/deck/.cfg"}, home="/home/deck")
    assert p == "/home/deck/.cfg/MangoHud/presets.conf"


def test_presets_path_rejects_xdg_config_home_outside_user_home():
    p = presets_path({"XDG_CONFIG_HOME": "/etc"}, home="/home/deck")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


def test_presets_path_defaults_to_home_config():
    p = presets_path({}, home="/home/deck")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


def test_presets_path_uses_trusted_decky_home_not_process_home():
    p = presets_path({"HOME": "/root"}, home="/home/deck")
    assert p == "/home/deck/.config/MangoHud/presets.conf"


def _fake_mangoapp(proc, pid, uid, environ):
    process = proc / str(pid)
    process.mkdir()
    (process / "comm").write_text("mangoapp\n")
    (process / "status").write_text(f"Name:\tmangoapp\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    raw = b"\0".join(f"{key}={value}".encode() for key, value in environ.items()) + b"\0"
    (process / "environ").write_bytes(raw)


def test_detect_ignores_mangoapp_owned_by_another_user(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    proc.mkdir()
    _fake_mangoapp(
        proc,
        10,
        1001,
        {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1", "HOME": "/home/other"},
    )
    monkeypatch.setattr(detection, "_PROC", str(proc))

    cap = detection.detect(home="/home/deck", uid=1000)

    assert cap["running"] is False
    assert cap["presetsPath"] == "/home/deck/.config/MangoHud/presets.conf"


def test_detect_uses_matching_user_and_trusted_home_fallback(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    proc.mkdir()
    _fake_mangoapp(proc, 10, 1000, {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"})
    monkeypatch.setattr(detection, "_PROC", str(proc))

    cap = detection.detect(home="/home/deck", uid=1000)

    assert cap["running"] is True
    assert cap["supported"] is True
    assert cap["presetsPath"] == "/home/deck/.config/MangoHud/presets.conf"


# ---- apply: write presets.conf + honest readback ----

def test_apply_writes_presets_conf_and_reads_it_back(tmp_path):
    path = str(tmp_path / "sub" / "presets.conf")  # parent dir does not exist yet
    model = coerce_model({"metrics": ["fps", "gpu"]})
    on_disk = apply_hud(model, path)
    assert on_disk == build_presets_conf(model)
    assert read_presets(path) == on_disk  # readback = what actually landed


def test_apply_new_path_uses_requested_user_ownership(tmp_path):
    path = str(tmp_path / "sub" / "presets.conf")
    owner = (os.getuid(), os.getgid())
    model = coerce_model({"items": [{"kind": "metric", "id": "fps"}]})

    apply_hud(model, path, owner=owner)

    assert (os.stat(path).st_uid, os.stat(path).st_gid) == owner
    assert (os.stat(tmp_path / "sub").st_uid, os.stat(tmp_path / "sub").st_gid) == owner


def test_apply_skips_atomic_replace_when_bytes_are_unchanged(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    model = coerce_model({"items": [{"kind": "metric", "id": "fps"}]})
    apply_hud(model, path)
    writes = []
    monkeypatch.setattr(apply, "_write_atomic", lambda *args: writes.append(args))

    on_disk = apply_hud(model, path)

    assert on_disk == build_presets_conf(model)
    assert writes == []


def test_read_presets_missing_returns_none(tmp_path):
    assert read_presets(str(tmp_path / "nope.conf")) is None


def test_clear_presets_removes_our_file_and_is_idempotent(tmp_path):
    path = str(tmp_path / "presets.conf")
    apply_hud(coerce_model({"metrics": ["fps"]}), path)
    assert read_presets(path) is not None
    assert clear_presets(path) is True  # hands the overlay back to MangoHud's stock defaults
    assert read_presets(path) is None
    assert clear_presets(path) is True  # already gone — must not raise


def test_apply_restores_a_preexisting_user_presets_file_on_disable(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "# personal MangoHud presets\n[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)

    apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    assert read_presets(path) != original

    assert clear_presets(path) is True
    assert read_presets(path) == original
    assert not (tmp_path / "presets.conf.pdc-backup").exists()
    assert clear_presets(path) is True
    assert read_presets(path) == original


def test_clear_presets_refuses_to_overwrite_an_external_edit(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "external-before\n"
    external_edit = "external-after\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    (tmp_path / "presets.conf").write_text(external_edit)

    cleared = clear_presets(path)

    assert cleared is False
    assert read_presets(path) == external_edit
    assert read_presets(f"{path}.pdc-backup") == original


def test_clear_presets_never_deletes_an_unmanaged_file(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\ngpu_stats=1\n"
    (tmp_path / "presets.conf").write_text(original)

    assert clear_presets(path) is True
    assert read_presets(path) == original


def test_failed_restore_keeps_a_retryable_state(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    real_replace = apply.os.replace

    def fail_backup_restore(source, destination):
        if source == f"{path}.pdc-backup":
            raise PermissionError
        return real_replace(source, destination)

    monkeypatch.setattr(apply.os, "replace", fail_backup_restore)
    assert clear_presets(path) is False
    assert (tmp_path / "presets.conf.pdc-backup").exists()
    marker = json.loads(read_presets(str(tmp_path / "presets.conf.pdc-managed")))
    assert marker["phase"] == "restoring"

    monkeypatch.setattr(apply.os, "replace", real_replace)
    assert clear_presets(path) is True
    assert read_presets(path) == original
    assert not (tmp_path / "presets.conf.pdc-managed").exists()


def test_retry_after_restored_backup_only_removes_the_marker(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    real_remove = apply.os.remove

    def fail_marker_removal(candidate):
        if candidate == f"{path}.pdc-managed":
            raise PermissionError
        return real_remove(candidate)

    monkeypatch.setattr(apply.os, "remove", fail_marker_removal)
    assert clear_presets(path) is False
    assert read_presets(path) == original
    assert not (tmp_path / "presets.conf.pdc-backup").exists()
    marker = json.loads(read_presets(f"{path}.pdc-managed"))
    assert marker["phase"] == "restoring"

    monkeypatch.setattr(apply.os, "remove", real_remove)
    assert clear_presets(path) is True
    assert read_presets(path) == original
    assert not (tmp_path / "presets.conf.pdc-managed").exists()


def test_legacy_marker_does_not_authorize_clear_without_expected_content(tmp_path):
    path = str(tmp_path / "presets.conf")
    content = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(content)
    (tmp_path / "presets.conf.pdc-managed").write_text("1\n")

    assert clear_presets(path) is False
    assert read_presets(path) == content
    assert read_presets(f"{path}.pdc-managed") == "1\n"


def test_unknown_marker_never_authorizes_deletion(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    (tmp_path / "presets.conf.pdc-managed").write_text("unexpected\n")

    assert clear_presets(path) is False
    assert read_presets(path) == original


def test_failed_marker_write_leaves_the_original_without_an_orphan_backup(
    tmp_path, monkeypatch
):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    real_write = ownership._write_atomic

    def fail_marker_write(candidate, text, owner=None):
        if candidate == f"{path}.pdc-managed":
            raise PermissionError
        return real_write(candidate, text, owner)

    monkeypatch.setattr(ownership, "_write_atomic", fail_marker_write)

    with pytest.raises(PermissionError):
        apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    assert read_presets(path) == original
    assert not (tmp_path / "presets.conf.pdc-backup").exists()
    assert not (tmp_path / "presets.conf.pdc-managed").exists()


def test_clear_presets_reports_failed_removal(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    apply_hud(coerce_model({"items": [{"kind": "metric", "id": "fps"}]}), path)
    monkeypatch.setattr(apply.os, "remove", lambda _path: (_ for _ in ()).throw(PermissionError()))

    assert clear_presets(path) is False


def test_apply_bakes_pdc_values_into_presets(tmp_path):
    path = str(tmp_path / "presets.conf")
    model = coerce_model({"items": [{"kind": "metric", "id": "pdc_tdp"}], "enabled": True})
    on_disk = apply_hud(model, path, {"pdc_tdp": "21W"})
    assert "custom_text=TDP 21W" in on_disk
    assert "exec=" not in on_disk


def test_reload_uses_discovered_mangohud_control_tool(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0})()

    tools = {
        "mangohudctl": "/usr/local/bin/mangohudctl",
        "mangoapp": "/usr/local/bin/mangoapp",
    }
    monkeypatch.setattr(apply.shutil, "which", lambda name, **kwargs: tools.get(name))
    monkeypatch.setattr(apply, "_mangoapp_cwd", lambda: "/home/deck", raising=False)
    monkeypatch.setattr(apply.subprocess, "run", run)

    assert apply.reload_mangoapp() is True
    assert calls[0][0] == ["/usr/local/bin/mangohudctl", "set", "reload_config", "true"]
    assert calls[0][1]["timeout"] == 2
    assert calls[0][1]["cwd"] == "/home/deck"


def test_reload_failure_is_non_fatal(monkeypatch):
    def run(command, **kwargs):
        raise OSError("missing")

    monkeypatch.setattr(apply.shutil, "which", lambda *a, **k: "/usr/bin/mangohudctl")
    monkeypatch.setattr(apply.subprocess, "run", run)

    assert apply.reload_mangoapp() is False


def test_reload_without_control_tool_is_non_fatal(monkeypatch):
    monkeypatch.setattr(apply.shutil, "which", lambda *a, **k: None)

    assert apply.reload_mangoapp() is False


def test_reload_without_mangoapp_cwd_does_not_create_the_wrong_ipc_queue(monkeypatch):
    calls = []
    monkeypatch.setattr(apply.shutil, "which", lambda *a, **k: "/usr/bin/mangohudctl")
    monkeypatch.setattr(apply, "_mangoapp_cwd", lambda: None)
    monkeypatch.setattr(apply.subprocess, "run", lambda *a, **k: calls.append((a, k)))

    assert apply.reload_mangoapp() is False
    assert calls == []


def test_reload_cwd_ignores_a_mangoapp_owned_by_another_user(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    process = proc / "10"
    process.mkdir(parents=True)
    (process / "comm").write_text("mangoapp\n")
    (process / "status").write_text("Name:\tmangoapp\nUid:\t1001\t1001\t1001\t1001\n")
    (process / "cwd").symlink_to(tmp_path)
    monkeypatch.setattr(apply, "_PROC", str(proc))

    assert apply._mangoapp_cwd(uid=1000) is None
    assert apply._mangoapp_cwd(uid=1001) == str(tmp_path)


def test_reload_searches_service_path(monkeypatch):
    monkeypatch.setenv("PATH", "/opt/mangohud/bin")

    def which(name, *, path):
        if "/opt/mangohud/bin" not in path:
            return None
        return f"/opt/mangohud/bin/{name}"

    monkeypatch.setattr(apply.shutil, "which", which)
    monkeypatch.setattr(apply, "_mangoapp_cwd", lambda: "/home/deck")
    monkeypatch.setattr(
        apply.subprocess,
        "run",
        lambda *a, **k: type("Result", (), {"returncode": 0})(),
    )

    assert apply.reload_mangoapp() is True
