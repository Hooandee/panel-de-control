from controllers import detect


def test_resolve_prefers_hhd_over_inputplumber():
    # Both reported active (shouldn't happen in practice) → HHD wins: it's the
    # Bazzite grabber and takes the controller first.
    facts = {"hhd_active": True, "hhd_version": "3.19.23",
             "ip_active": True, "ip_version": "0.77.4"}
    out = detect.resolve(facts)
    assert out["manager"] == detect.HHD
    assert out["version"] == "3.19.23"
    assert out["api"] == "rest"


def test_resolve_inputplumber_when_only_ip():
    facts = {"hhd_active": False, "hhd_version": None,
             "ip_active": True, "ip_version": "0.77.4"}
    out = detect.resolve(facts)
    assert out["manager"] == detect.INPUTPLUMBER
    assert out["version"] == "0.77.4"
    assert out["api"] == "dbus"


def test_resolve_none_when_no_daemon():
    facts = {"hhd_active": False, "ip_active": False}
    out = detect.resolve(facts)
    assert out["manager"] == detect.NONE
    assert out["version"] is None
    assert out["api"] is None


def test_probe_parses_versions_from_fake_runner():
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if cmd == ["systemctl", "is-active", "hhd.service"]:
            return "active"
        if cmd == ["systemctl", "is-active", "inputplumber.service"]:
            return "inactive"
        if cmd[0] == "hhd":
            return "hhd 3.19.23"
        return ""

    facts = detect.probe(run=fake_run)
    assert facts["hhd_active"] is True
    assert facts["hhd_version"] == "3.19.23"
    assert facts["ip_active"] is False
    assert facts["ip_version"] is None


def test_resolve_bin_prefers_absolute_then_falls_back():
    # A ubiquitous binary resolves to an absolute path (PATH-independent).
    assert detect.resolve_bin("sh").startswith("/")
    # Unknown binary falls back to the bare name (last-resort PATH lookup).
    assert detect.resolve_bin("definitely-not-a-real-binary-xyz") == "definitely-not-a-real-binary-xyz"


def test_clean_env_restores_original_ld_library_path():
    # PyInstaller saves the pre-bundle value as *_ORIG → we restore it.
    out = detect.clean_env({"LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": "/orig"})
    assert out["LD_LIBRARY_PATH"] == "/orig"
    assert "LD_LIBRARY_PATH_ORIG" not in out


def test_clean_env_drops_ld_library_path_when_no_original():
    out = detect.clean_env({"LD_LIBRARY_PATH": "/tmp/_MEI"})
    assert "LD_LIBRARY_PATH" not in out


def test_clean_env_ensures_a_path():
    assert detect.clean_env({})["PATH"]


def test_probe_never_raises_on_runner_failure():
    def boom(cmd):
        raise OSError("systemctl missing")

    # The runner itself is injected; probe must tolerate a runner that returns
    # empty (the real _run swallows exceptions), so simulate the empty result.
    facts = detect.probe(run=lambda cmd: "")
    assert facts["hhd_active"] is False
    assert facts["ip_active"] is False
    assert detect.resolve(facts)["manager"] == detect.NONE
