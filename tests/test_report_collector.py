import os

from report.collector import (
    SCHEMA,
    build_bundle,
    capabilities_from,
    kernel_logs,
    redact_obj,
    redact_text,
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


def test_build_bundle_includes_kernel():
    b = build_bundle(
        app="a", categories=[], text="", environment={}, capabilities={},
        state={}, stores={}, logs=[], kernel={"dmesg": "x", "journal": None},
    )
    assert b["kernel"] == {"dmesg": "x", "journal": None}


def test_capabilities_from_distils_backends():
    caps = capabilities_from({
        "tdp": {"backend": "asus-armoury", "supported": True},
        "fan_curve": {"source": "asus_custom_fan_curve", "supported": True, "mode_based": False},
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
