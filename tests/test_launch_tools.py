import os

from launch.tools import detect_tools


def _write_os_release(root, text):
    d = os.path.join(root, "etc")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "os-release"), "w") as f:
        f.write(text)


def _fake_which(present):
    return lambda name: ("/usr/bin/" + name) if name in present else None


def test_detects_tools_from_path(tmp_path):
    _write_os_release(str(tmp_path), 'ID=bazzite\nPRETTY_NAME="Bazzite"\n')
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which({"mangohud", "gamemoderun"}))
    assert t["mangohud"] is True
    assert t["gamemode"] is True
    assert t["gamescope"] is False
    assert t["distro"] == "bazzite"
    assert t["locale_reliable"] is True


def test_lsfg_via_wrapper_file(tmp_path):
    open(os.path.join(str(tmp_path), "lsfg"), "w").close()
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which(set()))
    assert t["lsfg"] is True


def test_lsfg_via_config_dir(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), ".config", "lsfg-vk"))
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which(set()))
    assert t["lsfg"] is True


def test_lsfg_absent(tmp_path):
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which(set()))
    assert t["lsfg"] is False


def test_steamos_locale_unreliable(tmp_path):
    _write_os_release(str(tmp_path), 'ID=steamos\nPRETTY_NAME="SteamOS Holo"\n')
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which(set()))
    assert t["distro"] == "steamos"
    assert t["locale_reliable"] is False


def test_unknown_distro_defaults_other(tmp_path):
    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=_fake_which(set()))
    assert t["distro"] == "other"
    assert t["locale_reliable"] is True


def test_never_raises_on_bad_which(tmp_path):
    def boom(_):
        raise RuntimeError("no PATH")

    t = detect_tools(root=str(tmp_path), home=str(tmp_path), which=boom)
    assert t["mangohud"] is False
