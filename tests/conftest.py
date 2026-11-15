import device_registry
import pytest
from theme_support import theme_rpc  # noqa: F401
from upscalers_mako_support import setup  # noqa: F401
from upscalers_support import dll_catalog, fake_catalog, helix_catalog, proc, steam  # noqa: F401


@pytest.fixture(autouse=True)
def _host_is_not_a_desktop(monkeypatch):
    # Unrecognised hardware falls back to the desktop profile when the host has
    # no battery, and CI runners are battery-less VMs. Tests that need that path
    # pass their own fake sysfs root, which still goes through the real check.
    real = device_registry._is_desktop_host
    monkeypatch.setattr(
        device_registry,
        "_is_desktop_host",
        lambda root: False if root == "/" else real(root),
    )


@pytest.fixture(autouse=True)
def _no_release_lookups(monkeypatch):
    # Tests install the catalog's pinned assets; the newest-release lookup never reaches the network here.
    from upscalers import latest

    def offline(url):
        raise OSError("offline in tests")

    monkeypatch.setattr(latest, "_fetch", offline)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    """A fully initialised Plugin on a fake TDP backend and fan, on AC power."""
    from main_harness import FakeBackend, FakeFan, fake_decky, load_main

    logs = fake_decky(monkeypatch, tmp_path)
    import fans.control as fan_control
    import lifecycle
    import tdp.factory as factory

    monkeypatch.setattr(factory, "select_backend", lambda device, **kw: FakeBackend())
    monkeypatch.setattr(fan_control, "select_fan_backend", lambda device, **kw: FakeFan())
    monkeypatch.setattr(lifecycle, "read_on_ac", lambda root="/": True)
    main = load_main(monkeypatch)
    monkeypatch.setattr(main, "read_on_ac", lambda root="/": True, raising=False)
    instance = main.Plugin()
    instance._init()
    instance._test_logs = logs
    return instance
