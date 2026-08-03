import hashlib
import json
import os

import pytest

from mangohud.ownership import (
    HudOwnershipConflict,
    read_text,
    restore_managed,
    write_managed,
)


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _write_marker(path, phase, managed, rollback, previous=None):
    marker = {
        "version": 1,
        "phase": phase,
        "managed_sha256": _hash(managed),
        "rollback": {
            "present": rollback is not None,
            "sha256": _hash(rollback) if rollback is not None else None,
        },
    }
    if previous is not None:
        marker["previous_sha256"] = _hash(previous)
    with open(f"{path}.pdc-managed", "w") as handle:
        json.dump(marker, handle)


def test_update_refuses_external_edit_without_touching_backup(tmp_path):
    path = str(tmp_path / "presets.conf")
    (tmp_path / "presets.conf").write_text("external-before\n")
    write_managed(path, "pdc-one\n")
    (tmp_path / "presets.conf").write_text("external-after\n")
    backup_before = read_text(f"{path}.pdc-backup")

    with pytest.raises(HudOwnershipConflict) as error:
        write_managed(path, "pdc-two\n")

    assert error.value.reason == "managed_content_mismatch"
    assert read_text(path) == "external-after\n"
    assert read_text(f"{path}.pdc-backup") == backup_before


def test_restore_refuses_missing_managed_file(tmp_path):
    path = str(tmp_path / "presets.conf")
    write_managed(path, "pdc\n")
    os.remove(path)

    with pytest.raises(HudOwnershipConflict) as error:
        restore_managed(path)

    assert error.value.reason == "managed_content_missing"
    assert read_text(f"{path}.pdc-managed") is not None


def test_installing_with_rollback_content_resumes_without_losing_external_file(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    desired = "pdc\n"
    (tmp_path / "presets.conf").write_text(external)
    _write_marker(path, "installing", desired, external)

    result = write_managed(path, desired)

    assert result.content == desired
    assert read_text(path) == desired
    assert read_text(f"{path}.pdc-backup") == external
    assert json.loads(read_text(f"{path}.pdc-managed"))["phase"] == "managed"


def test_installing_with_managed_content_finalizes_and_preserves_rollback(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    desired = "pdc\n"
    (tmp_path / "presets.conf").write_text(desired)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(path, "installing", desired, external)

    write_managed(path, desired)
    restored = restore_managed(path)

    assert restored.content == external
    assert read_text(path) == external


def test_updating_with_previous_content_finishes_the_new_write(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    previous = "pdc-one\n"
    desired = "pdc-two\n"
    (tmp_path / "presets.conf").write_text(previous)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(path, "updating", desired, external, previous=previous)

    result = write_managed(path, desired)

    assert result.content == desired
    assert read_text(f"{path}.pdc-backup") == external
    assert json.loads(read_text(f"{path}.pdc-managed"))["phase"] == "managed"


def test_updating_with_new_content_finalizes_without_rewriting_rollback(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    previous = "pdc-one\n"
    desired = "pdc-two\n"
    (tmp_path / "presets.conf").write_text(desired)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(path, "updating", desired, external, previous=previous)

    write_managed(path, desired)
    restored = restore_managed(path)

    assert restored.content == external
    assert read_text(path) == external


def test_restoring_with_rollback_already_in_place_only_removes_marker(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    managed = "pdc\n"
    (tmp_path / "presets.conf").write_text(external)
    _write_marker(path, "restoring", managed, external)

    result = restore_managed(path)

    assert result.content == external
    assert read_text(path) == external
    assert read_text(f"{path}.pdc-managed") is None


def test_restoring_without_rollback_and_missing_managed_file_finalizes(tmp_path):
    path = str(tmp_path / "presets.conf")
    _write_marker(path, "restoring", "pdc\n", None)

    result = restore_managed(path)

    assert result.content is None
    assert read_text(path) is None
    assert read_text(f"{path}.pdc-managed") is None


def test_legacy_marker_migrates_only_when_content_matches_desired(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    desired = "pdc\n"
    (tmp_path / "presets.conf").write_text(desired)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    (tmp_path / "presets.conf.pdc-managed").write_text("managed\n")

    result = write_managed(path, desired)

    marker = json.loads(read_text(f"{path}.pdc-managed"))
    assert result.content == desired
    assert marker["version"] == 1
    assert marker["phase"] == "managed"
    assert marker["rollback"]["sha256"] == _hash(external)


def test_legacy_marker_mismatch_preserves_all_files_byte_for_byte(tmp_path):
    path = str(tmp_path / "presets.conf")
    current = "external-edit\n"
    backup = "external-before\n"
    marker = "managed\n"
    (tmp_path / "presets.conf").write_text(current)
    (tmp_path / "presets.conf.pdc-backup").write_text(backup)
    (tmp_path / "presets.conf.pdc-managed").write_text(marker)

    with pytest.raises(HudOwnershipConflict) as error:
        write_managed(path, "pdc\n")

    assert error.value.reason == "legacy_content_mismatch"
    assert read_text(path) == current
    assert read_text(f"{path}.pdc-backup") == backup
    assert read_text(f"{path}.pdc-managed") == marker


def test_replace_conflict_adopts_current_external_content_as_new_rollback(tmp_path):
    path = str(tmp_path / "presets.conf")
    (tmp_path / "presets.conf").write_text("external-before\n")
    write_managed(path, "pdc-one\n")
    (tmp_path / "presets.conf").write_text("external-after\n")

    result = write_managed(path, "pdc-two\n", replace_conflict=True)

    assert result.content == "pdc-two\n"
    assert read_text(f"{path}.pdc-backup") == "external-after\n"
    assert restore_managed(path).content == "external-after\n"


def test_unknown_json_phase_never_authorizes_a_write(tmp_path):
    path = str(tmp_path / "presets.conf")
    current = "pdc-one\n"
    backup = "external\n"
    (tmp_path / "presets.conf").write_text(current)
    (tmp_path / "presets.conf.pdc-backup").write_text(backup)
    _write_marker(path, "future-phase", current, backup)
    marker_before = read_text(f"{path}.pdc-managed")

    with pytest.raises(HudOwnershipConflict) as error:
        write_managed(path, "pdc-two\n")

    assert error.value.reason == "marker_invalid"
    assert read_text(path) == current
    assert read_text(f"{path}.pdc-backup") == backup
    assert read_text(f"{path}.pdc-managed") == marker_before


def test_new_request_retargets_an_update_that_has_not_written_old_desired(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    previous = "pdc-one\n"
    interrupted_desired = "pdc-two\n"
    newest_desired = "pdc-three\n"
    (tmp_path / "presets.conf").write_text(previous)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(
        path,
        "updating",
        interrupted_desired,
        external,
        previous=previous,
    )

    result = write_managed(path, newest_desired)

    marker = json.loads(read_text(f"{path}.pdc-managed"))
    assert result.content == newest_desired
    assert marker["phase"] == "managed"
    assert marker["managed_sha256"] == _hash(newest_desired)
    assert restore_managed(path).content == external


def test_new_request_retargets_an_install_that_still_has_rollback_content(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    interrupted_desired = "pdc-one\n"
    newest_desired = "pdc-two\n"
    (tmp_path / "presets.conf").write_text(external)
    _write_marker(path, "installing", interrupted_desired, external)

    result = write_managed(path, newest_desired)

    marker = json.loads(read_text(f"{path}.pdc-managed"))
    assert result.content == newest_desired
    assert marker["phase"] == "managed"
    assert marker["managed_sha256"] == _hash(newest_desired)
    assert restore_managed(path).content == external


def test_restore_abandons_install_when_external_content_is_still_intact(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    (tmp_path / "presets.conf").write_text(external)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(path, "installing", "pdc\n", external)

    result = restore_managed(path)

    assert result.content == external
    assert read_text(path) == external
    assert read_text(f"{path}.pdc-backup") is None
    assert read_text(f"{path}.pdc-managed") is None


def test_restore_accepts_previous_owned_content_during_interrupted_update(tmp_path):
    path = str(tmp_path / "presets.conf")
    external = "external\n"
    previous = "pdc-one\n"
    (tmp_path / "presets.conf").write_text(previous)
    (tmp_path / "presets.conf.pdc-backup").write_text(external)
    _write_marker(path, "updating", "pdc-two\n", external, previous=previous)

    result = restore_managed(path)

    assert result.content == external
    assert read_text(path) == external
    assert read_text(f"{path}.pdc-backup") is None
    assert read_text(f"{path}.pdc-managed") is None


def test_replace_conflict_adopts_missing_external_file_as_absent_rollback(tmp_path):
    path = str(tmp_path / "presets.conf")
    (tmp_path / "presets.conf").write_text("external-before\n")
    write_managed(path, "pdc-one\n")
    os.remove(path)

    result = write_managed(path, "pdc-two\n", replace_conflict=True)

    assert result.content == "pdc-two\n"
    assert read_text(f"{path}.pdc-backup") is None
    assert restore_managed(path).content is None
    assert read_text(path) is None
