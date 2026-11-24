import { afterEach, expect, test } from "vitest";
import { steamLibraryFolders } from "./steamLibraries";

const store = globalThis as unknown as { installFolderStore?: unknown };

afterEach(() => { delete store.installFolderStore; });

test("lists the mounted library folders Steam knows, once each", () => {
  store.installFolderStore = { AllInstallFolders: [
    { strFolderPath: "/home/deck/.local/share/Steam", bIsMounted: true },
    { strFolderPath: "/run/media/deck/SD", bIsMounted: true },
    { strFolderPath: "/run/media/deck/SD", bIsMounted: true },
    { strFolderPath: "/run/media/deck/Old", bIsMounted: false },
    { strFolderPath: "relative" },
  ] };

  expect(steamLibraryFolders()).toEqual(["/home/deck/.local/share/Steam", "/run/media/deck/SD"]);
});

test("answers nothing when Steam has no install folder store", () => {
  expect(steamLibraryFolders()).toEqual([]);
});
