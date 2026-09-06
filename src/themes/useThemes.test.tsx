// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ThemesDependencies } from "./themesClient";
import { useThemes } from "./useThemes";

describe("useThemes", () => {
  it("derives dynamic cards during render without duplicating catalog state", async () => {
    const dependencies: ThemesDependencies = {
      adapter: {
        inspect: vi.fn(async () => ({ status: "missing" as const, themes: [] })),
        requireReady: vi.fn(), reloadTheme: vi.fn(), restoreThemeSnapshot: vi.fn(),
        reconcileRecoveredThemes: vi.fn(), setPatchValue: vi.fn(), deleteTheme: vi.fn(),
      },
      installer: {
        prepare: vi.fn(), commit: vi.fn(), discardReceipt: vi.fn(), rollback: vi.fn(),
        pendingRecoveries: vi.fn(async () => []), acknowledgeRollback: vi.fn(),
      },
      activator: { activate: vi.fn(), deactivate: vi.fn() },
      publication: { check: vi.fn(async () => ({
        status: "published" as const,
        checkedAt: 10,
        themes: [{
          catalogId: "example-theme", cssLoaderName: "Example Theme", publishedVersion: "1.2.3",
          displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
          description: { es: "Descripcion", en: "Description", it: "Descrizione" },
          author: "Example Author", tags: [], notes: {}, compatibility: "compatible" as const,
        }],
      })) },
    };
    const { result } = renderHook(() => useThemes(dependencies));

    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(result.current.snapshot.status).toBe("missing");
    expect(result.current.cards.map((card) => card.id)).toEqual(["example-theme"]);
  });

  it("exposes uninstall through the shared themes client", async () => {
    const installedTheme = {
      id: "Example Theme", name: "Example Theme", displayName: "Example Theme",
      version: "1.2.3", author: "Example Author", enabled: true, patches: [],
    };
    const after = {
      status: "ready" as const,
      pluginVersion: "2.1.2",
      backendVersion: 9,
      themes: [],
    };
    const deleteTheme = vi.fn(async () => after);
    const discardReceipt = vi.fn(async () => undefined);
    const dependencies: ThemesDependencies = {
      adapter: {
        inspect: vi.fn(async () => ({ ...after, themes: [installedTheme] })),
        requireReady: vi.fn(), reloadTheme: vi.fn(), restoreThemeSnapshot: vi.fn(),
        reconcileRecoveredThemes: vi.fn(), setPatchValue: vi.fn(), deleteTheme,
      },
      installer: {
        prepare: vi.fn(), commit: vi.fn(), discardReceipt, rollback: vi.fn(),
        pendingRecoveries: vi.fn(async () => []), acknowledgeRollback: vi.fn(),
      },
      activator: { activate: vi.fn(), deactivate: vi.fn() },
      publication: { check: vi.fn(async () => ({
        status: "published" as const,
        checkedAt: 10,
        themes: [{
          catalogId: "example-theme", cssLoaderName: "Example Theme", publishedVersion: "1.2.3",
          displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
          description: { es: "Descripcion", en: "Description", it: "Descrizione" },
          author: "Example Author", tags: [], notes: {}, compatibility: "compatible" as const,
        }],
      })) },
    };
    const { result } = renderHook(() => useThemes(dependencies));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    let removed = false;
    await act(async () => { removed = await result.current.uninstall("example-theme"); });

    expect(removed).toBe(true);
    expect(deleteTheme).toHaveBeenCalledWith("Example Theme");
    expect(discardReceipt).toHaveBeenCalledWith("example-theme");
  });
});
