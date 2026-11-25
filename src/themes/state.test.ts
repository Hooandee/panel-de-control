import { describe, expect, it } from "vitest";

import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedEarlyTheme, PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
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
  return { status: "ready", themes };
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

  it("keeps releases for a newer Panel visible but not installable", () => {
    const state = publication();
    if (state.status !== "published") throw new Error("fixture");
    const cards = deriveThemeCards({
      ...state,
      themes: [{ ...RELEASE, compatibility: "incompatible-panel" }],
    }, ready([]));

    expect(cards[0]).toMatchObject({ installed: false, installable: false });
    expect(cards[0].targetVersion).toBeUndefined();
  });

  it("does not offer a downgrade when the local version is newer", () => {
    expect(deriveThemeCards(publication(), ready([installed("Example Theme", "2.0.0")]))[0])
      .toMatchObject({ versionRelation: "local-newer", updateAvailable: false });
  });

  describe("early builds", () => {
    const DUO: PublishedThemeRelease = {
      ...RELEASE,
      catalogId: "hooandee-duo",
      cssLoaderName: "Hooandee Duo",
      publishedVersion: "0.3.0",
    };
    const earlyOf = (release: PublishedThemeRelease, version: string): PublishedEarlyTheme => ({
      catalogId: release.catalogId,
      earlyVersion: version,
      release: { ...release, publishedVersion: version },
    });
    const withEarly = (early: PublishedEarlyTheme, status: "published" | "cached" = "published") =>
      ({ ...publication(status), early: [early] }) as ThemePublicationState;
    const duoCard = (installedVersion: string, early = earlyOf(DUO, "0.3.0")) =>
      deriveThemeCards(withEarly(early), ready([installed("Hooandee Duo", installedVersion)]))
        .find((card) => card.id === "hooandee-duo");

    it("detects a newer early for a theme installed as solo-early", () => {
      expect(duoCard("0.2.0")).toMatchObject({
        earlyOnly: true,
        installable: false,
        updateAvailable: false,
        earlyUpdateAvailable: true,
        early: { version: "0.3.0", installable: true },
      });
    });

    it.each([["the same", "0.3.0"], ["a newer", "0.4.0"]])("does not flag an early when %s build is installed", (_, version) => {
      expect(duoCard(version)?.earlyUpdateAvailable).toBe(false);
    });

    it("does not flag an early the running Panel cannot install", () => {
      const early = earlyOf(DUO, "0.3.0");
      expect(duoCard("0.2.0", { ...early, release: { ...early.release, compatibility: "incompatible-panel" } })?.earlyUpdateAvailable)
        .toBe(false);
    });

    it("does not flag an early for a solo-early theme that is not installed", () => {
      const card = deriveThemeCards(withEarly(earlyOf(DUO, "0.3.0")), ready([])).find((entry) => entry.id === "hooandee-duo");
      expect(card?.earlyUpdateAvailable).toBe(false);
    });

    it("flags a newer early on a catalog theme only when the installed build is itself an early", () => {
      const early = earlyOf(RELEASE, "1.4.0");
      const card = (version: string) => deriveThemeCards(withEarly(early), ready([installed("Example Theme", version)]))[0];
      expect(card("1.3.0")).toMatchObject({ versionRelation: "local-newer", earlyUpdateAvailable: true });
      expect(card("1.2.3")).toMatchObject({ versionRelation: "current", earlyUpdateAvailable: false });
      expect(card("1.2.0")).toMatchObject({ updateAvailable: true, earlyUpdateAvailable: false });
    });
  });

  describe("offline versus no updates", () => {
    it("marks cards from the copy saved on this device as offline, not as up to date", () => {
      const card = deriveThemeCards(publication("cached"), ready([installed("Example Theme", "1.2.3")]))[0];
      expect(card).toMatchObject({ versionRelation: "current", updateAvailable: false, offline: true });
    });

    it("reports a live check with nothing newer as up to date and online", () => {
      const card = deriveThemeCards(publication("published"), ready([installed("Example Theme", "1.2.3")]))[0];
      expect(card).toMatchObject({ versionRelation: "current", updateAvailable: false, offline: false });
    });

    it("keeps solo-early cards and their early update visible from an offline copy", () => {
      const duo = { ...RELEASE, catalogId: "hooandee-duo", cssLoaderName: "Hooandee Duo", publishedVersion: "0.3.0" };
      const state = { ...publication("cached"), early: [{ catalogId: duo.catalogId, earlyVersion: "0.3.0", release: duo }] } as ThemePublicationState;
      const card = deriveThemeCards(state, ready([installed("Hooandee Duo", "0.2.0")])).find((entry) => entry.id === "hooandee-duo");
      expect(card).toMatchObject({ earlyOnly: true, offline: true, earlyUpdateAvailable: true });
    });
  });
});
