import os

from launch.proton_caps import detect_capabilities


def _write_proton(root, compat_name, body):
    d = os.path.join(root, ".steam", "steam", "compatibilitytools.d", compat_name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "proton"), "w") as f:
        f.write(body)


PROTON_BODY = """
    def config(self):
        self.check_environment("PROTON_NO_NTSYNC", "nontsync")
        self.check_environment("PROTON_ENABLE_HDR", "hdr")
        self.check_environment("PROTON_FSR4_RDNA3_UPGRADE", "fsr4rdna3")
        self.check_environment("PROTON_PREFER_SDL", "sdlinput")
"""


def test_reads_supported_vars_from_script(tmp_path):
    _write_proton(str(tmp_path), "GE-Proton10-21", PROTON_BODY)
    caps = detect_capabilities("GE-Proton10-21", home=str(tmp_path))
    assert caps["found"] is True
    assert "PROTON_NO_NTSYNC" in caps["envs"]
    assert "PROTON_ENABLE_HDR" in caps["envs"]
    assert "PROTON_FSR4_RDNA3_UPGRADE" in caps["envs"]
    assert "PROTON_PREFER_SDL" in caps["envs"]
    # Core vars always present.
    assert "PROTON_LOG" in caps["envs"]


def test_absent_var_not_reported(tmp_path):
    _write_proton(str(tmp_path), "GE-Proton10-21", PROTON_BODY)
    caps = detect_capabilities("GE-Proton10-21", home=str(tmp_path))
    # FSR3/XeSS aren't in this script → not offered.
    assert "PROTON_FSR3_UPGRADE" not in caps["envs"]
    assert "PROTON_XESS_UPGRADE" not in caps["envs"]


def test_not_found_is_conservative(tmp_path):
    caps = detect_capabilities("Nonexistent-Proton", home=str(tmp_path))
    assert caps["found"] is False
    # Only core vars — never promise unverified options.
    assert "PROTON_LOG" in caps["envs"]
    assert "PROTON_ENABLE_HDR" not in caps["envs"]


def test_never_raises(tmp_path):
    assert detect_capabilities("", home=str(tmp_path))["found"] is False
