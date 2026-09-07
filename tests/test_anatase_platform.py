import json
import os

import pytest

from controllers import hhd as default_hhd
from pdc_platform import anatase_hhd
from pdc_platform import (
    activate_import_paths,
    describe,
    plugin_root_from_platform_file,
    select_hhd_tdp_client,
)


def _write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(str(value))


def test_anatase_is_explicitly_first_class():
    assert describe("anatase") == {
        "id": "anatase",
        "support_tier": "first-class",
    }


def test_existing_first_class_platforms_keep_the_default_hhd_client():
    for os_id in ("steamos", "bazzite", "cachyos", None, "unknown"):
        assert select_hhd_tdp_client(os_id, default_hhd) is default_hhd


def test_only_anatase_selects_its_isolated_hhd_client():
    assert select_hhd_tdp_client("anatase", default_hhd) is anatase_hhd
    assert anatase_hhd is not default_hhd


def test_anatase_prioritises_plugin_modules_over_fedora_site_packages(tmp_path):
    plugin_root = str(tmp_path / "plugin")
    local_modules = os.path.join(plugin_root, "py_modules")
    os.makedirs(local_modules)
    paths = ["/usr/lib64/python3.14/site-packages", local_modules]

    activate_import_paths("anatase", plugin_root, paths)

    assert paths[0] == local_modules


def test_platform_package_resolves_the_real_plugin_root(tmp_path):
    plugin_root = str(tmp_path / "Panel de Control")
    package_file = os.path.join(
        plugin_root,
        "py_modules/pdc_platform/__init__.py",
    )

    assert plugin_root_from_platform_file(package_file) == plugin_root


def test_other_platforms_keep_their_existing_import_order(tmp_path):
    plugin_root = str(tmp_path / "plugin")
    local_modules = os.path.join(plugin_root, "py_modules")
    os.makedirs(local_modules)
    original = ["/usr/lib/python3/site-packages", local_modules]
    paths = list(original)

    for os_id in ("steamos", "bazzite", "cachyos", None):
        activate_import_paths(os_id, plugin_root, paths)
        assert paths == original


def test_anatase_hhd_client_reads_and_confirms_tdp_state(tmp_path, monkeypatch):
    root = str(tmp_path)
    _write(os.path.join(root, "etc/hhd/.token"), "local-token")
    gets = []
    posts = []
    states = iter(
        (
            {"hhd": {"settings": {"tdp_enable": True}}},
            {"hhd": {"settings": {"tdp_enable": False}}},
        )
    )

    def fake_get(path, token, timeout=5):
        gets.append((path, token, timeout))
        return next(states)

    def fake_post(path, token, payload, timeout=5):
        posts.append((path, token, json.loads(json.dumps(payload)), timeout))
        return {"accepted": True}

    monkeypatch.setattr(anatase_hhd, "_get", fake_get)
    monkeypatch.setattr(anatase_hhd, "_post", fake_post)

    assert anatase_hhd.current_tdp_enable(root=root) is True
    assert anatase_hhd.set_tdp_enable(False, root=root) is False
    assert gets == [
        ("/state", "local-token", 5),
        ("/state", "local-token", 5),
    ]
    assert posts == [
        (
            "/state",
            "local-token",
            {"hhd": {"settings": {"tdp_enable": False}}},
            5,
        )
    ]


def test_anatase_hhd_client_fails_closed_without_token(tmp_path):
    root = str(tmp_path)

    assert anatase_hhd.read_state(root=root) is None
    assert anatase_hhd.current_tdp_enable(root=root) is None
    assert anatase_hhd.set_tdp_enable(False, root=root) is None


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {"hhd": {}},
        {"hhd": {"settings": {}}},
        {"hhd": {"settings": {"tdp_enable": 0}}},
        {"hhd": {"settings": {"tdp_enable": "false"}}},
    ),
)
def test_anatase_hhd_client_fails_closed_on_unconfirmed_payload(
    tmp_path,
    monkeypatch,
    payload,
):
    root = str(tmp_path)
    _write(os.path.join(root, "etc/hhd/.token"), "local-token")
    monkeypatch.setattr(anatase_hhd, "_get", lambda *args, **kwargs: payload)
    monkeypatch.setattr(anatase_hhd, "_post", lambda *args, **kwargs: payload)

    assert anatase_hhd.current_tdp_enable(root=root) is None
    assert anatase_hhd.set_tdp_enable(False, root=root) is None
