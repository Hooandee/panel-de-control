import { afterEach, expect, test } from "vitest";
import { steamLibraryFolders, steamLibraryOf } from "./steamLibraries";

const store = globalThis as unknown as { installFolderStore?: unknown };

afterEach(() => { delete store.installFolderStore; });

test("maps each game to the mounted library Steam installed it in", () => {
  store.installFolderStore = { AllInstallFolders: [
    { strFolderPath: "/home/deck/.local/share/Steam", bIsMounted: true, vecApps: [{ nAppID: 1 }] },
    { strFolderPath: "/run/media/deck/SD", bIsMounted: true, vecApps: [{ nAppID: 870780 }] },
    { strFolderPath: "/run/media/deck/Old", bIsMounted: false, vecApps: [{ nAppID: 2 }] },
    { strFolderPath: "relative", vecApps: [{ nAppID: 3 }] },
  ] };

  expect(steamLibraryOf(870780)).toBe("/run/media/deck/SD");
  expect(steamLibraryOf(2)).toBeNull();
  expect(steamLibraryOf(3)).toBeNull();
  expect(steamLibraryFolders()).toEqual(["/home/deck/.local/share/Steam", "/run/media/deck/SD"]);
});

test("answers nothing when Steam has no install folder store", () => {
  expect(steamLibraryOf(870780)).toBeNull();
  expect(steamLibraryFolders()).toEqual([]);
});
