import json

from test_upscalers import APPID, _service, _write, steam, fake_catalog, proc
from upscalers import catalog, diagnostics
from upscalers.service import UpscalerError, UpscalerService


def test_failed_request_survives_restart_and_excludes_secrets(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.begin('install', APPID)
    def install(appid, choice):
        raise UpscalerError('download_failed', 'token=secret')
    service.run(install, APPID, {'build': 'fsr-test', 'model': 'lite', 'env': 'TOKEN=secret'})
    restored = UpscalerService(service.home, str(service.state_path.parent), service.gpu, proc=proc)
    report = restored.report()
    event = report['games'][0]['actions'][-1]
    assert event['action'] == 'install'
    assert event['state'] == 'error'
    assert event['requested'] == {'build': 'fsr-test', 'model': 'lite'}
    assert event['error'] == 'download_failed'
    assert 'secret' not in json.dumps(report)


def test_removed_install_keeps_previous_observation(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {'build': 'fsr-test'})
    service.begin('uninstall', APPID)
    service.run(service.uninstall, APPID)
    report = service.report()['games'][0]
    assert report['install'] is None
    assert report['previous']['applied']['build'] == 'fsr-test'
    assert report['previous']['observed']['result'] == 'not_run'
    assert report['actions'][-1]['state'] == 'done'


def test_active_and_job_precede_report_limit(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    for i in range(15):
        service.state['games'][str(i)] = {'history': [{'at': i}]}
    service.begin('install', 'job-game')
    report = service.report({'running': {'live_appid': 1234, 'stable_appid': 'different-key'}})
    assert [g['appid'] for g in report['games']][:2] == ['1234', 'job-game']
    assert len(report['games']) == 12


def test_frontend_context_is_bounded_and_does_not_infer_identity():
    context = diagnostics.frontend_context({'running': {'live_appid': 12, 'stable_appid': 'shortcut',
        'name': 'Game', 'is_non_steam': None, 'env': 'secret'}, 'status': 'available', 'token': 'secret'})
    assert context['running']['live_appid'] == '12'
    assert context['running']['stable_appid'] == 'shortcut'
    assert context['running']['is_non_steam'] is None
    assert 'secret' not in json.dumps(context)


def test_report_keeps_other_games_when_one_diagnostic_fails(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.state['games'] = {'bad': {'history': [{'at': 2}]}, 'good': {'history': [{'at': 1}]}}
    original = diagnostics.game_report
    def report(home, appid, entry, installed=None):
        if appid == 'bad':
            raise OSError('private detail')
        return original(home, appid, entry, installed)
    monkeypatch.setattr(diagnostics, 'game_report', report)
    result = service.report()['games']
    assert {k: v for k, v in result[0].items() if k != 'elapsed_ms'} == {'appid': 'bad', 'error': 'OSError'}
    assert result[1]['appid'] == 'good'


def test_frontend_rejects_wrong_types_and_non_live_ids():
    result = diagnostics.frontend_context({'collected_at': 1, 'status': [],
        'running': {'live_appid': '../not-id', 'name': False, 'stable_appid': 42}})
    assert result == {'status': 'unavailable', 'running': {'is_non_steam': None}, 'games': {}}


def test_diagnostic_failure_does_not_stop_operation(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.begin('test', APPID)
    def broken(*args):
        raise ValueError('bad diagnostic structure')
    monkeypatch.setattr(service, '_record_action', broken)
    service.run(lambda appid: {'ok': True}, APPID)
    assert service.job()['state'] == 'done'
    assert service.job()['result'] == {'ok': True}


def test_global_action_is_persistent_without_inventing_a_game(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    service.record_action('global', 'lsfg_install', 'done')
    restored = UpscalerService(service.home, str(service.state_path.parent), service.gpu, proc=proc)
    report = restored.report()
    assert report['global_actions'][-1]['action'] == 'lsfg_install'
    assert 'snapshot' not in report['global_actions'][-1]
    assert report['games'] == []
    assert 'global' not in restored.state['games']


def test_advanced_records_known_values_but_omits_paths_and_free_text(tmp_path):
    path = tmp_path / 'OptiScaler.ini'
    path.write_text('[Spoofing]\n; true or false - Default (auto) is true\nStreamline=auto\n[Custom]\nPath=auto\nScale=1\n')
    assert diagnostics.ini_request(path, 'Spoofing.Streamline', 'false') == {'key': 'Spoofing.Streamline', 'value': 'false'}
    assert diagnostics.ini_request(path, 'Custom.Scale', '2.5')['value'] == '2.5'
    for value in ('/home/private/token', 'TOKEN=secret', 'secret-token'):
        assert diagnostics.ini_request(path, 'Custom.Path', value)['value_omitted'] is True


def test_lsfg_request_and_applied_profile_are_preserved(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    knobs = {'multiplier': 3, 'flow': 'quality', 'performance': False}
    monkeypatch.setattr(service.lsfg, 'status', lambda: {'profiles': {APPID: {**knobs, 'exe': 'private'}}})
    service.record_action(APPID, 'lsfg_game', 'done', {**knobs, 'enabled': True, 'env': 'secret'})
    event = service.report()['games'][0]['actions'][-1]
    assert event['requested'] == {**knobs, 'enabled': True}
    assert event['applied_lsfg'] == {**knobs, 'enabled': True}


def test_advanced_current_value_is_not_a_documented_choice(tmp_path):
    path = tmp_path / 'OptiScaler.ini'
    path.write_text('[Spoofing]\n; true or false - Default (auto) is true\nStreamline=secret-token\n')
    assert diagnostics.ini_request(path, 'Spoofing.Streamline', 'secret-token') == {
        'key': 'Spoofing.Streamline', 'value_omitted': True}
    assert diagnostics.ini_request(path, 'Spoofing.Streamline', 'false')['value'] == 'false'


def test_job_references_survive_real_redaction_without_mutating_runtime(steam, fake_catalog, proc):
    from copy import deepcopy
    from pdc_report.collector import redact_obj

    service = _service(steam, fake_catalog, proc)
    first, second = 'a1b2c3d4e5f6', 'f6e5d4c3b2a1'
    service.state['games'][APPID] = {'history': [], 'actions': [
        {'action': 'install', 'job_id': first}, {'action': 'install', 'job_id': second},
        {'action': 'install', 'job_id': 'unexpected-private-token'}]}
    service.state['global_actions'] = [{'action': 'cancel', 'job_id': first}]
    service._job = {'id': first, 'appid': APPID, 'state': 'error'}
    before_state, before_job = deepcopy(service.state), deepcopy(service._job)
    report = redact_obj(service.report())
    actions = report['games'][0]['actions']
    assert report['job']['id'] == actions[0]['job_id'] == 'job-a1b2-c3d4-e5f6'
    assert actions[1]['job_id'] == 'job-f6e5-d4c3-b2a1'
    assert actions[0]['job_id'] != actions[1]['job_id']
    assert report['global_actions'][0]['job_id'] == report['job']['id']
    assert 'job_id' not in actions[2]
    assert 'unexpected-private-token' not in json.dumps(report)
    assert service.state == before_state
    assert service._job == before_job
    service._job['id'] = 'unexpected-private-token'
    assert 'id' not in redact_obj(service.report())['job']


def test_live_steam_facts_keep_licence_and_launch_parts_but_nothing_personal():
    from upscalers import diagnostics
    context = diagnostics.frontend_context({"status": "available", "games": {"3764200": {
        "ownership_flags": 2049 | 32, "owned_by_user": False, "free": False, "beta": "public", "build_id": 23634047,
        "compat_tool": "proton_experimental",
        "launch_options": 'API_KEY=secret-token WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command% -dx12 /home/alice/save'}}})
    facts = context["games"]["3764200"]
    assert facts["ownership"] == ["subscribed", "shared_license", "license_permanent"]
    assert facts["owned_by_user"] is False and facts["compat_tool"] == "proton_experimental"
    assert facts["launch_live"]["dll_overrides"] == [{"name": "dxgi", "mode": "n,b"}]
    assert "secret-token" not in str(context) and "alice" not in str(context)


def test_report_lists_the_games_own_upscalers_loaders_and_store_files(steam, fake_catalog, proc):
    _, game = steam
    target = game / "bin/x64_dx12"
    _write(target / "dinput8.dll", b"someone else's loader")
    _write(target / "steam_settings" / "configs.user.ini", b"x")
    service = _service(steam, fake_catalog, proc)
    service.install(APPID, {"build": "fsr-test"})
    files = service.diagnose(APPID)["game_files"]
    owners = {item["path"]: item["owner"] for item in files["loaders"]}
    assert owners["bin/x64_dx12/dxgi.dll"] == "panel" and owners["bin/x64_dx12/dinput8.dll"] == "other"
    assert files["store_files"] == ["steam_settings"]


def test_report_keeps_what_the_user_did_and_each_install_state_once():
    snapshot = {"applied": {"build": "fsr-4.1.2-beta"}}
    actions = ([{"action": "refresh_wiki", "state": "done", "snapshot": snapshot}] * 15
               + [{"action": "install", "state": "started", "snapshot": snapshot},
                  {"action": "install", "state": "done", "snapshot": snapshot},
                  {"action": "configure", "state": "done", "snapshot": {"applied": {"build": "fsr-3.1"}}}])
    events = diagnostics.report_actions(actions)
    assert [e["action"] for e in events] == ["install", "install", "configure"]
    assert ["snapshot" in e for e in events] == [True, False, True]


def test_report_lists_the_versions_offered_on_this_gpu(steam, fake_catalog, proc):
    service = _service(steam, fake_catalog, proc)
    builds = service.report()["builds"]
    assert builds and all(set(row) <= {"id", "supported", "may_fallback"} for row in builds)
    assert {row["id"] for row in builds} == {b.id for b in catalog.BUILDS.values() if b.available}


def test_report_stops_reading_games_past_its_budget(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.state['games'] = {str(i): {'history': [{'at': i}]} for i in range(5)}
    now = [0.0]
    monkeypatch.setattr('upscalers.service.time.monotonic', lambda: now[0])
    original = service.diagnose
    def slow(appid):
        now[0] += 2
        return original(appid)
    monkeypatch.setattr(service, 'diagnose', slow)
    report = service.report(budget_s=3)
    assert [g['appid'] for g in report['games']] == ['4', '3']
    assert report['games_skipped'] == ['2', '1', '0']
    assert 'reading' not in report and 'mako' in report and 'builds' in report


def test_partial_report_keeps_what_was_read_before_a_stuck_game(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    service.state['games'] = {'fast': {'history': [{'at': 2}]}, 'stuck': {'history': [{'at': 1}]}}
    partial = {}
    original = service.diagnose
    def diagnose(appid):
        if appid == 'stuck':
            raise KeyboardInterrupt
        return original(appid)
    monkeypatch.setattr(service, 'diagnose', diagnose)
    try:
        service.report(partial=partial)
    except KeyboardInterrupt:
        pass
    assert [g['appid'] for g in partial['games']] == ['fast']
    assert partial['reading'] == 'stuck'
    assert partial['gpu'] == service.gpu


def test_one_failing_report_section_keeps_the_rest(steam, fake_catalog, proc, monkeypatch):
    service = _service(steam, fake_catalog, proc)
    def broken():
        raise OSError('private detail')
    monkeypatch.setattr(service.lsfg, 'report', broken)
    report = service.report()
    assert report['lsfg'] == {'error': 'OSError'}
    assert 'private detail' not in json.dumps(report)
    assert 'mako' in report and 'helixsr' in report
