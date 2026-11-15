import hashlib
from pathlib import Path
import pytest
from upscalers import catalog, lsfg, recipe_catalog
from upscalers.catalog import Asset, Build
from upscalers.service import UpscalerService


APPID = "292030"


def _write(path: Path, data: bytes | str = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


@pytest.fixture
def steam(tmp_path):
    home = tmp_path / "home"
    root = home / ".local/share/Steam"
    _write(root / "steamapps/libraryfolders.vdf", '"libraryfolders"\n{\n "0"\n {\n  "path" "%s"\n }\n}\n' % root)
    _write(root / f"steamapps/appmanifest_{APPID}.acf",
           '"AppState"\n{\n "appid" "%s"\n "name" "Witcher"\n "installdir" "Witcher"\n "StateFlags" "4"\n}\n' % APPID)
    game = root / "steamapps/common/Witcher"
    _write(game / "REDprelauncher.exe", b"MZ" + b"\0" * 64)
    _write(game / "bin/x64_dx12/witcher3.exe", b"MZ" + b"\0" * 4096)
    _write(game / "bin/x64_dx12/amd_fidelityfx_upscaler_dx12.dll")
    _write(game / "bin/x64_dx12/nvngx_dlss.dll")
    return home, game


@pytest.fixture
def fake_catalog(monkeypatch, tmp_path):
    def asset(asset_id, filename, content, archive=False):
        return Asset(asset_id, filename, hashlib.sha256(content).hexdigest(), len(content), ("http://invalid",), archive)

    archive = asset(catalog.OPTISCALER_ARCHIVE, "opti.7z", b"archive", archive=True)
    extra = asset("extra", "amdxcffx64.dll", b"provider")
    assets = {a.id: a for a in (archive, extra)}
    builds = {
        "fsr-test": Build("fsr-test", "fsr", "4.1.1", ("rdna2",), 3, 3, assets=("extra",),
                          ini={"FSR.Fsr4Update": "true"}),
        "fsr-later": Build("fsr-later", "fsr", "4.1.2", ("rdna2",), 3, 3, available=False),
    }
    monkeypatch.setattr(catalog, "ASSETS", assets)
    monkeypatch.setattr(catalog, "BUILDS", builds)

    state = tmp_path / "state"
    unpacked = state / "cache" / archive.sha256 / "unpacked"
    _write(unpacked / "OptiScaler.dll", b"injector")
    _write(unpacked / "OptiScaler.ini", "[FSR]\nFsr4Update=auto\n[Log]\nLogToFile=auto\n[Spoofing]\n; true or false - Default (auto) is true\nDxgi=auto\n")
    _write(unpacked / "amd_fidelityfx_upscaler_dx12.dll", b"sdk")
    _write(unpacked / "D3D12_Optiscaler/D3D12Core.dll", b"core")
    _write(unpacked / "setup_linux.sh", b"junk")
    _write(unpacked / ".complete", archive.sha256)
    _write(state / "cache" / extra.sha256 / extra.filename, b"provider")
    return state


def _service(steam, state, proc, search=lambda term: []):
    home, _ = steam
    service = UpscalerService(str(home), str(state), "rdna2", proc=str(proc))
    service.search = search
    return service


@pytest.fixture
def dll_catalog(fake_catalog, monkeypatch):
    payload = b"standalone upscaler"
    asset = Asset("dll-test", "amd_fidelityfx_upscaler_dx12.dll", hashlib.sha256(payload).hexdigest(), len(payload), ("http://invalid",))
    monkeypatch.setitem(catalog.ASSETS, asset.id, asset)
    monkeypatch.setitem(catalog.BUILDS, "dll-test", Build("dll-test", "fsr", "4.0.2c", ("rdna2",), 2, 3,
                        replace={asset.filename: asset.id}, engine="dll", way="fsr"))
    _write(Path(fake_catalog) / "cache" / asset.sha256 / asset.filename, payload)
    return fake_catalog


@pytest.fixture
def proc(tmp_path):
    path = tmp_path / "proc"
    path.mkdir()
    return path


def without_bundled_recipes(monkeypatch):
    """APPID is Witcher 3, which has a curated recipe on Linux hosts; these tests describe hand-made recipes only."""
    monkeypatch.setattr(recipe_catalog, "bundled", lambda: recipe_catalog.Catalog(1, 0, {}, {}, {}))


class FakeHelix:
    """HelixSR's bridge as the service sees it: install/remove write what the real one writes."""

    def __init__(self, ready=True):
        self._ready = ready
        self.calls = []
        self.release = Path("HelixSR-3.2.0")

    def ready(self):
        return self._ready

    def digest(self):
        return None

    def install(self, game):
        self.calls.append(("install",))
        exe = game / "bin/x64_dx12"
        _write(exe / "amd_fidelityfx_upscaler_dx12.original.dll", b"game fsr")
        _write(exe / "helixsr-install.json", "{}")
        return {"installed": "fsr", "exe_folder": str(exe), "log_path": str(exe / "helixsr.log")}

    def remove(self, game):
        self.calls.append(("remove",))
        exe = game / "bin/x64_dx12"
        for name in ("helixsr-install.json", "amd_fidelityfx_upscaler_dx12.original.dll"):
            (exe / name).unlink(missing_ok=True)
        return {"installed": None}


@pytest.fixture
def helix_catalog(monkeypatch, fake_catalog):
    zipped = Asset(catalog.HELIXSR_ARCHIVE, "HelixSR.zip", "0" * 64, 10, ("http://invalid",), )
    monkeypatch.setitem(catalog.ASSETS, zipped.id, zipped)
    for build in (
        Build("hlx-fsr4", "helixsr", "FSR 4", ("rdna2",), 3, 2, archive=zipped.id, engine="helixsr", way="fsr"),
    ):
        monkeypatch.setitem(catalog.BUILDS, build.id, build)
    return fake_catalog


def payload(root, content):
    for name in lsfg.LAYER_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content + name.encode())
    return root


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


SCALER_MANIFEST = '# HelixSR Scaler, installed by HelixSR Desktop\n# version=\n# layout=ngx\nname=dxgi.dll\nLicenses/DirectX_LICENSE.txt\nLicenses/FidelityFX_v2_LICENSE.md\nLicenses/OptiPatcher_LICENSE.txt\nLicenses/OptiScaler_LICENSE.txt\nLicenses/XeSS_LICENSE.txt\ndxgi.dll\nOptiScaler.ini\nOptiScaler/D3D12_OptiScaler/D3D12Core.dll\nOptiScaler/amd_fidelityfx_framegeneration_dx12.dll\nOptiScaler/amd_fidelityfx_loader_dx12.dll\nOptiScaler/amd_fidelityfx_upscaler_dx12.amd.dll\nOptiScaler/amd_fidelityfx_upscaler_dx12.dll\nOptiScaler/amd_fidelityfx_vk.dll\nOptiScaler/libxell.dll\nOptiScaler/libxess.dll\nOptiScaler/libxess_dx11.dll\nOptiScaler/libxess_fg.dll\nOptiScaler/plugins/OptiPatcher.asi\nHelixSR/helixsr.dll\n'


def scaler_install(root):
    write(root, 'HelixSR-Scaler.files', SCALER_MANIFEST)
    write(root, 'OptiScaler.ini', '; HelixSR Scaler\n[HelixSR]\nInt8=auto\n[Sharpness]\nOverrideSharpness=auto\nSharpness=auto\n[CAS]\nEnabled=auto\n')
    write(root, 'dxgi.dll', 'MZproxy')
    write(root, 'HelixSR/helixsr.dll', 'MZprovider')
