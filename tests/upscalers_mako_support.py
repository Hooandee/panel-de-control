import hashlib
import io
import tarfile
from types import SimpleNamespace
import pytest
from upscalers import mako


def write(path, content=b'x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(mako.platform, 'machine', lambda: 'x86_64')
    home = tmp_path / 'home'
    library = home / '.steam/steam'
    dll = write(library / 'steamapps/common/Lossless Scaling/Lossless.dll')
    monkeypatch.setattr(mako.games, 'library_paths', lambda home: [library])
    manager = mako.Mako(str(home), tmp_path / 'state')
    archive = tmp_path / 'mako.tar.xz'
    with tarfile.open(archive, 'w:xz') as handle:
        for name in mako.PAYLOAD:
            content = b'#!/bin/sh\nexit 0\n' if name.startswith('bin/') else b'layer'
            info = tarfile.TarInfo('./' + name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    monkeypatch.setattr(mako, 'ASSET', SimpleNamespace(sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
    cache = SimpleNamespace(ensure=lambda *args: archive)
    calls = []
    def inspect(args, **kwargs):
        calls.append(args)
        kwargs['stdout'].write(b'{"schema_version":1,"compatible":true}')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mako.subprocess, 'run', inspect)
    return manager, cache, dll, calls


def release(manager):
    archive = manager.home.parent / "mako-next.tar.xz"
    with tarfile.open(archive, "w:xz") as handle:
        for name in mako.PAYLOAD:
            content = b"new renderer content " + name.encode()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            handle.addfile(info, io.BytesIO(content))
    return SimpleNamespace(ensure=lambda *args: archive), SimpleNamespace(sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
