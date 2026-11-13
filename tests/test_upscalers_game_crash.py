import os
import time

from upscalers import diagnostics, games

CONTEXT = """<?xml version="1.0" encoding="UTF-8"?>
<FGenericCrashContext><RuntimeProperties>
<CrashType>Crash</CrashType>
<ErrorMessage>Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x0 in Z:\\home\\someone\\Games\\FactoryGame\\Binaries\\Win64\\OptiScaler.dll
second line</ErrorMessage>
<CallStack>OptiScaler!UnknownFunction []
OptiScaler.dll!UnknownFunction []
amd_fidelityfx_upscaler_dx12.dll!ffxProvider []
FactoryGameSteam-Win64-Shipping.exe!FEngineLoop::Tick() []
OptiScaler.dll!Other []</CallStack>
</RuntimeProperties></FGenericCrashContext>
"""


def _crash(library, appid, project, folder, text=CONTEXT, age=0):
    path = library / "steamapps/compatdata" / appid / "pfx/drive_c/users/steamuser/AppData/Local" / project / "Saved/Crashes" / folder
    path.mkdir(parents=True)
    context = path / "CrashContext.runtime-xml"
    context.write_text(text)
    stamp = time.time() - age
    os.utime(context, (stamp, stamp))
    return context


def test_newest_unreal_crash_names_the_modules_on_its_stack(tmp_path, monkeypatch):
    monkeypatch.setattr(games, "library_paths", lambda home: [tmp_path])
    _crash(tmp_path, "526870", "FactoryGame", "old", CONTEXT.replace("OptiScaler.dll!UnknownFunction", "Old.dll!X"), age=3600)
    _crash(tmp_path, "526870", "FactoryGame", "new")
    crash = diagnostics.game_crash("/home/x", "526870")
    assert crash["type"] == "Crash"
    assert crash["modules"] == ["OptiScaler.dll", "amd_fidelityfx_upscaler_dx12.dll", "FactoryGameSteam-Win64-Shipping.exe"]
    assert crash["message"].endswith("in OptiScaler.dll")
    assert "someone" not in crash["message"] and "second line" not in crash["message"]


def test_old_or_missing_crashes_are_not_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(games, "library_paths", lambda home: [tmp_path])
    assert diagnostics.game_crash("/home/x", "1") is None
    _crash(tmp_path, "1", "Game", "a", age=30 * 24 * 3600)
    assert diagnostics.game_crash("/home/x", "1") is None


def test_crash_folders_named_by_guid_are_ordered_by_date(tmp_path, monkeypatch):
    monkeypatch.setattr(games, "library_paths", lambda home: [tmp_path])
    _crash(tmp_path, "7", "Game", "UECC-Windows-0000_0000", CONTEXT.replace("OptiScaler", "Old"), age=60)
    _crash(tmp_path, "7", "Game", "UECC-Windows-FFFF_0000", CONTEXT.replace("OptiScaler", "Older"), age=120)
    _crash(tmp_path, "7", "Game", "UECC-Windows-8888_0000")
    assert diagnostics.game_crash("/home/x", "7")["modules"][0] == "OptiScaler.dll"


def test_a_user_name_with_spaces_never_reaches_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(games, "library_paths", lambda home: [tmp_path])
    _crash(tmp_path, "9", "Game", "a", CONTEXT.replace("someone", "John Smith"))
    message = diagnostics.game_crash("/home/x", "9")["message"]
    assert "John" not in message and "Smith" not in message
    assert message.endswith("in OptiScaler.dll")
