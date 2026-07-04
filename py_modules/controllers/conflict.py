"""Detect a power-management conflict with Handheld Daemon.

HHD's TDP plugin (master toggle `hhd.settings.tdp_enable`, which also owns its
fan curve) writes the same firmware power rails Panel de Control does; when both
are active they fight (last-writer-wins → jitter). We only WARN — never touch
HHD's settings — and let the user disable one.
"""


def hhd_managing_power(hhd_state) -> bool:
    """True when HHD's TDP plugin is enabled (it also drives fans)."""
    if not hhd_state:
        return False
    return bool(hhd_state.get("hhd", {}).get("settings", {}).get("tdp_enable"))


def assess(hhd_state, our_tdp_supported: bool) -> dict:
    """A real conflict needs BOTH sides able to drive power on this device."""
    managing = hhd_managing_power(hhd_state)
    return {
        "hhd_managing_power": managing,
        "conflict": bool(managing and our_tdp_supported),
    }
