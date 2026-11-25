import json

from test_tdp_guard_rpc import plugin  # noqa: F401
from test_upscalers import steam, fake_catalog, proc  # noqa: F401

import game_force_close as gfc
from upscalers import game_session
from upscalers.game_session import GameSessions


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def tracker(clock, records, *, injections=None, probe=None, runtime=None):
    return GameSessions(
        injections=injections or (lambda appid: {}), runtime=runtime or (lambda appid: {}),
        probe=probe or (lambda appid: {"reaper": True, "processes": 3, "names": ["game.exe"]}),
        emit=records.append, submit=lambda job: job(), submit_later=lambda delay, job: pending.append(job),
        clock=clock, wall=clock)


pending = []


def setup_function():
    pending.clear()


# Session boundaries of PDC-JR75 (Legion Go S, Panel 0.95.1) as the journal recorded them for Detroit.
JR75_SESSIONS = [(596079.9, 597101.6, 'vanilla'), (597298.5, 597351.0, 'optiscaler+mako'),
                 (597381.2, 597405.6, 'vanilla'), (597435.7, 597512.3, 'vanilla')]


def test_jr75_sessions_are_classified_with_the_injections_active_at_launch():
    clock, records = Clock(), []
    injections = {
        'vanilla': {},
        'optiscaler+mako': {'mako': {'spatial': False, 'fg': True, 'engine': 5, 'multiplier': 2},
                            'optiscaler': {'build': 'fsr-4.1.2-beta', 'proxy': 'dxgi.dll', 'fg': 'off', 'quality': 'native'}},
    }
    current = {}
    sessions = tracker(clock, records, injections=lambda appid: injections[current['kind']])
    previous = None
    for start, end, kind in JR75_SESSIONS:
        current['kind'] = kind
        clock.now = start
        sessions.transition(previous, '1222140')
        clock.now = end
        sessions.transition('1222140', None)
        previous = None
    assert [(r['outcome'], r['injections']) for r in records] == [
        ('normal', {}), ('short', injections['optiscaler+mako']), ('short', {}), ('short', {})]
    assert [r['seconds'] for r in records] == [1021.7, 52.5, 24.4, 76.6]
    assert all(r['process'] == 'not_sampled' for r in records)


def test_process_probe_runs_only_while_the_session_is_still_open():
    clock, records = Clock(), []
    sessions = tracker(clock, records)
    sessions.transition(None, '4162040')
    clock.now = 30
    pending.pop()()
    sessions.transition('4162040', None)
    sessions.transition(None, '4162040')
    clock.now = 40
    sessions.transition('4162040', None)
    stale = pending.pop(0)
    stale()
    first, second = records
    assert first['process'] == {'reaper': True, 'processes': 3, 'names': ['game.exe']}
    assert second['process'] == 'not_sampled'


def test_a_failing_snapshot_never_hides_the_session():
    clock, records = Clock(), []

    def broken(appid):
        raise OSError('boom')
    sessions = tracker(clock, records, injections=broken, runtime=broken)
    sessions.transition(None, '4162040')
    clock.now = 31
    sessions.transition('4162040', None)
    assert records[0]['injections'] == {'error': 'OSError'}
    assert records[0]['mako_runtime'] == {'error': 'OSError'}
    assert records[0]['outcome'] == 'short'
    json.dumps(records[0])


def test_unchanged_game_context_does_not_split_a_session():
    clock, records = Clock(), []
    sessions = tracker(clock, records)
    sessions.transition(None, '1222140')
    sessions.transition('1222140', '1222140')
    assert records == []


def test_process_summary_reports_reaper_and_game_executables_only():
    def process(pid, ppid, name, argv=()):
        return gfc.Process(pid=pid, ppid=ppid, uid=1000, name=name, state='S', start=pid, argv=tuple(argv))
    table = {p.pid: p for p in [
        process(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=1222140', '--', 'proton']),
        process(11, 10, 'wineserver'), process(12, 10, 'detroit.exe'), process(13, 12, 'crashhandler.exe')]}
    summary = game_session.process_summary(table, '1222140', gfc.game_tree)
    assert summary == {'reaper': True, 'processes': 4, 'names': ['detroit.exe', 'crashhandler.exe']}
    assert game_session.process_summary(table, '999', gfc.game_tree) == {'reaper': False, 'processes': 0, 'names': []}


def test_service_snapshot_lists_scalers_configured_for_the_game(steam, fake_catalog, proc, monkeypatch):
    from test_upscalers import APPID, _service
    service = _service(steam, fake_catalog, proc)
    monkeypatch.setattr(service.mako, 'status', lambda: {'profiles': {APPID: {'enabled': True, 'engine': 5, 'multiplier': 2}}})
    service.state['games'][APPID] = {'install': {'engine': 'optiscaler', 'build': 'fsr-4.1.2-beta', 'proxy': 'dxgi.dll',
                                                  'options': {'fg': 'off', 'quality': 'native'}}}
    assert service.session_injections(APPID) == {
        'mako': {'spatial': False, 'fg': True, 'engine': 5, 'multiplier': 2},
        'optiscaler': {'build': 'fsr-4.1.2-beta', 'proxy': 'dxgi.dll', 'fg': 'off', 'quality': 'native'}}
    assert service.session_injections('1') == {}
    assert service.session_mako_runtime('missing') == {}


def test_plugin_records_a_session_when_the_game_context_changes(plugin, monkeypatch):
    records = []
    import main
    monkeypatch.setattr(main.decky.logger, 'info', lambda message, *args: records.append(message % args))
    plugin._set_current_appid('1222140')
    plugin._set_current_appid(None)
    plugin._game_session_executor.shutdown(wait=True)
    lines = [line for line in records if line.startswith('GAME_SESSION ')]
    assert len(lines) == 1
    record = json.loads(lines[0].split(' ', 1)[1])
    assert record['appid'] == '1222140' and record['outcome'] == 'short' and record['injections'] == {}
