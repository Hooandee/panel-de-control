import asyncio
import importlib
import pathlib
import sys
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def theme_rpc(tmp_path, monkeypatch):
    fake = types.ModuleType("decky")
    fake.DECKY_PLUGIN_SETTINGS_DIR = str(tmp_path / "settings")
    fake.DECKY_USER_HOME = str(tmp_path / "home")
    fake.DECKY_USER = "deck"
    fake.logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "decky", fake)
    monkeypatch.syspath_prepend(str(ROOT / "py_modules"))
    monkeypatch.syspath_prepend(str(ROOT))
    main = importlib.reload(importlib.import_module("main"))
    plugin = main.Plugin()
    plugin._init = lambda: None
    return main, plugin, fake


def test_prepare_bundled_theme_rpc_uses_panels_package_and_css_loader_theme_root(
    theme_rpc,
    monkeypatch,
):
    main, plugin, fake = theme_rpc
    captured = {}

    def prepare(theme_id, *, plugin_root, themes_root):
        captured.update(
            theme_id=theme_id,
            plugin_root=plugin_root,
            themes_root=themes_root,
        )
        return {
            "ok": True,
            "code": "prepared",
            "theme_id": "hooandee-gallery",
            "theme_name": "Hooandee Gallery",
            "version": "0.6.0",
            "transaction": "opaque-token",
        }

    monkeypatch.setattr(main.theme_packages, "prepare_bundled_theme", prepare)

    result = asyncio.run(plugin.prepare_bundled_theme_install("hooandee-gallery"))

    assert result["ok"] is True
    assert captured == {
        "theme_id": "hooandee-gallery",
        "plugin_root": ROOT,
        "themes_root": pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes",
    }


def test_prepare_bundled_theme_rpc_returns_a_recoverable_typed_failure(theme_rpc, monkeypatch):
    main, plugin, _ = theme_rpc

    def fail(*args, **kwargs):
        raise main.theme_packages.ThemePackageError("hash_mismatch", "bad archive")

    monkeypatch.setattr(main.theme_packages, "prepare_bundled_theme", fail)

    result = asyncio.run(plugin.prepare_bundled_theme_install("hooandee-gallery"))

    assert result == {
        "ok": False,
        "code": "hash_mismatch",
        "theme_id": "hooandee-gallery",
    }


def test_commit_and_rollback_theme_rpcs_use_the_opaque_transaction_token(theme_rpc, monkeypatch):
    main, plugin, fake = theme_rpc
    calls = []

    monkeypatch.setattr(
        main.theme_packages,
        "commit_theme_install",
        lambda token, root: calls.append(("commit", token, root)) or {"ok": True, "code": "committed"},
    )
    monkeypatch.setattr(
        main.theme_packages,
        "rollback_theme_install",
        lambda token, root: calls.append(("rollback", token, root)) or {"ok": True, "code": "rolled_back"},
    )

    assert asyncio.run(plugin.commit_theme_install("opaque-token"))["code"] == "committed"
    assert asyncio.run(plugin.rollback_theme_install("opaque-token"))["code"] == "rolled_back"
    themes_root = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes"
    assert calls == [
        ("commit", "opaque-token", themes_root),
        ("rollback", "opaque-token", themes_root),
    ]


def test_theme_root_prefers_decky_home(theme_rpc, monkeypatch):
    _, plugin, _ = theme_rpc
    monkeypatch.setenv("DECKY_HOME", "/srv/decky")

    assert plugin._themes_root() == pathlib.Path("/srv/decky/themes")


def test_recovery_rpcs_keep_rollback_pending_until_css_loader_acknowledges_it(
    theme_rpc,
    monkeypatch,
):
    main, plugin, _ = theme_rpc
    pending = [{
        "transaction": "opaque-token",
        "theme_name": "Hooandee Gallery",
        "previous_version": "0.5.0",
    }]
    def ack(token, root):
        return {"ok": True, "code": "acknowledged"}
    monkeypatch.setattr(main.theme_packages, "recover_theme_transactions", lambda root: pending)
    monkeypatch.setattr(main.theme_packages, "acknowledge_theme_rollback", ack)

    result = asyncio.run(plugin.get_theme_install_recoveries())
    confirmed = asyncio.run(plugin.acknowledge_theme_install_rollback("opaque-token"))

    assert result == {"ok": True, "code": "ready", "recoveries": pending}
    assert confirmed == {"ok": True, "code": "acknowledged"}


def test_remote_discovery_records_only_validated_css_loader_runtime(theme_rpc):
    _, plugin, _ = theme_rpc
    calls = []
    plugin._theme_remote_service = types.SimpleNamespace(
        check_releases=lambda force: calls.append(force) or {"status": "disabled"}
    )

    result = asyncio.run(
        plugin.check_theme_releases(
            False,
            css_loader_version="2.1.2",
            css_loader_backend=9,
        )
    )

    assert result == {"status": "disabled"}
    assert calls == [False]
    assert plugin._theme_remote_runtime.css_loader == "2.1.2"
    assert plugin._theme_remote_runtime.css_loader_backend == 9


def test_remote_discovery_sanitizes_an_unexpected_service_failure(theme_rpc):
    _, plugin, _ = theme_rpc

    def fail(_force):
        raise RuntimeError("private transport detail")

    plugin._theme_remote_service = types.SimpleNamespace(check_releases=fail)

    result = asyncio.run(
        plugin.check_theme_releases(
            False,
            css_loader_version="2.1.2",
            css_loader_backend=9,
        )
    )

    assert result == {
        "status": "recoverable-failure",
        "code": "invalid_descriptor",
        "retryable": True,
    }


@pytest.mark.parametrize(
    ("theme_id", "version", "code"),
    [
        ("../gallery", "0.7.9", "unsupported_theme"),
        ("hooandee-gallery", "v0.7.9", "invalid_descriptor"),
        ("hooandee-gallery", "0.7.9-beta.1", "invalid_descriptor"),
    ],
)
def test_remote_prepare_rejects_invalid_identity_before_scheduling(
    theme_rpc,
    theme_id,
    version,
    code,
):
    _, plugin, _ = theme_rpc
    calls = []
    plugin._theme_remote_service = types.SimpleNamespace(
        prepare_install=lambda *args: calls.append(args)
    )

    result = asyncio.run(plugin.prepare_remote_theme_install(theme_id, version))

    assert result == {"ok": False, "code": code, "theme_id": theme_id}
    assert calls == []


def test_remote_prepare_uses_only_the_confirmed_identity_and_version(theme_rpc):
    _, plugin, fake = theme_rpc
    calls = []
    prepared = {
        "ok": True,
        "code": "prepared",
        "theme_id": "hooandee-gallery",
        "theme_name": "Hooandee Gallery",
        "version": "0.7.9",
        "transaction": "opaque-token",
    }
    plugin._theme_remote_service = types.SimpleNamespace(
        prepare_install=lambda *args: calls.append(args) or prepared
    )

    result = asyncio.run(
        plugin.prepare_remote_theme_install("hooandee-gallery", "0.7.9")
    )

    assert result == prepared
    assert calls == [
        (
            "hooandee-gallery",
            "0.7.9",
            pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes",
        )
    ]


def test_remote_prepare_sanitizes_service_failures(theme_rpc):
    main, plugin, _ = theme_rpc

    def fail(*_args):
        raise main.theme_remote.ThemeRemoteError("publication_changed", "private detail")

    plugin._theme_remote_service = types.SimpleNamespace(prepare_install=fail)

    result = asyncio.run(
        plugin.prepare_remote_theme_install("hooandee-gallery", "0.7.9")
    )

    assert result == {
        "ok": False,
        "code": "publication_changed",
        "theme_id": "hooandee-gallery",
    }
