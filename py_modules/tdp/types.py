from dataclasses import dataclass


@dataclass(frozen=True)
class TdpLimits:
    min_w: int
    default_w: int
    max_w: int       # sustained / battery cap
    max_ac_w: int    # cap when on AC (>= max_w; charger boost)

    def clamp(self, watts: int, on_ac: bool = True) -> int:
        hi = self.max_ac_w if on_ac else self.max_w
        return max(self.min_w, min(int(watts), hi))

    def unlocked(self, unlock: bool) -> "TdpLimits":
        """When the user opts in (Ajustes toggle), raise the on-battery ceiling to
        the firmware/charger max — the hardware allows it, with the battery-drain
        consequences. No-op when unlock is False."""
        if not unlock or self.max_w >= self.max_ac_w:
            return self
        return TdpLimits(self.min_w, self.default_w, self.max_ac_w, self.max_ac_w)

    def with_cooler(self, ceiling: int | None) -> "TdpLimits":
        """Raise both ceilings to a device's cooler-attached max when the user
        confirms the external cooler is present (only exposed on the GPD Win 5,
        whose big cooler makes the higher rail thermally viable). No-op when the
        device has none or it wouldn't raise."""
        if not ceiling or ceiling <= self.max_ac_w:
            return self
        return TdpLimits(self.min_w, self.default_w, ceiling, ceiling)

    @classmethod
    def from_profile(cls, device) -> "TdpLimits":
        return cls(
            min_w=device.tdp_min,
            default_w=device.tdp_default,
            max_w=device.tdp_max,
            max_ac_w=device.tdp_max_charger,
        )


@dataclass(frozen=True)
class TdpResult:
    requested_w: int
    applied_w: int | None   # read back after writing (None if unreadable)
    ok: bool                # did the write stick / succeed
    detail: str             # detail surfaced to UI/log on failure
