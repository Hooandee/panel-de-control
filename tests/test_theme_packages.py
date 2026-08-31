import hashlib
import json
import multiprocessing
import stat
import time
import zipfile
from pathlib import Path

import pytest

import theme_packages


THEME_ID = "hooandee-gallery"
THEME_NAME = "Hooandee Gallery"
THEME_VERSION = "0.7.6"


def _hold_theme_mutation_lock(
    themes_root: str,
    ready: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    with theme_packages._mutation_lock(Path(themes_root)):
        ready.set()
        release.wait(timeout=5)


def _write_package(
    root: Path,
    *,
    catalog_id: str = THEME_ID,
    theme_name: str = THEME_NAME,
    version: str = THEME_VERSION,
    extra_entries: dict[str, bytes] | None = None,
) -> tuple[Path, dict]:
    archive = root / "gallery.zip"
    entries = {
        f"{theme_name}/theme.json": json.dumps({
            "name": theme_name,
            "display_name": theme_name,
            "author": "Hooandee",
            "version": version,
            "manifest_version": 9,
            "inject": {"tokens.css": ["bigpicture"]},
        }).encode(),
        f"{theme_name}/panel-theme.json": json.dumps({
            "schemaVersion": 1,
            "catalogId": catalog_id,
        }).encode(),
        f"{theme_name}/tokens.css": b":root { --gallery-accent: #fff; }\n",
        **(extra_entries or {}),
    }
    with zipfile.ZipFile(archive, "w") as package:
        for name, content in entries.items():
            package.writestr(name, content)
    blob = archive.read_bytes()
    descriptor = {
        "schemaVersion": 1,
        "id": THEME_ID,
        "cssLoaderName": THEME_NAME,
        "version": THEME_VERSION,
        "artifact": {
            "file": archive.name,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
        },
    }
    return archive, descriptor


def _mark_owned(installed: Path) -> None:
    (installed / "panel-theme.json").write_text(json.dumps({
        "schemaVersion": 1,
        "catalogId": THEME_ID,
    }), encoding="utf-8")


@pytest.mark.parametrize(
    "profile",
    [
        theme_packages.PackageProfile.BUNDLED_COMPAT,
        theme_packages.PackageProfile.REMOTE_V1,
    ],
)
def test_theme_mutations_share_a_nonblocking_process_lock(
    tmp_path: Path,
    profile: theme_packages.PackageProfile,
) -> None:
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_theme_mutation_lock,
        args=(str(themes_root), ready, release),
    )
    process.start()
    assert ready.wait(timeout=2)

    started = time.monotonic()
    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(
            archive,
            descriptor,
            themes_root,
            profile=profile,
        )

    assert error.value.code == "transaction_busy"
    assert time.monotonic() - started < 0.5
    release.set()
    process.join(timeout=2)
    assert process.exitcode == 0


def test_process_lock_is_released_when_its_owner_exits(tmp_path: Path) -> None:
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_theme_mutation_lock,
        args=(str(themes_root), ready, release),
    )
    process.start()
    assert ready.wait(timeout=2)
    release.set()
    process.join(timeout=2)
    assert process.exitcode == 0

    result = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert result["code"] == "prepared"


def test_journal_replace_flushes_its_containing_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flushed: list[Path] = []
    monkeypatch.setattr(theme_packages, "_fsync_directory", flushed.append)

    theme_packages._write_journal(tmp_path / "transaction.json", {"state": "staged"})

    assert flushed == [tmp_path]


def test_durable_replace_flushes_both_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source" / "theme"
    destination = tmp_path / "destination" / "theme"
    source.mkdir(parents=True)
    destination.parent.mkdir()
    flushed: list[Path] = []
    monkeypatch.setattr(theme_packages, "_fsync_directory", flushed.append)

    theme_packages._durable_replace(source, destination)

    assert flushed == [source.parent, destination.parent]
    assert destination.is_dir()


def _write_legacy_gallery(installed: Path, version: str = "v0.5.0") -> None:
    installed.mkdir(parents=True, exist_ok=True)
    (installed / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "display_name": THEME_NAME,
        "author": "Hooandee",
        "version": version,
        "target": "System-Wide",
        "manifest_version": 9,
        "inject": {"tokens.css": ["bigpicture"]},
    }), encoding="utf-8")
    for filename in ("tokens.css", "home.css", "system.css", "settings.css", "qam.css"):
        (installed / filename).write_text("legacy", encoding="utf-8")


def test_install_archive_replaces_the_owned_theme_as_one_complete_tree(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    (installed / "stale.css").write_text("stale", encoding="utf-8")
    css_loader_state = b'{"active": true, "Color de acento": "Salvia"}'
    user_state = b'{"active": false, "Modo claro": "Automatico"}'
    (installed / "config_ROOT.json").write_bytes(css_loader_state)
    (installed / "config_USER.json").write_bytes(user_state)

    result = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert result["ok"] is True
    assert result["code"] == "prepared"
    assert result["theme_id"] == THEME_ID
    assert result["theme_name"] == THEME_NAME
    assert result["version"] == THEME_VERSION
    assert isinstance(result["transaction"], str)
    assert not (installed / "stale.css").exists()
    assert (installed / "tokens.css").read_text(encoding="utf-8").startswith(":root")
    assert (installed / "config_ROOT.json").read_bytes() == css_loader_state
    assert (installed / "config_USER.json").read_bytes() == user_state

    committed = theme_packages.commit_theme_install(result["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_css_loader_state_cannot_be_swapped_to_a_symlink_during_copy(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    state = installed / "config_USER.json"
    state.write_bytes(b'{"active": true}')
    secret = tmp_path / "root-secret"
    secret.write_bytes(b"must-not-be-copied")
    original_copy = theme_packages.shutil.copy2

    def swap_then_copy(source, destination):
        state.unlink()
        state.symlink_to(secret)
        return original_copy(source, destination)

    monkeypatch.setattr(theme_packages.shutil, "copy2", swap_then_copy)

    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert (installed / "config_USER.json").read_bytes() == b'{"active": true}'
    theme_packages.commit_theme_install(prepared["transaction"], themes_root)


def test_css_loader_state_open_descriptor_survives_a_path_swap(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    state = installed / "config_USER.json"
    state.write_bytes(b'{"active": true}')
    secret = tmp_path / "root-secret"
    secret.write_bytes(b"must-not-be-copied")
    original_open = theme_packages.os.open
    swapped = False

    def open_then_swap(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        descriptor_fd = original_open(path, flags, mode, dir_fd=dir_fd)
        if path == "config_USER.json" and dir_fd is not None and not swapped:
            swapped = True
            theme_packages.os.unlink(path, dir_fd=dir_fd)
            theme_packages.os.symlink(secret, path, dir_fd=dir_fd)
        return descriptor_fd

    monkeypatch.setattr(theme_packages.os, "open", open_then_swap)

    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert swapped is True
    assert (installed / "config_USER.json").read_bytes() == b'{"active": true}'
    theme_packages.commit_theme_install(prepared["transaction"], themes_root)


def test_css_loader_state_rejects_an_existing_symlink(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    secret = tmp_path / "root-secret"
    secret.write_bytes(b"must-not-be-copied")
    (installed / "config_USER.json").symlink_to(secret)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "state_invalid"
    assert secret.read_bytes() == b"must-not-be-copied"


def test_install_hands_the_complete_tree_to_the_css_loader_owner(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    themes_root.mkdir()
    owner = themes_root.stat()
    handoffs: list[tuple[Path, int, int]] = []
    monkeypatch.setattr(
        theme_packages,
        "_set_tree_ownership",
        lambda path, uid, gid: handoffs.append((path, uid, gid)),
        raising=False,
    )

    theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert len(handoffs) == 1
    assert handoffs[0][0].name == THEME_NAME
    assert handoffs[0][1:] == (owner.st_uid, owner.st_gid)


def test_missing_themes_root_inherits_its_parent_owner(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    css_loader_home = tmp_path / "css-loader-home"
    css_loader_home.mkdir()
    themes_root = css_loader_home / "themes"
    owner = css_loader_home.stat()
    ownership_changes: list[tuple[Path, int, int]] = []
    original_chown = theme_packages.os.chown

    def record_chown(path, uid, gid, *, follow_symlinks=True):
        ownership_changes.append((Path(path), uid, gid))
        original_chown(path, uid, gid, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(theme_packages.os, "chown", record_chown)

    theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert (themes_root, owner.st_uid, owner.st_gid) in ownership_changes


def test_tree_ownership_handoff_covers_every_directory_and_file(tmp_path, monkeypatch):
    tree = tmp_path / "theme"
    nested = tree / "options"
    nested.mkdir(parents=True)
    (tree / "theme.json").write_text("{}", encoding="utf-8")
    (nested / "choice.css").write_text("body {}", encoding="utf-8")
    calls: list[tuple[Path, int, int, bool]] = []
    monkeypatch.setattr(
        theme_packages.os,
        "chown",
        lambda path, uid, gid, *, follow_symlinks: calls.append(
            (Path(path), uid, gid, follow_symlinks)
        ),
    )

    theme_packages._set_tree_ownership(tree, 12_345, 54_321)

    assert {path.relative_to(tree).as_posix() for path, *_ in calls} == {
        ".",
        "options",
        "options/choice.css",
        "theme.json",
    }
    assert all((uid, gid, follow) == (12_345, 54_321, False) for _, uid, gid, follow in calls)


def test_rollback_restores_the_complete_previous_theme_after_prepare(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    (installed / "old.css").write_text("old", encoding="utf-8")

    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    assert not (installed / "old.css").exists()

    rolled_back = theme_packages.rollback_theme_install(prepared["transaction"], themes_root)

    assert rolled_back == {"ok": True, "code": "rolled_back"}
    assert (installed / "old.css").read_text(encoding="utf-8") == "old"
    assert not (installed / "tokens.css").exists()
    assert list(tmp_path.glob(".panel-theme-transaction-*"))

    theme_packages.acknowledge_theme_rollback(prepared["transaction"], themes_root)
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_rollback_removes_a_new_theme_that_css_loader_did_not_accept(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"

    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    assert (themes_root / THEME_NAME / "tokens.css").exists()

    theme_packages.rollback_theme_install(prepared["transaction"], themes_root)

    assert not (themes_root / THEME_NAME).exists()
    theme_packages.acknowledge_theme_rollback(prepared["transaction"], themes_root)


def test_acknowledged_rollback_stays_terminal_when_cleanup_is_interrupted(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    theme_packages.rollback_theme_install(prepared["transaction"], themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(theme_packages.shutil, "rmtree", lambda *args, **kwargs: None)

    acknowledged = theme_packages.acknowledge_theme_rollback(
        prepared["transaction"], themes_root
    )

    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "acknowledged"
    assert theme_packages._active_transaction(themes_root) is False
    assert theme_packages.recover_theme_transactions(themes_root) == []


def test_committed_install_stays_terminal_when_cleanup_is_interrupted(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(theme_packages.shutil, "rmtree", lambda *args, **kwargs: None)

    committed = theme_packages.commit_theme_install(prepared["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "committed"
    assert theme_packages._active_transaction(themes_root) is False
    assert theme_packages.recover_theme_transactions(themes_root) == []


def test_commit_reports_success_when_only_terminal_cleanup_fails(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(
        theme_packages,
        "_durable_remove_tree",
        lambda _path: (_ for _ in ()).throw(OSError("simulated cleanup failure")),
    )

    committed = theme_packages.commit_theme_install(prepared["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "committed"


def test_acknowledge_reports_success_when_only_terminal_cleanup_fails(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = theme_packages.prepare_theme_archive(archive, descriptor, themes_root)
    theme_packages.rollback_theme_install(prepared["transaction"], themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(
        theme_packages,
        "_durable_remove_tree",
        lambda _path: (_ for _ in ()).throw(OSError("simulated cleanup failure")),
    )

    acknowledged = theme_packages.acknowledge_theme_rollback(
        prepared["transaction"], themes_root
    )

    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "acknowledged"


def test_recovery_rolls_back_an_interrupted_prepared_transaction(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    _write_legacy_gallery(installed)
    (installed / "old.css").write_text("old", encoding="utf-8")
    theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    recovered = theme_packages.recover_theme_transactions(themes_root)

    assert recovered == [{
        "transaction": recovered[0]["transaction"],
        "theme_name": THEME_NAME,
        "previous_version": "v0.5.0",
    }]
    assert (installed / "old.css").read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".panel-theme-transaction-*"))

    theme_packages.acknowledge_theme_rollback(recovered[0]["transaction"], themes_root)
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_recovery_cleans_a_staged_journal_when_the_previous_theme_was_never_moved(tmp_path):
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    (installed / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": "0.5.0",
    }), encoding="utf-8")
    token = "a" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    work.mkdir()
    theme_packages._write_journal(work / "transaction.json", {
        "schemaVersion": 1,
        "token": token,
        "themeId": THEME_ID,
        "themeName": THEME_NAME,
        "version": THEME_VERSION,
        "hadPrevious": True,
        "state": "staged",
    })

    assert theme_packages.recover_theme_transactions(themes_root) == []
    assert (installed / "theme.json").exists()
    assert not work.exists()


def test_recovery_never_mutates_a_theme_not_owned_by_panel(tmp_path):
    themes_root = tmp_path / "themes"
    installed = themes_root / "Third Party Theme"
    installed.mkdir(parents=True)
    marker = installed / "keep.css"
    marker.write_text("third-party", encoding="utf-8")
    token = "z" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    work.mkdir()
    theme_packages._write_journal(work / "transaction.json", {
        "schemaVersion": 1,
        "token": token,
        "themeId": THEME_ID,
        "themeName": "Third Party Theme",
        "version": THEME_VERSION,
        "hadPrevious": True,
        "state": "swapped",
    })

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.recover_theme_transactions(themes_root)

    assert error.value.code == "invalid_journal"
    assert marker.read_text(encoding="utf-8") == "third-party"
    assert work.exists()


def test_journal_transition_ignores_a_stale_temporary_file_from_a_crash(tmp_path):
    work = tmp_path / ".panel-theme-transaction-test"
    work.mkdir()
    (work / "transaction.tmp").write_text("interrupted", encoding="utf-8")
    journal = {
        "schemaVersion": 1,
        "token": "a" * 43,
        "themeId": THEME_ID,
        "themeName": THEME_NAME,
        "version": THEME_VERSION,
        "hadPrevious": False,
        "state": "staged",
    }

    theme_packages._write_journal(work / "transaction.json", journal)
    theme_packages._write_journal(work / "transaction.json", {**journal, "state": "swapped"})

    assert json.loads((work / "transaction.json").read_text(encoding="utf-8"))["state"] == "swapped"


def test_recovery_restores_backup_if_process_stops_between_the_two_swaps(tmp_path):
    themes_root = tmp_path / "themes"
    themes_root.mkdir()
    token = "b" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    backup = work / "previous"
    extracted = work / "extracted" / THEME_NAME
    backup.mkdir(parents=True)
    extracted.mkdir(parents=True)
    (backup / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": "0.5.0",
    }), encoding="utf-8")
    theme_packages._write_journal(work / "transaction.json", {
        "schemaVersion": 1,
        "token": token,
        "themeId": THEME_ID,
        "themeName": THEME_NAME,
        "version": THEME_VERSION,
        "hadPrevious": True,
        "state": "staged",
    })

    assert theme_packages.recover_theme_transactions(themes_root) == []
    assert (themes_root / THEME_NAME / "theme.json").exists()
    assert not work.exists()


def test_recovery_requires_css_loader_ack_if_process_stops_after_the_second_swap(tmp_path):
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    (installed / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": THEME_VERSION,
    }), encoding="utf-8")
    token = "c" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    backup = work / "previous"
    backup.mkdir(parents=True)
    (backup / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": "0.5.0",
    }), encoding="utf-8")
    theme_packages._write_journal(work / "transaction.json", {
        "schemaVersion": 1,
        "token": token,
        "themeId": THEME_ID,
        "themeName": THEME_NAME,
        "version": THEME_VERSION,
        "hadPrevious": True,
        "state": "staged",
    })

    recoveries = theme_packages.recover_theme_transactions(themes_root)

    assert recoveries == [{
        "transaction": token,
        "theme_name": THEME_NAME,
        "previous_version": "0.5.0",
    }]
    assert json.loads((installed / "theme.json").read_text(encoding="utf-8"))["version"] == "0.5.0"
    theme_packages.acknowledge_theme_rollback(token, themes_root)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda archive, descriptor: descriptor["artifact"].update(sha256="0" * 64), "hash_mismatch"),
        (lambda archive, descriptor: descriptor["artifact"].update(size=archive.stat().st_size + 1), "size_mismatch"),
        (lambda archive, descriptor: descriptor.update(version="0.6.1"), "identity_mismatch"),
    ],
)
def test_install_archive_rejects_unverified_packages_without_touching_existing_theme(
    tmp_path,
    mutate,
    code,
):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    marker = installed / "keep.css"
    marker.write_text("keep", encoding="utf-8")
    mutate(archive, descriptor)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == code
    assert marker.read_text(encoding="utf-8") == "keep"


def test_install_archive_cannot_target_a_third_party_theme_name(tmp_path):
    third_party_name = "Third Party Theme"
    archive, descriptor = _write_package(tmp_path, theme_name=third_party_name)
    descriptor["cssLoaderName"] = third_party_name
    themes_root = tmp_path / "themes"
    installed = themes_root / third_party_name
    installed.mkdir(parents=True)
    marker = installed / "keep.css"
    marker.write_bytes(b"third-party")

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "identity_mismatch"
    assert marker.read_bytes() == b"third-party"
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_install_archive_never_replaces_an_unowned_homonymous_folder(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    original_theme = b'{"name":"Hooandee Gallery","author":"Third Party"}'
    (installed / "theme.json").write_bytes(original_theme)
    marker = installed / "keep.css"
    marker.write_bytes(b"third-party")

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "identity_mismatch"
    assert (installed / "theme.json").read_bytes() == original_theme
    assert marker.read_bytes() == b"third-party"
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_install_archive_rejects_path_escape_without_writing_outside_theme_root(tmp_path):
    archive, descriptor = _write_package(
        tmp_path,
        extra_entries={f"{THEME_NAME}/../../escaped.css": b"escape"},
    )
    descriptor["artifact"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    descriptor["artifact"]["size"] = archive.stat().st_size
    themes_root = tmp_path / "themes"

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "unsafe_archive"
    assert not (tmp_path / "escaped.css").exists()


def test_install_archive_rejects_symlinks(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    with zipfile.ZipFile(archive, "a") as package:
        link = zipfile.ZipInfo(f"{THEME_NAME}/linked.css")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(link, "tokens.css")
    descriptor["artifact"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    descriptor["artifact"]["size"] = archive.stat().st_size

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, tmp_path / "themes")

    assert error.value.code == "unsafe_archive"


def test_install_archive_rejects_packaged_css_loader_state(tmp_path):
    archive, descriptor = _write_package(
        tmp_path,
        extra_entries={f"{THEME_NAME}/config_ROOT.json": b'{"active": true}'},
    )
    descriptor["artifact"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    descriptor["artifact"]["size"] = archive.stat().st_size

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, tmp_path / "themes")

    assert error.value.code == "unsafe_archive"


def test_install_archive_restores_previous_theme_when_atomic_swap_fails(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    marker = installed / "keep.css"
    marker.write_text("keep", encoding="utf-8")
    original_replace = theme_packages.os.replace
    calls = 0

    def fail_install(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated atomic swap failure")
        return original_replace(source, destination)

    monkeypatch.setattr(theme_packages.os, "replace", fail_install)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "install_failed"
    assert marker.read_text(encoding="utf-8") == "keep"


def test_failed_immediate_rollback_keeps_the_backup_for_startup_recovery(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    _mark_owned(installed)
    marker = installed / "keep.css"
    marker.write_text("keep", encoding="utf-8")
    original_replace = theme_packages.os.replace

    def fail_install_and_restore(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.name == THEME_NAME and destination_path == installed:
            raise OSError("simulated install failure")
        if source_path.name == "previous" and destination_path == installed:
            raise OSError("simulated immediate rollback failure")
        return original_replace(source, destination)

    monkeypatch.setattr(theme_packages.os, "replace", fail_install_and_restore)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "rollback_failed"
    transactions = list(tmp_path.glob(".panel-theme-transaction-*"))
    assert len(transactions) == 1
    assert (transactions[0] / "previous" / "keep.css").exists()

    monkeypatch.setattr(theme_packages.os, "replace", original_replace)
    assert theme_packages.recover_theme_transactions(themes_root) == []
    assert marker.read_text(encoding="utf-8") == "keep"


def test_install_bundled_theme_accepts_only_registered_package_ids(tmp_path):
    plugin_root = tmp_path / "plugin"
    packages = plugin_root / "theme-packages"
    packages.mkdir(parents=True)
    archive, descriptor = _write_package(packages)
    (packages / "gallery.json").write_text(json.dumps(descriptor), encoding="utf-8")

    result = theme_packages.prepare_bundled_theme(
        THEME_ID,
        plugin_root=plugin_root,
        themes_root=tmp_path / "themes",
    )

    assert result["ok"] is True
    with pytest.raises(theme_packages.ThemePackageError) as error:
        theme_packages.prepare_bundled_theme(
            "third-party-theme",
            plugin_root=plugin_root,
            themes_root=tmp_path / "themes",
        )
    assert error.value.code == "unsupported_theme"
