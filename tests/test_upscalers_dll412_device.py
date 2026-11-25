import pytest

from upscalers.service import UpscalerError, UpscalerService


@pytest.mark.parametrize("device", ["steam_deck_lcd", "steam_deck_oled"])
def test_deck_sdk_is_not_suggested_but_still_installs(tmp_path, monkeypatch, device):
    service = UpscalerService(str(tmp_path), str(tmp_path / "state"), "rdna2", device=device)
    calls = []
    monkeypatch.setattr(service, "_install_dll", lambda appid, build, choice: calls.append(build.id) or {"ok": True})
    assert service.install("42", {"build": "fsr-4.1.2-dll"}) == {"ok": True}
    assert service.install("42", {"build": "fsr-4.1.2-lite-dll"}) == {"ok": True}
    assert calls == ["fsr-4.1.2-dll", "fsr-4.1.2-lite-dll"]
    builds = {build["id"]: build for build in service.overview()["builds"]}
    assert builds["fsr-4.1.2-dll"]["supported"] is False
    assert builds["fsr-4.1.2-lite-dll"]["supported"] is True


def test_z2a_keeps_sdk_route(tmp_path, monkeypatch):
    service = UpscalerService(str(tmp_path), str(tmp_path / "state"), "rdna2", device="rog_xbox_ally")
    monkeypatch.setattr(service, "_install_dll", lambda *args: {"ok": True})
    assert service.install("42", {"build": "fsr-4.1.2-dll"}) == {"ok": True}
    builds = {build["id"]: build for build in service.overview()["builds"]}
    assert builds["fsr-4.1.2-dll"]["supported"] is True
