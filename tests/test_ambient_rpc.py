import asyncio

import pytest

from ambient.rpc import AmbientRpc
from ambient.service import AmbientService


class Host(AmbientRpc):
    def __init__(self, tmp_path):
        self._tmp = tmp_path
        (tmp_path / "home" / "Pictures").mkdir(parents=True)
        (tmp_path / "home" / "Pictures" / "a.jpg").write_bytes(b"A")

    def _ambient_service_factory(self):
        return AmbientService(str(self._tmp / "state"), str(self._tmp / "cache"), str(self._tmp / "home"))


@pytest.fixture
def host(tmp_path):
    h = Host(tmp_path)
    yield h
    h._ambient_stop()


def run(coro):
    return asyncio.run(coro)


def test_state_and_save_roundtrip(host):
    state = run(host.get_ambient_state())
    assert state["settings"]["music"]["inGameRadio"] == "continue"
    saved = run(host.save_ambient_settings({"version": 1, "music": {"inGameRadio": "pause"}}))
    assert saved["music"]["inGameRadio"] == "pause"


def test_radio_catalog_retry_reaches_service_without_breaking_no_argument_calls(host, monkeypatch):
    refreshes = []

    def catalog(self, force_refresh=False):
        refreshes.append(force_refresh)
        return {"countries": [], "tags": []}

    monkeypatch.setattr(AmbientService, "radio_catalog", catalog)
    assert run(host.get_ambient_radio_catalog()) == {"countries": [], "tags": []}
    run(host.get_ambient_radio_catalog(True))
    run(host.get_ambient_radio_catalog("false"))
    assert refreshes == [False, True, False]


def test_radio_search_transport_failure_survives_rpc_for_retry_ui(host, monkeypatch):
    from ambient.adapters.radio_browser import RadioBrowserError

    def discover(self, filters):
        raise RadioBrowserError("de1.api.radio-browser.info", "TimeoutError")

    monkeypatch.setattr(AmbientService, "discover_radio", discover)
    with pytest.raises(RadioBrowserError):
        run(host.discover_ambient_radio({"country": "JP"}))


def test_scan_then_url(host):
    scanned = run(host.scan_ambient_sources())
    media_id = scanned["collections"]["known.images"][0]["id"]
    assert run(host.get_ambient_media_url(media_id)).startswith("http://127.0.0.1:")
    assert run(host.get_ambient_media_url("local:nope")) is None


def test_invalid_arguments_are_rejected_without_raising(host):
    assert run(host.add_ambient_favorite("nope", "https://x.test/a.jpg", "a")) is None
    assert run(host.add_ambient_folder("/definitely/not/here", "background")) is None
    assert run(host.record_ambient_event("bogus", "x")) is False


def test_shared_library_folder_rpc_preserves_legacy_scope_validation(host):
    path = str(host._tmp / "home" / "Pictures")
    saved = run(host.add_ambient_folder(path, "library"))
    assert saved is not None and saved["collections"]["folders"] == [path]
    state = run(host.get_ambient_state())
    folder = next(entry for entry in state["collections"] if entry["kind"] == "folder")
    assert run(host.remove_ambient_item("library", folder["id"]))["collections"]["folders"] == []
    assert run(host.add_ambient_folder(path, "invalid")) is None
    assert run(host.remove_ambient_item("invalid", folder["id"])) is None
    assert run(host.add_ambient_favorite("library", "https://example.test/a.jpg", "a")) is None


def test_calls_after_stop_are_refused(host):
    host._ambient_stop()
    with pytest.raises(RuntimeError):
        run(host.get_ambient_state())


def test_diagnostics_do_not_start_service(tmp_path):
    h = Host(tmp_path)
    assert h.ambient_diagnostics() == {"mediaServer": "stopped", "started": False}


def test_concurrent_first_calls_share_one_service(tmp_path):
    made = []

    class Counting(Host):
        def _ambient_service_factory(self):
            made.append(1)
            return super()._ambient_service_factory()

    h = Counting(tmp_path)

    async def both():
        await asyncio.gather(h.get_ambient_state(), h.scan_ambient_sources())

    run(both())
    assert len(made) == 1
    h._ambient_stop()


def test_stop_returns_immediately(tmp_path):
    import time
    h = Host(tmp_path)
    run(h.scan_ambient_sources())
    run(h.get_ambient_media_url(run(h.scan_ambient_sources())["collections"]["known.images"][0]["id"]))
    started = time.monotonic()
    h._ambient_stop()
    assert time.monotonic() - started < 0.2


def test_cancel_without_service_does_not_start_resources(host):
    assert run(host.cancel_ambient_jobs()) is False
    assert host._ambient_service is None
    assert host._ambient_pools is None


def test_cancel_after_stop_does_not_restart_resources(host):
    run(host.get_ambient_state())
    host._ambient_stop()
    assert run(host.cancel_ambient_jobs()) is False
    assert host._ambient_service is None
    assert host._ambient_pools is None


def test_cancel_interrupts_active_conversion_and_allows_next_job(host, monkeypatch):
    import sys
    from pathlib import Path

    from ambient.adapters import optimizer

    monkeypatch.setattr(optimizer, "find_ffmpeg", lambda: sys.executable)
    outputs = []

    def commands(ffmpeg, source, target, height, fps):
        outputs.append(Path(target))
        code = "import pathlib,time; pathlib.Path(" + repr(target) + ").write_bytes(b'video');"
        if len(outputs) == 1:
            code += "time.sleep(20)"
        return [[sys.executable, "-c", code, "-c:v", "libx264"]]

    monkeypatch.setattr(optimizer, "build_commands", commands)

    async def scenario():
        scanned = await host.scan_ambient_sources()
        media_id = scanned["collections"]["known.images"][0]["id"]
        service = host._ambient_service
        previous_cancel = service._cancel
        conversion = asyncio.create_task(host.optimize_ambient_media(media_id, 200))
        try:
            async def wait_for_partial():
                while not outputs or not outputs[0].exists():
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_partial(), 5)
            assert not conversion.done()
            assert await asyncio.wait_for(host.cancel_ambient_jobs(), 1) is True
            assert previous_cancel.is_set()
            assert service._cancel is not previous_cancel
            assert not service._cancel.is_set()
            assert await asyncio.wait_for(conversion, 2) == {"error": "cancelled"}
            assert not outputs[0].exists()
            assert not Path(str(outputs[0]).replace(".part.mp4", "")).exists()
            recovered = await host.optimize_ambient_media(media_id, 200)
            assert recovered["encoder"] == "libx264"
            cached = await host.optimize_ambient_media(media_id, 200)
            assert cached["encoder"] == "cached"
            assert len(outputs) == 2
        finally:
            service.cancel_jobs()
            await asyncio.gather(conversion, return_exceptions=True)

    run(scenario())


def test_nasa_feed_failure_is_recorded_and_propagated(host, monkeypatch):
    from ambient.adapters.remote_sources import RemoteError
    def unavailable(**kwargs):
        raise RemoteError("nasa_unavailable")
    monkeypatch.setattr("ambient.rpc.nasa_images", unavailable)
    with pytest.raises(RemoteError, match="nasa_unavailable"):
        run(host.get_ambient_remote_feed("nasa-apod"))
    events = host.ambient_diagnostics()["events"]
    assert any(e["kind"] == "remote_error" and "nasa_unavailable" in e["detail"] for e in events)


def test_game_media_lookup_is_not_queued_behind_a_running_encode(host, monkeypatch):
    import threading

    release = threading.Event()

    async def scenario():
        await host.get_ambient_state()
        service = host._ambient_service
        monkeypatch.setattr(service, "optimize_media", lambda *_: release.wait(5) or {"encoder": "cached"})
        monkeypatch.setattr(service, "game_media", lambda *_, **__: {"trailer": None, "theme": None})
        encode = asyncio.create_task(host.optimize_ambient_media("local:x", 200))
        await asyncio.sleep(0.05)
        try:
            assert await asyncio.wait_for(host.get_ambient_game_media("413150", "Stardew Valley"), 1) == {"trailer": None, "theme": None}
            assert not encode.done()
        finally:
            release.set()
            await encode

    run(scenario())


def test_slow_network_calls_never_hold_back_settings(host, monkeypatch):
    import threading

    release = threading.Event()

    def stalled_download(self, url, collection=""):
        release.wait(5)
        return {"error": "timeout"}

    monkeypatch.setattr(AmbientService, "cache_remote", stalled_download)

    async def scenario():
        downloads = [asyncio.create_task(host.cache_ambient_remote(f"https://example.test/{i}.mp4")) for i in range(3)]
        await asyncio.sleep(0.05)
        try:
            state = await asyncio.wait_for(host.get_ambient_state(), 1)
            assert state["settings"]["version"] == 1
        finally:
            release.set()
            await asyncio.gather(*downloads)

    run(scenario())


def test_share_session_round_trip_and_stop(host, monkeypatch):
    from ambient.adapters import share_server

    monkeypatch.setattr(share_server, "lan_address", lambda: "127.0.0.1")
    monkeypatch.setattr(share_server.ShareServer.__init__, "__defaults__", ("127.0.0.1", lambda: "127.0.0.1", share_server.SESSION_TTL_SEC))
    session = run(host.start_ambient_share({"title": "T"}))
    assert session["url"].startswith("http://127.0.0.1:")
    host._ambient_service._share._pending.append("https://a.test/x")
    assert run(host.take_ambient_shared()) == {"links": ["https://a.test/x"], "active": True}
    assert run(host.stop_ambient_share()) is True
    assert run(host.take_ambient_shared())["active"] is False
    assert run(host.start_ambient_share("nope")) == {"error": "invalid_arguments"}
