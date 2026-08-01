"""HDR output on/off via gamescope's `hdr_enabled` convar. The `supported` gate lives in
main (device.hdr AND the color backend's gamescope probe). On/off is all we expose:
HDR content scans out directly, so its color can't be tuned from here. Never raises."""


class HdrBackend:
    """Toggles gamescope HDR. `runner(args) -> (rc, stdout)` is the shared gamescopectl
    runner (injected for testing)."""

    def __init__(self, runner):
        self._run = runner
        self._last_operation = None

    def set_enabled(self, on):
        rc, output = self._run(["hdr_enabled", "1" if on else "0"])
        response = (output or "").strip()[:200]
        self._last_operation = {
            "enabled": bool(on),
            "ok": rc == 0,
            "rc": rc,
            **({"response": response} if response else {}),
        }
        return rc == 0

    def diagnostics(self):
        return (
            dict(self._last_operation)
            if self._last_operation is not None
            else None
        )
