import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import { PanelThemeInstaller, ThemeInstallError } from "./panelThemeInstaller";
import { parseEarlyPublication, type PublishedThemeRelease, type ThemePublicationState } from "./remotePublication";
import { createRemotePublicationClient } from "./remotePublicationClient";
import { deriveThemeCards } from "./state";
import { ThemesClient, type ThemesDependencies } from "./themesClient";

const TEXT = { es: "Tema", en: "Theme", it: "Tema" };
const STABLE: PublishedThemeRelease = {
  catalogId: "stable-theme", cssLoaderName: "Stable Theme", publishedVersion: "1.0.0", displayName: TEXT,
  description: TEXT, author: "A", tags: [], notes: {}, compatibility: "compatible",
};
const RAW_EARLY = {
  catalogId: "early-theme", cssLoaderName: "Early Theme", earlyVersion: "0.3.0", displayName: TEXT,
  description: TEXT, author: "A", tags: [], notes: {}, compatibility: "compatible",
};
const EARLY = parseEarlyPublication({ status: "published", themes: [RAW_EARLY, { ...RAW_EARLY, catalogId: "stable-theme", cssLoaderName: "Stable Theme", earlyVersion: "1.1.0" }] });
const PUBLICATION: ThemePublicationState = { status: "published", checkedAt: 1, themes: [STABLE], early: EARLY };
const READY: CssLoaderReadySnapshot = { status: "ready", themes: [] };

describe("early access themes", () => {
  it("reads the early list and drops anything it cannot trust", () => {
    expect(EARLY.map((theme) => [theme.catalogId, theme.earlyVersion, theme.release.publishedVersion])).toEqual([
      ["early-theme", "0.3.0", "0.3.0"],
      ["stable-theme", "1.1.0", "1.1.0"],
    ]);
    expect(parseEarlyPublication({ status: "temporarily-unavailable", code: "offline", retryable: true })).toEqual([]);
    expect(parseEarlyPublication({ status: "published", themes: [{ ...RAW_EARLY, earlyVersion: "x" }] })).toEqual([]);
    expect(parseEarlyPublication(null)).toEqual([]);
  });

  it("lists an early-only theme without a regular install and tags a catalog theme with its early build", () => {
    const cards = deriveThemeCards(PUBLICATION, READY);
    expect(cards.map((card) => [card.id, card.installable, card.earlyOnly, card.early?.version])).toEqual([
      ["stable-theme", true, false, "1.1.0"],
      ["early-theme", false, true, "0.3.0"],
    ]);
  });

  it("never lets an unreadable early list hide the catalog", async () => {
    const client = createRemotePublicationClient(
      async () => ({ status: "published", checkedAt: 1, themes: [{ ...STABLE }] }),
      async () => { throw new Error("offline"); },
    );
    await expect(client.check(false)).resolves.toMatchObject({ status: "published", themes: [{ catalogId: "stable-theme" }] });
  });

  it("sends only an absolute picked path to the backend's early install", async () => {
    const prepareEarly = vi.fn(async () => ({
      ok: true, code: "prepared", theme_id: "early-theme", theme_name: "Early Theme", version: "0.2.0", transaction: "t",
    }));
    const installer = new PanelThemeInstaller({
      prepareEarly, prepareRemote: vi.fn(), commit: vi.fn(), discard: vi.fn(), rollback: vi.fn(), recoveries: vi.fn(), acknowledge: vi.fn(),
    });
    await expect(installer.prepare({ kind: "early-archive", catalogId: "early-theme", archivePath: "/home/deck/Downloads/a.zip" }))
      .resolves.toMatchObject({ themeId: "early-theme", version: "0.2.0" });
    expect(prepareEarly).toHaveBeenCalledWith("/home/deck/Downloads/a.zip");
    await expect(installer.prepare({ kind: "early-archive", catalogId: "early-theme", archivePath: "a.zip" }))
      .rejects.toBeInstanceOf(ThemeInstallError);
  });

  it("installs the picked zip through the usual verify, reload and commit steps", async () => {
    const reloadTheme = vi.fn(async () => READY);
    const prepare = vi.fn(async () => ({ themeId: "early-theme", themeName: "Early Theme", version: "0.2.0", transaction: "t" }));
    const commit = vi.fn(async () => undefined);
    const pickEarlyArchive = vi.fn(async (): Promise<string | null> => "/home/deck/Downloads/early.zip");
    const deps: ThemesDependencies = {
      adapter: {
        inspect: vi.fn(async () => READY), requireReady: vi.fn(async () => READY), reloadTheme,
        restoreThemeSnapshot: vi.fn(async () => READY), reconcileRecoveredThemes: vi.fn(async () => READY),
        setPatchValue: vi.fn(async () => READY), deleteTheme: vi.fn(async () => READY),
      },
      installer: {
        prepare, commit, discardReceipt: vi.fn(), rollback: vi.fn(), pendingRecoveries: vi.fn(async () => []), acknowledgeRollback: vi.fn(),
      },
      activator: { activate: vi.fn(async () => READY), deactivate: vi.fn(async () => READY) },
      publication: { check: vi.fn(async () => PUBLICATION) },
      pickEarlyArchive,
    };
    const client = new ThemesClient(deps);
    await client.refresh();
    await client.refreshPublication();

    await expect(client.install("early-theme")).resolves.toBe(false);
    await expect(client.installEarly("early-theme")).resolves.toBe(true);
    expect(prepare).toHaveBeenCalledWith({ kind: "early-archive", catalogId: "early-theme", archivePath: "/home/deck/Downloads/early.zip" });
    expect(reloadTheme).toHaveBeenCalledWith("Early Theme", "0.2.0", READY);
    expect(commit).toHaveBeenCalledWith("t");

    pickEarlyArchive.mockResolvedValueOnce(null);
    await expect(client.installEarly("early-theme")).resolves.toBe(false);
    expect(prepare).toHaveBeenCalledTimes(1);
  });
});
