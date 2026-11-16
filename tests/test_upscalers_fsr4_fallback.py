from pathlib import Path

import pytest

from upscalers import diagnostics, logread
from upscalers.service import UpscalerService

FALLBACK_LOG = (Path(__file__).parent / 'fixtures/upscalers/vulkan_fsr4_fallback.log').read_text()
FSR4_LOG = (
    '[I] NVSDK_NGX_VULKAN_CreateFeature1 Creating new FSR 3.X/4 w/Dx12 upscaler\n'
    '[I] FeatureProvider_Vk::ChangeFeature init successful for FSR 4.1.2 Lite, upscaler changed\n'
)
EXPECTED = {'requested': 'FSR 4', 'observed': 'FSR 2.2', 'reason': 'vulkan_textures'}


def make_service(tmp_path, log_text, build='fsr-4.1.2-beta', engine='optiscaler'):
    target = tmp_path / 'game'
    target.mkdir()
    (target / 'OptiScaler.log').write_text(log_text)
    service = UpscalerService(str(tmp_path), str(tmp_path / 'state'), 'rdna3')
    install = {'engine': engine, 'target': str(target), 'build': build, 'installed_at': 1}
    entry = service._game_state('4732690')
    entry['install'] = install
    entry['history'] = [{'build': build}]
    return service, install


def test_the_real_arknights_log_reads_as_a_fallback_from_fsr4(tmp_path):
    (tmp_path / logread.LOG_NAME).write_text(FALLBACK_LOG)
    facts = logread.read(tmp_path)
    assert facts['upscaler'] == 'FSR 2.2.1'
    assert logread.fallback({'engine': 'optiscaler', 'build': 'fsr-4.1.2-beta'}, facts) == EXPECTED


@pytest.mark.parametrize('log,build', [
    (FSR4_LOG, 'fsr-4.1.2-beta'),
    ('[I] Creating new fsr31 upscaler\n[I] amdxcffx64.dll loaded\n', 'fsr-4.1.1'),
    (FALLBACK_LOG, 'fsr-3.1'),
    (FALLBACK_LOG, 'xess'),
    ('[I] init successful for FSR 2.2.1, upscaler changed\n', 'fsr-3.1'),
    # Failed once, then FSR 4 came up: what runs is what counts.
    (FALLBACK_LOG + FSR4_LOG.replace('FSR 4.1.2 Lite', 'FSR 4.1.2'), 'fsr-4.1.2-beta'),
])
def test_no_fallback_when_fsr4_runs_or_was_not_asked_for(tmp_path, log, build):
    (tmp_path / logread.LOG_NAME).write_text(log)
    assert logread.fallback({'engine': 'optiscaler', 'build': build}, logread.read(tmp_path)) is None


def test_a_texture_failure_alone_is_a_fallback_with_no_observed_scaler(tmp_path):
    (tmp_path / logread.LOG_NAME).write_text(
        "[I] Creating new FSR 3.X/4 w/Dx12 upscaler\n[E] IFeature_VkwDx12::Evaluate Can't process Vulkan textures!\n")
    assert logread.fallback({'engine': 'optiscaler', 'build': 'fsr-4.1.2-beta'}, logread.read(tmp_path)) == {
        'requested': 'FSR 4', 'observed': None, 'reason': 'vulkan_textures'}


def test_a_numbered_fsr2_without_error_is_a_fallback_for_another_reason(tmp_path):
    (tmp_path / logread.LOG_NAME).write_text('[I] init successful for FSR 3.1.4, upscaler changed\n')
    assert logread.fallback({'engine': 'optiscaler', 'build': 'fsr-4.0.2c'}, logread.read(tmp_path)) == {
        'requested': 'FSR 4', 'observed': 'FSR 3.1', 'reason': 'backend_changed'}


def test_dll_and_proton_installs_are_never_judged_from_a_log(tmp_path):
    (tmp_path / logread.LOG_NAME).write_text(FALLBACK_LOG)
    facts = logread.read(tmp_path)
    for engine in ('dll', 'proton', 'helixsr'):
        assert logread.fallback({'engine': engine, 'build': 'fsr-4.1.2-dll'}, facts) is None


def test_live_verify_history_overview_and_report_carry_the_fact(tmp_path):
    service, install = make_service(tmp_path, FALLBACK_LOG)
    assert service.live('4732690')['fallback'] == EXPECTED
    verified = service.verify('4732690')
    assert verified['facts']['fallback'] == EXPECTED
    assert service._game_state('4732690')['history'][-1]['facts']['fallback'] == EXPECTED
    assert service.overview()['installs']['4732690']['fallback'] == EXPECTED
    observed = diagnostics.snapshot(install)['observed']
    assert observed['fallback'] == EXPECTED
    assert observed['upscaler'] == 'FSR 2.2.1'


def test_a_working_fsr4_reports_no_fallback_anywhere(tmp_path):
    service, install = make_service(tmp_path, FSR4_LOG)
    assert service.live('4732690')['fallback'] is None
    assert 'fallback' not in service.verify('4732690')['facts']
    assert service.overview()['installs']['4732690']['fallback'] is None
    assert 'fallback' not in diagnostics.snapshot(install)['observed']


def test_a_stale_log_proves_nothing(tmp_path):
    import os
    service, install = make_service(tmp_path, FALLBACK_LOG)
    install['verification_since'] = 100
    os.utime(tmp_path / 'game/OptiScaler.log', (1, 1))
    assert service.live('4732690')['fallback'] is None
