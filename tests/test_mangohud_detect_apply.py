import os

import pytest

from mangohud import apply
from mangohud import ownership
from mangohud.apply import apply_hud, clear_presets, reload_sessions
from mangohud.config import build_presets_conf, coerce_model
from mangohud.detect import detect_sessions, presets_path, presets_supported, session_alive


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


def _fake_mangoapp(
    proc,
    pid,
    uid,
    environ,
    *,
    starttime=None,
    cwd=None,
    stat_name="mangoapp",
):
    process = proc / str(pid)
    process.mkdir()
    (process / "comm").write_text("mangoapp\n")
    (process / "status").write_text(f"Name:\tmangoapp\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    raw = b"\0".join(f"{key}={value}".encode() for key, value in environ.items()) + b"\0"
    (process / "environ").write_bytes(raw)
    if starttime is not None:
        fields_before_starttime = " ".join(["0"] * 18)
        (process / "stat").write_text(
            f"{pid} ({stat_name}) S {fields_before_starttime} {starttime} 0\n"
        )
    if cwd is not None:
        (process / "cwd").symlink_to(cwd)


def _single_session(tmp_path):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    _fake_mangoapp(
        proc,
        20,
        1000,
        {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"},
        starttime=9001,
        cwd=cwd,
    )
    session = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))[0]
    return proc, session


def test_detect_sessions_returns_complete_ordered_process_identities(tmp_path):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    environ = {
        "STEAM_MANGOAPP_PRESETS_SUPPORTED": "1",
        "MANGOHUD_CONFIGFILE": str(home / "live.conf"),
    }
    _fake_mangoapp(
        proc,
        21,
        1000,
        environ,
        starttime=9002,
        cwd=cwd,
    )
    _fake_mangoapp(
        proc,
        20,
        1000,
        environ,
        starttime=9001,
        cwd=cwd,
        stat_name="mango (worker)",
    )

    sessions = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))

    expected_path = str(home / ".config/MangoHud/presets.conf")
    assert [
        (
            session.pid,
            session.starttime,
            session.uid,
            session.cwd,
            session.presets_path,
            session.presets_supported,
        )
        for session in sessions
    ] == [
        (20, 9001, 1000, str(cwd), expected_path, True),
        (21, 9002, 1000, str(cwd), expected_path, True),
    ]


def test_session_identity_rejects_pid_reuse(tmp_path):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    _fake_mangoapp(
        proc,
        20,
        1000,
        {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"},
        starttime=9001,
        cwd=cwd,
    )
    session = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))[0]
    fields_before_starttime = " ".join(["0"] * 18)
    (proc / "20" / "stat").write_text(
        f"20 (mangoapp) S {fields_before_starttime} 9999 0\n"
    )

    assert session_alive(session, proc_root=str(proc)) is False


def test_detect_sessions_ignores_mangoapp_owned_by_another_user(tmp_path):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    _fake_mangoapp(
        proc,
        10,
        1001,
        {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1", "HOME": "/home/other"},
        starttime=9001,
        cwd=cwd,
    )

    assert detect_sessions(home=str(home), uid=1000, proc_root=str(proc)) == ()


# ---- apply: write presets.conf + honest readback ----

def test_apply_writes_presets_conf_and_reads_it_back(tmp_path):
    path = str(tmp_path / "sub" / "presets.conf")  # parent dir does not exist yet
    model = coerce_model({"metrics": ["fps", "gpu"]})
    on_disk = apply_hud(model, path)
    assert on_disk == build_presets_conf(model)
    assert ownership.read_text(path) == on_disk


def test_apply_rejects_a_readback_that_differs_from_requested_config(
    tmp_path,
    monkeypatch,
):
    path = str(tmp_path / "presets.conf")
    model = coerce_model({"items": [{"kind": "metric", "id": "fps"}]})
    monkeypatch.setattr(
        ownership,
        "write_managed",
        lambda *_args, **_kwargs: ownership.FileMutation("different\n"),
    )

    with pytest.raises(OSError, match="does not match"):
        apply_hud(model, path)


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
    real_write = ownership._write_atomic

    def record_write(candidate, *args, **kwargs):
        writes.append(candidate)
        return real_write(candidate, *args, **kwargs)

    monkeypatch.setattr(ownership, "_write_atomic", record_write)

    on_disk = apply_hud(model, path)

    assert on_disk == build_presets_conf(model)
    assert path not in writes


def test_clear_presets_removes_our_file_and_is_idempotent(tmp_path):
    path = str(tmp_path / "presets.conf")
    apply_hud(coerce_model({"metrics": ["fps"]}), path)
    assert ownership.read_text(path) is not None
    assert clear_presets(path) is True  # hands the overlay back to MangoHud's stock defaults
    assert ownership.read_text(path) is None
    assert clear_presets(path) is True  # already gone — must not raise


def test_apply_restores_a_preexisting_user_presets_file_on_disable(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "# personal MangoHud presets\n[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)

    apply_hud(
        coerce_model({"items": [{"kind": "metric", "id": "fps"}]}),
        path,
        replace_conflict=True,
    )
    assert ownership.read_text(path) != original

    assert clear_presets(path) is True
    assert ownership.read_text(path) == original
    assert not (tmp_path / "presets.conf.pdc-backup").exists()
    assert clear_presets(path) is True
    assert ownership.read_text(path) == original


def test_clear_presets_refuses_to_overwrite_an_external_edit(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "external-before\n"
    external_edit = "external-after\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(
        coerce_model({"items": [{"kind": "metric", "id": "fps"}]}),
        path,
        replace_conflict=True,
    )
    (tmp_path / "presets.conf").write_text(external_edit)

    cleared = clear_presets(path)

    assert cleared is False
    assert ownership.read_text(path) == external_edit
    assert ownership.read_text(f"{path}.pdc-backup") == original


def test_clear_presets_never_deletes_an_unmanaged_file(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\ngpu_stats=1\n"
    (tmp_path / "presets.conf").write_text(original)

    assert clear_presets(path) is True
    assert ownership.read_text(path) == original


def test_failed_restore_keeps_a_retryable_state(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(
        coerce_model({"items": [{"kind": "metric", "id": "fps"}]}),
        path,
        replace_conflict=True,
    )
    real_replace = apply.os.replace

    def fail_backup_restore(source, destination):
        if source == f"{path}.pdc-backup":
            raise PermissionError
        return real_replace(source, destination)

    monkeypatch.setattr(apply.os, "replace", fail_backup_restore)
    assert clear_presets(path) is False
    assert (tmp_path / "presets.conf.pdc-backup").exists()

    monkeypatch.setattr(apply.os, "replace", real_replace)
    assert clear_presets(path) is True
    assert ownership.read_text(path) == original
    assert not (tmp_path / "presets.conf.pdc-managed").exists()


def test_retry_after_restored_backup_only_removes_the_marker(tmp_path, monkeypatch):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    apply_hud(
        coerce_model({"items": [{"kind": "metric", "id": "fps"}]}),
        path,
        replace_conflict=True,
    )
    real_remove = apply.os.remove

    def fail_marker_removal(candidate):
        if candidate == f"{path}.pdc-managed":
            raise PermissionError
        return real_remove(candidate)

    monkeypatch.setattr(apply.os, "remove", fail_marker_removal)
    assert clear_presets(path) is False
    assert ownership.read_text(path) == original
    assert not (tmp_path / "presets.conf.pdc-backup").exists()

    monkeypatch.setattr(apply.os, "remove", real_remove)
    assert clear_presets(path) is True
    assert ownership.read_text(path) == original
    assert not (tmp_path / "presets.conf.pdc-managed").exists()


def test_legacy_marker_does_not_authorize_clear_without_expected_content(tmp_path):
    path = str(tmp_path / "presets.conf")
    content = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(content)
    (tmp_path / "presets.conf.pdc-managed").write_text("1\n")

    assert clear_presets(path) is False
    assert ownership.read_text(path) == content
    assert ownership.read_text(f"{path}.pdc-managed") == "1\n"


def test_unknown_marker_never_authorizes_deletion(tmp_path):
    path = str(tmp_path / "presets.conf")
    original = "[preset 1]\nfps=1\n"
    (tmp_path / "presets.conf").write_text(original)
    (tmp_path / "presets.conf.pdc-managed").write_text("unexpected\n")

    assert clear_presets(path) is False
    assert ownership.read_text(path) == original


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
        apply_hud(
            coerce_model({"items": [{"kind": "metric", "id": "fps"}]}),
            path,
            replace_conflict=True,
        )
    assert ownership.read_text(path) == original
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


def test_reload_requests_every_live_session_from_the_same_snapshot(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd_a = tmp_path / "cwd-a"
    cwd_b = tmp_path / "cwd-b"
    proc.mkdir()
    home.mkdir()
    cwd_a.mkdir()
    cwd_b.mkdir()
    environ = {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"}
    _fake_mangoapp(proc, 20, 1000, environ, starttime=9001, cwd=cwd_a)
    _fake_mangoapp(proc, 21, 1000, environ, starttime=9002, cwd=cwd_b)
    sessions = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))
    calls = []
    monkeypatch.setattr(apply.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mangohudctl")

    def run(command, **kwargs):
        calls.append((command, kwargs["cwd"]))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(apply.subprocess, "run", run)

    result = reload_sessions(sessions, proc_root=str(proc))

    assert result.requested == ((20, 9001), (21, 9002))
    assert result.pending == ()
    assert calls == [
        (["/usr/bin/mangohudctl", "set", "reload_config", "true"], str(cwd_a)),
        (["/usr/bin/mangohudctl", "set", "reload_config", "true"], str(cwd_b)),
    ]


def test_reload_does_not_invoke_a_reused_pid(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    _fake_mangoapp(
        proc,
        20,
        1000,
        {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"},
        starttime=9001,
        cwd=cwd,
    )
    session = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))[0]
    fields_before_starttime = " ".join(["0"] * 18)
    (proc / "20" / "stat").write_text(
        f"20 (mangoapp) S {fields_before_starttime} 9999 0\n"
    )
    calls = []
    monkeypatch.setattr(apply.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mangohudctl")
    monkeypatch.setattr(apply.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    result = reload_sessions((session,), proc_root=str(proc))

    assert result.requested == ()
    assert result.pending == ((20, 9001),)
    assert calls == []


def test_partial_reload_returns_only_failed_identity_as_pending(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    proc.mkdir()
    home.mkdir()
    cwd.mkdir()
    environ = {"STEAM_MANGOAPP_PRESETS_SUPPORTED": "1"}
    _fake_mangoapp(proc, 20, 1000, environ, starttime=9001, cwd=cwd)
    _fake_mangoapp(proc, 21, 1000, environ, starttime=9002, cwd=cwd)
    sessions = detect_sessions(home=str(home), uid=1000, proc_root=str(proc))
    monkeypatch.setattr(apply.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mangohudctl")
    exits = iter((0, 1))
    monkeypatch.setattr(
        apply.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": next(exits)})(),
    )

    result = reload_sessions(sessions, proc_root=str(proc))

    assert result.requested == ((20, 9001),)
    assert result.pending == ((21, 9002),)


def test_reload_without_control_tool_keeps_session_pending(tmp_path, monkeypatch):
    proc, session = _single_session(tmp_path)
    monkeypatch.setattr(apply.shutil, "which", lambda *_args, **_kwargs: None)

    result = reload_sessions((session,), proc_root=str(proc))

    assert result.requested == ()
    assert result.pending == ((20, 9001),)


def test_reload_process_failure_is_non_fatal(tmp_path, monkeypatch):
    proc, session = _single_session(tmp_path)
    monkeypatch.setattr(
        apply.shutil,
        "which",
        lambda *_args, **_kwargs: "/usr/bin/mangohudctl",
    )
    monkeypatch.setattr(
        apply.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("missing")),
    )

    result = reload_sessions((session,), proc_root=str(proc))

    assert result.requested == ()
    assert result.pending == ((20, 9001),)
