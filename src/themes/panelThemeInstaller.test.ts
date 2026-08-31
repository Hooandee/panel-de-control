import { describe, expect, it, vi } from "vitest";

import {
  PanelThemeInstaller,
  ThemeInstallError,
} from "./panelThemeInstaller";
import {
  configurePanelThemeInstallHost,
  createPanelThemeInstaller,
} from "./panelThemeInstallHost";

describe("PanelThemeInstaller", () => {
  it("prepares a bundled package through Panel's backend and validates its identity", async () => {
    const prepare = vi.fn(async () => ({
      ok: true, code: "prepared", theme_id: "hooandee-gallery",
      theme_name: "Hooandee Gallery", version: "0.6.0", transaction: "opaque-token",
    }));
    const host = {
      prepare,
      commit: vi.fn(),
      rollback: vi.fn(),
      recoveries: vi.fn(),
      acknowledge: vi.fn(),
    };
    const installer = new PanelThemeInstaller(host);

    const result = await installer.prepare({
      kind: "bundled",
      packageId: "hooandee-gallery",
    });

    expect(result).toEqual({
      themeId: "hooandee-gallery",
      themeName: "Hooandee Gallery",
      version: "0.6.0",
      transaction: "opaque-token",
    });
    expect(prepare).toHaveBeenCalledWith("hooandee-gallery");
  });

  it("turns a typed backend rejection into a recoverable install error", async () => {
    const installer = new PanelThemeInstaller({
      prepare: vi.fn(async () => ({
        ok: false, code: "hash_mismatch", theme_id: "hooandee-gallery",
      })),
      commit: vi.fn(),
      rollback: vi.fn(),
      recoveries: vi.fn(),
      acknowledge: vi.fn(),
    });

    await expect(installer.prepare({
      kind: "bundled",
      packageId: "hooandee-gallery",
    })).rejects.toEqual(new ThemeInstallError("hash_mismatch", "Theme package installation failed"));
  });

  it("prepares an official update using only its catalog identity and confirmed version", async () => {
    const prepareRemote = vi.fn(async () => ({
      ok: true, code: "prepared", theme_id: "hooandee-gallery",
      theme_name: "Hooandee Gallery", version: "0.7.9", transaction: "remote-token",
    }));
    const installer = new PanelThemeInstaller({
      prepare: vi.fn(),
      prepareRemote,
      commit: vi.fn(),
      rollback: vi.fn(),
      recoveries: vi.fn(),
      acknowledge: vi.fn(),
    });

    const result = await installer.prepare({
      kind: "official-remote",
      channelId: "panel-pages-v1",
      catalogId: "hooandee-gallery",
      expectedVersion: "0.7.9",
    });

    expect(result).toMatchObject({
      themeId: "hooandee-gallery",
      version: "0.7.9",
      transaction: "remote-token",
    });
    expect(prepareRemote).toHaveBeenCalledWith("hooandee-gallery", "0.7.9");
  });

  it("rejects malformed remote requests before calling Panel", async () => {
    const prepareRemote = vi.fn();
    const installer = new PanelThemeInstaller({
      prepare: vi.fn(), prepareRemote, commit: vi.fn(), rollback: vi.fn(),
      recoveries: vi.fn(), acknowledge: vi.fn(),
    });

    await expect(installer.prepare({
      kind: "official-remote",
      channelId: "panel-pages-v1",
      catalogId: "hooandee-gallery",
      expectedVersion: "v0.7.9",
    })).rejects.toMatchObject({ code: "unsupported_source" });
    expect(prepareRemote).not.toHaveBeenCalled();
  });

  it("fails closed on an unknown backend response", async () => {
    const installer = new PanelThemeInstaller({
      prepare: vi.fn(async () => ({ ok: true })),
      commit: vi.fn(),
      rollback: vi.fn(),
      recoveries: vi.fn(),
      acknowledge: vi.fn(),
    });

    await expect(installer.prepare({
      kind: "bundled",
      packageId: "hooandee-gallery",
    })).rejects.toMatchObject({ code: "malformed_response" });
  });

  it("commits and rolls back only after validating Panel's acknowledgement", async () => {
    const host = {
      prepare: vi.fn(),
      commit: vi.fn(async () => ({ ok: true, code: "committed" })),
      rollback: vi.fn(async () => ({ ok: true, code: "rolled_back" })),
      recoveries: vi.fn(async () => ({ ok: true, code: "ready", recoveries: [] })),
      acknowledge: vi.fn(async () => ({ ok: true, code: "acknowledged" })),
    };
    const installer = new PanelThemeInstaller(host);

    await expect(installer.commit("opaque-token")).resolves.toBeUndefined();
    await expect(installer.rollback("opaque-token")).resolves.toBeUndefined();
    await expect(installer.acknowledgeRollback("opaque-token")).resolves.toBeUndefined();

    expect(host.commit).toHaveBeenCalledWith("opaque-token");
    expect(host.rollback).toHaveBeenCalledWith("opaque-token");
    expect(host.acknowledge).toHaveBeenCalledWith("opaque-token");
  });

  it("validates durable pending recoveries before exposing them to the client", async () => {
    const host = {
      prepare: vi.fn(), commit: vi.fn(), rollback: vi.fn(), acknowledge: vi.fn(),
      recoveries: vi.fn(async () => ({
        ok: true,
        code: "ready",
        recoveries: [{
          transaction: "opaque-token",
          theme_name: "Hooandee Gallery",
          previous_version: "v0.5.0",
        }],
      })),
    };

    await expect(new PanelThemeInstaller(host).pendingRecoveries()).resolves.toEqual([{
      transaction: "opaque-token",
      themeName: "Hooandee Gallery",
      previousVersion: "v0.5.0",
    }]);
  });

  it("preserves a blocked invalid-journal recovery result", async () => {
    const installer = new PanelThemeInstaller({
      prepare: vi.fn(), commit: vi.fn(), rollback: vi.fn(), acknowledge: vi.fn(),
      recoveries: vi.fn(async () => ({ ok: false, code: "invalid_journal" })),
    });

    await expect(installer.pendingRecoveries()).rejects.toMatchObject({
      code: "invalid_journal",
    });
  });
});

describe("Panel theme install host", () => {
  it("uses the current scoped backend host and releases only its own lease", async () => {
    const first = {
      prepare: vi.fn(async () => ({ ok: false, code: "first" })), commit: vi.fn(), rollback: vi.fn(),
      recoveries: vi.fn(), acknowledge: vi.fn(),
    };
    const second = {
      prepare: vi.fn(async () => ({ ok: false, code: "second" })), commit: vi.fn(), rollback: vi.fn(),
      recoveries: vi.fn(), acknowledge: vi.fn(),
    };
    const releaseFirst = configurePanelThemeInstallHost(first);
    const releaseSecond = configurePanelThemeInstallHost(second);

    releaseFirst();
    await expect(createPanelThemeInstaller().prepare({
      kind: "bundled",
      packageId: "hooandee-gallery",
    })).rejects.toMatchObject({ code: "second" });
    expect(first.prepare).not.toHaveBeenCalled();
    expect(second.prepare).toHaveBeenCalledOnce();

    releaseSecond();
    await expect(createPanelThemeInstaller().prepare({
      kind: "bundled",
      packageId: "hooandee-gallery",
    })).rejects.toMatchObject({ code: "backend_unavailable" });
  });
});
