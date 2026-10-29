import json
import re

import pulse
from journal import Journal
from journal_context import active_themes
from pulse import Pulse, report, system_sample
from report import collector as report_collector


def _pulse(directory, *, boot="boot-a", now=None, **kwargs):
    clock = now or (lambda: 1_790_000_000.0)
    return Pulse(str(directory), sample=lambda: {"avail_mb": 900}, clock=clock, current_boot=lambda: boot, **kwargs)


def test_each_tick_leaves_a_synced_file_with_the_latest_samples(tmp_path):
    beat = _pulse(tmp_path, keep=2, context=lambda: {"themes": ["Hooandee Duo 0.1.7"]})
    for _ in range(3):
        beat.tick()
    saved = json.loads((tmp_path / "pulse.json").read_text())
    assert saved["stopped"] is False and saved["boot"] == "boot-a"
    assert len(saved["samples"]) == 2
    assert saved["samples"][-1]["ctx"] == {"themes": ["Hooandee Duo 0.1.7"]}


def test_a_clean_stop_is_not_reported_as_an_unclean_end(tmp_path):
    beat = _pulse(tmp_path)
    beat.tick()
    beat.stop()
    assert _pulse(tmp_path).set_aside_previous() is None
    assert report(str(tmp_path))["unclean"] == []


def test_a_forced_reboot_keeps_the_last_samples_and_what_panel_was_doing(tmp_path):
    times = iter([100.0, 110.0, 120.0])
    beat = _pulse(tmp_path, now=lambda: next(times), recent=lambda: [{"s": "rpc", "m": "load_theme_extension"}])
    beat.tick()
    beat.tick()

    end = _pulse(tmp_path, boot="boot-b").set_aside_previous()

    assert end["system_rebooted"] is True
    assert end["last_t"] == 120.0 and end["ran_s"] == 20.0
    kept = report(str(tmp_path))["unclean"]
    assert len(kept) == 1 and kept[0]["system_rebooted"] is True
    assert kept[0]["recent"] == [{"s": "rpc", "m": "load_theme_extension"}]
    assert not (tmp_path / "pulse.json").exists()


def test_panel_dying_inside_the_same_boot_is_not_a_system_reboot(tmp_path):
    _pulse(tmp_path).tick()
    assert _pulse(tmp_path).set_aside_previous()["system_rebooted"] is False


def test_only_the_newest_unclean_ends_are_kept(tmp_path):
    for second in range(6):
        _pulse(tmp_path, now=lambda second=second: float(second)).tick()
        _pulse(tmp_path, boot=f"next-{second}").set_aside_previous()
    assert [end["last_t"] for end in report(str(tmp_path))["unclean"]] == [2.0, 3.0, 4.0, 5.0]


def test_the_run_reports_the_previous_unclean_end_once(tmp_path):
    _pulse(tmp_path).tick()
    seen = []
    beat = _pulse(tmp_path, boot="boot-b", interval_s=60, on_unclean=seen.append)
    beat.start()
    beat.stop()
    assert len(seen) == 1 and seen[0]["system_rebooted"] is True


def test_system_sample_reads_memory_pressure_gpu_and_steam_memory(tmp_path):
    proc = tmp_path / "proc"
    (proc / "pressure").mkdir(parents=True)
    (proc / "meminfo").write_text("MemTotal: 16000000 kB\nMemAvailable: 2048000 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
    (proc / "pressure/memory").write_text("some avg10=12.50 avg60=3.00 avg300=1.00 total=1\nfull avg10=4.00 avg60=0 avg300=0 total=1\n")
    (proc / "loadavg").write_text("3.10 2.00 1.00 2/900 1234\n")
    (proc / "uptime").write_text("321.5 100.0\n")
    for pid, name in ((10, "steamwebhelper"), (11, "steamwebhelper"), (12, "bash")):
        (proc / str(pid)).mkdir()
        (proc / str(pid) / "comm").write_text(f"{name}\n")
        (proc / str(pid) / "statm").write_text("100000 25600 0 0 0 0 0\n")
    gpu = tmp_path / "sys/class/drm/card1/device"
    gpu.mkdir(parents=True)
    (gpu / "gpu_busy_percent").write_text("97\n")
    (gpu / "mem_info_vram_used").write_text(str(512 * 1048576))
    (gpu / "mem_info_vram_total").write_text(str(12 * 1024 * 1048576))

    sample = system_sample(str(tmp_path))

    assert sample["avail_mb"] == 2000 and sample["total_mb"] == 15625 and sample["psi_mem"] == 12.5
    assert sample["load1"] == 3.1 and sample["up"] == 321.5
    assert sample["gpu"] == {"busy": 97, "vram_mb": 512, "vram_total_mb": 12288, "gtt_mb": None}
    assert sample["proc"]["steamwebhelper"]["n"] == 2 and "bash" not in sample["proc"]


def test_journal_keeps_the_latest_records_before_they_reach_disk(tmp_path):
    diary = Journal(str(tmp_path))
    for index in range(10):
        diary.write("INFO", "rpc", "load_theme_extension", a=f"[\"duo\",{index}]")
    latest = diary.latest()
    assert len(latest) == 8 and latest[-1]["a"] == "[\"duo\",9]"


def test_active_themes_reads_the_theme_section():
    sections = {"themes": {"theme_report_diagnostics": {"installed": [
        {"name": "Hooandee Duo", "version": "0.1.7", "active": True},
        {"name": "Hooandee Gallery", "version": "0.9.50", "active": False},
    ]}}}
    assert active_themes(sections) == ["Hooandee Duo 0.1.7"]
    assert active_themes({"themes": {"truncated": "…"}}) is None


def test_kernel_tails_skip_split_lock_noise_and_cover_earlier_boots():
    cmds = report_collector._KERNEL_CMDS
    noise = re.compile(report_collector._KERNEL_NOISE_FREE)
    assert not noise.search("kernel: x86/split lock detection: #DB: CHTTPClientThre/3387 took a bus_lock trap")
    assert noise.search("kernel: amdgpu 0000:c4:00.0: amdgpu: ring gfx_0.0.0 timeout")
    for key, boot in (("previous_boot_kernel", "-1"), ("previous_boot_tail", "-1"), ("boot_minus_2_tail", "-2")):
        assert cmds[key][cmds[key].index("-b") + 1] == boot
        assert report_collector._KERNEL_NOISE_FREE in cmds[key]
    assert "--list-boots" in cmds["boots"]


def test_the_box_never_grows_past_its_cap_whatever_the_context_holds(tmp_path):
    beat = _pulse(tmp_path, keep=500, context=lambda: {"blob": "x" * 3000, "odd": object()})
    for _ in range(40):
        beat.tick()
    saved = (tmp_path / "pulse.json").read_text()
    assert len(saved) <= pulse._MAX_FILE_BYTES
    assert json.loads(saved)["samples"][-1]["ctx"]["blob"] == "x" * 3000
    assert beat.write_failures == 0


def test_the_default_window_is_the_last_two_minutes(tmp_path):
    beat = _pulse(tmp_path)
    for _ in range(20):
        beat.tick()
    assert len(json.loads((tmp_path / "pulse.json").read_text())["samples"]) == 12


def test_latest_records_are_short_even_for_long_messages(tmp_path):
    diary = Journal(str(tmp_path))
    diary.write("ERROR", "log", "boom " * 2000)
    assert len(diary.latest()[-1]["m"]) == 160
