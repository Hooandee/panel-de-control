import { describe, expect, it } from "vitest";

import type { KioskState } from "../api";
import { kioskDescriptionKey } from "./kioskStatus";

const base: KioskState = {
  supported: true,
  available: true,
  reason: "ok",
  enabled: true,
  running: false,
  mechanism: "armada-lease",
  last_error: null,
};

describe("kioskDescriptionKey", () => {
  it("says what is really happening", () => {
    expect(kioskDescriptionKey({ ...base, enabled: false })).toBe("settings.kiosk.desc");
    expect(kioskDescriptionKey({ ...base, running: true })).toBe("settings.kiosk.running");
    expect(kioskDescriptionKey({ ...base, last_error: "boom" })).toBe("settings.kiosk.retrying");
    expect(kioskDescriptionKey({ ...base, available: false, reason: "not_in_game_mode" })).toBe("settings.kiosk.waiting");
    expect(kioskDescriptionKey(base)).toBe("settings.kiosk.starting");
    expect(kioskDescriptionKey({ ...base, reason: "no_runtime", available: false })).toBe("settings.kiosk.noRuntime");
  });
});
