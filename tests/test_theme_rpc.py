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


def test_bundled_theme_prepare_rpc_is_not_exposed(theme_rpc):
    _, plugin, _ = theme_rpc

    assert not hasattr(plugin, "prepare_bundled_theme_install")


def test_remote_service_uses_the_fixed_pages_channel_and_dedicated_cache(
    theme_rpc,
    monkeypatch,
):
    main, plugin, fake = theme_rpc
    captured = {}

    class Transport:
        def __init__(self, pages_base_url):
            captured["transport_url"] = pages_base_url

    class Service:
        def __init__(self, channel, **options):
            captured["channel"] = channel
            captured.update(options)

    monkeypatch.setattr(main.theme_transport, "ThemeHttpTransport", Transport)
    monkeypatch.setattr(main.theme_remote, "ThemeRemoteService", Service)

    plugin._new_theme_remote_service()

    assert captured["transport_url"] == "https://hooandee.github.io/panel-de-control"
    assert captured["channel"] == main.theme_remote.OfficialThemeChannel(
        pages_base_url="https://hooandee.github.io/panel-de-control",
        catalog_path="themes/v1/catalog.json",
    )
    assert isinstance(captured["cache"], main.theme_remote.ThemeCatalogCacheStore)
    captured["cache"].save(b'{"schemaVersion":1,"themes":[]}', 25.0)
    expected_cache = pathlib.Path(
        fake.DECKY_PLUGIN_SETTINGS_DIR
    ) / "theme-catalog-cache.json"
    assert expected_cache.is_file()


def test_commit_and_rollback_theme_rpcs_use_the_opaque_transaction_token(theme_rpc, monkeypatch):
    main, plugin, fake = theme_rpc
    calls = []

    monkeypatch.setattr(
        main.theme_packages,
        "commit_theme_install",
        lambda token, root, *, receipts_path: calls.append(
            ("commit", token, root, receipts_path)
        ) or {"ok": True, "code": "committed"},
    )
    monkeypatch.setattr(
        main.theme_packages,
        "rollback_theme_install",
        lambda token, root, *, receipts_path: calls.append(
            ("rollback", token, root, receipts_path)
        ) or {"ok": True, "code": "rolled_back"},
    )

    assert asyncio.run(plugin.commit_theme_install("opaque-token"))["code"] == "committed"
    assert asyncio.run(plugin.rollback_theme_install("opaque-token"))["code"] == "rolled_back"
    themes_root = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes"
    receipts_path = pathlib.Path(fake.DECKY_PLUGIN_SETTINGS_DIR) / "theme-extension-receipts.json"
    assert calls == [
        ("commit", "opaque-token", themes_root, receipts_path),
        ("rollback", "opaque-token", themes_root, receipts_path),
    ]


def test_discard_theme_receipt_rpc_uses_only_backend_derived_paths(theme_rpc, monkeypatch):
    main, plugin, fake = theme_rpc
    calls = []
    monkeypatch.setattr(
        main.theme_packages,
        "discard_orphaned_theme_receipt",
        lambda catalog_id, root, receipts_path: calls.append(
            (catalog_id, root, receipts_path)
        ) or {"ok": True, "code": "discarded"},
    )

    result = asyncio.run(plugin.discard_theme_extension_receipt("example-theme"))

    assert result == {"ok": True, "code": "discarded"}
    assert calls == [(
        "example-theme",
        pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes",
        pathlib.Path(fake.DECKY_PLUGIN_SETTINGS_DIR) / "theme-extension-receipts.json",
    )]


@pytest.mark.parametrize("catalog_id", ["../theme", "", None])
def test_discard_theme_receipt_rpc_rejects_invalid_identity_before_offload(
    theme_rpc,
    catalog_id,
):
    _, plugin, _ = theme_rpc

    async def fail_if_offloaded(_call):
        pytest.fail("invalid identity reached theme offload")

    plugin._offload_theme_call = fail_if_offloaded

    result = asyncio.run(plugin.discard_theme_extension_receipt(catalog_id))

    assert result == {"ok": False, "code": "unsupported_theme"}


def test_discard_theme_receipt_rpc_sanitizes_typed_errors(theme_rpc, monkeypatch):
    main, plugin, _ = theme_rpc

    def fail(*_args):
        raise main.theme_packages.ThemePackageError(
            "theme_present",
            "/private/theme/path is still present",
        )

    monkeypatch.setattr(main.theme_packages, "discard_orphaned_theme_receipt", fail)

    result = asyncio.run(plugin.discard_theme_extension_receipt("example-theme"))

    assert result == {"ok": False, "code": "theme_present"}


def test_discard_theme_receipt_rpc_sanitizes_unexpected_errors_and_warns(
    theme_rpc,
    monkeypatch,
):
    main, plugin, fake = theme_rpc
    warnings = []
    fake.logger.warning = lambda *args: warnings.append(args)

    def fail(*_args):
        raise RuntimeError("/private/theme/path failed")

    monkeypatch.setattr(main.theme_packages, "discard_orphaned_theme_receipt", fail)

    result = asyncio.run(plugin.discard_theme_extension_receipt("example-theme"))

    assert result == {"ok": False, "code": "discard_failed"}
    assert len(warnings) == 1
    assert "/private/theme/path" not in repr(warnings)


def test_theme_root_prefers_decky_home(theme_rpc, monkeypatch):
    _, plugin, _ = theme_rpc
    monkeypatch.setenv("DECKY_HOME", "/srv/decky")

    assert plugin._themes_root() == pathlib.Path("/srv/decky/themes")


def test_extension_rpcs_return_the_exact_backend_contract(theme_rpc, monkeypatch):
    main, plugin, fake = theme_rpc
    themes_root = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes"
    receipts_path = (
        pathlib.Path(fake.DECKY_PLUGIN_SETTINGS_DIR)
        / "theme-extension-receipts.json"
    )
    descriptor = {
        "catalogId": "example-theme",
        "cssLoaderName": "Example Theme",
        "version": "1.2.3",
        "abiVersion": 1,
        "entrypoint": "panel-extension.js",
        "size": 42,
        "sha256": "a" * 64,
    }
    loaded = {
        key: value for key, value in descriptor.items() if key not in ("entrypoint", "size")
    } | {"source": "module.exports=extension"}
    calls = []
    monkeypatch.setattr(
        main.theme_packages,
        "list_theme_extensions",
        lambda root, receipts: calls.append(("list", root, receipts)) or [descriptor],
    )
    monkeypatch.setattr(
        main.theme_packages,
        "load_theme_extension",
        lambda catalog_id, version, root, receipts: calls.append(
            ("load", catalog_id, version, root, receipts)
        ) or loaded,
    )

    assert asyncio.run(plugin.list_theme_extensions()) == [{
        "catalogId": "example-theme",
        "cssLoaderName": "Example Theme",
        "version": "1.2.3",
        "abiVersion": 1,
        "sha256": "a" * 64,
    }]
    assert asyncio.run(plugin.load_theme_extension("example-theme", "1.2.3")) == loaded
    assert calls == [
        ("list", themes_root, receipts_path),
        ("load", "example-theme", "1.2.3", themes_root, receipts_path),
    ]


@pytest.mark.parametrize(
    ("catalog_id", "version"),
    [
        ("../theme", "1.2.3"),
        ("example-theme", "v1.2.3"),
        ("example-theme", "1.2.3-beta.1"),
    ],
)
def test_load_extension_rejects_invalid_identity_before_offloading(
    theme_rpc,
    monkeypatch,
    catalog_id,
    version,
):
    main, plugin, _ = theme_rpc
    monkeypatch.setattr(
        main.theme_packages,
        "load_theme_extension",
        lambda *_args: pytest.fail("invalid identity reached storage"),
    )

    with pytest.raises(RuntimeError, match="extension_unavailable"):
        asyncio.run(plugin.load_theme_extension(catalog_id, version))


def test_load_extension_sanitizes_backend_failures(theme_rpc, monkeypatch):
    main, plugin, _ = theme_rpc

    def fail(*_args):
        raise main.theme_packages.ThemePackageError(
            "extension_unavailable",
            "/private/theme/path changed",
        )

    monkeypatch.setattr(main.theme_packages, "load_theme_extension", fail)

    with pytest.raises(RuntimeError) as error:
        asyncio.run(plugin.load_theme_extension("example-theme", "1.2.3"))

    assert str(error.value) == "extension_unavailable"


def test_recovery_rpcs_keep_rollback_pending_until_css_loader_acknowledges_it(
    theme_rpc,
    monkeypatch,
):
    main, plugin, _ = theme_rpc
    pending = [{
        "transaction": "opaque-token",
        "theme_name": "Example Theme",
        "previous_version": "0.5.0",
    }]
    def ack(token, root, *, receipts_path):
        return {"ok": True, "code": "acknowledged"}
    monkeypatch.setattr(
        main.theme_packages,
        "recover_theme_transactions",
        lambda root, *, receipts_path: pending,
    )
    monkeypatch.setattr(main.theme_packages, "acknowledge_theme_rollback", ack)

    result = asyncio.run(plugin.get_theme_install_recoveries())
    confirmed = asyncio.run(plugin.acknowledge_theme_install_rollback("opaque-token"))

    assert result == {"ok": True, "code": "ready", "recoveries": pending}
    assert confirmed == {"ok": True, "code": "acknowledged"}


def test_activation_recovery_rpcs_persist_before_mutation_and_acknowledge_exactly(
    theme_rpc,
    monkeypatch,
):
    main, plugin, fake = theme_rpc
    path = pathlib.Path(fake.DECKY_PLUGIN_SETTINGS_DIR) / "theme-activation-recovery.json"
    snapshot = {
        "status": "ready",
        "pluginVersion": "2.1.2",
        "backendVersion": 9,
        "themes": [],
    }
    calls = []
    monkeypatch.setattr(
        main.theme_activation,
        "begin_theme_activation",
        lambda value, journal_path: calls.append(("begin", value, journal_path)) or {
            "ok": True,
            "code": "prepared",
            "transaction": "token",
        },
    )
    monkeypatch.setattr(
        main.theme_activation,
        "get_theme_activation_recovery",
        lambda journal_path: calls.append(("pending", journal_path)) or {
            "transaction": "token",
            "snapshot": snapshot,
            "recoverable": False,
        },
    )
    monkeypatch.setattr(
        main.theme_activation,
        "mark_theme_activation_settled",
        lambda transaction, journal_path: calls.append(
            ("settle", transaction, journal_path)
        ) or {"ok": True, "code": "settled"},
    )
    monkeypatch.setattr(
        main.theme_activation,
        "acknowledge_theme_activation",
        lambda transaction, journal_path: calls.append(
            ("acknowledge", transaction, journal_path)
        ) or {"ok": True, "code": "acknowledged"},
    )

    prepared = asyncio.run(plugin.begin_theme_activation(snapshot))
    pending = asyncio.run(plugin.get_theme_activation_recovery())
    settled = asyncio.run(plugin.settle_theme_activation("token"))
    acknowledged = asyncio.run(plugin.acknowledge_theme_activation("token"))

    assert prepared == {"ok": True, "code": "prepared", "transaction": "token"}
    assert pending == {
        "ok": True,
        "code": "ready",
        "recovery": {
            "transaction": "token",
            "snapshot": snapshot,
            "recoverable": False,
        },
    }
    assert settled == {"ok": True, "code": "settled"}
    assert acknowledged == {"ok": True, "code": "acknowledged"}
    assert calls == [
        ("begin", snapshot, path),
        ("pending", path),
        ("settle", "token", path),
        ("acknowledge", "token", path),
    ]


def test_remote_discovery_delegates_to_the_theme_service(theme_rpc):
    _, plugin, _ = theme_rpc
    calls = []
    plugin._theme_remote_service = types.SimpleNamespace(
        check_releases=lambda force: calls.append(force) or {"status": "disabled"}
    )

    result = asyncio.run(plugin.check_theme_releases(False))

    assert result == {"status": "disabled"}
    assert calls == [False]


def test_remote_discovery_without_css_loader_keeps_catalog_visible(theme_rpc):
    _, plugin, fake = theme_rpc
    plugins = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "plugins"
    assert not plugins.exists()

    def check_releases(_force):
        return {
            "status": "published",
            "checkedAt": 100.0,
            "themes": [
                {
                    "catalogId": "example-theme",
                    "compatibility": "compatible",
                }
            ],
        }

    plugin._theme_remote_service = types.SimpleNamespace(
        check_releases=check_releases
    )

    result = asyncio.run(plugin.check_theme_releases(False))

    assert result["themes"] == [
        {
            "catalogId": "example-theme",
            "compatibility": "compatible",
        }
    ]


def test_remote_install_does_not_require_css_loader_version_metadata(theme_rpc):
    _, plugin, _ = theme_rpc
    expected = {
        "ok": True,
        "code": "prepared",
        "theme_id": "example-theme",
        "theme_name": "Example Theme",
        "version": "1.2.3",
        "transaction": "token",
    }
    plugin._theme_remote_service = types.SimpleNamespace(
        prepare_install=lambda *_args: expected
    )

    result = asyncio.run(
        plugin.prepare_remote_theme_install("example-theme", "1.2.3")
    )

    assert result == expected


def test_remote_discovery_sanitizes_an_unexpected_service_failure(theme_rpc):
    _, plugin, _ = theme_rpc

    def fail(_force):
        raise RuntimeError("private transport detail")

    plugin._theme_remote_service = types.SimpleNamespace(check_releases=fail)

    result = asyncio.run(plugin.check_theme_releases(False))

    assert result == {
        "status": "recoverable-failure",
        "code": "invalid_descriptor",
        "retryable": True,
    }


@pytest.mark.parametrize(
    ("theme_id", "version", "code"),
    [
        ("../theme", "1.2.3", "unsupported_theme"),
        ("example-theme", "v1.2.3", "invalid_descriptor"),
        ("example-theme", "1.2.3-beta.1", "invalid_descriptor"),
        ("example-theme", "1.1٢.3", "invalid_descriptor"),
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
        "theme_id": "example-theme",
        "theme_name": "Example Theme",
        "version": "1.2.3",
        "transaction": "opaque-token",
    }
    plugin._theme_remote_service = types.SimpleNamespace(
        prepare_install=lambda *args: calls.append(args) or prepared
    )

    result = asyncio.run(
        plugin.prepare_remote_theme_install("example-theme", "1.2.3")
    )

    assert result == prepared
    assert calls == [
        (
            "example-theme",
            "1.2.3",
            pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes",
            pathlib.Path(fake.DECKY_PLUGIN_SETTINGS_DIR)
            / "theme-extension-receipts.json",
        )
    ]


def test_remote_prepare_sanitizes_service_failures(theme_rpc):
    main, plugin, _ = theme_rpc

    def fail(*_args):
        raise main.theme_remote.ThemeRemoteError("publication_changed", "private detail")

    plugin._theme_remote_service = types.SimpleNamespace(prepare_install=fail)

    result = asyncio.run(
        plugin.prepare_remote_theme_install("example-theme", "1.2.3")
    )

    assert result == {
        "ok": False,
        "code": "publication_changed",
        "theme_id": "example-theme",
    }
