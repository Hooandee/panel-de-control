"""GPU family cases shared with the Windows port (windows/tests/PanelDeControl.Core.Tests/Upscalers).

Each case is the CPU vendor, the chip's name and the display GPUs' PCI ids in card order; `generation` is what
`device_registry.gpu_facts` answers. The rules live in shared/upscalers/gpus.json, which Linux and Windows both read.
Rewrite after a rule change with `PYTHONPATH=py_modules python tests/test_gpu_generation_parity.py --write`.
"""

import json
import sys
import tempfile
from pathlib import Path

import device_registry

FIXTURE = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers" / "gpu_generations.json"

CHIPS = [
    ("amd", "AMD Custom APU 0405"), ("amd", "AMD Custom APU 0932"), ("amd", "AMD Van Gogh"), ("amd", "AMD Sephiroth"),
    ("amd", "AMD Ryzen Z1 Extreme"), ("amd", "AMD Ryzen Z1"), ("amd", "AMD Ryzen Z2"), ("amd", "AMD Ryzen Z2 A"),
    ("amd", "AMD Ryzen Z2 Go"), ("amd", "AMD Ryzen Z2 Extreme"), ("amd", "AMD Ryzen AI Z2 Extreme"),
    ("amd", "AMD Ryzen AI 9 HX 370 w/ Radeon 890M"), ("amd", "AMD Ryzen AI Max+ 395"), ("amd", "AMD Ryzen 7 7840U"),
    ("amd", "AMD Ryzen 7 8840U w/ Radeon 780M Graphics"), ("amd", "AMD Ryzen 7 6800U"), ("amd", "AMD Ryzen 5 7535HS"),
    ("amd", "AMD Ryzen 7 7735U"), ("amd", "AMD Ryzen 9 6900HX"), ("amd", "AMD Ryzen 5 6600U"), ("amd", "AMD Ryzen 9 9950X3D"),
    ("intel", "Intel Core Ultra 7 258V"), ("Intel", "Intel(R) Core(TM) i9-14900K"), ("amd", ""), ("", ""),
    ("qualcomm", "Snapdragon 8 Elite"),
]
PCI_SETS = {
    "none": [],
    "van-gogh": [("0x1002", "0x163f")], "phoenix": [("0x1002", "0x15bf")], "strix": [("0x1002", "0x150e")],
    "rx9070": [("0x1002", "0x7550")], "rx7900": [("0x1002", "0x744c")], "new-amd": [("0x1002", "0x9999")],
    "arc": [("0x8086", "0x7d55")], "nvidia": [("0x10de", "0x2684")],
    "nvidia-then-amd": [("0x10de", "0x2684"), ("0x1002", "0x7550")], "amd-igpu-and-dgpu": [("0x1002", "0x9999"), ("0x1002", "0x7550")],
    "intel-then-amd": [("0x8086", "0x7d55"), ("0x1002", "0x7550")],
}


def _sysfs(root: Path, cards) -> None:
    for index, (vendor, device) in enumerate(cards):
        folder = root / "sys/class/drm" / f"card{index}" / "device"
        folder.mkdir(parents=True)
        (folder / "vendor").write_text(vendor + "\n")
        (folder / "device").write_text(device + "\n")


def snapshot() -> dict:
    cases = []
    for (vendor, chip), (name, cards) in [(chip, pci) for chip in CHIPS for pci in PCI_SETS.items()]:
        with tempfile.TemporaryDirectory() as folder:
            _sysfs(Path(folder), cards)
            facts = device_registry.gpu_facts(vendor, chip, folder)
        cases.append({"vendor": vendor, "chip": chip, "pci": name, "generation": facts["generation"], "source": facts["source"]})
    return {"schema_version": 1, "pci_sets": {key: [list(card) for card in cards] for key, cards in PCI_SETS.items()}, "cases": cases}


def test_fixture_matches_the_linux_backend():
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == snapshot()


if __name__ == "__main__" and "--write" in sys.argv:
    FIXTURE.write_text(json.dumps(snapshot(), indent=1) + "\n", encoding="utf-8")
