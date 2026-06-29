import glob
import os

_HWMON = "sys/class/hwmon"

# Generic ACPI fan chip that usually mirrors a vendor chip with nicer labels.
_GENERIC_FAN_CHIP = "acpi_fan"

# Friendly name + priority for well-known temperature sources (AMD handhelds +
# Intel). Lower priority shows first. Unknown chips fall back to priority 2 with
# their own label; known-noisy chips are demoted to last.
_TEMP_RULES = {
    "k10temp": ("CPU", 0),
    "coretemp": ("CPU", 0),
    "amdgpu": ("GPU", 1),
}
_TEMP_DEMOTE = ("nvme", "mt7921", "iwlwifi", "ucsi", "BAT", "AC")


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> int | None:
    v = _read(path)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def curate_fans(fans: list[dict]) -> list[dict]:
    """Drop the generic acpi_fan chip when a vendor chip also reports fans."""
    has_vendor = any(f["chip"] != _GENERIC_FAN_CHIP for f in fans)
    if has_vendor:
        return [f for f in fans if f["chip"] != _GENERIC_FAN_CHIP]
    return list(fans)


def curate_temps(temps: list[dict]) -> list[dict]:
    """Surface CPU/GPU first with friendly labels; demote known-noisy sensors."""

    def rank(t: dict) -> tuple[str, int]:
        chip = t["chip"]
        if chip in _TEMP_RULES:
            return _TEMP_RULES[chip]
        if any(chip.startswith(d) for d in _TEMP_DEMOTE):
            return t["label"], 3
        return t["label"], 2

    decorated = []
    for i, t in enumerate(temps):
        label, prio = rank(t)
        decorated.append((prio, i, {"label": label, "celsius": t["celsius"]}))
    decorated.sort(key=lambda x: (x[0], x[1]))
    return [d[2] for d in decorated]


class FanReader:
    """Reads fan speeds + temperatures from sysfs hwmon. Read-only. Never raises."""

    def __init__(self, root: str = "/") -> None:
        self._root = root

    def _chips(self) -> list[str]:
        return sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*")))

    def read(self) -> dict:
        raw_fans: list[dict] = []
        raw_temps: list[dict] = []

        for d in self._chips():
            name = _read(os.path.join(d, "name")) or ""

            for inp in sorted(glob.glob(os.path.join(d, "fan*_input"))):
                rpm = _read_int(inp)
                if rpm is None:
                    continue
                n = os.path.basename(inp)[len("fan"):-len("_input")]
                label = _read(os.path.join(d, f"fan{n}_label")) or f"{name or 'fan'} {n}".strip()
                pwm = _read_int(os.path.join(d, f"pwm{n}"))
                percent = round(pwm / 255 * 100) if pwm is not None else None
                raw_fans.append({"chip": name, "label": label, "rpm": rpm, "percent": percent})

            for inp in sorted(glob.glob(os.path.join(d, "temp*_input"))):
                milli = _read_int(inp)
                if milli is None:
                    continue
                n = os.path.basename(inp)[len("temp"):-len("_input")]
                label = _read(os.path.join(d, f"temp{n}_label")) or f"{name or 'temp'} {n}".strip()
                raw_temps.append({"chip": name, "label": label, "celsius": round(milli / 1000, 1)})

        fans = curate_fans(raw_fans)
        temps = curate_temps(raw_temps)
        return {
            "supported": len(fans) > 0,
            "fans": [{"label": f["label"], "rpm": f["rpm"], "percent": f["percent"]} for f in fans],
            "temps": temps,
        }
