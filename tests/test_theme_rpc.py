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


def test_theme_runtime_probe_reads_css_loader_files_without_frontend_input(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    css_loader = plugins / "SDH-CssLoader"
    css_loader.mkdir(parents=True)
    (css_loader / "package.json").write_text(
        '{"name":"SDH-CssLoader","version":"2.1.2"}',
        encoding="utf-8",
    )
    (css_loader / "css_theme.py").write_text(
        "CSS_LOADER_VER = 9\n",
        encoding="utf-8",
    )

    runtime = main.theme_runtime.probe_css_loader_runtime(
        plugins,
        panel_version="0.37.12",
    )

    assert runtime == main.theme_remote.ThemeRuntimeVersions(
        panel="0.37.12",
        css_loader="2.1.2",
        css_loader_backend=9,
    )


def test_theme_runtime_probe_accepts_a_valid_panel_prerelease(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    css_loader = plugins / "SDH-CssLoader"
    css_loader.mkdir(parents=True)
    (css_loader / "package.json").write_text(
        '{"name":"SDH-CssLoader","version":"2.1.2"}',
        encoding="utf-8",
    )
    (css_loader / "css_theme.py").write_text(
        "CSS_LOADER_VER = 9\n",
        encoding="utf-8",
    )

    runtime = main.theme_runtime.probe_css_loader_runtime(
        plugins,
        panel_version="0.37.13-dev.abcdef0",
    )

    assert runtime.panel == "0.37.13-dev.abcdef0"


def test_theme_runtime_probe_rejects_a_symlinked_css_loader_manifest(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    css_loader = plugins / "SDH-CssLoader"
    css_loader.mkdir(parents=True)
    outside = tmp_path / "outside-package.json"
    outside.write_text(
        '{"name":"SDH-CssLoader","version":"99.0.0"}',
        encoding="utf-8",
    )
    (css_loader / "package.json").symlink_to(outside)
    (css_loader / "css_theme.py").write_text(
        "CSS_LOADER_VER = 9\n",
        encoding="utf-8",
    )

    with pytest.raises(main.theme_runtime.ThemeRuntimeProbeError):
        main.theme_runtime.probe_css_loader_runtime(
            plugins,
            panel_version="0.37.12",
        )


def write_css_loader_runtime(
    plugins: pathlib.Path,
    *,
    package_version: str = "2.1.2",
    backend_source: str = "CSS_LOADER_VER = 9\n",
) -> None:
    css_loader = plugins / "SDH-CssLoader"
    css_loader.mkdir(parents=True)
    (css_loader / "package.json").write_text(
        f'{{"name":"SDH-CssLoader","version":"{package_version}"}}',
        encoding="utf-8",
    )
    (css_loader / "css_theme.py").write_text(backend_source, encoding="utf-8")


def test_theme_runtime_probe_accepts_the_maximum_safe_backend_version(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    write_css_loader_runtime(
        plugins,
        backend_source="CSS_LOADER_VER = 9007199254740991\n",
    )

    runtime = main.theme_runtime.probe_css_loader_runtime(
        plugins,
        panel_version="0.37.12",
    )

    assert runtime.css_loader_backend == 9_007_199_254_740_991


@pytest.mark.parametrize(
    "backend_source",
    [
        "CSS_LOADER_VER = 0\n",
        "CSS_LOADER_VER = 9٢\n",
        "CSS_LOADER_VER = 9007199254740992\n",
        f"CSS_LOADER_VER = {'9' * 5_000}\n",
    ],
)
def test_theme_runtime_probe_rejects_malformed_backend_versions_with_typed_error(
    theme_rpc,
    tmp_path,
    backend_source,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    write_css_loader_runtime(plugins, backend_source=backend_source)

    with pytest.raises(main.theme_runtime.ThemeRuntimeProbeError):
        main.theme_runtime.probe_css_loader_runtime(
            plugins,
            panel_version="0.37.12",
        )


def test_theme_runtime_probe_rejects_unicode_digits_in_css_loader_semver(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    write_css_loader_runtime(plugins, package_version="2.1.2١")

    with pytest.raises(main.theme_runtime.ThemeRuntimeProbeError):
        main.theme_runtime.probe_css_loader_runtime(
            plugins,
            panel_version="0.37.12",
        )


def test_theme_runtime_probe_rejects_unicode_digits_in_panel_semver(
    theme_rpc,
    tmp_path,
):
    main, _, _ = theme_rpc
    plugins = tmp_path / "plugins"
    write_css_loader_runtime(plugins)

    with pytest.raises(main.theme_runtime.ThemeRuntimeProbeError):
        main.theme_runtime.probe_css_loader_runtime(
            plugins,
            panel_version="0.37.12١",
        )


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
    def ack(token, root):
        return {"ok": True, "code": "acknowledged"}
    monkeypatch.setattr(main.theme_packages, "recover_theme_transactions", lambda root: pending)
    monkeypatch.setattr(main.theme_packages, "acknowledge_theme_rollback", ack)

    result = asyncio.run(plugin.get_theme_install_recoveries())
    confirmed = asyncio.run(plugin.acknowledge_theme_install_rollback("opaque-token"))

    assert result == {"ok": True, "code": "ready", "recoveries": pending}
    assert confirmed == {"ok": True, "code": "acknowledged"}


def test_remote_discovery_uses_the_authoritative_css_loader_runtime(theme_rpc):
    main, plugin, _ = theme_rpc
    calls = []
    runtime = main.theme_remote.ThemeRuntimeVersions(
        panel="0.37.12",
        css_loader="2.1.2",
        css_loader_backend=9,
    )
    plugin._probe_theme_runtime = lambda: runtime
    plugin._theme_remote_service = types.SimpleNamespace(
        check_releases=lambda force: calls.append(
            (force, plugin._theme_remote_runtime)
        ) or {"status": "disabled"}
    )

    result = asyncio.run(plugin.check_theme_releases(False))

    assert result == {"status": "disabled"}
    assert calls == [(False, runtime)]


def test_remote_discovery_without_css_loader_keeps_catalog_visible(theme_rpc):
    main, plugin, fake = theme_rpc
    plugins = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "plugins"
    assert not plugins.exists()
    observed = []

    def check_releases(force):
        runtime = plugin._theme_remote_runtime
        observed.append((force, runtime))
        return {
            "status": "published",
            "checkedAt": 100.0,
            "themes": [
                {
                    "catalogId": "example-theme",
                    "compatibility": (
                        "compatible"
                        if runtime.css_loader and runtime.css_loader_backend > 0
                        else "incompatible-css-loader"
                    ),
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
            "compatibility": "incompatible-css-loader",
        }
    ]
    assert observed == [
        (
            False,
            main.theme_remote.ThemeRuntimeVersions(
                panel=main.read_version(),
                css_loader="",
                css_loader_backend=0,
            ),
        )
    ]


def test_remote_install_without_css_loader_remains_blocked(theme_rpc):
    _, plugin, fake = theme_rpc
    plugins = pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "plugins"
    assert not plugins.exists()
    calls = []
    plugin._theme_remote_service = types.SimpleNamespace(
        prepare_install=lambda *args: calls.append(args)
    )

    result = asyncio.run(
        plugin.prepare_remote_theme_install("example-theme", "1.2.3")
    )

    assert result == {
        "ok": False,
        "code": "incompatible_css_loader",
        "theme_id": "example-theme",
    }
    assert calls == []


def test_remote_discovery_sanitizes_an_unexpected_service_failure(theme_rpc):
    main, plugin, _ = theme_rpc
    plugin._probe_theme_runtime = lambda: main.theme_remote.ThemeRuntimeVersions(
        panel="0.37.12",
        css_loader="2.1.2",
        css_loader_backend=9,
    )

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
    main, plugin, fake = theme_rpc
    calls = []
    prepared = {
        "ok": True,
        "code": "prepared",
        "theme_id": "example-theme",
        "theme_name": "Example Theme",
        "version": "1.2.3",
        "transaction": "opaque-token",
    }
    runtime = main.theme_remote.ThemeRuntimeVersions(
        panel="0.37.12",
        css_loader="2.1.2",
        css_loader_backend=9,
    )
    plugin._probe_theme_runtime = lambda: runtime
    plugin._theme_remote_service = types.SimpleNamespace(prepare_install=lambda *args: calls.append(
        (*args, plugin._theme_remote_runtime)
    ) or prepared)

    result = asyncio.run(
        plugin.prepare_remote_theme_install("example-theme", "1.2.3")
    )

    assert result == prepared
    assert calls == [
        (
            "example-theme",
            "1.2.3",
            pathlib.Path(fake.DECKY_USER_HOME) / "homebrew" / "themes",
            runtime,
        )
    ]


def test_remote_prepare_sanitizes_service_failures(theme_rpc):
    main, plugin, _ = theme_rpc
    plugin._probe_theme_runtime = lambda: main.theme_remote.ThemeRuntimeVersions(
        panel="0.37.12",
        css_loader="2.1.2",
        css_loader_backend=9,
    )

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
