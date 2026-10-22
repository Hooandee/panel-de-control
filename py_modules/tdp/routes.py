"""The TDP route ladder each machine declares. The factory walks it in order and takes the
first route that is present and ready; nothing in the factory depends on the machine key."""
from dataclasses import dataclass


@dataclass(frozen=True)
class TdpRoutes:
    # Firmware and platform interfaces, probed in order before any generic AMD path.
    firmware: tuple[str, ...] = ("asus", "lenovo", "msi")
    # The Anatase kernel adds its own interfaces (amd-dptc, msi-claw-a8); None means
    # amd-dptc first, then the same firmware chain.
    anatase_firmware: tuple[str, ...] | None = None
    # How ryzenadj confirms a write: "normal" reads STAPM when it can, "strict" requires
    # all three limits before and after every write (restoring them on failure), None
    # leaves ryzenadj out of the ladder.
    ryzenadj: str | None = "normal"
    # ryzenadj that cannot read before its first write yields to the next rung instead
    # of opening its circuit.
    ryzenadj_yields_when_unreadable: bool = False
    # Some firmware never lets ryzenadj read back: write without confirmation instead.
    ryzenadj_readback_fallback: bool = False
    # Write-only rungs below ryzenadj, each verified by measured package power.
    write_only: tuple[str, ...] = ("alib",)
    # Intel CPUs never reach the AMD rungs.
    intel: tuple[str, ...] = ("msi", "intel")
    # Only drive the CPU when its firmware PL1 ceiling is readable (desktops).
    requires_firmware_ceiling: bool = False
    # Write PL1 to both RAPL surfaces (MMIO and MSR) and trust the lower readback.
    rapl_sync_surfaces: bool = False
    # asus-armoury reports trustworthy live bounds on this model.
    asus_trust_live_bounds: bool = False

    def chain(self, *, arch: str, vendor: str, os_id: str | None) -> tuple[str, ...]:
        if arch == "arm":
            return ("arm_levels",)
        if vendor == "intel":
            return self.intel
        firmware = self.firmware
        if os_id == "anatase":
            firmware = (
                self.anatase_firmware
                if self.anatase_firmware is not None
                else ("dptc", *self.firmware)
            )
        ryzenadj = ("ryzenadj",) if self.ryzenadj is not None else ()
        return (*firmware, *ryzenadj, *self.write_only)


DEFAULT = TdpRoutes()

# Strict ryzenadj that yields, then an unconfirmed but measured ryzenadj write (it held
# the limit on hardware), then ALIB.
STRICT_RYZENADJ = TdpRoutes(
    ryzenadj="strict",
    ryzenadj_yields_when_unreadable=True,
    write_only=("ryzenadj_unverified", "alib"),
)

ASUS = TdpRoutes(
    firmware=("asus", "asus_nb_wmi", "lenovo", "msi"),
    anatase_firmware=("asus", "asus_nb_wmi"),
)
LENOVO = TdpRoutes(
    firmware=("lenovo", "asus", "msi"),
    anatase_firmware=("lenovo", "asus", "msi"),
)
ROG_FLOW_Z13 = TdpRoutes(
    ryzenadj="strict",
    ryzenadj_yields_when_unreadable=True,
    write_only=("ryzenadj_unverified", "alib"),
    asus_trust_live_bounds=True,
)
ONEXPLAYER_3 = TdpRoutes(rapl_sync_surfaces=True)
ZOTAC = TdpRoutes(ryzenadj="strict", ryzenadj_readback_fallback=True, write_only=())
GPD_WIN_MINI = TdpRoutes(ryzenadj="strict", write_only=())
# ALIB cannot read back; on Strix Halo it let a 30 W limit draw 70 W.
ONEXPLAYER_APEX = TdpRoutes(
    firmware=(),
    anatase_firmware=("dptc",),
    ryzenadj_yields_when_unreadable=True,
    write_only=("ryzenadj_unverified", "alib"),
)
MSI_CLAW_A8 = TdpRoutes(firmware=(), anatase_firmware=("msi_a8",), write_only=())
# Fremont's AMD Custom CPU 1772 is not a Ryzen Mobile model: ryzenadj reports
# "unsupported model 124". Keep firmware paths discoverable, never generic AMD writes.
STEAM_MACHINE = TdpRoutes(
    firmware=("asus", "lenovo", "msi"),
    anatase_firmware=("asus", "lenovo", "msi"),
    ryzenadj=None,
    write_only=(),
)
# steamdeck-hwmon is exclusive: steamos-manager also writes the same caps.
STEAM_DECK = TdpRoutes(firmware=("deck",), anatase_firmware=("deck",), ryzenadj=None, write_only=())
# AMD desktop CPUs have no verifiable power path (ryzenadj reports success without
# readback, AMD RAPL can confirm a write it ignores).
DESKTOP = TdpRoutes(
    firmware=(),
    anatase_firmware=(),
    ryzenadj=None,
    write_only=(),
    intel=("intel",),
    requires_firmware_ceiling=True,
    rapl_sync_surfaces=True,
)
