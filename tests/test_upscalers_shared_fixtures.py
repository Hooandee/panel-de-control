"""Game detection cases shared with the Windows port (windows/tests/PanelDeControl.Core.Tests/Upscalers).

Both sides read the same images, folder trees and Steam files and must reach the same answers. The PE images are
built from their spec here; `python tests/test_upscalers_shared_fixtures.py --write` rebuilds them and records what
these functions answer (run it with `PYTHONPATH=py_modules`), which the Windows port must then match.
"""

import base64
import json
import os
import struct
import sys
from pathlib import Path

import pytest

from steam_cleaner import vdf
from upscalers import games, pe

FIXTURE_DIR = Path(__file__).parents[1] / "shared" / "fixtures" / "upscalers"
DOCUMENTS = ("pe_images.json", "game_folders.json", "steam_library.json")

_SECTION_ALIGN = 0x1000
_FILE_ALIGN = 0x200


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _import_section(rva: int, imports: list[str], delay_imports: list[str], dangling: bool) -> tuple[bytes, tuple, tuple]:
    descriptors = len(imports) + (1 if dangling else 0)
    import_size = 20 * (descriptors + 1) if descriptors else 0
    delay_size = 32 * (len(delay_imports) + 1) if delay_imports else 0
    strings_at = import_size + delay_size
    strings = bytearray()
    offsets = []
    for name in imports + delay_imports:
        offsets.append(strings_at + len(strings))
        strings += name.encode("latin-1") + b"\0"
    data = bytearray(strings_at) + strings
    for index in range(len(imports)):
        struct.pack_into("<I", data, index * 20 + 12, rva + offsets[index])
    if dangling:
        struct.pack_into("<I", data, len(imports) * 20 + 12, 0x7FFF0000)
    for index in range(len(delay_imports)):
        struct.pack_into("<I", data, import_size + index * 32 + 4, rva + offsets[len(imports) + index])
    return bytes(data), ((rva, import_size) if import_size else (0, 0)), ((rva + import_size, delay_size) if delay_size else (0, 0))


def _version_string(key: str, value: str, value_words: int | None) -> bytes:
    key_bytes = key.encode("utf-16-le") + b"\0\0"
    value_bytes = value.encode("utf-16-le") + b"\0\0"
    head = 6 + len(key_bytes)
    padding = (-head) % 4
    words = len(value_bytes) // 2 if value_words is None else value_words
    length = head + padding + len(value_bytes)
    block = struct.pack("<HHH", length, words, 1) + key_bytes + b"\0" * padding + value_bytes
    return block + b"\0" * ((-len(block)) % 4)


def build_pe(spec: dict) -> bytes:
    """A small, valid-enough PE image: import and delay-import tables, a version-string blob in .rsrc and raw tails."""
    plus = spec.get("pe32plus", True)
    optional_size = 240 if plus else 224
    sections = []
    imports_data, import_dir, delay_dir = _import_section(
        _SECTION_ALIGN, spec.get("imports", []), spec.get("delay_imports", []), spec.get("dangling_import", False))
    if imports_data:
        sections.append((b".idata", imports_data))
    if "version" in spec:
        blob = b"".join(_version_string(item["key"], item["value"], item.get("value_words")) for item in spec["version"])
        sections.append((b".rsrc", b"VS_VERSION_INFO\0" + blob))
    headers = _align(0x40 + 4 + 20 + optional_size + 40 * len(sections), _FILE_ALIGN)
    image = bytearray(headers)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0" if not spec.get("bad_signature") else b"NE\0\0"
    struct.pack_into("<HHIIIHH", image, 0x44, 0x8664 if plus else 0x14C, len(sections), 0, 0, 0, optional_size, 0x22)
    optional = 0x58
    struct.pack_into("<H", image, optional, 0x20B if plus else 0x10B)
    directories = optional + (112 if plus else 96)
    struct.pack_into("<II", image, directories + 8, *import_dir)
    struct.pack_into("<II", image, directories + 13 * 8, *delay_dir)
    table = optional + optional_size
    rva, raw = _SECTION_ALIGN, headers
    for index, (name, data) in enumerate(sections):
        raw_size = _align(len(data), _FILE_ALIGN)
        struct.pack_into("<8sIIII", image, table + index * 40, name, len(data), rva, raw_size, raw)
        image += data + b"\0" * (raw_size - len(data))
        rva += _align(len(data), _SECTION_ALIGN)
        raw += raw_size
    for tail in spec.get("tails", []):
        image += tail.encode("ascii") + b"\0"
    if spec.get("not_mz"):
        image[0:2] = b"ZM"
    if "truncate" in spec:
        del image[spec["truncate"]:]
    return bytes(image)


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _image_bytes(document: dict, image_id: str) -> bytes:
    return base64.b64decode(document["images"][image_id]["base64"])


def _materialize(root: Path, tree: dict, images: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for directory in tree.get("dirs", []):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for relative, entry in tree.get("files", {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if "image" in entry:
            data = base64.b64decode(images[entry["image"]]["base64"])
        elif "text" in entry:
            data = entry["text"].replace("{root}", str(root)).encode("utf-8")
        elif "base64" in entry:
            data = base64.b64decode(entry["base64"])
        else:
            data = b"x"
        with path.open("wb") as handle:
            handle.write(data)
            if entry.get("size", 0) > len(data):
                handle.truncate(entry["size"])
    for relative, target in tree.get("symlinks", {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(root / target, path)


def _pe_case(document: dict, case: dict, tmp_path: Path):
    path = tmp_path / f"{case['id']}.bin"
    path.write_bytes(_image_bytes(document, case["input"]["image"]))
    operation = case["operation"]
    if operation == "imported_dlls":
        try:
            return {"dlls": sorted(pe.imported_dlls(str(path)))}
        except (OSError, ValueError, struct.error):
            return {"error": True}
    if operation == "graphics_apis":
        return pe.graphics_apis(str(path))
    if operation == "version_strings":
        return pe.version_strings(str(path))
    if operation == "embedded_upscalers":
        return sorted(games.embedded_upscalers(path))
    if operation == "streamline_major":
        return games.streamline_major(path)
    raise AssertionError(f"unsupported operation {operation}")


def _relative(root: Path, value: str | None) -> str | None:
    return None if value is None else Path(os.path.relpath(value, root)).as_posix()


def _games_case(document: dict, case: dict, tmp_path: Path):
    root = tmp_path / case["id"] / "game"
    _materialize(root, document["trees"][case["input"]["tree"]], _load("pe_images.json")["images"])
    operation = case["operation"]
    if operation == "analyze":
        result = games.analyze(root, case["input"].get("chosen_exe"), case["input"].get("recipe_exe"))
        result["target"] = _relative(root, result["target"])
        return result
    if operation == "shipped_upscalers":
        return games.shipped_upscalers(root)
    if operation == "graphics_apis":
        return games._graphics_apis(root / case["input"]["exe"])
    raise AssertionError(f"unsupported operation {operation}")


def _steam_case(case: dict, tmp_path: Path):
    operation = case["operation"]
    inputs = case["input"]
    if operation == "update_state":
        return games.update_state(inputs["flags"])
    if operation == "parse_vdf":
        path = tmp_path / f"{case['id']}.vdf"
        path.write_bytes(base64.b64decode(inputs["base64"]) if "base64" in inputs else inputs["text"].encode("utf-8"))
        try:
            return {"value": vdf.read_text(path)}
        except UnicodeDecodeError:
            return {"error": "decode"}
        except ValueError as error:
            return {"error": str(error)}
    root = (tmp_path / case["id"]).resolve()
    home = root / "home"
    _materialize(root, {"files": inputs["files"], "dirs": inputs.get("dirs", [])}, {})
    if operation == "library_paths":
        return [Path(os.path.relpath(path, root)).as_posix() for path in games.library_paths(str(home))]
    if operation == "find_installed":
        installed = games.find_installed(str(home), inputs["appid"])
        if installed is None:
            return None
        return {
            "appid": installed.appid,
            "name": installed.name,
            "root": Path(os.path.relpath(installed.root, root)).as_posix(),
            "state_flags": installed.state_flags,
            "build_id": installed.build_id,
            "update_state": games.update_state(installed.state_flags),
        }
    raise AssertionError(f"unsupported operation {operation}")


def _run(name: str, document: dict, case: dict, tmp_path: Path):
    if name == "pe_images.json":
        return _pe_case(document, case, tmp_path)
    if name == "game_folders.json":
        return _games_case(document, case, tmp_path)
    return _steam_case(case, tmp_path)


def _cases():
    for name in DOCUMENTS:
        for case in _load(name)["cases"]:
            yield pytest.param(name, case, id=f"{name.removesuffix('.json')}:{case['id']}")


def test_shared_upscaler_fixtures_are_versioned():
    for name in DOCUMENTS:
        document = _load(name)
        assert document["schema_version"] == 1
        assert document["cases"]
        assert len({case["id"] for case in document["cases"]}) == len(document["cases"])


def test_pe_images_are_built_from_their_spec():
    for image_id, image in _load("pe_images.json")["images"].items():
        assert base64.b64decode(image["base64"]) == build_pe(image["spec"]), image_id


@pytest.mark.parametrize(("name", "case"), list(_cases()))
def test_shared_upscaler_fixture(name, case, tmp_path):
    assert _run(name, _load(name), case, tmp_path) == case["expected"]


def _write_fixtures(tmp_path: Path) -> None:
    images = _load("pe_images.json")
    for image in images["images"].values():
        image["base64"] = base64.b64encode(build_pe(image["spec"])).decode("ascii")
    (FIXTURE_DIR / "pe_images.json").write_text(json.dumps(images, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name in DOCUMENTS:
        document = _load(name)
        (tmp_path / name).mkdir(parents=True)
        for case in document["cases"]:
            case["expected"] = json.loads(json.dumps(_run(name, document, case, tmp_path / name)))
        (FIXTURE_DIR / name).write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__" and "--write" in sys.argv:
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        _write_fixtures(Path(scratch).resolve())
