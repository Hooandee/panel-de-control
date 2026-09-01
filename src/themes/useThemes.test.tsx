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
        reconcileRecoveredThemes: vi.fn(), setPatchValue: vi.fn(),
      },
      installer: {
        prepare: vi.fn(), commit: vi.fn(), rollback: vi.fn(),
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
});
