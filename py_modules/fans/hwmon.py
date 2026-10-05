import glob
import os
import time

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

# ARM SoCs expose each thermal zone as its own hwmon chip named "<zone>_thermal"
# (Qualcomm cpu7_middle_thermal / gpuss_0_thermal, Rockchip bigcore0_thermal).
_SOC_GPU_ZONES = ("gpu",)
_SOC_CPU_ZONES = ("cpu", "core", "soc")


def _soc_zone_rule(chip: str) -> tuple[str, int] | None:
    if not chip.endswith("_thermal"):
        return None
    zone = chip[: -len("_thermal")]
    if any(key in zone for key in _SOC_GPU_ZONES):
        return "GPU", 1
    if any(key in zone for key in _SOC_CPU_ZONES):
        return "CPU", 0
    return None


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


_MAX_FANS = 2  # no target device has >2 physical fans; extra hwmon channels are phantom

# 0xFFFF is the all-ones sentinel the Legion Go S lenovo_wmi_other driver returns
# mid-ramp; it is not a real speed (handheld fans top out ~8000 RPM), so we report
# it as unknown rather than a fake 65535.
_INVALID_RPM = 0xFFFF
# Which chips, inputs and labels exist only changes on hotplug; listing and re-reading them on
# every poll (the software fan loop polls each second) cost more than the readings themselves.
_LAYOUT_TTL_S = 60.0

# The lenovo_wmi_other driver exposes a fixed two-channel layout regardless of how
# many fans are populated (it logs "all fans exposed. Use with caution"). The Legion
# Go original (83E1) and Go S have ONE physical fan, so the second channel is a
# phantom. The Legion Go 2's two real fans read RPM over the EC, not this hwmon, so
# they never reach here — collapse this chip to a single (spinning) fan.
_SINGLE_FAN_CHIP = "lenovo_wmi_other"


def _collapse_single_fan_chip(fans: list[dict]) -> list[dict]:
    """Keep only one channel for a chip known to over-expose phantom fans, preferring
    a spinning one (fall back to the first when all read 0, e.g. silent mode)."""
    channels = [i for i, f in enumerate(fans) if f["chip"] == _SINGLE_FAN_CHIP]
    if len(channels) <= 1:
        return fans
    spinning = [i for i in channels if (fans[i].get("rpm") or 0) > 0]
    keep = (spinning or channels)[0]
    drop = set(channels) - {keep}
    return [f for i, f in enumerate(fans) if i not in drop]


def curate_fans(fans: list[dict]) -> list[dict]:
    """Drop the generic acpi_fan chip when a vendor chip also reports fans, collapse
    the lenovo_wmi_other phantom channel, then cap at 2 — the MSI Claw chip exposes 4
    channels but only 2 fans spin, so prefer the spinning ones and drop the phantom
    0-RPM channels (fall back to the first 2 when all read 0, e.g. silent mode)."""
    has_vendor = any(f["chip"] != _GENERIC_FAN_CHIP for f in fans)
    fans = [f for f in fans if f["chip"] != _GENERIC_FAN_CHIP] if has_vendor else list(fans)
    fans = _collapse_single_fan_chip(fans)
    if len(fans) > _MAX_FANS:
        spinning = [f for f in fans if (f.get("rpm") or 0) > 0]
        fans = (spinning or fans)[:_MAX_FANS]
    return fans


def _rank_temp(t: dict, desktop: bool = False, device_key: str | None = None) -> tuple[str, int]:
    chip = t["chip"]
    raw_label = str(t.get("label", "")).lower()
    if desktop:
        if device_key == "steam_machine" and chip == "acpitz":
            return "CPU", 0
        if chip in ("k10temp", "coretemp"):
            return "CPU", 0
        if chip in ("steamdeck_hwmon", "jupiter") and "cpu" in raw_label:
            return "CPU", 0
        if chip == "amdgpu":
            if "junction" in raw_label:
                return "GPU junction", 1
            if "mem" in raw_label:
                return "VRAM", 1
            return "GPU", 1
    if chip in _TEMP_RULES:
        return _TEMP_RULES[chip]
    soc = _soc_zone_rule(chip)
    if soc is not None:
        return soc
    if any(chip.startswith(d) for d in _TEMP_DEMOTE):
        return t["label"], 3
    return t["label"], 2


def curate_temps(temps: list[dict], desktop: bool = False, device_key: str | None = None) -> list[dict]:
    """Show only the meaningful CPU/GPU sensors with friendly labels, dropping the
    generic noise (acpitz, wifi, nvme, battery…) that clutters the monitor. If a
    device exposes no recognized CPU/GPU sensor, fall back to showing everything
    (ranked) so the list is never silently empty."""

    decorated = []
    for i, t in enumerate(temps):
        label, prio = _rank_temp(t, desktop, device_key)
        decorated.append((prio, i, {"label": label, "celsius": t["celsius"]}))
    decorated.sort(key=lambda x: (x[0], x[1]))
    # Keep only recognized CPU/GPU (priority 0/1); fall back to all when none match.
    known = [d for d in decorated if d[0] <= 1]
    chosen = known if known else decorated

    # Collapse rows sharing a friendly label (e.g. Intel coretemp's Package + every
    # core all map to "CPU") into one, keeping the hottest — no wall of duplicates.
    # (dict preserves first-seen order, so no separate order list is needed.)
    collapsed: dict[str, dict] = {}
    for _prio, _i, row in chosen:
        label = row["label"]
        if label not in collapsed or row["celsius"] > collapsed[label]["celsius"]:
            collapsed[label] = row
    result = list(collapsed.values())

    # A GPU sensor with no CPU sensor IS the whole APU (e.g. Steam Deck exposes only
    # amdgpu, no k10temp) — label it "APU" rather than implying discrete graphics.
    labels = {r["label"] for r in result}
    if not desktop and "GPU" in labels and "CPU" not in labels:
        for r in result:
            if r["label"] == "GPU":
                r["label"] = "APU"
    return result


def extract_cpu_gpu_temps(fan_state: dict) -> tuple:
    """(cpu_celsius, gpu_celsius) from a FanReader.read() result. Prefer labels
    'CPU'/'GPU', fall back to position 0/1. None when absent."""
    temps = fan_state.get("temps") or []
    by_label = {t.get("label"): t.get("celsius") for t in temps}
    cpu = by_label.get("CPU", temps[0]["celsius"] if temps else None)
    gpu = by_label.get("GPU", temps[1]["celsius"] if len(temps) >= 2 else None)
    return cpu, gpu


class FanReader:
    """Reads fan speeds + temperatures from sysfs hwmon. Read-only. Never raises."""

    def __init__(self, root: str = "/", desktop: bool = False, device_key: str | None = None) -> None:
        self._root = root
        self._desktop = bool(desktop)
        self._device_key = device_key
        self._layout_cache: list[tuple] | None = None
        self._layout_until = 0.0
        self._layout_names: tuple[tuple[str, str], ...] = ()
        self._driving: list[tuple[str, str]] | None = None

    def set_desktop(self, enabled: bool) -> None:
        self._desktop = bool(enabled)
        self._driving = None

    def _chips(self) -> list[str]:
        return sorted(glob.glob(os.path.join(self._root, _HWMON, "hwmon*")))

    def _scan_layout(self) -> list[tuple]:
        layout = []
        for d in self._chips():
            name = _read(os.path.join(d, "name")) or ""
            fans = []
            for inp in sorted(glob.glob(os.path.join(d, "fan*_input"))):
                n = os.path.basename(inp)[len("fan"):-len("_input")]
                # Vendor chips like lenovo_wmi_other expose no fanN_label; fall back to
                # a clean generic ("Fan 1"), never the raw chip name. The monitor UI
                # localizes this to "Ventilador N" anyway; this keeps the label honest
                # in exported diagnostics too.
                label = _read(os.path.join(d, f"fan{n}_label")) or f"Fan {n}"
                max_rpm = _read_int(os.path.join(d, f"fan{n}_max"))
                if (max_rpm is None and self._device_key == "steam_machine"
                        and name in ("steamdeck_hwmon", "jupiter")):
                    max_rpm = 1800
                fans.append((inp, label, os.path.join(d, f"pwm{n}"), max_rpm))
            temps = []
            for inp in sorted(glob.glob(os.path.join(d, "temp*_input"))):
                n = os.path.basename(inp)[len("temp"):-len("_input")]
                label = _read(os.path.join(d, f"temp{n}_label")) or f"{name or 'temp'} {n}".strip()
                temps.append((inp, label))
            layout.append((name, fans, temps))
        return layout

    def driving_temps(self) -> tuple[float | None, float | None] | None:
        """(cpu, gpu) reading only the inputs ranked CPU/GPU, for loops that poll every second.
        None when this machine has no recognized CPU/GPU sensor (callers then do a full read)."""
        layout = self._layout()
        if self._driving is None:
            self._driving = [
                (label, inp)
                for name, _fans, temps in layout
                for inp, raw_label in temps
                if (label := _rank_temp({"chip": name, "label": raw_label}, self._desktop, self._device_key)[0])
                in ("CPU", "GPU")
            ]
        if not self._driving:
            return None
        hottest: dict[str, float] = {}
        for label, inp in self._driving:
            milli = _read_int(inp)
            if milli is not None:
                hottest[label] = max(hottest.get(label, float("-inf")), round(milli / 1000, 1))
            elif not os.path.exists(inp):
                self.invalidate()
        return hottest.get("CPU"), hottest.get("GPU")

    def fan_rpms(self) -> list[int]:
        """Current fan speeds only (no temperatures, no curation)."""
        rpms = []
        for _name, fans, _temps in self._layout():
            for inp, _label, _pwm, _max in fans:
                rpm = _read_int(inp)
                if rpm is not None and rpm != _INVALID_RPM:
                    rpms.append(rpm)
                elif rpm is None and not os.path.exists(inp):
                    self.invalidate()
        return rpms

    def invalidate(self) -> None:
        """Forget the cached chip layout, after a fan driver is loaded or unloaded."""
        self._layout_cache = None

    def _chip_names(self) -> tuple[tuple[str, str], ...]:
        return tuple((d, _read(os.path.join(d, "name")) or "") for d in self._chips())

    def _layout(self) -> list[tuple]:
        # Drivers can register again in another order (resume, reload): a chip list or
        # name that no longer matches means the cached paths point at other sensors.
        now = time.monotonic()
        names = self._chip_names()
        if self._layout_cache is None or now >= self._layout_until or names != self._layout_names:
            self._layout_cache = self._scan_layout()
            self._layout_names = names
            self._layout_until = now + _LAYOUT_TTL_S
            self._driving = None
        return self._layout_cache

    def read(self) -> dict:
        raw_fans: list[dict] = []
        raw_temps: list[dict] = []
        vanished = False

        for name, fans, temps in self._layout():
            for inp, label, pwm_path, max_rpm in fans:
                rpm = _read_int(inp)
                if rpm is None:
                    vanished = vanished or not os.path.exists(inp)
                    continue
                if rpm == _INVALID_RPM:
                    rpm = None  # glitch read: keep the fan, report speed unknown
                pwm = _read_int(pwm_path)
                percent = round(pwm / 255 * 100) if pwm is not None else None
                raw_fans.append({"chip": name, "label": label, "rpm": rpm,
                                 "percent": percent, "max_rpm": max_rpm})

            for inp, label in temps:
                milli = _read_int(inp)
                if milli is None:
                    vanished = vanished or not os.path.exists(inp)
                    continue
                raw_temps.append({"chip": name, "label": label, "celsius": round(milli / 1000, 1)})

        if vanished:
            self.invalidate()

        fans = curate_fans(raw_fans)
        temps = curate_temps(raw_temps, desktop=self._desktop, device_key=self._device_key)
        visible_fans = []
        for fan in fans:
            item = {"label": fan["label"], "rpm": fan["rpm"],
                    "percent": fan["percent"], "max_rpm": fan.get("max_rpm")}
            if self._desktop and self._device_key == "steam_machine":
                if fan["chip"] in ("steamdeck_hwmon", "jupiter"):
                    item["channel"] = "system"
                elif fan["chip"] == "amdgpu":
                    item["channel"] = "gpu"
            visible_fans.append(item)
        state = {
            "supported": len(fans) > 0,
            "fans": visible_fans,
            "temps": temps,
        }
        if self._desktop:
            state["desktop"] = True
            state["device_key"] = self._device_key
        return state
