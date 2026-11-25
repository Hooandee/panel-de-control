from tdp.steamos_manager import Detector


def test_active_service_is_presence_not_power_state():
    detector = Detector(lambda cmd: 'steamos-manager.service loaded active running SteamOS Manager\n')
    assert detector.active() is True


def test_other_or_inactive_service_is_not_presence():
    for output in ('', 'other-steamos-manager.service loaded active running Other\n'):
        assert Detector(lambda cmd: output).active() is False


def test_capture_failures_are_unknown():
    for output in (None, '[exit 1] permission denied'):
        assert Detector(lambda cmd: output).active() is None

    def failed(cmd):
        raise OSError('unavailable')

    assert Detector(failed).active() is None


def test_cache_expires_and_recovers_from_failed_probe():
    now = [0]
    outputs = iter([None, 'steamos-manager.service loaded active running SteamOS Manager\n', ''])
    calls = []

    def run(cmd):
        calls.append(cmd)
        return next(outputs)

    detector = Detector(run, clock=lambda: now[0])
    assert detector.active() is None
    now[0] = 14
    assert detector.active() is None
    assert len(calls) == 1
    now[0] = 15
    assert detector.active() is True
    now[0] = 30
    assert detector.active() is False
    assert all('--state=active' in cmd for cmd in calls)
