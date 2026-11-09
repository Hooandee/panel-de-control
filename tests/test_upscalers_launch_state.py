import json
import stat

import pytest

from upscalers.launch_state import LaunchReceipts, MAX_BYTES


def receipt(value="secret-token"):
    return {"version": 1, "env": [{"name": "CUSTOM", "before": value, "applied": "new"}],
            "wrappers": {"before": ['"/private/path with space/tool"'], "applied": ["mako-run"], "added": ["mako-run"]}}


def test_restart_roundtrip_is_private_and_isolates_owners(tmp_path):
    store = LaunchReceipts(tmp_path)
    assert store.get("42", "mako") is None
    assert store.set("42", "mako", receipt())
    assert LaunchReceipts(tmp_path).get("42", "mako") == receipt()
    assert store.get("42", "lsfg") is None
    assert store.get("43", "mako") is None
    path = next(store.directory.glob("*.json"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.set("42", "mako", None)
    assert store.get("42", "mako") is None


def test_empty_receipt_survives_restart(tmp_path):
    empty = {"version": 1, "env": [], "wrappers": {"before": [], "applied": [], "added": []}}
    LaunchReceipts(tmp_path).set("nonsteam:42", "upscaler", empty)
    assert LaunchReceipts(tmp_path).get("nonsteam:42", "upscaler") == empty


@pytest.mark.parametrize("bad", [
    {"version": True, "env": [], "wrappers": {}},
    {**receipt(), "raw_command": "private"},
    {**receipt(), "env": [{"name": "BAD NAME", "before": None, "applied": "x"}]},
    {**receipt(), "env": [{"name": "X", "before": 3, "applied": "x"}]},
    {**receipt(), "env": [{"name": "X", "before": None, "applied": "x"}] * 2},
    {**receipt(), "wrappers": {"before": [], "applied": "mako-run", "added": []}},
    {**receipt(), "wrappers": {"before": [], "applied": ["x"] * 65, "added": []}},
    {**receipt(), "wrappers": {"before": ["x" * 513], "applied": [], "added": []}},
    receipt("x\nTOKEN=y"),
])
def test_rejects_invalid_without_replacing_previous(tmp_path, bad):
    store = LaunchReceipts(tmp_path)
    store.set("42", "mako", receipt())
    with pytest.raises(ValueError, match="launch_receipt_invalid"):
        store.set("42", "mako", bad)
    assert store.get("42", "mako") == receipt()


@pytest.mark.parametrize(("appid", "owner"), [("../../escape", "mako"), ("42", "../../escape"), ("42", "other"), ("", "lsfg")])
def test_identity_cannot_escape_store(tmp_path, appid, owner):
    with pytest.raises(ValueError, match="launch_receipt_invalid"):
        LaunchReceipts(tmp_path).set(appid, owner, receipt())


def test_corrupt_oversized_and_symlink_receipts_are_not_read(tmp_path):
    store = LaunchReceipts(tmp_path)
    store.set("42", "mako", receipt())
    path = next(store.directory.glob("*.json"))
    for data in ("{", " " * (MAX_BYTES + 1)):
        path.write_text(data)
        assert store.get("42", "mako") is None
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(receipt()))
    path.symlink_to(outside)
    assert store.get("42", "mako") is None
    with pytest.raises(ValueError, match="launch_receipt_conflict"):
        store.set("42", "mako", receipt("overwrite"))
    assert json.loads(outside.read_text()) == receipt()


def test_symlink_store_refuses_reads_and_writes(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "launch-receipts").symlink_to(outside, target_is_directory=True)
    store = LaunchReceipts(tmp_path)
    with pytest.raises(ValueError, match="launch_receipt_conflict"):
        store.set("42", "mako", receipt())
    with pytest.raises(ValueError, match="launch_receipt_conflict"):
        store.get("42", "mako")


@pytest.mark.parametrize("pending", [True, False])
def test_pending_intent_survives_restart_without_raw_launch(tmp_path, pending):
    value = {**receipt(), "pending": pending}
    LaunchReceipts(tmp_path).set("42", "mako", value)
    assert LaunchReceipts(tmp_path).get("42", "mako") == value


@pytest.mark.parametrize("pending", [1, "true", None, {}])
def test_pending_state_must_be_boolean(tmp_path, pending):
    with pytest.raises(ValueError, match="launch_receipt_invalid"):
        LaunchReceipts(tmp_path).set("42", "mako", {**receipt(), "pending": pending})
