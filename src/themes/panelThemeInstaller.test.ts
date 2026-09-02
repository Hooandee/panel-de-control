import { describe, expect, it, vi } from "vitest";

import { PanelThemeInstaller, ThemeInstallError } from "./panelThemeInstaller";
import { configurePanelThemeInstallHost, createPanelThemeInstaller } from "./panelThemeInstallHost";

function host(overrides: Record<string, unknown> = {}) {
  return {
    prepareRemote: vi.fn(async () => ({
      ok: true, code: "prepared", theme_id: "example-theme",
      theme_name: "Example Theme", version: "1.2.3", transaction: "opaque-token",
    })),
    commit: vi.fn(async () => ({ ok: true, code: "committed" })),
    rollback: vi.fn(async () => ({ ok: true, code: "rolled_back" })),
    recoveries: vi.fn(async () => ({ ok: true, code: "ready", recoveries: [] })),
    acknowledge: vi.fn(async () => ({ ok: true, code: "acknowledged" })),
    discard: vi.fn(async () => ({ ok: true, code: "discarded" })),
    ...overrides,
  };
}

const REQUEST = {
  kind: "official-remote" as const,
  channelId: "panel-pages-v1" as const,
  catalogId: "example-theme",
  expectedVersion: "1.2.3",
};

describe("PanelThemeInstaller", () => {
  it("prepares only the compiled official channel and validates the response", async () => {
    const backend = host();
    const installer = new PanelThemeInstaller(backend);

    await expect(installer.prepare(REQUEST)).resolves.toEqual({
      themeId: "example-theme", themeName: "Example Theme", version: "1.2.3", transaction: "opaque-token",
    });
    expect(backend.prepareRemote).toHaveBeenCalledWith("example-theme", "1.2.3");
  });

  it.each([
    { ...REQUEST, channelId: "other" },
    { ...REQUEST, catalogId: "../escape" },
    { ...REQUEST, expectedVersion: "v1.2.3" },
  ])("rejects unsupported remote requests before RPC", async (request) => {
    const backend = host();
    const installer = new PanelThemeInstaller(backend);

    await expect(installer.prepare(request as never)).rejects.toMatchObject({ code: "unsupported_source" });
    expect(backend.prepareRemote).not.toHaveBeenCalled();
  });

  it("turns typed backend rejection into a safe install error", async () => {
    const installer = new PanelThemeInstaller(host({
      prepareRemote: vi.fn(async () => ({ ok: false, code: "hash_mismatch" })),
    }));

    await expect(installer.prepare(REQUEST)).rejects.toEqual(
      new ThemeInstallError("hash_mismatch", "Theme package installation failed"),
    );
  });

  it("validates transaction acknowledgements and pending recoveries", async () => {
    const installer = new PanelThemeInstaller(host({
      recoveries: vi.fn(async () => ({
        ok: true,
        code: "ready",
        recoveries: [{ transaction: "token", theme_name: "Example Theme", previous_version: "v1.2.2" }],
      })),
    }));

    await expect(installer.pendingRecoveries()).resolves.toEqual([{
      transaction: "token", themeName: "Example Theme", previousVersion: "v1.2.2",
    }]);
    await expect(installer.commit("token")).resolves.toBeUndefined();
    await expect(installer.rollback("token")).resolves.toBeUndefined();
    await expect(installer.acknowledgeRollback("token")).resolves.toBeUndefined();
  });

  it.each(["discarded", "absent"])("accepts the %s receipt discard result", async (code) => {
    const installer = new PanelThemeInstaller(host({
      discard: vi.fn(async () => ({ ok: true, code })),
    }));

    await expect(installer.discardReceipt("example-theme")).resolves.toBeUndefined();
  });

  it("turns a typed receipt discard rejection into a safe install error", async () => {
    const installer = new PanelThemeInstaller(host({
      discard: vi.fn(async () => ({ ok: false, code: "theme_present" })),
    }));

    await expect(installer.discardReceipt("example-theme")).rejects.toEqual(
      new ThemeInstallError("theme_present", "Theme receipt discard failed"),
    );
  });

  it("rejects a malformed receipt discard result", async () => {
    const installer = new PanelThemeInstaller(host({
      discard: vi.fn(async () => ({ ok: true, code: "committed" })),
    }));

    await expect(installer.discardReceipt("example-theme")).rejects.toMatchObject({
      code: "malformed_response",
    });
  });
});

describe("Panel theme install host", () => {
  it("uses the current scoped backend host and releases only its own lease", async () => {
    const first = host({ prepareRemote: vi.fn(async () => ({ ok: false, code: "first" })) });
    const second = host({ prepareRemote: vi.fn(async () => ({ ok: false, code: "second" })) });
    const releaseFirst = configurePanelThemeInstallHost(first);
    const releaseSecond = configurePanelThemeInstallHost(second);

    releaseFirst();
    await expect(createPanelThemeInstaller().prepare(REQUEST)).rejects.toMatchObject({ code: "second" });
    expect(first.prepareRemote).not.toHaveBeenCalled();

    releaseSecond();
    await expect(createPanelThemeInstaller().prepare(REQUEST)).rejects.toMatchObject({ code: "backend_unavailable" });
  });

  it("routes receipt discard through the current scoped backend host", async () => {
    const backend = host();
    const release = configurePanelThemeInstallHost(backend);

    await expect(createPanelThemeInstaller().discardReceipt("example-theme")).resolves.toBeUndefined();
    expect(backend.discard).toHaveBeenCalledWith("example-theme");

    release();
    await expect(createPanelThemeInstaller().discardReceipt("example-theme")).rejects.toMatchObject({
      code: "backend_unavailable",
    });
  });
});
