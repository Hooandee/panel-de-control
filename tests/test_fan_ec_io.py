import threading
import time

from fans import ec_io
from fans.ec_io import EcSys


def test_read_does_not_try_to_load_ec_sys(monkeypatch):
    ec = EcSys(root="/")
    loads = []
    monkeypatch.setattr(ec, "_ensure_loaded", lambda: loads.append(True))

    assert ec.read(0x4A) is None
    assert loads == []


def test_writable_tries_to_load_ec_sys(monkeypatch):
    ec = EcSys(root="/")
    loads = []
    monkeypatch.setattr(ec, "_ensure_loaded", lambda: loads.append(True))

    assert ec.writable() is False
    assert loads == [True]


def test_write_tries_to_load_ec_sys(monkeypatch):
    ec = EcSys(root="/")
    loads = []
    monkeypatch.setattr(ec, "_ensure_loaded", lambda: loads.append(True))

    assert ec.write(0x4A, 1) is False
    assert loads == [True]


def test_concurrent_writable_waits_for_the_module_load(monkeypatch):
    ec = EcSys(root="/")
    loaded = threading.Event()
    calls = []

    monkeypatch.setattr(ec_io.os, "access", lambda *a, **k: loaded.is_set())

    def load(*a, **k):
        calls.append(True)
        time.sleep(0.03)
        loaded.set()

    import subprocess
    monkeypatch.setattr(subprocess, "run", load)
    monkeypatch.setattr("controllers.detect.resolve_bin", lambda name: name)
    monkeypatch.setattr("controllers.detect.clean_env", lambda: {})

    barrier = threading.Barrier(3)
    results = []

    def probe():
        barrier.wait()
        results.append(ec.writable())

    threads = [threading.Thread(target=probe) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert calls == [True]
    assert results == [True, True]
