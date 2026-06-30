import { ScalarControl } from "./types";

// SteamClient brightness adapter. Isolated here so the rest of the UI is stable
// if a device needs a different call. Never throws — degrades to "unavailable"
// only when the API is genuinely absent (the register METHOD doesn't exist), not
// merely when registration returns no unsubscribe handle.
export const displayBrightness: ScalarControl = {
  subscribe(cb) {
    try {
      const display = SteamClient?.System?.Display;
      if (!display || typeof display.RegisterForBrightnessChanges !== "function") return null;
      const reg = display.RegisterForBrightnessChanges((data: { flBrightness?: number }) => {
        if (typeof data?.flBrightness === "number") cb(data.flBrightness);
      });
      // Supported even if registration returns no handle → unsubscribe no-ops.
      return () => {
        try {
          reg?.unregister?.();
        } catch {
          /* ignore */
        }
      };
    } catch {
      return null;
    }
  },
  set(fraction) {
    try {
      SteamClient?.System?.Display?.SetBrightness?.(fraction);
    } catch {
      /* ignore */
    }
  },
};
