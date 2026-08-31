from __future__ import annotations

import hashlib
import json
import multiprocessing
import stat
import time
import zipfile
from pathlib import Path

import pytest

import theme_packages


THEME_ID = "example-theme"
THEME_NAME = "Example Theme"
THEME_VERSION = "1.2.3"
LEGACY_THEME_ID = "hooandee-gallery"
LEGACY_THEME_NAME = "Hooandee Gallery"
EXTENSION_SOURCE = b"module.exports=Object.freeze({abiVersion:1,mount(){return()=>{}}});\n"


class SimulatedProcessLoss(BaseException):
    pass


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
    extension_source: bytes | None = None,
) -> tuple[Path, dict]:
    archive = root / "example-theme.zip"
    marker: dict[str, object] = {
        "schemaVersion": 2,
        "catalogId": catalog_id,
    }
    if extension_source is not None:
        marker["extension"] = {
            "abiVersion": 1,
            "entrypoint": "panel-extension.js",
            "size": len(extension_source),
            "sha256": hashlib.sha256(extension_source).hexdigest(),
        }
    entries = {
        f"{theme_name}/theme.json": json.dumps({
            "name": theme_name,
            "display_name": theme_name,
            "author": "Example Author",
            "version": version,
            "manifest_version": 9,
            "inject": {"tokens.css": ["bigpicture"]},
            "patches": {},
        }).encode(),
        f"{theme_name}/panel-theme.json": json.dumps(marker).encode(),
        f"{theme_name}/tokens.css": b":root { --example-accent: #fff; }\n",
        **(
            {f"{theme_name}/panel-extension.js": extension_source}
            if extension_source is not None
            else {}
        ),
        **(extra_entries or {}),
    }
    with zipfile.ZipFile(archive, "w") as package:
        for name, content in entries.items():
            package.writestr(name, content)
    blob = archive.read_bytes()
    descriptor = {
        "schemaVersion": 1,
        "id": catalog_id,
        "cssLoaderName": theme_name,
        "version": version,
        "artifact": {
            "file": archive.name,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
        },
    }
    return archive, descriptor


def _mark_owned(installed: Path, version: str = THEME_VERSION) -> None:
    (installed / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": version,
        "manifest_version": 9,
        "inject": {"tokens.css": ["bigpicture"]},
        "patches": {},
    }), encoding="utf-8")
    (installed / "panel-theme.json").write_text(json.dumps({
        "schemaVersion": 2,
        "catalogId": THEME_ID,
    }), encoding="utf-8")


def _journal(
    token: str,
    *,
    state: str,
    had_previous: bool,
    previous_version: str | None = None,
    new_receipt: dict[str, object] | None = None,
    previous_receipt: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "token": token,
        "themeId": THEME_ID,
        "themeName": THEME_NAME,
        "version": THEME_VERSION,
        "hadPrevious": had_previous,
        "previousVersion": previous_version,
        "newReceipt": new_receipt,
        "previousReceipt": previous_receipt,
        "state": state,
    }


def _write_owned_tree(path: Path, version: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "theme.json").write_text(json.dumps({
        "name": THEME_NAME,
        "version": version,
        "manifest_version": 9,
        "inject": {"tokens.css": ["bigpicture"]},
        "patches": {},
    }), encoding="utf-8")
    (path / "panel-theme.json").write_text(json.dumps({
        "schemaVersion": 2,
        "catalogId": THEME_ID,
    }), encoding="utf-8")
    (path / "tokens.css").write_text("body {}\n", encoding="utf-8")


def _receipts(themes_root: Path) -> Path:
    return themes_root.parent / "settings" / "theme-extension-receipts.json"


def _prepare_theme_archive(archive, descriptor, themes_root):
    return theme_packages.prepare_theme_archive(
        archive,
        descriptor,
        themes_root,
        receipts_path=_receipts(Path(themes_root)),
    )


def _commit_theme_install(token, themes_root):
    return theme_packages.commit_theme_install(
        token, themes_root, receipts_path=_receipts(Path(themes_root))
    )


def _rollback_theme_install(token, themes_root):
    return theme_packages.rollback_theme_install(
        token, themes_root, receipts_path=_receipts(Path(themes_root))
    )


def _acknowledge_theme_rollback(token, themes_root):
    return theme_packages.acknowledge_theme_rollback(
        token, themes_root, receipts_path=_receipts(Path(themes_root))
    )


def _recover_theme_transactions(themes_root):
    return theme_packages.recover_theme_transactions(
        themes_root, receipts_path=_receipts(Path(themes_root))
    )


def test_theme_mutations_share_a_nonblocking_process_lock(
    tmp_path: Path,
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
        _prepare_theme_archive(
            archive,
            descriptor,
            themes_root,
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

    result = _prepare_theme_archive(archive, descriptor, themes_root)

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


def test_transaction_directory_is_not_visible_before_its_created_journal_is_durable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    original_write_journal = theme_packages._write_journal
    visible_at_first_journal: list[list[Path]] = []

    def observe_first_journal(path: Path, journal: dict[str, object]) -> None:
        if not visible_at_first_journal:
            visible_at_first_journal.append(
                list(tmp_path.glob(".panel-theme-transaction-*"))
            )
        original_write_journal(path, journal)

    monkeypatch.setattr(theme_packages, "_write_journal", observe_first_journal)

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)

    assert visible_at_first_journal == [[]]
    _rollback_theme_install(prepared["transaction"], themes_root)
    _acknowledge_theme_rollback(prepared["transaction"], themes_root)


@pytest.mark.parametrize("had_previous_extension", [False, True])
def test_recovery_removes_only_an_authenticated_created_transaction(
    tmp_path: Path,
    had_previous_extension: bool,
) -> None:
    themes_root = tmp_path / "themes"
    receipt_store = _receipts(themes_root)
    previous_version = None
    previous_receipt = None
    if had_previous_extension:
        archive, descriptor = _write_package(
            tmp_path,
            version="1.2.2",
            extension_source=EXTENSION_SOURCE,
        )
        installed = _prepare_theme_archive(archive, descriptor, themes_root)
        _commit_theme_install(installed["transaction"], themes_root)
        previous_version = "1.2.2"
        previous_receipt = theme_packages._read_receipts(
            receipt_store,
            strict=True,
        )[0]
    else:
        themes_root.mkdir()

    token = "d" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    (work / "extracted").mkdir(parents=True)
    (work / "extracted" / "partial.css").write_text("partial", encoding="utf-8")
    theme_packages._write_journal(
        work / "transaction.json",
        _journal(
            token,
            state="created",
            had_previous=had_previous_extension,
            previous_version=previous_version,
            previous_receipt=previous_receipt,
        ),
    )

    assert _recover_theme_transactions(themes_root) == []
    assert not work.exists()
    assert theme_packages._read_receipts(receipt_store, strict=True) == (
        [previous_receipt] if previous_receipt is not None else []
    )
    if had_previous_extension:
        assert theme_packages._installed_version(themes_root / THEME_NAME) == "1.2.2"
    else:
        assert not (themes_root / THEME_NAME).exists()


def test_recovery_rejects_a_forged_created_transaction_without_deleting_it(
    tmp_path: Path,
) -> None:
    themes_root = tmp_path / "themes"
    themes_root.mkdir()
    token = "e" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    work.mkdir()
    (work / "not-created-by-panel").write_text("keep", encoding="utf-8")
    theme_packages._write_journal(
        work / "transaction.json",
        _journal(token, state="created", had_previous=False),
    )

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _recover_theme_transactions(themes_root)

    assert error.value.code == "invalid_journal"
    assert (work / "not-created-by-panel").read_text(encoding="utf-8") == "keep"


def test_recovery_rejects_a_swapped_transaction_with_an_unrelated_receipt(
    tmp_path: Path,
) -> None:
    themes_root = tmp_path / "themes"
    receipt_store = _receipts(themes_root)
    archive, descriptor = _write_package(
        tmp_path,
        version="1.2.2",
        extension_source=EXTENSION_SOURCE + b"// previous\n",
    )
    previous = _prepare_theme_archive(archive, descriptor, themes_root)
    _commit_theme_install(previous["transaction"], themes_root)
    archive, descriptor = _write_package(
        tmp_path,
        extension_source=EXTENSION_SOURCE,
    )
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    transaction = tmp_path / f".panel-theme-transaction-{prepared['transaction']}"
    forged_receipt = {
        **theme_packages._read_receipts(receipt_store, strict=True)[0],
        "version": "9.9.9",
    }
    theme_packages._write_receipts(receipt_store, [forged_receipt])

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _recover_theme_transactions(themes_root)

    assert error.value.code == "invalid_journal"
    assert theme_packages._installed_version(themes_root / THEME_NAME) == THEME_VERSION
    assert transaction.exists()


@pytest.mark.parametrize(
    ("had_previous", "with_extension", "crash_boundary"),
    [
        (True, False, "rejected"),
        (True, False, "restored"),
        (True, True, "receipt"),
        (True, True, "journal"),
        (False, False, "rejected"),
        (False, True, "receipt"),
        (False, False, "journal"),
    ],
)
def test_recovery_finishes_rollback_after_every_durable_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    had_previous: bool,
    with_extension: bool,
    crash_boundary: str,
) -> None:
    themes_root = tmp_path / "themes"
    receipt_store = _receipts(themes_root)
    previous_receipts: list[dict[str, object]] = []
    if had_previous:
        previous_source = EXTENSION_SOURCE + b"// previous\n" if with_extension else None
        archive, descriptor = _write_package(
            tmp_path,
            version="1.2.2",
            extension_source=previous_source,
        )
        previous = _prepare_theme_archive(archive, descriptor, themes_root)
        _commit_theme_install(previous["transaction"], themes_root)
        previous_receipts = theme_packages._read_receipts(receipt_store, strict=True)

    archive, descriptor = _write_package(
        tmp_path,
        extension_source=EXTENSION_SOURCE if with_extension else None,
    )
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    transaction = tmp_path / f".panel-theme-transaction-{prepared['transaction']}"
    destination = themes_root / THEME_NAME
    original_durable_replace = theme_packages._durable_replace
    original_replace_receipt = theme_packages._replace_receipt
    original_write_journal = theme_packages._write_journal

    def crash_after_replace(source: Path, target: Path) -> None:
        original_durable_replace(source, target)
        if crash_boundary == "rejected" and target == transaction / "rejected":
            raise SimulatedProcessLoss
        if crash_boundary == "restored" and source == transaction / "previous":
            raise SimulatedProcessLoss

    def crash_after_receipt(
        path: Path,
        catalog_id: str,
        receipt: dict[str, object] | None,
    ) -> None:
        original_replace_receipt(path, catalog_id, receipt)
        if crash_boundary == "receipt":
            raise SimulatedProcessLoss

    def crash_after_journal(path: Path, journal: dict[str, object]) -> None:
        original_write_journal(path, journal)
        if crash_boundary == "journal" and journal["state"] == "rolled_back":
            raise SimulatedProcessLoss

    monkeypatch.setattr(theme_packages, "_durable_replace", crash_after_replace)
    monkeypatch.setattr(theme_packages, "_replace_receipt", crash_after_receipt)
    monkeypatch.setattr(theme_packages, "_write_journal", crash_after_journal)

    with pytest.raises(SimulatedProcessLoss):
        _rollback_theme_install(prepared["transaction"], themes_root)

    monkeypatch.setattr(theme_packages, "_durable_replace", original_durable_replace)
    monkeypatch.setattr(theme_packages, "_replace_receipt", original_replace_receipt)
    monkeypatch.setattr(theme_packages, "_write_journal", original_write_journal)

    pending = _recover_theme_transactions(themes_root)

    assert pending == [{
        "transaction": prepared["transaction"],
        "theme_name": THEME_NAME,
        "previous_version": "1.2.2" if had_previous else None,
    }]
    assert theme_packages._read_receipts(receipt_store, strict=True) == previous_receipts
    if had_previous:
        assert theme_packages._installed_version(themes_root / THEME_NAME) == "1.2.2"
    else:
        assert not destination.exists()
    _acknowledge_theme_rollback(prepared["transaction"], themes_root)


def _write_legacy_gallery(installed: Path, version: str = "v0.5.0") -> None:
    installed.mkdir(parents=True, exist_ok=True)
    (installed / "theme.json").write_text(json.dumps({
        "name": LEGACY_THEME_NAME,
        "display_name": LEGACY_THEME_NAME,
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

    result = _prepare_theme_archive(archive, descriptor, themes_root)

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

    committed = _commit_theme_install(result["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


@pytest.mark.parametrize("legacy_version", ["0.7.8", "v0.7.8"])
def test_install_archive_upgrades_a_known_legacy_gallery_preview_marker(
    tmp_path,
    legacy_version,
):
    archive, descriptor = _write_package(
        tmp_path,
        catalog_id=LEGACY_THEME_ID,
        theme_name=LEGACY_THEME_NAME,
        version="0.7.9",
    )
    themes_root = tmp_path / "themes"
    installed = themes_root / LEGACY_THEME_NAME
    _write_legacy_gallery(installed, version=legacy_version)
    preview_marker = {
        "schemaVersion": 1,
        "catalogId": LEGACY_THEME_ID,
        "runtime": {
            "moduleId": "gallery",
            "surfaces": ["library", "library-grid", "game-details", "settings"],
        },
    }
    (installed / "panel-theme.json").write_text(
        json.dumps(preview_marker),
        encoding="utf-8",
    )
    css_loader_state = b'{"active": true, "Color de acento": "Ambrosia"}'
    (installed / "config_USER.json").write_bytes(css_loader_state)

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)

    assert prepared["code"] == "prepared"
    assert prepared["version"] == "0.7.9"
    assert (installed / "config_USER.json").read_bytes() == css_loader_state
    _rollback_theme_install(prepared["transaction"], themes_root)
    assert json.loads((installed / "theme.json").read_text(encoding="utf-8"))[
        "version"
    ] == legacy_version
    assert json.loads((installed / "panel-theme.json").read_text(encoding="utf-8")) == preview_marker
    assert (installed / "config_USER.json").read_bytes() == css_loader_state
    _acknowledge_theme_rollback(prepared["transaction"], themes_root)


@pytest.mark.parametrize("active_content", [True, "yes"])
def test_install_archive_rejects_an_active_legacy_preview_marker(tmp_path, active_content):
    archive, descriptor = _write_package(
        tmp_path,
        catalog_id=LEGACY_THEME_ID,
        theme_name=LEGACY_THEME_NAME,
        version="0.7.9",
    )
    themes_root = tmp_path / "themes"
    installed = themes_root / LEGACY_THEME_NAME
    _write_legacy_gallery(installed, version="0.7.8")
    (installed / "panel-theme.json").write_text(json.dumps({
        "schemaVersion": 1,
        "catalogId": LEGACY_THEME_ID,
        "executableContent": active_content,
    }), encoding="utf-8")
    original_manifest = (installed / "theme.json").read_bytes()

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "identity_mismatch"
    assert (installed / "theme.json").read_bytes() == original_manifest
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

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)

    assert (installed / "config_USER.json").read_bytes() == b'{"active": true}'
    _commit_theme_install(prepared["transaction"], themes_root)


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

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)

    assert swapped is True
    assert (installed / "config_USER.json").read_bytes() == b'{"active": true}'
    _commit_theme_install(prepared["transaction"], themes_root)


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
        _prepare_theme_archive(archive, descriptor, themes_root)

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

    _prepare_theme_archive(archive, descriptor, themes_root)

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

    _prepare_theme_archive(archive, descriptor, themes_root)

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
    _mark_owned(installed, "1.2.2")
    (installed / "old.css").write_text("old", encoding="utf-8")

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    assert not (installed / "old.css").exists()

    rolled_back = _rollback_theme_install(prepared["transaction"], themes_root)

    assert rolled_back == {"ok": True, "code": "rolled_back"}
    assert (installed / "old.css").read_text(encoding="utf-8") == "old"
    assert not (installed / "tokens.css").exists()
    assert list(tmp_path.glob(".panel-theme-transaction-*"))

    _acknowledge_theme_rollback(prepared["transaction"], themes_root)
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_rollback_removes_a_new_theme_that_css_loader_did_not_accept(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"

    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    assert (themes_root / THEME_NAME / "tokens.css").exists()

    _rollback_theme_install(prepared["transaction"], themes_root)

    assert not (themes_root / THEME_NAME).exists()
    _acknowledge_theme_rollback(prepared["transaction"], themes_root)


def test_acknowledged_rollback_stays_terminal_when_cleanup_is_interrupted(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    _rollback_theme_install(prepared["transaction"], themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(theme_packages.shutil, "rmtree", lambda *args, **kwargs: None)

    acknowledged = _acknowledge_theme_rollback(
        prepared["transaction"], themes_root
    )

    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "acknowledged"
    assert theme_packages._active_transaction(themes_root) is False
    assert _recover_theme_transactions(themes_root) == []


def test_committed_install_stays_terminal_when_cleanup_is_interrupted(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(theme_packages.shutil, "rmtree", lambda *args, **kwargs: None)

    committed = _commit_theme_install(prepared["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "committed"
    assert theme_packages._active_transaction(themes_root) is False
    assert _recover_theme_transactions(themes_root) == []


def test_commit_reports_success_when_only_terminal_cleanup_fails(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(
        theme_packages,
        "_durable_remove_tree",
        lambda _path: (_ for _ in ()).throw(OSError("simulated cleanup failure")),
    )

    committed = _commit_theme_install(prepared["transaction"], themes_root)

    assert committed == {"ok": True, "code": "committed"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "committed"


def test_acknowledge_reports_success_when_only_terminal_cleanup_fails(tmp_path, monkeypatch):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    prepared = _prepare_theme_archive(archive, descriptor, themes_root)
    _rollback_theme_install(prepared["transaction"], themes_root)
    transaction = next(tmp_path.glob(".panel-theme-transaction-*"))

    monkeypatch.setattr(
        theme_packages,
        "_durable_remove_tree",
        lambda _path: (_ for _ in ()).throw(OSError("simulated cleanup failure")),
    )

    acknowledged = _acknowledge_theme_rollback(
        prepared["transaction"], themes_root
    )

    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert json.loads((transaction / "transaction.json").read_text(encoding="utf-8"))[
        "state"
    ] == "acknowledged"


def test_recovery_rolls_back_an_interrupted_prepared_transaction(tmp_path):
    archive, descriptor = _write_package(
        tmp_path,
        catalog_id=LEGACY_THEME_ID,
        theme_name=LEGACY_THEME_NAME,
        version="0.7.9",
    )
    themes_root = tmp_path / "themes"
    installed = themes_root / LEGACY_THEME_NAME
    _write_legacy_gallery(installed)
    (installed / "old.css").write_text("old", encoding="utf-8")
    _prepare_theme_archive(archive, descriptor, themes_root)

    recovered = _recover_theme_transactions(themes_root)

    assert recovered == [{
        "transaction": recovered[0]["transaction"],
        "theme_name": LEGACY_THEME_NAME,
        "previous_version": "v0.5.0",
    }]
    assert (installed / "old.css").read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".panel-theme-transaction-*"))

    _acknowledge_theme_rollback(recovered[0]["transaction"], themes_root)
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_recovery_cleans_a_staged_journal_when_the_previous_theme_was_never_moved(tmp_path):
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    _write_owned_tree(installed, "0.5.0")
    token = "a" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    work.mkdir()
    theme_packages._write_journal(work / "transaction.json", _journal(
        token,
        state="staged",
        had_previous=True,
        previous_version="0.5.0",
    ))

    assert _recover_theme_transactions(themes_root) == []
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
        **_journal(
            token,
            state="swapped",
            had_previous=True,
            previous_version="0.5.0",
        ),
        "themeName": "Third Party Theme",
    })

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _recover_theme_transactions(themes_root)

    assert error.value.code == "invalid_journal"
    assert marker.read_text(encoding="utf-8") == "third-party"
    assert work.exists()


def test_journal_transition_ignores_a_stale_temporary_file_from_a_crash(tmp_path):
    work = tmp_path / ".panel-theme-transaction-test"
    work.mkdir()
    (work / "transaction.tmp").write_text("interrupted", encoding="utf-8")
    journal = _journal("a" * 43, state="staged", had_previous=False)

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
    _write_owned_tree(backup, "0.5.0")
    _write_owned_tree(extracted, THEME_VERSION)
    theme_packages._write_journal(work / "transaction.json", _journal(
        token,
        state="staged",
        had_previous=True,
        previous_version="0.5.0",
    ))

    assert _recover_theme_transactions(themes_root) == []
    assert (themes_root / THEME_NAME / "theme.json").exists()
    assert not work.exists()


def test_recovery_requires_css_loader_ack_if_process_stops_after_the_second_swap(tmp_path):
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    _write_owned_tree(installed, THEME_VERSION)
    token = "c" * 43
    work = tmp_path / f".panel-theme-transaction-{token}"
    backup = work / "previous"
    _write_owned_tree(backup, "0.5.0")
    theme_packages._write_journal(work / "transaction.json", _journal(
        token,
        state="staged",
        had_previous=True,
        previous_version="0.5.0",
    ))

    recoveries = _recover_theme_transactions(themes_root)

    assert recoveries == [{
        "transaction": token,
        "theme_name": THEME_NAME,
        "previous_version": "0.5.0",
    }]
    assert json.loads((installed / "theme.json").read_text(encoding="utf-8"))["version"] == "0.5.0"
    _acknowledge_theme_rollback(token, themes_root)


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
        _prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == code
    assert marker.read_text(encoding="utf-8") == "keep"


def test_install_archive_cannot_replace_an_unowned_theme_folder(tmp_path):
    third_party_name = "Third Party Theme"
    archive, descriptor = _write_package(tmp_path, theme_name=third_party_name)
    descriptor["cssLoaderName"] = third_party_name
    themes_root = tmp_path / "themes"
    installed = themes_root / third_party_name
    installed.mkdir(parents=True)
    marker = installed / "keep.css"
    marker.write_bytes(b"third-party")

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "identity_mismatch"
    assert marker.read_bytes() == b"third-party"
    assert not list(tmp_path.glob(".panel-theme-transaction-*"))


def test_install_archive_never_replaces_an_unowned_homonymous_folder(tmp_path):
    archive, descriptor = _write_package(tmp_path)
    themes_root = tmp_path / "themes"
    installed = themes_root / THEME_NAME
    installed.mkdir(parents=True)
    original_theme = b'{"name":"Example Theme","author":"Third Party"}'
    (installed / "theme.json").write_bytes(original_theme)
    marker = installed / "keep.css"
    marker.write_bytes(b"third-party")

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _prepare_theme_archive(archive, descriptor, themes_root)

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
        _prepare_theme_archive(archive, descriptor, themes_root)

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
        _prepare_theme_archive(archive, descriptor, tmp_path / "themes")

    assert error.value.code == "unsafe_archive"


def test_install_archive_rejects_packaged_css_loader_state(tmp_path):
    archive, descriptor = _write_package(
        tmp_path,
        extra_entries={f"{THEME_NAME}/config_ROOT.json": b'{"active": true}'},
    )
    descriptor["artifact"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    descriptor["artifact"]["size"] = archive.stat().st_size

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _prepare_theme_archive(archive, descriptor, tmp_path / "themes")

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

    def fail_install(source, destination):
        if Path(source).name == THEME_NAME and Path(destination) == installed:
            raise OSError("simulated atomic swap failure")
        return original_replace(source, destination)

    monkeypatch.setattr(theme_packages.os, "replace", fail_install)

    with pytest.raises(theme_packages.ThemePackageError) as error:
        _prepare_theme_archive(archive, descriptor, themes_root)

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
        _prepare_theme_archive(archive, descriptor, themes_root)

    assert error.value.code == "rollback_failed"
    transactions = list(tmp_path.glob(".panel-theme-transaction-*"))
    assert len(transactions) == 1
    assert (transactions[0] / "previous" / "keep.css").exists()

    monkeypatch.setattr(theme_packages.os, "replace", original_replace)
    assert _recover_theme_transactions(themes_root) == []
    assert marker.read_text(encoding="utf-8") == "keep"
