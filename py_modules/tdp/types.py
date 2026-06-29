from dataclasses import dataclass


@dataclass(frozen=True)
class TdpLimits:
    min_w: int
    default_w: int
    max_w: int       # sustained / battery cap
    max_ac_w: int    # cap when on AC (>= max_w; charger boost)

    def clamp(self, watts: int) -> int:
        return max(self.min_w, min(int(watts), self.max_ac_w))

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
