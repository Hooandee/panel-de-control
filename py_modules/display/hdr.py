"""HDR output on/off via gamescope's `hdr_enabled` convar. The `supported` gate lives in
main (device.hdr AND the color backend's gamescope probe). On/off is all we expose:
HDR content scans out directly, so its color can't be tuned from here. Never raises."""


class HdrBackend:
    """Toggles gamescope HDR. `runner(args) -> (rc, stdout)` is the shared gamescopectl
    runner (injected for testing)."""

    def __init__(self, runner):
        self._run = runner

    def set_enabled(self, on):
        rc, _ = self._run(["hdr_enabled", "1" if on else "0"])
        return rc == 0
