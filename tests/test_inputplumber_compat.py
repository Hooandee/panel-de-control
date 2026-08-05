import json

import pytest

from controllers.inputplumber_compat import (
    ManifestError,
    load_builds,
    owned_paths,
    select_build,
)


STOCK_HASH = "4" * 64
COMMIT = "b" * 40


def _entry(version="0.77.4", stock_hash=STOCK_HASH):
    return {
        "version": version,
        "upstream_commit": COMMIT,
        "patch": f"assets/inputplumber/v{version}-xbox-hd.patch",
        "artifact": f"bin/inputplumber-xbox-hd-v{version}",
        "artifact_sha256": f"bin/inputplumber-xbox-hd-v{version}.sha256",
        "provenance": f"bin/inputplumber-xbox-hd-v{version}.provenance",
        "stock_sha256": [stock_hash],
        "verified_platforms": ["steamos-test-rc73xa"],
    }


def _write_manifest(tmp_path, builds=None, **root_overrides):
    root = tmp_path / "plugin"
    path = root / "assets/inputplumber/compatibility.json"
    path.parent.mkdir(parents=True)
    manifest = {
        "schema": 1,
        "device": "rog_xbox_ally_x",
        "builds": builds if builds is not None else [_entry()],
        **root_overrides,
    }
    path.write_text(json.dumps(manifest))
    return root


def test_loads_sorted_immutable_builds_and_owned_paths(tmp_path):
    root = _write_manifest(
        tmp_path, [_entry("0.77.4"), _entry("0.78.0", "5" * 64)]
    )

    builds = load_builds(str(root))

    assert [build.version for build in builds] == ["0.78.0", "0.77.4"]
    assert builds[1].stock_sha256 == (STOCK_HASH,)
    assert owned_paths(str(root), builds[1:]) == (
        str(root / "assets/inputplumber/v0.77.4-xbox-hd.patch"),
        str(root / "bin/inputplumber-xbox-hd-v0.77.4"),
        str(root / "bin/inputplumber-xbox-hd-v0.77.4.sha256"),
        str(root / "bin/inputplumber-xbox-hd-v0.77.4.provenance"),
    )
    with pytest.raises(AttributeError):
        builds[0].version = "0.79.0"


def test_selects_only_exact_inputplumber_xbox_build(tmp_path):
    builds = load_builds(str(_write_manifest(tmp_path)))

    selected = select_build(
        builds,
        manager="inputplumber",
        device_key="rog_xbox_ally_x",
        version="0.77.4",
        stock_sha256=STOCK_HASH,
    )

    assert selected is not None
    assert selected.version == "0.77.4"


@pytest.mark.parametrize(
    "manager,device,version,stock",
    [
        ("hhd", "rog_xbox_ally_x", "0.77.4", STOCK_HASH),
        ("none", "rog_xbox_ally_x", "0.77.4", STOCK_HASH),
        ("inputplumber", "legion_go_2", "0.77.4", STOCK_HASH),
        ("inputplumber", "rog_xbox_ally_x", "0.78.0", STOCK_HASH),
        ("inputplumber", "rog_xbox_ally_x", "0.77.4", "0" * 64),
        ("inputplumber", "rog_xbox_ally_x", None, STOCK_HASH),
    ],
)
def test_selection_fails_closed(manager, device, version, stock, tmp_path):
    builds = load_builds(str(_write_manifest(tmp_path)))

    assert select_build(
        builds,
        manager=manager,
        device_key=device,
        version=version,
        stock_sha256=stock,
    ) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda entry: entry.update(extra=True),
        lambda entry: entry.update(version="v0.77.4"),
        lambda entry: entry.update(upstream_commit="B" * 40),
        lambda entry: entry.update(patch="/tmp/patch"),
        lambda entry: entry.update(artifact="../inputplumber"),
        lambda entry: entry.update(artifact="bin/unversioned-inputplumber"),
        lambda entry: entry.update(stock_sha256=["A" * 64]),
        lambda entry: entry.update(stock_sha256=[]),
        lambda entry: entry.update(verified_platforms=[]),
    ],
)
def test_rejects_invalid_build_entries(tmp_path, mutate):
    entry = _entry()
    mutate(entry)
    root = _write_manifest(tmp_path, [entry])

    with pytest.raises(ManifestError):
        load_builds(str(root))


def test_rejects_unknown_root_fields_duplicates_and_more_than_three(tmp_path):
    reused_path = _entry("0.78.0", "5" * 64)
    reused_path["artifact"] = _entry()["artifact"]
    invalid_manifests = [
        ([_entry()], {"extra": True}),
        ([_entry(), _entry()], {}),
        ([_entry(), reused_path], {}),
        ([_entry(f"0.77.{index}") for index in range(4)], {}),
    ]

    for index, (builds, overrides) in enumerate(invalid_manifests):
        root = _write_manifest(tmp_path / str(index), builds, **overrides)
        with pytest.raises(ManifestError):
            load_builds(str(root))
