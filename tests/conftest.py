import device_registry
import pytest


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
