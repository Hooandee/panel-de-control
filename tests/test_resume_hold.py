"""For _RESUME_HOLD_S after a resume every core stays online and the GPU stays as the
kernel restored it; each step is marked in the pulse and both apply once afterwards."""
import asyncio
import dataclasses


from tests.test_gpu_clock_rpc import _FakeGpuClock, _make_plugin


class _RecordingGpuClock(_FakeGpuClock):
    def __init__(self):
        super().__init__()
        self.writes = []

    def set(self, lo, hi):
        self.writes.append((int(lo), int(hi)))
        return super().set(lo, hi)


class _Beat:
    def __init__(self):
        self.marks = []
        self.bursts = []

    def mark(self, step, *, sync=True, **detail):
        self.marks.append(step)

    def burst(self, seconds, interval_s=2.0):
        self.bursts.append(seconds)


def _plugin(tmp_path, monkeypatch, device_key="legion_go"):
    gpu = _RecordingGpuClock()
    plugin, _ = _make_plugin(tmp_path, monkeypatch, gpu)
    asyncio.run(plugin.set_gpu_clock(800, 1200))
    gpu.writes.clear()
    plugin._device = dataclasses.replace(plugin._device, key=device_key)
    plugin._pulse = _Beat()
    intents = []
    monkeypatch.setattr(plugin, "_cpu_intent", lambda: {
        "smt": True, "boost": True, "cores": 3,
        "frequency": {"manual": False, "min_khz": None, "max_khz": None},
    })

    def run_cpu_apply(intent, generation, enabled=None, preserve_frequency_ownership=False):
        intents.append(intent["cores"])

    monkeypatch.setattr(plugin, "_run_cpu_apply", run_cpu_apply)
    monkeypatch.setattr(plugin, "_record_cpu_result", lambda *a, **k: None)
    return plugin, gpu, intents


def _resume(plugin):
    plugin._log_lifecycle_event({"event": "resume_detected", "suspend_seconds": 6861.0})


def test_cores_and_manual_gpu_wait_after_resume_then_apply_once(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)

    async def scenario():
        _resume(plugin)
        assert plugin._resume_hold_active()

        plugin._reapply_all()
        plugin._apply_cpu()  # AC change inside the same window
        await plugin._offload_call(lambda: None)
        assert intents == [None, None]
        assert gpu.writes == []
        assert "hold:cores" in plugin._pulse.marks and "hold:gpu" in plugin._pulse.marks

        plugin._release_resume_hold(plugin._resume_token)
        await plugin._offload_call(lambda: None)
        assert not plugin._resume_hold_active()
        assert intents[-1] == 3
        assert gpu.writes == [(800, 1200)]
        marks = plugin._pulse.marks
        assert marks.index("release:cores") < marks.index("release:gpu") < marks.index("release:done")
        assert [h["action"] for h in plugin._resume_hold_history] == ["held", "held", "released"]
        diagnostics = plugin._cpu_gpu_diagnostics()["resume_hold"]
        assert diagnostics["active"] is False and diagnostics["history"][-1]["held"] == ["cores", "gpu"]

    asyncio.run(scenario())


def test_a_newer_resume_restarts_the_hold(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)

    async def scenario():
        _resume(plugin)
        old = plugin._resume_token
        _resume(plugin)
        plugin._release_resume_hold(old)
        assert plugin._resume_hold_active()
        plugin._apply_cpu()
        await plugin._offload_call(lambda: None)
        assert intents == [None]

    asyncio.run(scenario())


def test_release_without_held_writes_applies_nothing(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)

    async def scenario():
        _resume(plugin)
        plugin._release_resume_hold(plugin._resume_token)
        assert intents == [] and gpu.writes == []

    asyncio.run(scenario())


def test_without_a_resume_cores_and_gpu_apply_at_once(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)
    plugin._apply_cpu()
    plugin._apply_gpu_clock()
    assert intents == [3]
    assert gpu.writes == [(800, 1200)]
    assert plugin._pulse.marks == []


def test_user_core_change_during_the_hold_is_not_blocked(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)

    async def scenario():
        _resume(plugin)
        await plugin._apply_cpu_awaited(trigger="set_cores")
        assert intents == [3]

    asyncio.run(scenario())


def test_resume_reapply_marks_each_hardware_step_in_order(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch, device_key="rog_ally")
    _resume(plugin)
    assert plugin._pulse.bursts == [60.0]

    plugin._reapply_all()

    steps = [m for m in plugin._pulse.marks if m.startswith("reapply:")]
    assert steps == [
        "reapply:cpu", "reapply:gpu", "reapply:tdp", "reapply:fans",
        "reapply:hdr", "reapply:color", "reapply:audio", "reapply:done",
    ]


def test_no_marks_outside_a_resume(tmp_path, monkeypatch):
    plugin, gpu, intents = _plugin(tmp_path, monkeypatch)
    plugin._reapply_all()
    assert plugin._pulse.marks == []
