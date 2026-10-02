import type { KioskState } from "../api";

export function kioskDescriptionKey(state: KioskState): string {
  if (state.reason === "no_browser") return "settings.kiosk.noBrowser";
  if (!state.enabled) return "settings.kiosk.desc";
  if (state.running) return "settings.kiosk.running";
  if (state.last_error) return "settings.kiosk.retrying";
  if (!state.available) return "settings.kiosk.waiting";
  return "settings.kiosk.starting";
}
