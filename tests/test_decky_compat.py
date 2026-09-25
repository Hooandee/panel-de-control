import asyncio

import decky_compat
import pytest


SHARED_TARGET = {
    "id": "shared-1",
    "title": "SharedJSContext",
    "url": "https://steamloopback.host/routes/library/home",
    "webSocketDebuggerUrl": "ws://127.0.0.1:8080/devtools/page/shared-1",
}


def _state(**overrides):
    values = {
        "decky_has_loaded": True,
        "decky_backend": False,
        "decky_backend_absent": True,
        "decky_plugin_loader": False,
        "decky_plugin_loader_absent": True,
        "decky_auth_token": False,
        "decky_auth_token_absent": True,
        "dfl": False,
        "dfl_absent": True,
        "sp_react": False,
        "sp_react_absent": True,
        "app": True,
        "stage_one": False,
        "stage_one_absent": True,
        "before_login": True,
        "before_login_ready": True,
    }
    values.update(overrides)
    return decky_compat.FrontendState(**values)


class _FakeTransport:
    def __init__(self, *, targets=None, states=None, recovery=None):
        self._targets = list(targets or [SHARED_TARGET])
        self._states = list(states or [])
        self._recovery = recovery or {
            "status": "recovered",
            "decky_backend": True,
            "decky_plugin_loader": True,
        }
        self.list_calls = 0
        self.probe_calls = 0
        self.recovery_calls = 0
        self.recovery_scripts = []

    async def list_targets(self):
        self.list_calls += 1
        return self._targets

    async def probe(self, target):
        self.probe_calls += 1
        if self._states:
            return self._states.pop(0)
        return _state(decky_has_loaded=False)

    async def recover(self, target, script):
        self.recovery_calls += 1
        self.recovery_scripts.append(script)
        return self._recovery


async def _no_sleep(_seconds):
    return None


def test_other_decky_versions_never_construct_the_cdp_transport():
    def forbidden_transport():
        raise AssertionError("CDP must remain untouched outside Decky v3.2.6")

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.8",
            transport_factory=forbidden_transport,
        )
    )

    assert result.status == "skipped_version"
    assert result.attempted is False


def test_version_gate_is_literal():
    assert decky_compat.is_affected_version("v3.2.6") is True
    for version in ("3.2.6", "v3.2.6-pre1", "v3.2.7", "v3.2.8", ""):
        assert decky_compat.is_affected_version(version) is False


def test_broken_326_state_must_be_observed_twice_before_recovery():
    transport = _FakeTransport(states=[_state(), _state()])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "recovered"
    assert result.attempted is True
    assert transport.probe_calls == 2
    assert transport.recovery_calls == 1


def test_healthy_326_frontend_is_never_modified():
    healthy = _state(
        decky_backend=True,
        decky_backend_absent=False,
        decky_plugin_loader=True,
        decky_plugin_loader_absent=False,
    )
    transport = _FakeTransport(states=[healthy])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "already_loaded"
    assert result.attempted is False
    assert transport.recovery_calls == 0


def test_326_with_the_legacy_api_is_never_modified():
    compatible = _state(stage_one=True, stage_one_absent=False)
    transport = _FakeTransport(states=[compatible])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "legacy_api_available"
    assert result.attempted is False
    assert transport.recovery_calls == 0


def test_partial_frontend_state_fails_closed():
    partial = _state(decky_auth_token=True, decky_auth_token_absent=False)
    transport = _FakeTransport(states=[partial])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "ambiguous_state"
    assert result.attempted is False
    assert transport.recovery_calls == 0


@pytest.mark.parametrize(
    "partial_state",
    (
        _state(decky_backend_absent=False),
        _state(decky_plugin_loader_absent=False),
        _state(stage_one_absent=False),
    ),
)
def test_defined_but_unhealthy_values_fail_closed_before_exact_state(partial_state):
    transport = _FakeTransport(states=[partial_state, _state()])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "ambiguous_state"
    assert result.attempted is False
    assert transport.probe_calls == 1
    assert transport.recovery_calls == 0


def test_missing_required_signals_never_trigger_recovery():
    cases = (
        _state(decky_has_loaded=False),
        _state(app=False),
        _state(before_login_ready=False),
    )

    for state in cases:
        transport = _FakeTransport(states=[state, state])
        result = asyncio.run(
            decky_compat.recover_frontend(
                "v3.2.6",
                transport_factory=lambda: transport,
                probe_attempts=2,
                probe_interval_s=0,
                sleep=_no_sleep,
            )
        )
        assert result.status == "observation_timeout"
        assert result.attempted is False
        assert transport.recovery_calls == 0


def test_missing_upstream_replacement_api_fails_closed():
    unsupported = _state(before_login=False, before_login_ready=False)
    transport = _FakeTransport(states=[unsupported])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "unsupported_api"
    assert result.attempted is False
    assert transport.recovery_calls == 0


def test_multiple_shared_targets_fail_closed():
    duplicate = dict(SHARED_TARGET, id="shared-2")
    transport = _FakeTransport(targets=[SHARED_TARGET, duplicate])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "ambiguous_target"
    assert result.attempted is False
    assert transport.probe_calls == 0


def test_non_local_shared_target_is_rejected():
    remote = dict(
        SHARED_TARGET,
        webSocketDebuggerUrl="ws://192.0.2.1:8080/devtools/page/shared-1",
    )
    transport = _FakeTransport(targets=[remote])

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "ambiguous_target"
    assert result.attempted is False


def test_failed_postcondition_is_reported_without_retry():
    transport = _FakeTransport(
        states=[_state(), _state()],
        recovery={
            "status": "postcondition_failed",
            "decky_backend": False,
            "decky_plugin_loader": False,
        },
    )

    result = asyncio.run(
        decky_compat.recover_frontend(
            "v3.2.6",
            transport_factory=lambda: transport,
            probe_attempts=2,
            probe_interval_s=0,
            sleep=_no_sleep,
        )
    )

    assert result.status == "postcondition_failed"
    assert result.attempted is True
    assert transport.recovery_calls == 1


def test_cdp_recovery_has_an_integral_receive_timeout(monkeypatch):
    transport = decky_compat.LocalCdpTransport(timeout_s=0.01)
    cancelled = False

    async def never_returns(_target, _expression, _await_promise):
        nonlocal cancelled
        try:
            await asyncio.Event().wait()
        finally:
            cancelled = True

    monkeypatch.setattr(transport, "_evaluate", never_returns)

    with pytest.raises(TimeoutError):
        asyncio.run(transport.recover(SHARED_TARGET, "ignored"))

    assert cancelled is True


def test_recovery_script_is_local_one_shot_and_does_not_restart_steam():
    script = decky_compat.build_recovery_script()

    assert "http://localhost:1337/frontend/index.js?v=v3.2.6" in script
    assert "pdc-compat=" in script
    assert "importTimeoutMs = 4000" in script
    assert "Promise.race([importBundle, importDeadline])" in script
    assert 'new Error("import_timeout")' in script
    assert "__pdcDecky326Recovery" in script
    assert "BFinishedInitBeforeLogin" in script
    assert "BFinishedInitStageOne" in script
    assert 'typeof app.BFinishedInitStageOne === "undefined"' in script
    assert "app.BFinishedInitStageOne === stageOneCompat" in script
    assert "delete app.BFinishedInitStageOne" in script
    assert "RestartJSContext" not in script
    assert "location.reload" not in script
