import json
import os
import re
import time

import pulse
from journal import Journal
from journal_context import active_themes
from pulse import Pulse, report, system_sample
from pdc_report import collector as report_collector


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


def test_kernel_tails_skip_split_lock_noise():
    cmds = report_collector._KERNEL_CMDS
    noise = re.compile(report_collector._KERNEL_NOISE_FREE)
    assert not noise.search("kernel: x86/split lock detection: #DB: CHTTPClientThre/3387 took a bus_lock trap")
    assert noise.search("kernel: amdgpu 0000:c4:00.0: amdgpu: ring gfx_0.0.0 timeout")
    for key in ("previous_boot_kernel", "previous_boot_tail"):
        assert cmds[key][cmds[key].index("-b") + 1] == "-1"
        assert report_collector._KERNEL_NOISE_FREE in cmds[key]


def test_kernel_tails_run_unfiltered_where_journalctl_lacks_pattern_matching():
    calls = []

    def run(cmd):
        calls.append(cmd)
        if "--grep" in cmd and report_collector._KERNEL_NOISE_FREE in cmd:
            return "[exit 1] Compiled without pattern matching support"
        if cmd[:3] == ["/usr/bin/journalctl", "-b", "-1"] and "-k" in cmd:
            return "kernel: amdgpu: ring gfx timeout"
        return None

    out = report_collector.kernel_logs(run)
    assert out["previous_boot_kernel"] == "kernel: amdgpu: ring gfx timeout"
    retried = [cmd for cmd in calls if cmd[:3] == ["/usr/bin/journalctl", "-b", "-1"] and "-k" in cmd and "-p" in cmd]
    assert retried[-1] == ["/usr/bin/journalctl", "-b", "-1", "-k", "-p", "warning", "-n", "150", "--no-pager"]


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



def test_a_late_tick_cannot_undo_the_clean_stop(tmp_path):
    beat = _pulse(tmp_path)
    beat.tick()
    beat.stop()
    beat.tick()
    assert json.loads((tmp_path / "pulse.json").read_text())["stopped"] is True


def test_stop_gives_up_instead_of_waiting_on_a_busy_disk(tmp_path):
    beat = _pulse(tmp_path)
    beat._write_lock.acquire()
    started = time.monotonic()
    beat.stop()
    assert time.monotonic() - started < 2 * pulse._STOP_WAIT_S + 0.5
    assert beat.write_failures == 1
    beat._write_lock.release()


def test_a_second_live_instance_is_not_an_unclean_end(tmp_path):
    (tmp_path / "pulse.json").write_text(json.dumps(
        {"boot": "boot-a", "pid": os.getppid(), "started": 1.0, "stopped": False, "samples": [{"t": 2.0}]}))
    assert _pulse(tmp_path).set_aside_previous() is None
    assert (tmp_path / "pulse.json").exists()


def test_an_odd_previous_file_does_not_kill_the_black_box(tmp_path):
    (tmp_path / "pulse.json").write_text(json.dumps({"boot": "boot-z", "started": "x", "samples": ["x"]}))
    beat = _pulse(tmp_path, interval_s=60)
    beat.start()
    beat.stop()
    assert json.loads((tmp_path / "pulse.json").read_text())["stopped"] is True


def test_the_bundle_redacts_the_black_box(tmp_path):
    bundle = report_collector.build_bundle(
        app="pdc", categories=[], text="", environment={}, capabilities={}, state={}, stores={}, logs=[],
        journal={"pulse": {"current": {"recent": [{"a": "/home/deck/Games/x.zip"}]}}}, home="/home/deck")
    assert "/home/deck" not in json.dumps(bundle)


def test_system_sample_reads_whether_each_connected_screen_is_on(tmp_path):
    drm = tmp_path / "sys/class/drm"
    for name, status, dpms in (("card1-eDP-1", "connected", "Off"), ("card1-DP-1", "disconnected", "Off"),
                               ("card1-HDMI-A-1", "connected", "On")):
        (drm / name).mkdir(parents=True)
        (drm / name / "status").write_text(f"{status}\n")
        (drm / name / "dpms").write_text(f"{dpms}\n")
    assert system_sample(str(tmp_path))["screen"] == {"HDMI-A-1": "On", "eDP-1": "Off"}
    assert system_sample(str(tmp_path / "none"))["screen"] is None


def test_the_box_keeps_the_last_lifecycle_transitions_through_an_unclean_end(tmp_path):
    events = [{"t": float(index), "event": name, "suspend_seconds": 9}
              for index, name in enumerate(("baseline", "ac_changed", "ac_stable", "x" * 200, "resume_detected"))]
    beat = _pulse(tmp_path, lifecycle=lambda: events)
    beat.tick()
    saved = json.loads((tmp_path / "pulse.json").read_text())
    assert [entry["event"] for entry in saved["lifecycle"]] == ["ac_changed", "ac_stable", "x" * 40, "resume_detected"]
    assert saved["lifecycle"][-1] == {"t": 4.0, "event": "resume_detected"}

    end = _pulse(tmp_path, boot="boot-b").set_aside_previous()
    assert end["lifecycle"][-1]["event"] == "resume_detected"
    assert report(str(tmp_path))["unclean"][0]["lifecycle"][-1]["event"] == "resume_detected"


def test_a_broken_lifecycle_source_never_stops_the_box(tmp_path):
    def broken():
        raise RuntimeError("boom")

    beat = _pulse(tmp_path, lifecycle=broken)
    beat.tick()
    saved = json.loads((tmp_path / "pulse.json").read_text())
    assert "lifecycle" not in saved and beat.write_failures == 0


def _cpu_process(root, pid, ticks, born=100, name='MainThread', appid='292030'):
    directory = root / 'proc' / str(pid)
    directory.mkdir(parents=True, exist_ok=True)
    fields = ['0'] * 22
    fields[0], fields[11], fields[19] = 'R', str(ticks), str(born)
    (directory / 'stat').write_text(f'{pid} ({name}) ' + ' '.join(fields))
    (directory / 'comm').write_text(name)
    (directory / 'environ').write_bytes(f'SECRET=never-export\0SteamAppId={appid}\0'.encode())


def test_process_cpu_uses_interval_and_identifies_game_without_exporting_environment(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    _cpu_process(tmp_path, 42, 100)
    assert sampler.sample()['top_cpu'] == []
    sampler.clock = lambda: 12.0
    _cpu_process(tmp_path, 42, 500)
    result = sampler.sample()
    assert result['interval_s'] == 2.0
    assert result['top_cpu'] == [{'pid': 42, 'name': 'MainThread', 'cpu_pct': 200.0, 'steam_appid': '292030'}]
    assert 'SECRET' not in json.dumps(result)


def test_process_cpu_never_attributes_reused_pid_or_negative_delta(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    _cpu_process(tmp_path, 42, 500)
    sampler.sample()
    sampler.clock = lambda: 12.0
    _cpu_process(tmp_path, 42, 900, born=200)
    assert sampler.sample()['top_cpu'] == []
    sampler.clock = lambda: 14.0
    _cpu_process(tmp_path, 42, 100, born=200)
    assert sampler.sample()['top_cpu'] == []


def test_performance_readbacks_are_real_and_missing_is_unknown(tmp_path):
    assert pulse.performance_sample(str(tmp_path)) == {'boost': None, 'cpu_khz': None, 'power_caps_uw': []}
    cpu = tmp_path / 'sys/devices/system/cpu/cpufreq'
    (cpu / 'policy0').mkdir(parents=True)
    (cpu / 'boost').write_text('0')
    (cpu / 'policy0/scaling_cur_freq').write_text('1700000')
    chip = tmp_path / 'sys/class/hwmon/hwmon0'
    chip.mkdir(parents=True)
    (chip / 'name').write_text('amdgpu')
    (chip / 'power1_cap').write_text('3000000')
    result = pulse.performance_sample(str(tmp_path))
    assert result['boost'] == 0
    assert result['cpu_khz'] == {'min': 1700000, 'max': 1700000}
    assert result['power_caps_uw'] == [{'chip': 'amdgpu', 'rail': 'power1_cap', 'uw': 3000000}]


def test_top_cpu_is_bounded_and_unknown_names_and_partial_appids_are_not_exported(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    for pid in range(10):
        _cpu_process(tmp_path, pid, 100, name='private document ) title')
    sampler.sample()
    sampler.clock = lambda: 12.0
    for pid in range(10):
        _cpu_process(tmp_path, pid, 500 + pid, name='private document ) title')
        (tmp_path / 'proc' / str(pid) / 'environ').write_bytes(b'SteamAppId=123')
    result = sampler.sample()
    assert len(result['top_cpu']) == 5
    assert all(row['name'] == 'other' and row['steam_appid'] is None for row in result['top_cpu'])
    assert 'private' not in json.dumps(result)
    assert result['cpu_basis'] == 'one_logical_cpu'


def test_process_disappearing_does_not_break_the_sampler(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    _cpu_process(tmp_path, 42, 100)
    sampler.sample()
    (tmp_path / 'proc/42/stat').unlink()
    sampler.clock = lambda: 12.0
    assert sampler.sample()['observed'] == 0


def test_default_pulse_includes_process_cpu_and_performance(tmp_path):
    beat = Pulse(str(tmp_path))
    beat.tick()
    saved = json.loads((tmp_path / 'pulse.json').read_text())['samples'][-1]
    assert saved['process_cpu']['interval_s'] is None
    assert 'boost' in saved['performance']


def test_twelve_typical_samples_with_diagnostics_fit_existing_budget(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    for pid in range(5):
        _cpu_process(tmp_path, pid, 100)
    sampler.sample()
    sampler.clock = lambda: 20.0
    for pid in range(5):
        _cpu_process(tmp_path, pid, 500)
    sample = {**system_sample(str(tmp_path)), 'process_cpu': sampler.sample(),
              'ctx': {'game': '292030', 'themes': ['Hooandee Gallery 0.9.57'], 'eco_enabled': True,
                      'support_sample_age_s': 2, 'tdp_w': 3, 'w': 3, 'cpu_c': 50, 'gpu_c': 47, 'rpm': 2172, 'ac': True},
              'proc': {name: {'n': 3, 'rss_mb': 1500} for name in pulse._WATCHED_PROCESSES}}
    encoded = pulse._encode({'samples': [sample] * 12, 'recent': [{'m': 'x' * 160}] * 8})
    assert len(json.loads(encoded)['samples']) == 12


def test_known_process_cpu_is_kept_even_outside_top_five(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    for pid in range(6):
        _cpu_process(tmp_path, pid, 100, name='steam' if pid == 0 else 'MainThread')
    sampler.sample()
    sampler.clock = lambda: 12.0
    for pid in range(6):
        _cpu_process(tmp_path, pid, 110 if pid == 0 else 500, name='steam' if pid == 0 else 'MainThread')
    result = sampler.sample()
    assert all(row['name'] != 'steam' for row in result['top_cpu'])
    assert result['known_cpu_pct']['steam'] == 5.0
    assert result['known_cpu_pct']['PluginLoader'] is None


def test_known_cpu_is_unknown_if_a_group_member_has_no_valid_delta(tmp_path):
    sampler = pulse.ProcessSampler(str(tmp_path), clock=lambda: 10.0, ticks_per_second=100)
    _cpu_process(tmp_path, 10, 100, name='steamwebhelper')
    sampler.sample()
    _cpu_process(tmp_path, 11, 500, name='steamwebhelper')
    sampler.clock = lambda: 12.0
    assert sampler.sample()['known_cpu_pct']['steamwebhelper'] is None
    sampler.clock = lambda: 14.0
    assert sampler.sample()['known_cpu_pct']['steamwebhelper'] == 0.0
    _cpu_process(tmp_path, 11, 100, born=200, name='steamwebhelper')
    sampler.clock = lambda: 16.0
    assert sampler.sample()['known_cpu_pct']['steamwebhelper'] is None
