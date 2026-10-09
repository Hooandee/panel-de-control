import { describe, expect, it, vi } from "vitest";

import { configureThemeHealthHost, createThemeCleanupHost, readThemeHealth, ThemeCleanupError } from "./themeCleanupHost";

const health = { folders: [], panel: null, undo: { available: false, moved: 0, disabled: 0 } };

describe("theme cleanup host", () => {
  it("fails closed until the backend host is configured", async () => {
    await expect(readThemeHealth()).rejects.toMatchObject({ code: "backend_unavailable" });
  });

  it("passes the recorded names and returns the names to enable again", async () => {
    const setAside = vi.fn(async () => ({ ok: true, moved: [], failed: [] }));
    const release = configureThemeHealthHost({
      health: async () => health,
      setAside,
      restore: async () => ({ ok: true, restored: [], kept: [], reenable: ["Other", 4] }),
      acknowledgeRestore: async () => ({ ok: true }),
    });
    const host = createThemeCleanupHost();

    await host.setAside(["Other"]);
    await expect(host.restore()).resolves.toEqual(["Other"]);
    await expect(readThemeHealth()).resolves.toEqual(health);
    expect(setAside).toHaveBeenCalledWith(["Other"]);
    release();
  });

  it("turns a backend refusal into a coded error", async () => {
    const host = createThemeCleanupHost({
      health: async () => health,
      setAside: async () => ({ ok: false, code: "transaction_busy" }),
      restore: async () => null,
      acknowledgeRestore: async () => ({ ok: false, code: "transaction_busy" }),
    });

    await expect(host.setAside([])).rejects.toEqual(new ThemeCleanupError("transaction_busy", "Theme cleanup was refused (transaction_busy)"));
    await expect(host.restore()).rejects.toMatchObject({ code: "malformed_response" });
    await expect(host.acknowledgeRestore()).rejects.toMatchObject({ code: "transaction_busy" });
  });
});
