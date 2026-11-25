import os

import pytest

from upscalers import diagnostics, service as service_module
from upscalers.service import UpscalerService


@pytest.fixture
def verified_lite(tmp_path, monkeypatch):
    target = tmp_path / 'game'
    target.mkdir()
    (target / '.pdc-upscaler').mkdir()
    (target / '.pdc-upscaler/manifest.json').write_text('{}')
    (target / 'dxgi.dll').write_bytes(b'MZ')
    (target / 'OptiScaler.ini').write_text('[FSR]\nFsr4GpuSupport=4\n')
    log = target / 'OptiScaler.log'
    log.write_text('Creating new FSR 4.1.2 Lite upscaler\nRender Resolution: 1280x800, Display Resolution 1280x800\n')
    os.utime(log, (150, 150))
    service = UpscalerService(str(tmp_path), str(tmp_path / 'state'), 'rdna2')
    monkeypatch.setattr(service, '_find', lambda _: None)
    monkeypatch.setattr(service_module.time, 'time', lambda: 200)
    entry = service._game_state('1')
    entry['install'] = {'build': 'fsr-4.1.2-beta', 'target': str(target), 'proxy': 'dxgi.dll',
                        'installed_at': 100, 'options': {'model': 'lite', 'quality': 'native'}}
    entry['history'] = [{'build': 'fsr-4.1.2-beta', 'result': 'pending'}]
    assert service.verify('1')['result'] == 'active'
    return service, entry, log


def test_model_change_requires_new_log_and_preserves_install_date(verified_lite):
    service, entry, log = verified_lite
    service.configure('1', {'model': 'full', 'quality': 'native'})
    install = entry['install']
    assert install['installed_at'] == 100
    assert install['verification_since'] == 200
    assert service._status(install, entry) == 'pending'
    assert 'facts' not in entry['history'][-1]
    assert entry['history'][-2]['result'] == 'active'
    verification = service.verify('1')
    assert verification['result'] == 'not_run' and verification['facts']['stale'] is True
    assert 'resolution' not in verification['facts']
    assert service._status(install, entry) == 'pending'
    assert diagnostics.snapshot(install)['observed']['result'] == 'not_run'
    report = diagnostics.game_report(service.home, '1', entry)
    assert report['log_verdict'] == 'not_run'
    assert report['current']['observed']['result'] == 'not_run'
    log.write_text('Creating new FSR 4.1.2 upscaler\nRender Resolution: 1280x800, Display Resolution 1280x800\n')
    os.utime(log, (201, 201))
    assert service.verify('1')['result'] == 'active'
    assert service._status(install, entry) == 'active'
    assert entry['history'][-1]['facts']['upscaler'] == 'FSR 4.1.2'
    assert diagnostics.snapshot(install)['observed']['result'] == 'active'


@pytest.mark.parametrize('previous,next_model', [('lite', 'lite'), (None, 'lite'), ('lite', None)])
def test_equivalent_default_model_does_not_invalidate(verified_lite, previous, next_model):
    service, entry, _ = verified_lite
    entry['install']['options']['model'] = previous
    service.configure('1', {'model': next_model, 'quality': 'native'})
    assert 'verification_since' not in entry['install']
    assert service._status(entry['install'], entry) == 'active'
    assert len(entry['history']) == 1
