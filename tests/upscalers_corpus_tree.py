"""Rebuilds a captured game library (tests/fixtures/upscalers_corpus/<machine>.json) as a fake home.

A capture keeps metadata only: relative file tree with sizes, PE imports and version strings, upscaler entry
points compiled into executables, Steam manifests and shortcut rows. Here every executable and library becomes
a small PE image that `upscalers.pe` reads back exactly as the real one, sized like the original (sparse), so
the backend sees the same game without any of its data.
"""

import json
import os
import re
import struct
from pathlib import Path

from upscalers import games

CORPUS = Path(__file__).parent / "fixtures" / "upscalers_corpus"
_TOKEN = re.compile(r"@home|@lib\d+")
_SECTION_ALIGN = 0x1000
_FILE_ALIGN = 0x200


def machines() -> list[str]:
    return sorted(path.stem for path in CORPUS.glob("*.json"))


def load(machine: str) -> dict:
    return json.loads((CORPUS / f"{machine}.json").read_text(encoding="utf-8"))


def _align(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _version_block(strings: dict[str, str]) -> bytes:
    """The String entries of a version resource as `pe.version_strings` walks them: header, key, padding, value."""
    out = bytearray(b"\0" * 16)
    for key, value in strings.items():
        while len(out) % 4:
            out += b"\0"
        header = len(out)
        name = key.encode("utf-16-le") + b"\0\0"
        text = value.encode("utf-16-le") + b"\0\0"
        body = bytearray(name)
        while (6 + len(body)) % 4:
            body += b"\0"
        body += text
        out += struct.pack("<HHH", 6 + len(body), len(value) + 1, 1) + body
        assert len(out) > header
    return bytes(out)


def pe_image(imports: list[str] | None, version: dict[str, str] | None, extra: bytes = b"") -> bytes:
    """A PE32+ image with an import table naming `imports` and a .rsrc holding `version`."""
    if imports is None:
        return b"MZ" + b"\0" * 62 + extra
    imports = list(imports)
    names = bytearray()
    offsets = []
    descriptors = 20 * (len(imports) + 1)
    for name in imports:
        offsets.append(descriptors + len(names))
        names += name.encode("ascii", "replace") + b"\0"
    idata_rva = _SECTION_ALIGN
    idata = bytearray()
    for offset in offsets:
        idata += struct.pack("<IIIII", 0, 0, 0, idata_rva + offset, 0)
    idata += b"\0" * 20 + names
    rsrc = _version_block(version or {})
    rsrc_rva = idata_rva + _align(max(len(idata), 1), _SECTION_ALIGN)
    headers = 0x40 + 4 + 20 + 0xF0 + 40 * 2
    idata_raw = _align(headers, _FILE_ALIGN)
    rsrc_raw = idata_raw + _align(max(len(idata), 1), _FILE_ALIGN)

    image = bytearray(rsrc_raw + _align(max(len(rsrc), 1), _FILE_ALIGN))
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", image, 0x44, 0x8664, 2, 0, 0, 0, 0xF0, 0x22)
    optional = 0x58
    struct.pack_into("<H", image, optional, 0x20B)
    directories = optional + 112
    struct.pack_into("<II", image, directories + 1 * 8, idata_rva, len(idata) if imports else 0)
    table = optional + 0xF0
    for index, (name, rva, data, raw) in enumerate(((b".idata", idata_rva, idata, idata_raw),
                                                    (b".rsrc", rsrc_rva, rsrc, rsrc_raw))):
        header = table + index * 40
        image[header:header + 8] = name.ljust(8, b"\0")
        struct.pack_into("<IIII", image, header + 8, len(data), rva, _align(max(len(data), 1), _FILE_ALIGN), raw)
        image[raw:raw + len(data)] = data
    return bytes(image) + extra


def shortcuts_vdf(entries: list[dict]) -> bytes:
    """Steam's binary shortcuts.vdf with appid, name, exe, start folder and launch options per entry."""
    out = bytearray(b"\x00shortcuts\x00")
    for index, entry in enumerate(entries):
        out += b"\x00" + str(index).encode() + b"\x00"
        out += b"\x02appid\x00" + struct.pack("<I", int(entry["appid"]) & 0xFFFFFFFF)
        for key in ("AppName", "Exe", "StartDir", "LaunchOptions"):
            out += b"\x01" + key.encode() + b"\x00" + str(entry.get(key.lower(), "")).encode() + b"\x00"
        out += b"\x08"
    return bytes(out + b"\x08\x08")


class FakeHome:
    """The capture laid out under `base`: home, extra Steam libraries and absolute system paths."""

    def __init__(self, base: Path, capture: dict):
        self.base = base
        self.capture = capture
        self.home = base / "home"
        self.system = base / "system"
        self.libraries = []
        for index, in_home in enumerate(capture.get("library_in_home") or [True]):
            self.libraries.append(self.home / ".local/share/Steam" if index == 0 and in_home else base / "libraries" / f"lib{index}")

    # ---- paths ------------------------------------------------------------------------------------
    def real(self, text: str) -> str:
        """Tokens back to fake paths, inside any text (launch options, scripts)."""
        return _TOKEN.sub(lambda m: str(self.home) if m.group(0) == "@home" else str(self.libraries[int(m.group(0)[4:])]), text)

    def real_path(self, value: str) -> str:
        """A path field (exe, start folder): tokens mapped, other absolute paths moved under the fake system root."""
        quoted = len(value) > 1 and value.startswith('"') and value.endswith('"')
        raw = value[1:-1] if quoted else value
        if raw.startswith("/"):
            raw = str(self.system) + raw
        raw = self.real(raw)
        return f'"{raw}"' if quoted else raw

    def tokens(self, value):
        """The reverse of `real`, applied through a plan so it reads the same on every machine."""
        if isinstance(value, dict):
            return {self.tokens(k): self.tokens(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.tokens(v) for v in value]
        if not isinstance(value, str):
            return value
        pairs = [(str(lib), f"@lib{i}") for i, lib in enumerate(self.libraries)]
        pairs += [(str(self.home), "@home"), (str(self.system), ""), (str(self.base), "@base")]
        pairs += [(str(Path(real).resolve()), token) for real, token in pairs]
        for real, token in sorted(pairs, key=lambda pair: -len(pair[0])):
            value = value.replace(real, token)
        return value

    # ---- build ------------------------------------------------------------------------------------
    def build(self) -> None:
        for library in self.libraries:
            (library / "steamapps").mkdir(parents=True, exist_ok=True)
        steam = self.libraries[0] if self.libraries[0].is_relative_to(self.home) else self.home / ".local/share/Steam"
        folders = "".join(f' "{i}"\n {{\n  "path" "{lib}"\n }}\n' for i, lib in enumerate(self.libraries))
        (steam / "steamapps").mkdir(parents=True, exist_ok=True)
        (steam / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders"\n{{\n{folders}}}\n')
        shortcuts: dict[int, list[dict]] = {}
        for game in self.capture["games"]:
            if game["kind"] == "steam":
                self._steam(game)
            else:
                shortcuts.setdefault(int(game.get("profile", 0)), []).append(game)
                self._shortcut(game)
        for profile, entries in shortcuts.items():
            config = steam / "userdata" / str(profile + 1) / "config"
            config.mkdir(parents=True, exist_ok=True)
            rows = [{"appid": game["appid"], "appname": game["shortcut"]["appname"],
                     "exe": self.real_path(game["shortcut"]["exe"]), "startdir": self.real_path(game["shortcut"]["startdir"]),
                     "launchoptions": self.real(game["shortcut"]["launchoptions"])} for game in entries]
            (config / "shortcuts.vdf").write_bytes(shortcuts_vdf(rows))

    def _steam(self, game: dict) -> None:
        library = self.libraries[game.get("library", 0)]
        fields = {"appid": game["appid"], "name": game["name"], "installdir": game["installdir"],
                  "StateFlags": game.get("stateflags") or "4", "buildid": game.get("buildid") or ""}
        body = "".join(f' "{key}" "{value}"\n' for key, value in fields.items())
        (library / "steamapps" / f"appmanifest_{game['appid']}.acf").write_text(f'"AppState"\n{{\n{body}}}\n')
        root = library / "steamapps/common" / game["installdir"]
        root.mkdir(parents=True, exist_ok=True)
        self._compat(library, game)
        if game.get("tree"):
            self.tree(root, game["tree"])

    def _compat(self, library: Path, game: dict) -> None:
        compat = game.get("compat")
        if not compat:
            return
        folder = library / "steamapps/compatdata" / game["appid"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "version").write_text(compat["version"] + "\n")
        if compat.get("pfx"):
            (folder / "pfx").mkdir(exist_ok=True)

    def _shortcut(self, game: dict) -> None:
        self._compat(self.libraries[0], game)
        resolved = game.get("resolved")
        if resolved is None:
            return
        start = self.real_path(game["shortcut"]["startdir"]).strip('"')
        if start:
            Path(start).mkdir(parents=True, exist_ok=True)
        root = Path(self.real_path(resolved["root"]))
        root.mkdir(parents=True, exist_ok=True)
        if game.get("tree"):
            self.tree(root, game["tree"])
        for script, text in (game.get("scripts") or {}).items():
            path = Path(self.real_path(script))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.real(text))
            path.chmod(0o755)
        if game.get("unifideck"):
            mapping = self.home / ".local/share/unifideck/games.map"
            mapping.parent.mkdir(parents=True, exist_ok=True)
            with mapping.open("a") as handle:
                handle.writelines(self.real(row) + "\n" for row in game["unifideck"])
        exe = Path(self.real_path(game["shortcut"]["exe"]).strip('"'))
        if game.get("exe_file") and not exe.exists():
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_bytes(b"")
            exe.chmod(0o755)

    def tree(self, root: Path, tree: dict) -> None:
        for relative in tree.get("dirs", []):
            (root / relative).mkdir(parents=True, exist_ok=True)
        for relative, record in tree.get("files", {}).items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            info = record[1] if len(record) > 1 else {}
            if "symlink" in info:
                if not path.exists():
                    os.symlink(self.real(info["symlink"]), path)
                continue
            write_file(path, record[0], info, self.real)


def write_file(path: Path, size: int, info: dict, real=lambda text: text) -> None:
    lower = path.name.lower()
    if "imports" in info or "version" in info:
        extra = b"".join(needle for kind in info.get("embedded", ()) for needle in games.EMBEDDED[kind])
        if info.get("optiscaler"):
            extra += b"OptiScaler"
        data = pe_image(info.get("imports", []), info.get("version"), extra)
    elif info.get("embedded") or info.get("optiscaler") or lower.endswith((".exe", ".dll")):
        data = b"MZ" + b"\0" * 62
        data += b"".join(needle for kind in info.get("embedded", ()) for needle in games.EMBEDDED[kind])
        data += b"OptiScaler" if info.get("optiscaler") else b""
    elif info.get("elf"):
        data = b"\x7fELF"
    elif "text" in info:
        data = real(info["text"]).encode("utf-8")
    elif "markers" in info:
        data = marker_text(info["markers"])
    else:
        data = b""
    path.write_bytes(data)
    if size > len(data):
        with path.open("r+b") as handle:
            handle.truncate(size)
    if info.get("elf") and info.get("exec") or lower.endswith((".sh", ".appimage")):
        path.chmod(0o755)


def marker_text(markers: dict) -> bytes:
    lines = []
    if markers.get("hlx_dlss"):
        lines.append("FFX upscaler: HLX DLSS")
    if markers.get("hlx_fsr4"):
        lines.append("HLX-FSR-4 own runtime active: 1")
    if markers.get("helix_scaler_ini"):
        lines.append("; HelixSR Scaler\n[HelixSR]")
    data = ("\n".join(lines) + "\n").encode() if lines else b""
    if "utf8" not in markers:
        data += b"\xff\xfe"
    if markers.get("oversize"):
        data += b"\n" * (256 * 1024 + 1)
    return data
