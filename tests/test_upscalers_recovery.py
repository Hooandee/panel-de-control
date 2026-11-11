import hashlib
import json
import shutil
from pathlib import Path

import pytest

from test_upscalers import APPID, _service, _write, fake_catalog, proc, steam  # noqa: F401
from upscalers import assets as assets_mod
from upscalers import catalog, games, latest, prefix_dependencies
from upscalers import service as service_mod
from upscalers.catalog import Asset, Build
from upscalers.service import UpscalerError


class Killed(BaseException):
    pass


def test_service_killed_mid_copy_keeps_the_original_for_the_next_attempt(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    target = game / "bin/x64_dx12"
    original = _write(target / "dxgi.dll", b"ORIGINAL reshade dxgi")
    service = _service(steam, fake_catalog, proc)
    real_copy = shutil.copyfile

    def dying(src, dst, *args, **kwargs):
        result = real_copy(src, dst, *args, **kwargs)
        if Path(dst).name == "dxgi.dll":
            raise Killed()
        return result

    with monkeypatch.context() as patched:
        patched.setattr(service_mod.shutil, "copyfile", dying)
        patched.setattr(service_mod.UpscalerService, "_remove_files", staticmethod(lambda target, configuration=None: []))
        with pytest.raises(Killed):
            service.install(APPID, {"build": "fsr-test"})

    restarted = _service(steam, fake_catalog, proc)
    assert restarted.state["games"].get(APPID, {}).get("install") is None
    restarted.install(APPID, {"build": "fsr-test"})
    restarted.uninstall(APPID)
    assert original.read_bytes() == b"ORIGINAL reshade dxgi"
    assert not (target / games.MANIFEST_DIR).exists()


def test_leftovers_without_a_manifest_return_the_backed_up_originals(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    _write(target / "dxgi.dll", b"panel injector")
    _write(target / games.MANIFEST_DIR / "backup/dxgi.dll", b"original dxgi")
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    service.uninstall(APPID)
    assert (target / "dxgi.dll").read_bytes() == b"original dxgi"


def test_a_failed_download_leaves_the_working_install_in_place(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    target = Path(service.state["games"][APPID]["install"]["target"])
    net = Asset("net", "net.dll", hashlib.sha256(b"n").hexdigest(), 1, ("https://invalid.example/net.dll",))
    monkeypatch.setitem(catalog.ASSETS, "net", net)
    monkeypatch.setitem(catalog.BUILDS, "fsr-net", Build("fsr-net", "fsr", "4.1.2", ("rdna2",), 3, 3, assets=("net",)))
    monkeypatch.setattr(assets_mod, "BACKOFF_S", (0, 0))
    monkeypatch.setattr(assets_mod.AssetCache, "_fetch", lambda *args: (_ for _ in ()).throw(OSError("HTTP 504")))
    with pytest.raises(assets_mod.AssetError, match="download_failed"):
        service.install(APPID, {"build": "fsr-net"})
    assert service.state["games"][APPID]["install"]["build"] == "fsr-test"
    assert (target / "dxgi.dll").is_file()


def test_an_interrupted_checkpoint_folder_never_blocks_other_games(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    orphan = Path(fake_catalog) / "scaler-transitions" / ("0" * 64)
    orphan.mkdir(parents=True)
    service.install(APPID, {"build": "fsr-test"})
    assert not orphan.exists()


def test_playing_while_a_change_is_pending_never_strands_the_game(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {"build": "fsr-test"})
    target = Path(service.state["games"][APPID]["install"]["target"])
    _write(target / "OptiScaler.log", b"written while playing")
    _write(target / "OptiScaler.ini", b"[Upscalers]\nDx12Upscaler=xess\n")
    assert service.begin_scaler_transition(APPID)["recovery"] is True
    service.finish_scaler_transition(APPID, checkpoint["token"], False)
    assert not service.scaler_transitions.pending(APPID)
    service.uninstall(APPID)


def test_rolling_back_after_playing_restores_the_game(steam, fake_catalog, proc):
    _, game = steam
    before = {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}
    service = _service(steam, fake_catalog, proc)
    checkpoint = service.begin_scaler_transition(APPID)
    service.install(APPID, {"build": "fsr-test"})
    target = Path(service.state["games"][APPID]["install"]["target"])
    _write(target / "OptiScaler.log", b"written while playing")
    service.finish_scaler_transition(APPID, checkpoint["token"], True)
    after = {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}
    assert after == before


def test_a_disk_error_mid_install_reports_itself_and_cleans_up(steam, fake_catalog, proc, monkeypatch):
    _, game = steam
    before = {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}
    service = _service(steam, fake_catalog, proc)
    checkpoint = service.begin_scaler_transition(APPID)
    real = shutil.copyfile
    calls = {"count": 0}

    def flaky(src, dst, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError(28, "No space left on device")
        return real(src, dst, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(service_mod.shutil, "copyfile", flaky)
        with pytest.raises(OSError, match="No space"):
            service.install(APPID, {"build": "fsr-test"})
    service.finish_scaler_transition(APPID, checkpoint["token"], True)
    after = {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}
    assert after == before


def _transaction(tmp_path):
    compat = tmp_path / "steamapps/compatdata/123"
    (compat / "pfx").mkdir(parents=True)
    transaction = compat.parent / ".pdc-dependencies-123"
    transaction.mkdir()
    return compat, transaction


def test_a_transaction_without_receipt_that_published_nothing_rolls_back(tmp_path):
    compat, transaction = _transaction(tmp_path)
    receipt = prefix_dependencies._recovered(compat, transaction)
    assert receipt["state"] == "rolled_back"
    prefix_dependencies.finish(receipt, str(tmp_path))
    assert not transaction.exists()
    assert (compat / "pfx").is_dir()


def test_a_transaction_interrupted_mid_publish_puts_the_original_prefix_back(tmp_path):
    compat, transaction = _transaction(tmp_path)
    (compat / "pfx").rename(transaction / "original-pfx")
    (transaction / "original-pfx/marker").write_text("original")
    receipt = prefix_dependencies._recovered(compat, transaction)
    assert receipt["state"] == "rolled_back"
    assert (compat / "pfx/marker").read_text() == "original"


def test_a_corrupt_receipt_after_publishing_is_still_recoverable(tmp_path):
    compat, transaction = _transaction(tmp_path)
    (transaction / "original-pfx").mkdir()
    (transaction / "receipt.json").write_text("{not json")
    receipt = prefix_dependencies._recovered(compat, transaction)
    assert receipt["state"] == "published"
    assert json.loads((transaction / "receipt.json").read_text())["state"] == "published"


# ---- newest releases -------------------------------------------------------------------------------------

PINNED = Asset("reframework-nightly", "REFramework.zip", "a" * 64, 10,
               ("https://github.com/praydog/REFramework-nightly/releases/download/old/REFramework.zip",), member="dinput8.dll")


def _release(tag, published, digest="b" * 64, prerelease=False, name="REFramework.zip", owner="praydog/REFramework-nightly"):
    return {"tag_name": tag, "published_at": published, "prerelease": prerelease, "draft": False, "assets": [{
        "name": name, "size": 12, "digest": f"sha256:{digest}",
        "browser_download_url": f"https://github.com/{owner}/releases/download/{tag}/{name}"}]}


def test_newest_release_with_its_published_digest_is_chosen(tmp_path):
    releases = [_release("n1", "2026-11-01T00:00:00Z", "c" * 64), _release("n2", "2026-11-08T00:00:00Z")]
    resolver = latest.Resolver(tmp_path, fetch=lambda url: json.dumps(releases).encode())
    chosen = resolver.resolve(PINNED)
    assert (chosen.sha256, chosen.size, chosen.member) == ("b" * 64, 12, "dinput8.dll")
    assert chosen.urls[0].endswith("/n2/REFramework.zip")
    assert resolver.version(chosen) == "n2"


def test_releases_without_digest_from_elsewhere_or_unstable_are_ignored(tmp_path):
    releases = [
        _release("pre", "2026-11-09T00:00:00Z", prerelease=True),
        _release("fork", "2026-11-09T00:00:00Z", owner="someone/fork"),
        {**_release("nodigest", "2026-11-09T00:00:00Z"), "assets": [{**_release("x", "y")["assets"][0], "digest": None}]},
    ]
    resolver = latest.Resolver(tmp_path, fetch=lambda url: json.dumps(releases).encode())
    assert resolver.resolve(PINNED) == PINNED


def test_last_known_release_is_used_offline_and_lookups_are_spaced(tmp_path):
    calls = []
    now = [1000.0]

    def fetch(url):
        calls.append(url)
        if len(calls) > 1:
            raise OSError("offline")
        return json.dumps([_release("n2", "2026-11-08T00:00:00Z")]).encode()

    resolver = latest.Resolver(tmp_path, fetch=fetch, clock=lambda: now[0])
    assert resolver.resolve(PINNED).sha256 == "b" * 64
    assert resolver.resolve(PINNED).sha256 == "b" * 64
    assert len(calls) == 1
    now[0] += latest.FRESH_S + 1
    restarted = latest.Resolver(tmp_path, fetch=fetch, clock=lambda: now[0])
    assert restarted.resolve(PINNED).sha256 == "b" * 64
    assert len(calls) == 2


def test_untracked_assets_stay_pinned(tmp_path):
    asset = Asset("fsr-4.1.2-dll-upscaler", "x.7z", "a" * 64, 1, ("https://example.invalid/x",))
    assert latest.Resolver(tmp_path, fetch=lambda url: b"[]").resolve(asset) is asset


def test_a_broken_newest_release_falls_back_to_the_catalog_one(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    archive = catalog.BUILDS["fsr-test"].archive
    pinned = catalog.ASSETS[archive]
    newest = Asset(pinned.id, "newest.7z", "f" * 64, 99, ("https://example.invalid/newest.7z",), archive=pinned.archive,
                   generation=pinned.generation)
    monkeypatch.setattr(service.latest, "resolve", lambda asset: newest if asset.id == pinned.id else asset)
    monkeypatch.setattr(service.latest, "tracked", lambda asset: asset.id == pinned.id)
    monkeypatch.setattr(assets_mod, "BACKOFF_S", (0, 0))
    real_fetch = assets_mod.AssetCache._fetch

    def fetch(cache, url, asset, progress, cancelled):
        if asset.sha256 == newest.sha256:
            raise assets_mod.AssetError("hash_mismatch")
        return real_fetch(cache, url, asset, progress, cancelled)

    monkeypatch.setattr(assets_mod.AssetCache, "_fetch", fetch)
    service.install(APPID, {"build": "fsr-test"})
    assert service.cache.ready(pinned) and not service.cache.ready(newest)
    assert service.state["games"][APPID]["install"]["build"] == "fsr-test"
    component = next(item for item in service.state["games"][APPID]["install"]["components"] if item["id"] == pinned.id)
    assert component["source"] == "pinned" and component["fallback"] == "hash_mismatch"


def test_a_cancelled_install_reports_cancelled_and_keeps_the_game(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    net = Asset("net2", "net.dll", hashlib.sha256(b"n").hexdigest(), 1, ("https://invalid.example/net.dll",))
    monkeypatch.setitem(catalog.ASSETS, "net2", net)
    monkeypatch.setitem(catalog.BUILDS, "fsr-net2", Build("fsr-net2", "fsr", "4.1.2", ("rdna2",), 3, 3, assets=("net2",)))
    service._cancel.set()
    monkeypatch.setattr(assets_mod.AssetCache, "_fetch", lambda *args: (_ for _ in ()).throw(assets_mod.AssetError("cancelled")))
    with pytest.raises(assets_mod.AssetError, match="cancelled"):
        service.install(APPID, {"build": "fsr-net2"})
    assert service.state["games"][APPID]["install"]["build"] == "fsr-test"



def _log(target, render, output="1920x1080", started=None):
    from datetime import datetime, timedelta
    clock = (started or datetime.now()).strftime("%H:%M:%S.000000")
    _write(target / "OptiScaler.log", (f"[{clock}] [I] Creating new FSR 4 upscaler\n"
                                        f"[{clock}] [I] IFeature::SetInitParameters Render Resolution: {render}, Display Resolution {output}, Quality: 0\n").encode())


@pytest.mark.parametrize("render, result", [("1129x635", "respected"), ("960x540", "ignored")])
def test_first_launch_shows_whether_the_game_takes_panels_quality(steam, fake_catalog, proc, render, result):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test", "quality": "balanced"})
    target = Path(service.state["games"][APPID]["install"]["target"])
    _log(target, render)
    assert service.game(APPID)["install"]["quality_check"]["result"] == result


def test_a_new_quality_waits_for_the_next_launch_before_judging(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test", "quality": "balanced"})
    target = Path(service.state["games"][APPID]["install"]["target"])
    from datetime import datetime, timedelta
    _log(target, "960x540", started=datetime.now() - timedelta(minutes=1))
    service.configure(APPID, {"build": "fsr-test", "quality": "performance"})
    (target / "OptiScaler.log").write_text((target / "OptiScaler.log").read_text() + "[I] still playing\n")
    assert service.game(APPID)["install"]["quality_check"] is None


def test_a_file_the_game_updated_survives_a_version_change(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    _write(target / "dxgi.dll", b"game dxgi 1.0")
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    (target / "dxgi.dll").write_bytes(b"game dxgi 2.0 from an update")
    service.install(APPID, {"build": "fsr-test", "quality": "balanced"})
    service.uninstall(APPID)
    assert (target / "dxgi.dll").read_bytes() == b"game dxgi 2.0 from an update"


def test_reframework_rewriting_its_config_never_blocks_the_next_change(tmp_path):
    from upscalers.scaler_transition import Checkpoints
    root = tmp_path / "game"
    root.mkdir()
    seed = tmp_path / "seed.txt"
    seed.write_text("REFrameworkConfig_MenuOpen=false\n")
    loader = tmp_path / "dinput8.dll"
    loader.write_bytes(b"framework")
    service_mod.UpscalerService._apply_files(service_mod.UpscalerService.__new__(service_mod.UpscalerService),
                                             root, {"dinput8.dll": loader, "re2_fw_config.txt": seed}, "[x]\n")
    (root / "re2_fw_config.txt").write_text("REFrameworkConfig_MenuOpen=false\nREFrameworkConfig_FontSize=18\n")
    Checkpoints(tmp_path / "state").begin("883710", root, {"install": {}}, None, target=str(root), configuration={})


def test_a_failed_release_lookup_waits_before_asking_again(tmp_path):
    calls = []
    now = [10_000.0]

    def fetch(url):
        calls.append(url)
        raise OSError("offline")

    resolver = latest.Resolver(tmp_path, fetch=fetch, clock=lambda: now[0])
    assert resolver.resolve(PINNED) == PINNED
    assert resolver.resolve(PINNED) == PINNED
    assert len(calls) == 1
    now[0] += latest.RETRY_S + 1
    resolver.resolve(PINNED)
    assert len(calls) == 2


def test_wine_paths_in_reports_hide_the_user_name():
    from report import collector
    assert "alice" not in collector.redact_text(r"Z:\home\alice\.local\share\Steam\game.log")


# ---- reports tell our failures from someone else's -------------------------------------------------------
def test_report_shows_the_ini_as_panel_wrote_it_and_what_changed_after(steam, fake_catalog, proc):
    from upscalers import diagnostics
    _, game = steam
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    install = service.state["games"][APPID]["install"]
    path = Path(install["target"]) / "OptiScaler.ini"
    assert diagnostics.ini_drift(install, path)["status"] == "as_written"
    service.configure(APPID, {**install["options"], "quality": "performance"})
    assert diagnostics.ini_drift(install, path)["status"] == "as_written"
    text = path.read_text()
    written = install["ini_written"]["values"]
    assert written
    key = next(iter(written))
    name = key.split(".", 1)[1]
    path.write_text(text.replace(f"{name}={written[key]}", f"{name}=changed", 1))
    drift = diagnostics.ini_drift(install, path)
    assert drift["status"] == "changed" and drift["keys"][key] == {"panel": written[key], "now": "changed"}
    path.unlink()
    assert diagnostics.ini_drift(install, path)["status"] == "missing"
    assert diagnostics.ini_drift({}, path) == {"status": "unrecorded"}


def test_a_failed_job_keeps_its_detail_in_the_game_history(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)

    def failing(appid, choice):
        raise assets_mod.AssetError("download_failed", "HTTPError: HTTP Error 503: Service Unavailable")

    failing.__name__ = "install"
    service.begin("install", APPID)
    service.run(failing, APPID, {"build": "fsr-test"})
    last = service.state["games"][APPID]["actions"][-1]
    assert last["error"] == "download_failed" and last["detail"] == "HTTPError; HTTP Error 503"


@pytest.mark.parametrize(("raw", "kept"), [
    ("URLError: <urlopen error [Errno -2] Name or service not known>", "URLError; Name or service not known"),
    ("token=secret https://x.invalid/?sig=abc", None),
    ("1048576", "1048576"),
    ("OSError: [Errno 28] No space left on device: '/home/deck/x'", "OSError; No space left on device"),
])
def test_error_detail_keeps_only_recognisable_causes(raw, kept):
    from upscalers import diagnostics
    assert diagnostics.error_detail(raw) == kept


def _steam_game(home, appid, folder, build="1"):
    root = home / ".local/share/Steam"
    _write(root / f"steamapps/appmanifest_{appid}.acf",
           '"AppState"\n{\n "appid" "%s"\n "name" "%s"\n "installdir" "%s"\n "StateFlags" "4"\n "buildid" "%s"\n}\n' % (appid, folder, folder, build))
    return root / "steamapps/common" / folder


def test_a_steam_game_shipping_only_its_linux_build_is_a_linux_game(steam, fake_catalog, proc):
    home, _ = steam
    game = _steam_game(home, "1086940", "Baldurs Gate 3")
    binary = _write(game / "bin/bg3", b"\x7fELF" + b"\0" * 64)
    binary.chmod(0o755)
    _write(game / "bin/amd_fidelityfx_dx12.dll", b"MZ")
    service = _service(steam, fake_catalog, proc)
    detail = service.game("1086940")
    assert detail["native"] is True
    with pytest.raises(UpscalerError, match="native_game"):
        service.install("1086940", {"build": "fsr-test"})


def test_a_windows_game_with_linux_helpers_stays_a_windows_game(steam, fake_catalog, proc):
    home, game = steam
    helper = _write(game / "tools/crashpad_handler", b"\x7fELF" + b"\0" * 64)
    helper.chmod(0o755)
    assert games.find_installed(str(home), APPID).native is False
    deep = _steam_game(home, "555", "Deep")
    _write(deep / "a/b/c/d/e/f/g/Game.exe", b"MZ")
    _write(deep / "launcher", b"\x7fELF").chmod(0o755)
    assert games.find_installed(str(home), "555").native is False


def test_reinstalling_keeps_what_panel_added_to_the_launch_options(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    first = service.install(APPID, {"build": "fsr-test"})
    service.record_added_args(APPID, [], first["overrides"], [])
    service.install(APPID, {"build": "fsr-test"})
    # The options are already in place, so the second pass adds nothing new.
    service.record_added_args(APPID, [], [], [])
    assert service.uninstall(APPID)["overrides"] == first["overrides"] != []
