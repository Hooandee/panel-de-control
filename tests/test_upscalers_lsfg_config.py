import shlex
import tomllib

import pytest

from upscalers.lsfg import Lsfg
from test_upscalers_lsfg_update import payload


@pytest.mark.parametrize('home_name', ['home', 'home with spaces', "someone's home"])
def test_explicit_config_ignores_external_xdg_and_keeps_it_intact(tmp_path, monkeypatch, home_name):
    home = tmp_path / home_name
    external = home / '.var/app/org.anatase.Steam/config'
    foreign = external / 'lsfg-vk/conf.toml'
    foreign.parent.mkdir(parents=True)
    original = b'version = 2\n[[profile]]\nname = "foreign"\nmultiplier = 4\n'
    foreign.write_bytes(original)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(external))
    engine = Lsfg(str(home), tmp_path / 'state')
    try:
        engine.install(payload(tmp_path / 'bundle', b'layer'), '2.0.0')
        result = engine.set_game('292030', 'Witcher', {'multiplier': 2}, 'witcher3.exe')
        encoded = result['env']['LSFGVK_CONFIG']
        assert shlex.split(encoded) == [str(engine.config_path)]
        assert engine.config_path != foreign
        selected = tomllib.loads(engine.config_path.read_text())
        assert selected['profile'][0]['name'] == result['env']['LSFGVK_PROFILE']
        assert selected['global']['log_file'] == str(engine.runtime_log.path)
        assert foreign.read_bytes() == original
        assert engine.set_game('292030', 'Witcher', None)['env'] == {}
        assert tomllib.loads(engine.config_path.read_text())['profile'][0]['multiplier'] == 1
        assert foreign.read_bytes() == original
    finally:
        engine.close()


@pytest.mark.parametrize(('scale', 'preset'), [(0.75, 'balanced'), (0.6, 'performance'), (1.0, 'quality'), (0.3, 'fastest')])
def test_manifest_keeps_the_nearest_preset_so_an_older_version_can_still_read_it(tmp_path, scale, preset):
    import json

    engine = Lsfg(str(tmp_path / 'home'), tmp_path / 'state')
    try:
        engine.install(payload(tmp_path / 'bundle', b'layer'), '2.0.0')
        engine.set_game('1', 'One', {'multiplier': 2, 'flow_scale': scale})
        engine.set_game('2', 'Two', {'multiplier': 3, 'flow_scale': 0.75})
        profiles = json.loads((tmp_path / 'state' / 'lsfg.json').read_text())['profiles']
        assert profiles['1']['flow'] == preset
        assert profiles['1']['flow_scale'] == scale
        assert profiles['2']['flow'] == 'balanced'
    finally:
        engine.close()
