import asyncio
import json
import threading
from pathlib import Path

import pytest

from test_tdp_guard_rpc import plugin
from upscalers.service import UpscalerService


def test_support_snapshot_keeps_loop_alive_while_mako_is_locked(plugin, tmp_path):
    profile = json.loads((Path(__file__).parent / "fixtures/upscalers/mako_support_profile.json").read_text())
    service = UpscalerService(str(tmp_path / "home"), str(tmp_path / "state"), "rdna2")
    plugin._upscaler_service = service
    locked = threading.Event()
    heartbeat = threading.Event()
    released_by_heartbeat = []

    def update_mako():
        with service.mako._lock:
            locked.set()
            released_by_heartbeat.append(heartbeat.wait(2))
            service.mako._save(profile)

    writer = threading.Thread(target=update_mako)
    writer.start()
    assert locked.wait(2)

    async def read():
        asyncio.get_running_loop().call_later(0.01, heartbeat.set)
        return await plugin._support_upscalers_state()

    try:
        snapshot = asyncio.run(read())
    finally:
        heartbeat.set()
        writer.join(2)
    assert released_by_heartbeat == [True]
    assert snapshot["gpu"] == "rdna2"
    assert snapshot["mako"]["profiles"] == profile["profiles"]
    assert snapshot["installs"] == {}


def test_support_snapshot_errors_keep_section_unavailable(plugin, tmp_path, monkeypatch):
    import main

    service = UpscalerService(str(tmp_path / "home"), str(tmp_path / "state"), "rdna2")
    plugin._upscaler_service = service

    def failed_read():
        raise OSError("read failed")

    monkeypatch.setattr(service.mako, "_state", failed_read)
    with pytest.raises(OSError, match="read failed"):
        asyncio.run(plugin._support_upscalers_state())
    monkeypatch.setattr(main, "_SUPPORT_SECTIONS", {"upscalers": (("_support_upscalers_state", ()),)})
    assert asyncio.run(plugin._support_section_states()) == {
        "upscalers": {"unavailable": "OSError"},
    }


def test_support_snapshot_does_not_initialize_unused_service(plugin):
    plugin._upscaler_service = None
    assert asyncio.run(plugin._support_upscalers_state()) == {"loaded": False}
