import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import {
  configurePanelThemeActivationJournalHost,
  createPanelThemeActivationJournal,
  PanelThemeActivationJournal,
} from "./panelThemeActivationJournal";

const SNAPSHOT: CssLoaderReadySnapshot = {
  status: "ready",
  pluginVersion: "2.1.2",
  backendVersion: 9,
  themes: [{
    id: "example",
    name: "Example Theme",
    displayName: "Example Theme",
    version: "1.2.3",
    author: "Example Author",
    enabled: false,
    patches: [{
      name: "Color",
      defaultValue: "Blue",
      value: "Red",
      options: ["Blue", "Red"],
      type: "dropdown",
      rawType: "dropdown",
    }],
  }],
};

function host(overrides: Record<string, unknown> = {}) {
  return {
    begin: vi.fn(async () => ({ ok: true, code: "prepared", transaction: "token" })),
    pending: vi.fn(async () => ({
      ok: true,
      code: "ready",
      recovery: { transaction: "token", snapshot: SNAPSHOT, recoverable: true },
    })),
    settle: vi.fn(async () => ({ ok: true, code: "settled" })),
    acknowledge: vi.fn(async () => ({ ok: true, code: "acknowledged" })),
    ...overrides,
  };
}

describe("PanelThemeActivationJournal", () => {
  it("persists, loads, and acknowledges the exact backend snapshot", async () => {
    const backend = host();
    const journal = new PanelThemeActivationJournal(backend);

    await expect(journal.begin(SNAPSHOT)).resolves.toBe("token");
    await expect(journal.pending()).resolves.toEqual({ transaction: "token", snapshot: SNAPSHOT });
    await expect(journal.settle("token")).resolves.toBeUndefined();
    await expect(journal.acknowledge("token")).resolves.toBeUndefined();
    expect(backend.begin).toHaveBeenCalledWith(SNAPSHOT);
    expect(backend.settle).toHaveBeenCalledWith("token");
    expect(backend.acknowledge).toHaveBeenCalledWith("token");
  });

  it("fails closed on a malformed durable snapshot", async () => {
    const journal = new PanelThemeActivationJournal(host({
      pending: vi.fn(async () => ({
        ok: true,
        code: "ready",
        recovery: {
          transaction: "token",
          recoverable: true,
          snapshot: { ...SNAPSHOT, themes: [{ ...SNAPSHOT.themes[0], enabled: 1 }] },
        },
      })),
    }));

    await expect(journal.pending()).rejects.toMatchObject({ code: "malformed_response" });
  });

  it("does not recover or acknowledge while an old backend mutation is unsettled", async () => {
    const backend = host({
      pending: vi.fn(async () => ({
        ok: true,
        code: "ready",
        recovery: { transaction: "token", snapshot: SNAPSHOT, recoverable: false },
      })),
    });
    const journal = new PanelThemeActivationJournal(backend);

    await expect(journal.pending()).rejects.toMatchObject({ code: "mutation_unsettled" });
    expect(backend.acknowledge).not.toHaveBeenCalled();
  });

  it("uses only the current scoped backend host", async () => {
    const first = host({ begin: vi.fn(async () => ({ ok: false, code: "first" })) });
    const second = host({ begin: vi.fn(async () => ({ ok: true, code: "prepared", transaction: "second" })) });
    const releaseFirst = configurePanelThemeActivationJournalHost(first);
    const releaseSecond = configurePanelThemeActivationJournalHost(second);

    releaseFirst();
    await expect(createPanelThemeActivationJournal().begin(SNAPSHOT)).resolves.toBe("second");
    releaseSecond();
    await expect(createPanelThemeActivationJournal().begin(SNAPSHOT)).rejects.toMatchObject({
      code: "backend_unavailable",
    });
  });
});
