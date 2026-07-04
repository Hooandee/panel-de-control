import os

from fans import expose


def _write(path: str, content: str = "") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _make_param(root: str) -> None:
    _write(os.path.join(root, "sys/module/lenovo_wmi_other/parameters/expose_all_fans"), "N\n")


def _make_fan_node(root: str) -> None:
    d = os.path.join(root, "sys/class/hwmon/hwmon9")
    _write(os.path.join(d, "name"), "lenovo_wmi_other\n")
    _write(os.path.join(d, "fan1_input"), "0\n")


class _Runner:
    """Records modprobe invocations; optionally creates the fan node on load."""

    def __init__(self, root=None, succeed=True):
        self.calls = []
        self._root = root
        self._succeed = succeed

    def __call__(self, cmd):
        self.calls.append(cmd)
        # Simulate the kernel creating the fan hwmon when the module is (re)loaded
        # with the param, so the post-check can see it.
        if self._root and cmd[:2] == ["modprobe", "lenovo_wmi_other"]:
            _make_fan_node(self._root)
        return self._succeed


def test_noop_when_module_param_absent(tmp_path):
    r = _Runner()
    root = str(tmp_path)
    assert expose.ensure_fan_sensor(run=r, root=root) is False
    assert r.calls == []
    assert not os.path.exists(os.path.join(root, expose._MODPROBE_CONF))


def test_noop_when_fan_already_exposed(tmp_path):
    root = str(tmp_path)
    _make_param(root)
    _make_fan_node(root)
    r = _Runner()
    assert expose.ensure_fan_sensor(run=r, root=root) is True
    assert r.calls == []  # already present → no reload


def test_enables_and_persists_when_missing(tmp_path):
    root = str(tmp_path)
    _make_param(root)  # lenovo device, but fan node hidden
    r = _Runner(root=root)
    assert expose.ensure_fan_sensor(run=r, root=root) is True
    # modprobe -r then reload with the param
    assert ["modprobe", "-r", "lenovo_wmi_other"] in r.calls
    assert any(c[:2] == ["modprobe", "lenovo_wmi_other"] and "expose_all_fans=Y" in c for c in r.calls)
    # persisted for future boots
    conf = os.path.join(root, expose._MODPROBE_CONF)
    assert os.path.exists(conf)
    assert "expose_all_fans=Y" in open(conf).read()


def test_conf_not_duplicated(tmp_path):
    root = str(tmp_path)
    _make_param(root)
    r = _Runner(root=root)
    expose.ensure_fan_sensor(run=r, root=root)
    first = open(os.path.join(root, expose._MODPROBE_CONF)).read()
    # second run (node now present via simulation) is a no-op on the conf
    expose.ensure_fan_sensor(run=_Runner(root=root), root=root)
    assert open(os.path.join(root, expose._MODPROBE_CONF)).read() == first


def test_never_raises_on_run_error(tmp_path):
    root = str(tmp_path)
    _make_param(root)

    def boom(cmd):
        raise RuntimeError("modprobe blew up")

    # must swallow and return False (node never appeared)
    assert expose.ensure_fan_sensor(run=boom, root=root) is False


def test_remove_conf(tmp_path):
    root = str(tmp_path)
    conf = os.path.join(root, expose._MODPROBE_CONF)
    _write(conf, "options lenovo_wmi_other expose_all_fans=Y\n")
    expose.remove_conf(root=root)
    assert not os.path.exists(conf)
    # idempotent — no error when already gone
    expose.remove_conf(root=root)
