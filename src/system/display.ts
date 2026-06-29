import { ScalarControl } from "./types";

// SteamClient brightness adapter. Surface confirmed against the same API Steam's
// own OSD uses; isolated here so the rest of the UI is stable if a device needs
// a different call. Never throws — degrades to "unavailable" if the API is absent.
export const displayBrightness: ScalarControl = {
  subscribe(cb) {
    try {
      const reg = SteamClient?.System?.Display?.RegisterForBrightnessChanges?.(
        (data: { flBrightness?: number }) => {
          if (typeof data?.flBrightness === "number") cb(data.flBrightness);
        },
      );
      if (reg && typeof reg.unregister === "function") {
        return () => {
          try {
            reg.unregister();
          } catch {
            /* ignore */
          }
        };
      }
    } catch {
      /* API unavailable */
    }
    return null;
  },
  set(fraction) {
    try {
      SteamClient?.System?.Display?.SetBrightness?.(fraction);
    } catch {
      /* ignore */
    }
  },
};
