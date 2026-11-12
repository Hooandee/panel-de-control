import asyncio
import sys

from test_tdp_guard_rpc import plugin


def test_failed_visible_action_records_request_and_error(plugin, monkeypatch):
    from upscalers.service import UpscalerError
    class Service:
        def __init__(self):
            self.events = []
        def record_action(self, *args):
            self.events.append(args)
        def configure(self, appid, choice):
            raise UpscalerError('not_patched')
    service = Service()
    monkeypatch.setattr(plugin, '_init', lambda: None)
    monkeypatch.setattr(plugin, '_upscalers', lambda: service)
    events = []
    monkeypatch.setattr(sys.modules['main'], '_upscalers_journal', lambda *args, **kw: events.append(kw))
    try:
        asyncio.run(plugin._upscalers_call('configure', '42', {'build': 'fsr-test', 'env': 'secret'}))
    except RuntimeError as error:
        assert str(error) == 'not_patched'
    else:
        raise AssertionError('expected refusal')
    assert service.events == [('42', 'configure', 'started', {'build': 'fsr-test'}),
                              ('42', 'configure', 'error', {'build': 'fsr-test'}, 'not_patched')]
    assert events[-1]['appid'] == '42'


def test_report_failure_keeps_separate_running_identities(plugin, monkeypatch):
    async def unavailable(*args):
        raise TimeoutError()
    monkeypatch.setattr(plugin, '_upscalers_call', unavailable)
    monkeypatch.setattr(plugin, '_current_appid', 'backend-key')
    monkeypatch.setattr(plugin, '_current_game_name', 'Backend game', raising=False)
    report = asyncio.run(plugin._upscalers_report({'upscalers': {'status': 'available',
        'running': {'live_appid': '42', 'stable_appid': 'frontend-key', 'name': 'Frontend game', 'env': 'secret'}}}))
    assert report['error'] == 'diagnostics_unavailable'
    assert report['frontend']['running']['live_appid'] == '42'
    assert report['backend_running']['stable_appid'] == 'backend-key'
    assert 'env' not in report['frontend']['running']
    assert 'upscalers' not in plugin._launch_report_state({'upscalers': {'running': 'private'}})['frontend']


def test_report_timeout_keeps_games_read_before_it(plugin, monkeypatch):
    async def slow(method, frontend, budget, partial):
        partial.update({'gpu': 'rdna3', 'games': [{'appid': '526870', 'elapsed_ms': 900}], 'reading': '1934680'})
        raise TimeoutError()
    monkeypatch.setattr(plugin, '_upscalers_call', slow)
    report = asyncio.run(plugin._upscalers_report({'upscalers': {'status': 'available'}}))
    assert report['error'] == 'diagnostics_unavailable'
    assert report['reason'] == 'TimeoutError'
    assert report['games'] == [{'appid': '526870', 'elapsed_ms': 900}]
    assert report['reading'] == '1934680'
    assert report['frontend']['status'] == 'available'


def test_plugin_close_stops_lossless_log_monitor(plugin, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from upscalers.lsfg import Lsfg
    from test_upscalers_lsfg_update import payload
    engine = Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    engine.install(payload(tmp_path / 'bundle', b'layer'), '2.0.0')
    worker = engine.runtime_log._thread
    events = []
    service = SimpleNamespace(lsfg=engine, cancel=lambda: events.append('cancel'))
    monkeypatch.setattr(plugin, '_upscaler_service', service, raising=False)
    plugin._close_upscalers_sync()
    assert events == ['cancel']
    assert not worker.is_alive()
    engine.status()
    assert not worker.is_alive()
