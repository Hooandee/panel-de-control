from tdp.powerstation import Detector, probe


def _runner(outputs, calls):
    def run(command):
        calls.append(command)
        return outputs.get(tuple(command), "")

    return run


def test_probe_reports_tdp_interface_from_active_powerstation():
    calls = []
    outputs = {
        ("systemctl", "is-active", "powerstation.service"): "active",
        (
            "busctl",
            "--system",
            "tree",
            "org.shadowblip.PowerStation",
        ): """
        /org/shadowblip/Performance/GPU/Card0
        /org/shadowblip/Performance/GPU/Card0/Connector0
        """,
        (
            "busctl",
            "--system",
            "introspect",
            "org.shadowblip.PowerStation",
            "/org/shadowblip/Performance/GPU/Card0",
            "org.shadowblip.GPU.Card.TDP",
        ): "TDP property readwrite u 15",
    }

    assert probe(_runner(outputs, calls)) is True


def test_probe_rejects_active_service_without_tdp_interface():
    calls = []
    outputs = {
        ("systemctl", "is-active", "powerstation.service"): "active",
        (
            "busctl",
            "--system",
            "tree",
            "org.shadowblip.PowerStation",
        ): "/org/shadowblip/Performance/GPU/Card0",
    }

    assert probe(_runner(outputs, calls)) is False


def test_probe_stops_when_powerstation_is_inactive():
    calls = []

    assert probe(_runner({}, calls)) is False
    assert calls == [["systemctl", "is-active", "powerstation.service"]]


def test_detector_caches_probe_for_bounded_polling_cost():
    calls = []
    now = [100.0]
    outputs = {
        ("systemctl", "is-active", "powerstation.service"): "active",
        (
            "busctl",
            "--system",
            "tree",
            "org.shadowblip.PowerStation",
        ): "/org/shadowblip/Performance/GPU/Card0",
        (
            "busctl",
            "--system",
            "introspect",
            "org.shadowblip.PowerStation",
            "/org/shadowblip/Performance/GPU/Card0",
            "org.shadowblip.GPU.Card.TDP",
        ): "TDP property readwrite u 15",
    }
    detector = Detector(
        run=_runner(outputs, calls),
        clock=lambda: now[0],
        cache_seconds=15,
    )

    assert detector.tdp_active() is True
    first_probe_calls = len(calls)
    now[0] = 110.0
    assert detector.tdp_active() is True
    assert len(calls) == first_probe_calls
    now[0] = 116.0
    assert detector.tdp_active() is True
    assert len(calls) > first_probe_calls
