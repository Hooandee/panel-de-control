import os

from report.collector import (
    SCHEMA,
    build_bundle,
    capabilities_from,
    controller_daemon_cmds,
    kernel_logs,
    redact_obj,
    redact_text,
    sysfs_snapshot,
    tail_logs,
)


def test_kernel_logs_redacts_and_caps():
    def run(cmd):
        return "error /home/deck/x failed" if "dmesg" in cmd[0] else None
    out = kernel_logs(run, cap=1000)
    assert "~/x" in out["dmesg"] and "/home/deck" not in out["dmesg"]
    assert out["journal"] is None  # runner returned None → honest null


def test_kernel_logs_runner_raising_is_null():
    def run(cmd):
        raise OSError("boom")
    out = kernel_logs(run)
    assert out["dmesg"] is None and out["journal"] is None


def test_controller_daemon_cmds_hhd():
    cmd = controller_daemon_cmds("hhd")["controller"]
    assert "journalctl" in cmd[0] and "hhd.service" in cmd


def test_controller_daemon_cmds_inputplumber():
    cmd = controller_daemon_cmds("inputplumber")["controller"]
    assert "inputplumber.service" in cmd


def test_controller_daemon_cmds_none_is_empty():
    assert controller_daemon_cmds("none") == {}
    assert controller_daemon_cmds(None) == {}


def test_kernel_logs_captures_extra_controller_journal():
    def run(cmd):
        return "HHD woke up /home/deck/x" if "hhd.service" in cmd else None
    out = kernel_logs(run, extra=controller_daemon_cmds("hhd"))
    assert "~/x" in out["controller"] and "/home/deck" not in out["controller"]


def test_build_bundle_includes_kernel():
    b = build_bundle(
        app="a", categories=[], text="", environment={}, capabilities={},
        state={}, stores={}, logs=[], kernel={"dmesg": "x", "journal": None},
    )
    assert b["kernel"] == {"dmesg": "x", "journal": None}


def test_capabilities_from_distils_backends():
    caps = capabilities_from({
        "tdp": {"backend": "asus-armoury", "supported": True},
        "fan_curve": {"source": "asus_custom_fan_curve", "supported": True},
        "battery": {"charge_limit": {"supported": True, "adjustable": False}},
        "gpu": {"supported": False},
        "color": {"supported": True},
        "controller": {"manager": "inputplumber", "kind": "remap"},
    })
    assert caps["tdp_backend"] == "asus-armoury"
    assert caps["fan_source"] == "asus_custom_fan_curve"
    assert caps["charge_limit_supported"] is True
    assert caps["charge_limit_adjustable"] is False
    assert caps["gpu_clock_supported"] is False
    assert caps["controller_manager"] == "inputplumber"


def test_capabilities_from_tolerates_missing():
    caps = capabilities_from({})
    assert caps["tdp_backend"] is None
    assert caps["tdp_supported"] is False


# ---- redact_text ----------------------------------------------------------
def test_redact_text_home_paths():
    assert redact_text("/home/deck/homebrew/x.log") == "~/homebrew/x.log"
    assert redact_text("error at /home/juandi/foo") == "error at ~/foo"


def test_redact_text_custom_home_prefix():
    # A home not under /home (unusual) is still scrubbed when passed explicitly.
    assert redact_text("/var/lib/me/f", home="/var/lib/me") == "~/f"


def test_redact_text_hostname_word_boundary():
    assert redact_text("host steamdeck up", hostname="steamdeck") == "host HOST up"
    # Short/empty hostname is ignored (too risky to blanket-replace).
    assert redact_text("a b c", hostname="") == "a b c"


def test_redact_text_keeps_device_names():
    # The username 'deck' must NOT nuke 'Steam Deck' - we only scrub PATHS.
    assert redact_text("Steam Deck OLED") == "Steam Deck OLED"


def test_redact_text_scrubs_labeled_serials():
    # DMI/dmesg serial lines: keep the label for context, drop the value.
    out = redact_text("board_serial: ABCD1234EFGH")
    assert "ABCD1234EFGH" not in out and "[serial]" in out and "board_serial" in out
    out = redact_text("product_serial=XYZ98765QP")
    assert "XYZ98765QP" not in out and "[serial]" in out
    out = redact_text("System Info: Serial Number: 9F8E7D6C5B")
    assert "9F8E7D6C5B" not in out and "[serial]" in out


def test_redact_text_scrubs_standalone_serial_run():
    # A long mixed alphanumeric token anywhere is scrubbed...
    assert "XJ8KD93MABZ" not in redact_text("unit XJ8KD93MABZ online")


def test_redact_text_serial_run_leaves_words_and_numbers():
    # ...but pure words and pure numbers (timestamps) are left intact.
    assert redact_text("steamdeck up at 1700000000") == "steamdeck up at 1700000000"


def test_redact_text_passes_non_strings():
    assert redact_text(42) == 42
    assert redact_text(None) is None


# ---- redact_obj -----------------------------------------------------------
def test_redact_obj_scrubs_serial_like_keys():
    out = redact_obj({"product_serial": "ABC123", "board_uuid": "x", "model": "Ally"})
    assert out["product_serial"] == "[redacted]"
    assert out["board_uuid"] == "[redacted]"
    assert out["model"] == "Ally"


def test_redact_obj_recurses_and_redacts_paths():
    out = redact_obj({"logs": [{"p": "/home/deck/a"}], "n": 1})
    assert out["logs"][0]["p"] == "~/a"
    assert out["n"] == 1


# ---- tail_logs ------------------------------------------------------------
def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


def test_tail_logs_missing_dir_is_empty():
    assert tail_logs("/no/such/dir") == []


def test_tail_logs_newest_first_and_redacts(tmp_path):
    d = str(tmp_path)
    _write(os.path.join(d, "old.log"), "old /home/deck/x\n")
    _write(os.path.join(d, "new.log"), "new line\n")
    # Make new.log newer.
    os.utime(os.path.join(d, "new.log"), (2_000_000_000, 2_000_000_000))
    os.utime(os.path.join(d, "old.log"), (1_000_000_000, 1_000_000_000))
    logs = tail_logs(d, max_files=2)
    assert [x["name"] for x in logs] == ["new.log", "old.log"]
    assert "~/x" in logs[1]["text"] and "/home/deck" not in logs[1]["text"]


def test_tail_logs_caps_bytes_and_drops_partial_first_line(tmp_path):
    d = str(tmp_path)
    _write(os.path.join(d, "a.log"), "AAAA\nBBBB\nCCCC\n")
    logs = tail_logs(d, max_bytes=6)  # only the tail fits
    assert logs[0]["text"].endswith("CCCC\n")
    assert "AAAA" not in logs[0]["text"]  # partial leading line dropped


# ---- build_bundle ---------------------------------------------------------
def test_build_bundle_shape_and_redaction():
    b = build_bundle(
        app="panel-de-control",
        categories=["tdp", "fans"],
        text="falla /home/deck/thing",
        environment={"product_name": "Ally", "product_serial": "S3CR3T"},
        capabilities={"tdp": "asus-armoury"},
        state={"tdp": {"watts": 15}},
        stores={"profiles": {}},
        logs=[{"name": "x.log", "text": "boom"}],
    )
    assert b["schema"] == SCHEMA
    assert b["app"] == "panel-de-control"
    assert b["categories"] == ["tdp", "fans"]
    assert b["text"] == "falla ~/thing"  # path redacted in free text too
    assert b["environment"]["product_serial"] == "[redacted]"
    assert b["capabilities"]["tdp"] == "asus-armoury"


def test_build_bundle_truncates_long_text():
    b = build_bundle(
        app="a", categories=[], text="x" * 9000,
        environment={}, capabilities={}, state={}, stores={}, logs=[],
    )
    assert len(b["text"]) <= 4000


def test_build_bundle_tolerates_none_categories():
    b = build_bundle(
        app="a", categories=None, text=None,
        environment={}, capabilities={}, state={}, stores={}, logs=[],
    )
    assert b["categories"] == []
    assert b["text"] == ""


def test_build_bundle_includes_sysfs():
    b = build_bundle(
        app="a", categories=[], text="", environment={}, capabilities={},
        state={}, stores={}, logs=[], sysfs={"hwmon": [{"name": "asus"}]},
    )
    assert b["sysfs"] == {"hwmon": [{"name": "asus"}]}


def test_build_bundle_defaults_sysfs_empty():
    b = build_bundle(
        app="a", categories=[], text="", environment={}, capabilities={},
        state={}, stores={}, logs=[],
    )
    assert b["sysfs"] == {}


# ---- sysfs_snapshot -------------------------------------------------------
def _mk(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _build_fake_sysfs(root):
    # hwmon0 = a vendor fan chip with pwm + fan + temp label nodes.
    _mk(os.path.join(root, "sys/class/hwmon/hwmon0/name"), "asus\n")
    _mk(os.path.join(root, "sys/class/hwmon/hwmon0/pwm1"), "128\n")
    _mk(os.path.join(root, "sys/class/hwmon/hwmon0/pwm1_enable"), "2\n")
    _mk(os.path.join(root, "sys/class/hwmon/hwmon0/fan1_input"), "3200\n")
    _mk(os.path.join(root, "sys/class/hwmon/hwmon0/temp1_label"), "Tctl\n")
    # hwmon1 = a temp-only chip.
    _mk(os.path.join(root, "sys/class/hwmon/hwmon1/name"), "k10temp\n")
    _mk(os.path.join(root, "sys/class/hwmon/hwmon1/temp1_label"), "Tctl\n")
    # firmware-attributes: vendor WMI TDP attributes.
    _mk(os.path.join(root, "sys/class/firmware-attributes/asus-armoury/attributes/ppt_pl1_spl/current_value"), "17\n")
    _mk(os.path.join(root, "sys/class/firmware-attributes/asus-armoury/attributes/ppt_pl2_sppt/current_value"), "25\n")
    # power_supply: a battery with a charge threshold + a charger without one.
    _mk(os.path.join(root, "sys/class/power_supply/BAT0/energy_full"), "1\n")
    _mk(os.path.join(root, "sys/class/power_supply/BAT0/cycle_count"), "38\n")
    _mk(os.path.join(root, "sys/class/power_supply/BAT0/charge_control_end_threshold"), "80\n")
    _mk(os.path.join(root, "sys/class/power_supply/ADP0/online"), "1\n")
    # platform_profile: the ACPI single-file interface + a vendor class profile
    # (Legion's lenovo-wmi-gamezone with its firmware modes).
    _mk(os.path.join(root, "sys/firmware/acpi/platform_profile"), "balanced\n")
    _mk(os.path.join(root, "sys/firmware/acpi/platform_profile_choices"), "quiet balanced performance custom\n")
    _mk(os.path.join(root, "sys/class/platform-profile/platform-profile-0/name"), "lenovo-wmi-gamezone\n")
    _mk(os.path.join(root, "sys/class/platform-profile/platform-profile-0/profile"), "balanced\n")
    _mk(os.path.join(root, "sys/class/platform-profile/platform-profile-0/choices"), "quiet balanced performance custom\n")


def test_sysfs_snapshot_hwmon(tmp_path):
    _build_fake_sysfs(str(tmp_path))
    snap = sysfs_snapshot(root=str(tmp_path))
    chips = {c["name"]: c["nodes"] for c in snap["hwmon"]}
    assert set(chips["asus"]) == {"pwm1", "pwm1_enable", "fan1_input", "temp1_label"}
    assert chips["k10temp"] == ["temp1_label"]


def test_sysfs_snapshot_firmware_attributes(tmp_path):
    _build_fake_sysfs(str(tmp_path))
    snap = sysfs_snapshot(root=str(tmp_path))
    assert snap["firmware_attributes"]["asus-armoury"] == ["ppt_pl1_spl", "ppt_pl2_sppt"]


def test_sysfs_snapshot_power_supply(tmp_path):
    _build_fake_sysfs(str(tmp_path))
    snap = sysfs_snapshot(root=str(tmp_path))
    assert "charge_control_end_threshold" in snap["power_supply"]["BAT0"]
    assert "cycle_count" in snap["power_supply"]["BAT0"]
    assert "charge_control_end_threshold" not in snap["power_supply"]["ADP0"]


def test_sysfs_snapshot_platform_profile(tmp_path):
    _build_fake_sysfs(str(tmp_path))
    snap = sysfs_snapshot(root=str(tmp_path))
    pp = snap["platform_profile"]
    assert pp["acpi"]["current"] == "balanced"
    assert pp["acpi"]["choices"] == "quiet balanced performance custom"
    cls = pp["class"]["platform-profile-0"]
    assert cls["name"] == "lenovo-wmi-gamezone"
    assert cls["profile"] == "balanced"
    assert cls["choices"] == "quiet balanced performance custom"


def test_sysfs_snapshot_platform_profile_absent(tmp_path):
    snap = sysfs_snapshot(root=str(tmp_path))
    assert snap["platform_profile"] == {"acpi": {}, "class": {}}


def test_sysfs_snapshot_acpi_present_and_writable(tmp_path):
    _mk(os.path.join(str(tmp_path), "proc/acpi/call"), "")
    snap = sysfs_snapshot(root=str(tmp_path))
    assert snap["acpi"]["call_present"] is True
    assert snap["acpi"]["call_writable"] is True


def test_sysfs_snapshot_acpi_absent(tmp_path):
    snap = sysfs_snapshot(root=str(tmp_path))
    assert snap["acpi"]["call_present"] is False
    assert snap["acpi"]["call_writable"] is False


def test_sysfs_snapshot_modules_lists_acpi_call(tmp_path):
    _mk(
        os.path.join(str(tmp_path), "proc/modules"),
        "amdgpu 12288 3 - Live 0x0000000000000000\n"
        "acpi_call 16384 0 - Live 0x0000000000000000\n",
    )
    snap = sysfs_snapshot(root=str(tmp_path))
    assert "acpi_call" in snap["modules"] and "amdgpu" in snap["modules"]


def test_sysfs_snapshot_modules_without_acpi_call(tmp_path):
    _mk(os.path.join(str(tmp_path), "proc/modules"), "amdgpu 12288 3 - Live 0x0\n")
    snap = sysfs_snapshot(root=str(tmp_path))
    assert "acpi_call" not in snap["modules"]


def test_sysfs_snapshot_empty_root_never_raises(tmp_path):
    snap = sysfs_snapshot(root=str(tmp_path))
    assert snap == {
        "hwmon": [],
        "firmware_attributes": {},
        "power_supply": {},
        "platform_profile": {"acpi": {}, "class": {}},
        "acpi": {"call_present": False, "call_writable": False},
        "modules": [],
    }


def test_sysfs_snapshot_missing_root_never_raises():
    # A non-existent root must still return the full shape, never throw.
    snap = sysfs_snapshot(root="/no/such/root/xyz")
    assert snap["hwmon"] == [] and snap["modules"] == []


def test_sysfs_snapshot_redacts_serial_in_node_value(tmp_path):
    # A serial leaking through a small node value is scrubbed.
    _mk(os.path.join(str(tmp_path), "sys/class/hwmon/hwmon0/name"), "chipXJ8KD93MABZ\n")
    snap = sysfs_snapshot(root=str(tmp_path), home="/home/deck")
    assert "XJ8KD93MABZ" not in snap["hwmon"][0]["name"]


def test_sysfs_snapshot_is_size_capped(tmp_path):
    # A pathological chip count still yields a bounded, flagged snapshot.
    root = str(tmp_path)
    for i in range(200):
        _mk(os.path.join(root, f"sys/class/hwmon/hwmon{i}/name"), f"chip{i}\n")
    snap = sysfs_snapshot(root=root)
    assert len(snap["hwmon"]) <= 32  # chip cap, no recursive/unbounded sweep
