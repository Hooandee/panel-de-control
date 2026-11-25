import shlex
import tomllib

import pytest

from upscalers import lsfg, service as service_module
from upscalers.lsfg import Lsfg, LsfgError

DAVE = "1868140"


def native_layer(home):
    (home / ".local/lib").mkdir(parents=True)
    (home / ".local/lib/liblsfg-vk.so").write_bytes(b"v1")
    manifest = home / ".local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")


def lossless(home, dll="Lossless.dll"):
    game = home / ".local/share/Steam/steamapps/common/Lossless Scaling"
    game.mkdir(parents=True)
    (game / dll).write_bytes(b"dll")
    (game.parent.parent / "appmanifest_993090.acf").write_text("x")
    return game / dll


def arm_engine(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return home, Lsfg(str(home), tmp_path / "state", arm=True)


def test_arm_without_a_native_layer_says_why_and_installs_nothing(tmp_path):
    home, engine = arm_engine(tmp_path)
    try:
        status = engine.status()
        assert status["arm"] is True
        assert status["unavailable"] == "lsfg_arm_no_layer"
        with pytest.raises(LsfgError) as error:
            engine.install_native()
        assert error.value.code == "lsfg_arm_no_layer"
        assert not (home / ".local/lib").exists() and not engine.config_path.exists()
    finally:
        engine.close()


def test_arm_ignores_a_v2_layer_it_cannot_configure(tmp_path):
    home, engine = arm_engine(tmp_path)
    try:
        (home / ".local/lib").mkdir(parents=True)
        (home / ".local/lib/liblsfg-vk-layer.so").write_bytes(b"v2")
        assert engine.status()["unavailable"] == "lsfg_arm_no_layer"
    finally:
        engine.close()


def test_dave_the_diver_gets_a_v1_profile_and_the_native_launch_env(tmp_path):
    home, engine = arm_engine(tmp_path)
    try:
        native_layer(home)
        dll = lossless(home)
        layer_before = (home / ".local/lib/liblsfg-vk.so").read_bytes()
        status = engine.install_native()
        assert status["installed"] and status["unavailable"] is None
        assert status["dll"] == str(dll)
        result = engine.set_game(DAVE, "Dave the Diver", {"multiplier": 3, "flow_scale": 0.75, "performance": True}, "DaveTheDiver.exe")
        env = result["env"]
        assert env["ENABLE_GAMESCOPE_WSI"] == "0" and env["DXVK_HDR"] == "0"
        assert env["LSFG_PROCESS"] == f"pdc-{DAVE}"
        assert shlex.split(env["LSFG_CONFIG"]) == [str(engine.config_path)]
        assert not any(key.startswith("LSFGVK_") for key in env)
        text = engine.config_path.read_text()
        assert text.splitlines()[0] == lsfg.MARKER
        config = tomllib.loads(text)
        assert config["version"] == 1
        assert config["global"] == {"dll": str(dll), "no_fp16": False}
        assert config["game"] == [{"exe": f"pdc-{DAVE}", "multiplier": 3, "flow_scale": 0.75, "performance_mode": True}]
        assert "profile" not in config and "active_in" not in text and "lsfg-vk.dll" not in text
        assert (home / ".local/lib/liblsfg-vk.so").read_bytes() == layer_before
    finally:
        engine.close()


def test_arm_uninstall_removes_the_config_but_never_the_native_layer(tmp_path):
    home, engine = arm_engine(tmp_path)
    try:
        native_layer(home)
        engine.install_native()
        engine.set_game(DAVE, "Dave", {"multiplier": 2})
        engine.uninstall()
        assert not engine.config_path.exists()
        assert (home / ".local/lib/liblsfg-vk.so").is_file()
        assert not engine.status()["installed"]
    finally:
        engine.close()


def test_arm_leaves_the_users_own_config_alone_until_adopted(tmp_path):
    home, engine = arm_engine(tmp_path)
    try:
        native_layer(home)
        engine.config_path.parent.mkdir(parents=True)
        original = b'version = 1\n[global]\ndll = "/x/Lossless.dll"\n'
        engine.config_path.write_bytes(original)
        assert engine.status()["foreign"] is True
        with pytest.raises(LsfgError) as error:
            engine.install_native()
        assert error.value.code == "lsfg_foreign"
        assert engine.config_path.read_bytes() == original
        engine.adopt_foreign()
        assert (home / ".local/lib/liblsfg-vk.so").is_file()
        assert engine.install_native()["installed"]
        engine.uninstall()
        engine.restore_foreign()
        assert engine.config_path.read_bytes() == original
    finally:
        engine.close()


def test_x86_keeps_the_v2_layer_config_and_launch_env(tmp_path):
    from test_upscalers_lsfg_update import payload

    engine = Lsfg(str(tmp_path / "home"), tmp_path / "state", arm=False)
    try:
        assert engine.status()["unavailable"] is None
        engine.install(payload(tmp_path / "bundle", b"layer"), "2.0.0")
        env = engine.set_game(DAVE, "Dave", {"multiplier": 2}, "DaveTheDiver.exe")["env"]
        assert env["LSFGVK_PROFILE"] == f"pdc-{DAVE}" and "LSFG_PROCESS" not in env
        config = tomllib.loads(engine.config_path.read_text())
        assert config["version"] == 2 and config["profile"][0]["active_in"] == ["DaveTheDiver.exe"]
        with pytest.raises(LsfgError):
            engine.install_native()
    finally:
        engine.close()


def test_service_never_downloads_the_x86_archive_on_arm(tmp_path, monkeypatch):
    home, engine = arm_engine(tmp_path)
    try:
        calls = []
        stub = type("S", (), {})()
        stub.lsfg = engine
        stub.cache = type("C", (), {"ensure": lambda *a, **k: calls.append(1)})()
        with pytest.raises(service_module.UpscalerError) as error:
            service_module.UpscalerService.lsfg_install(stub)
        assert error.value.code == "lsfg_arm_no_layer" and not calls
    finally:
        engine.close()
