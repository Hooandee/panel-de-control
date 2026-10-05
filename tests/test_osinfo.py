import os

from osinfo import read_os_name


def _write_os_release(root, text):
    d = os.path.join(root, "etc")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "os-release"), "w") as f:
        f.write(text)


def test_missing_file_returns_none(tmp_path):
    assert read_os_name(root=str(tmp_path)) is None


def test_prefers_pretty_name(tmp_path):
    _write_os_release(str(tmp_path), 'NAME="Bazzite"\nPRETTY_NAME="Bazzite 43"\n')
    assert read_os_name(root=str(tmp_path)) == "Bazzite 43"


def test_falls_back_to_name(tmp_path):
    _write_os_release(str(tmp_path), 'ID=cachyos\nNAME="CachyOS"\n')
    assert read_os_name(root=str(tmp_path)) == "CachyOS"


def test_strips_quotes(tmp_path):
    _write_os_release(str(tmp_path), 'PRETTY_NAME="SteamOS Holo 3.8.11"\n')
    assert read_os_name(root=str(tmp_path)) == "SteamOS Holo 3.8.11"


def test_ignores_malformed_lines(tmp_path):
    _write_os_release(str(tmp_path), "garbage-no-equals\nPRETTY_NAME=Plain\n")
    assert read_os_name(root=str(tmp_path)) == "Plain"


def test_empty_returns_none(tmp_path):
    _write_os_release(str(tmp_path), "")
    assert read_os_name(root=str(tmp_path)) is None


def test_host_root_wins_over_an_emulator_rootfs(monkeypatch, tmp_path):
    import osinfo

    host = tmp_path / "host"
    (host / "etc").mkdir(parents=True)
    (host / "etc/os-release").write_text('NAME="Armada"\nID=armada\n')
    monkeypatch.setattr(osinfo, "_HOST_ROOT", str(host))
    assert osinfo.read_os_id() == "armada"
    assert osinfo.read_os_name() == "Armada"


def test_unreadable_host_root_falls_back_to_the_given_root(monkeypatch, tmp_path):
    import osinfo

    monkeypatch.setattr(osinfo, "_HOST_ROOT", str(tmp_path / "missing"))
    assert osinfo._os_release_paths("/")[-1] == "/etc/os-release"
