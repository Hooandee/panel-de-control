// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { APP_TYPE_TOOL } from "../tdp/gameIdentity";
import { listInstalledGames, listLibraryGames } from "./steamApi";

type SteamWindow = { collectionStore?: unknown };

describe("library games for theme cover editors", () => {
  afterEach(() => { delete (window as unknown as SteamWindow).collectionStore; });

  it("lists installed and not-installed games and shortcuts, never tools", () => {
    (window as unknown as SteamWindow).collectionStore = { allAppsCollection: { allApps: [
      { appid: 10, display_name: "Installed", app_type: 1, local_per_client_data: { installed: true } },
      { appid: 20, display_name: "In the cloud", app_type: 1, local_per_client_data: { installed: false } },
      { appid: 30, display_name: "Proton", app_type: APP_TYPE_TOOL, local_per_client_data: { installed: true } },
      { appid: 3000000000, display_name: "Shortcut", app_type: 1073741824 },
      { appid: 40, app_type: 1 },
      null,
    ] } };
    expect(listLibraryGames()).toEqual([
      { appId: 10, name: "Installed" },
      { appId: 20, name: "In the cloud" },
      { appId: 3000000000, name: "Shortcut" },
      { appId: 40, name: "40" },
    ]);
    expect(listInstalledGames().map((game) => game.liveAppid)).not.toContain(20);
  });

  it("returns nothing without Steam's library", () => {
    expect(listLibraryGames()).toEqual([]);
  });
});
