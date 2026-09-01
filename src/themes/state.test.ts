import { describe, expect, it } from "vitest";

import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
import { deriveThemeCards } from "./state";

const RELEASE: PublishedThemeRelease = {
  catalogId: "example-theme",
  cssLoaderName: "Example Theme",
  publishedVersion: "1.2.3",
  displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
  description: { es: "Descripcion", en: "Description", it: "Descrizione" },
  author: "Example Author",
  tags: ["dark"],
  notes: { es: "Novedades", en: "Changes", it: "Novita" },
  compatibility: "compatible",
  exclusiveGroup: "interface",
};

function publication(status: "published" | "cached" = "published"): ThemePublicationState {
  return {
    status,
    checkedAt: 100,
    themes: [RELEASE],
    ...(status === "cached" ? { code: "offline" as const, retryable: true } : {}),
  } as ThemePublicationState;
}

function installed(name: string, version: string, enabled = false): CssLoaderTheme {
  return { id: name, name, displayName: name, version, author: "Author", enabled, patches: [] };
}

function ready(themes: CssLoaderTheme[]): CssLoaderSnapshot {
  return { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes };
}

describe("deriveThemeCards", () => {
  it.each(["published", "cached"] as const)("derives cards only from %s publication entries", (status) => {
    const cards = deriveThemeCards(publication(status), { status: "missing", themes: [] });

    expect(cards).toHaveLength(1);
    expect(cards[0]).toMatchObject({
      id: "example-theme",
      release: RELEASE,
      installed: false,
      active: false,
      targetVersion: "1.2.3",
      installable: true,
      versionRelation: "not-installed",
    });
  });

  it("returns no local or invented cards without a usable publication", () => {
    expect(deriveThemeCards({ status: "unchecked" }, ready([]))).toEqual([]);
    expect(deriveThemeCards({ status: "recoverable-failure", code: "offline", retryable: true }, ready([])))
      .toEqual([]);
  });

  it("matches installed state only by sanitized CSS Loader identity", () => {
    const cards = deriveThemeCards(publication(), ready([
      installed("Example Theme", "1.2.2", true),
      installed("Theme containing Example Theme", "9.0.0", true),
    ]));

    expect(cards[0]).toMatchObject({
      installed: true,
      active: true,
      installedVersion: "1.2.2",
      updateAvailable: true,
      versionRelation: "update-available",
    });
  });

  it("keeps incompatible releases visible but not installable", () => {
    const state = publication();
    if (state.status !== "published") throw new Error("fixture");
    const cards = deriveThemeCards({
      ...state,
      themes: [{ ...RELEASE, compatibility: "incompatible-css-loader" }],
    }, ready([]));

    expect(cards[0]).toMatchObject({ installed: false, installable: false });
    expect(cards[0].targetVersion).toBeUndefined();
  });

  it("does not offer a downgrade when the local version is newer", () => {
    expect(deriveThemeCards(publication(), ready([installed("Example Theme", "2.0.0")]))[0])
      .toMatchObject({ versionRelation: "local-newer", updateAvailable: false });
  });
});
