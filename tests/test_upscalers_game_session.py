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
        emit=records.append, submit=lambda job: job(), submit_later=lambda delay, job: later(delay, job),
        clock=clock, wall=clock)


pending = []
cancelled = []


class Timer:
    def __init__(self, delay):
        self.delay = delay

    def cancel(self):
        cancelled.append(self.delay)


def later(delay, job):
    pending.append(job)
    return Timer(delay)


def setup_function():
    pending.clear()
    cancelled.clear()


SESSIONS = [(596079.9, 597101.6, 'vanilla'), (597298.5, 597351.0, 'optiscaler+mako'),
                 (597381.2, 597405.6, 'vanilla'), (597435.7, 597512.3, 'vanilla')]


def test_sessions_are_classified_with_the_injections_active_at_launch():
    clock, records = Clock(), []
    injections = {
        'vanilla': {},
        'optiscaler+mako': {'mako': {'spatial': False, 'fg': True, 'engine': 5, 'multiplier': 2},
                            'optiscaler': {'build': 'fsr-4.1.2-beta', 'proxy': 'dxgi.dll', 'fg': 'off', 'quality': 'native'}},
    }
    current = {}
    sessions = tracker(clock, records, injections=lambda appid: injections[current['kind']])
    previous = None
    for start, end, kind in SESSIONS:
        current['kind'] = kind
        clock.now = start
        sessions.transition(previous, '1222140', launch=True)
        clock.now = end
        sessions.transition('1222140', None)
        previous = None
    assert [(r['outcome'], r['injections']) for r in records] == [
        ('normal', {}), ('short', injections['optiscaler+mako']), ('short', {}), ('short', {})]
    assert [r['seconds'] for r in records] == [1021.7, 52.5, 24.4, 76.6]
    assert all(r['process'] == [{'at': 'finish', 'reaper': True, 'processes': 3, 'names': ['game.exe']}] for r in records)


def test_process_probe_runs_only_while_the_session_is_still_open():
    clock, records = Clock(), []
    sessions = tracker(clock, records)
    sessions.transition(None, '4162040')
    clock.now = 30
    pending.pop(0)()
    pending.pop(0)()
    sessions.transition('4162040', None)
    sessions.transition(None, '4162040')
    clock.now = 40
    sessions.transition('4162040', None)
    for stale in list(pending):
        stale()
    first, second = records
    sample = {'reaper': True, 'processes': 3, 'names': ['game.exe']}
    assert first['process'] == [{'at': 5} | sample, {'at': 20} | sample]
    assert second['process'] == [{'at': 'finish'} | sample]


def test_a_game_that_dies_before_the_first_probe_is_still_sampled_at_finish():
    clock, records = Clock(), []
    sessions = tracker(clock, records, probe=lambda appid: {'reaper': False, 'processes': 0, 'names': []})
    sessions.transition(None, '4162040', launch=True)
    clock.now = 3
    sessions.transition('4162040', None)
    assert records[0]['process'] == [{'at': 'finish', 'reaper': False, 'processes': 0, 'names': []}]
    assert cancelled == [5, 20]


def test_sessions_not_seen_starting_claim_no_outcome():
    clock, records = Clock(), []
    sessions = tracker(clock, records)
    sessions.transition(None, '1222140')
    clock.now = 12
    sessions.transition('1222140', None)
    assert records[0]['start'] == 'attached' and 'outcome' not in records[0]
    sessions.transition(None, '1222140', launch=True)
    clock.now = 20
    sessions.transition('1222140', None)
    assert records[1]['start'] == 'launch' and records[1]['outcome'] == 'short'


def test_unknown_injections_are_null_with_a_reason_not_empty():
    clock, records = Clock(), []
    sessions = tracker(clock, records, injections=lambda appid: None)
    sessions.transition(None, '1222140', launch=True)
    clock.now = 100
    sessions.transition('1222140', None)
    assert records[0]['injections'] is None and records[0]['injections_reason'] == 'service_unavailable'
    queued = []
    sessions = GameSessions(injections=lambda a: {}, runtime=lambda a: {}, probe=lambda a: {}, emit=records.append,
                            submit=queued.append, submit_later=lambda d, j: None, clock=clock, wall=clock)
    sessions.transition(None, '7', launch=True)
    sessions.transition('7', None)
    queued[-1]()
    assert records[1]['injections'] is None and records[1]['injections_reason'] == 'not_captured'


def test_duration_is_taken_when_the_transition_happens_not_when_the_job_runs():
    clock, records = Clock(), []
    queued = []
    sessions = GameSessions(injections=lambda a: {}, runtime=lambda a: {}, probe=lambda a: {}, emit=records.append,
                            submit=queued.append, submit_later=lambda d, j: None, clock=clock, wall=clock)
    sessions.transition(None, '1', launch=True)
    clock.now = 10
    sessions.transition('1', None)
    clock.now = 500
    for job in queued:
        job()
    assert records[0]['seconds'] == 10 and records[0]['outcome'] == 'short'


def test_close_emits_the_open_session_without_probing_and_cancels_timers():
    clock, records = Clock(), []
    probes = []
    sessions = tracker(clock, records, probe=lambda appid: probes.append(appid))
    sessions.transition(None, '1222140', launch=True)
    clock.now = 42
    sessions.close()
    assert probes == [] and cancelled == [5, 20]
    assert records[0]['ended_by'] == 'plugin_unload' and records[0]['seconds'] == 42
    assert records[0]['mako_runtime'] == 'not_collected'
    sessions.close()
    assert len(records) == 1


def test_a_failing_snapshot_never_hides_the_session():
    clock, records = Clock(), []

    def broken(appid):
        raise OSError('boom')
    sessions = tracker(clock, records, injections=broken, runtime=broken)
    sessions.transition(None, '4162040', launch=True)
    clock.now = 31
    sessions.transition('4162040', None)
    assert records[0]['injections'] is None and records[0]['injections_reason'] == 'error:OSError'
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


def _plugin_records(plugin, monkeypatch, act):
    records = []
    import main
    monkeypatch.setattr(main.decky.logger, 'info', lambda message, *args: records.append(message % args))
    act()
    plugin._game_session_executor.shutdown(wait=True)
    return [json.loads(line.split(' ', 1)[1]) for line in records if line.startswith('GAME_SESSION ')]


def test_plugin_records_a_session_when_the_game_context_changes(plugin, monkeypatch):
    def act():
        plugin._set_current_appid('1222140', True)
        plugin._set_current_appid(None)
    (record,) = _plugin_records(plugin, monkeypatch, act)
    assert record['appid'] == '1222140' and record['outcome'] == 'short' and record['start'] == 'launch'
    assert record['injections'] is None and record['injections_reason'] == 'service_unavailable'


def test_profile_editors_do_not_claim_a_launch(plugin, monkeypatch):
    def act():
        plugin._set_current_appid('1222140')
        plugin._set_current_appid(None)
    (record,) = _plugin_records(plugin, monkeypatch, act)
    assert record['start'] == 'attached' and 'outcome' not in record


def test_plugin_unload_emits_the_open_session(plugin, monkeypatch):
    def act():
        plugin._set_current_appid('1222140', True)
        plugin._close_upscalers_sync()
    (record,) = _plugin_records(plugin, monkeypatch, act)
    assert record['ended_by'] == 'plugin_unload'


def test_only_a_report_after_an_observed_idle_counts_as_a_launch(plugin, monkeypatch):
    import asyncio

    def act():
        asyncio.run(plugin.set_current_game('1222140'))
        asyncio.run(plugin.set_current_game(None))
        asyncio.run(plugin.set_current_game('1222140'))
        asyncio.run(plugin.set_current_game(None))
    first, second = _plugin_records(plugin, monkeypatch, act)
    assert (first['start'], second['start']) == ('attached', 'launch')
