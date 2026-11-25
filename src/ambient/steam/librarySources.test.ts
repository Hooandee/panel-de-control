// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { gameHero, installedGameAppIds, isStoreApp, libraryHeroUrl, neighborAppIdsIn, selectedAppIdFromHero, selectedAppIdIn } from "./librarySources";

describe("library sources", () => {
  afterEach(() => {
    delete (globalThis as { collectionStore?: unknown }).collectionStore;
    delete (globalThis as { appStore?: unknown }).appStore;
    delete (globalThis as { appDetailsStore?: unknown }).appDetailsStore;
  });

  // Steam Deck LCD, Steam client captured over CDP: /assets/548430/library_hero.jpg is 404 while the hashed path is 200.
  describe("gameHero", () => {
    const stores = (custom: string[], heroes: string[]) => {
      Object.assign(globalThis, {
        appStore: { GetAppOverviewByAppID: (id: number) => ({ appid: id }), GetCustomHeroImageURLs: () => custom },
        appDetailsStore: { GetHeroImagesForAppId: () => ({ rgHeroImages: heroes }) },
      });
    };
    const hash = "35c4a38067592e934fbb389098eccb0d8a8de000";

    it("keeps the plain path when Steam exposes nothing else", () => {
      expect(gameHero(588650).url).toBe("https://steamloopback.host/assets/588650/library_hero.jpg");
      stores([], ["https://shared.steamstatic.com/store_item_assets/steam/apps/588650/library_hero.jpg?t=0"]);
      expect(gameHero(588650).url).toBe("https://steamloopback.host/assets/588650/library_hero.jpg");
    });

    it("serves hashed store art from the local asset path", () => {
      stores([], [`https://shared.steamstatic.com/store_item_assets/steam/apps/548430/${hash}/library_hero.jpg?t=0`]);
      expect(gameHero(548430)).toEqual({ url: `https://steamloopback.host/assets/548430/${hash}/library_hero.jpg`, source: "hashed" });
    });

    it("ignores hashed art that belongs to another app", () => {
      stores([], [`https://shared.steamstatic.com/store_item_assets/steam/apps/1/${hash}/library_hero.jpg`]);
      expect(gameHero(2).url).toBe("https://steamloopback.host/assets/2/library_hero.jpg");
    });

    it("prefers the user's custom hero, also for non-Steam shortcuts", () => {
      stores(["/customimages/2953644062_hero.png?v=1"], [`https://shared.steamstatic.com/store_item_assets/steam/apps/2953644062/${hash}/library_hero.jpg`]);
      expect(gameHero("2953644062")).toEqual({ url: "https://steamloopback.host/customimages/2953644062_hero.png?v=1", source: "custom" });
    });

    it("ignores custom art outside Steam's own asset paths and survives broken stores", () => {
      stores(["https://example.com/x.png", "/other/x.png"], []);
      expect(gameHero(7).url).toBe("https://steamloopback.host/assets/7/library_hero.jpg");
      Object.assign(globalThis, { appStore: { GetAppOverviewByAppID: () => { throw new Error("gone"); } } });
      expect(gameHero(7).url).toBe("https://steamloopback.host/assets/7/library_hero.jpg");
    });
  });

  it("lists installed games only", () => {
    (globalThis as { collectionStore?: unknown }).collectionStore = {
      allAppsCollection: {
        allApps: [
          { appid: 730, app_type: 1, local_per_client_data: { installed: true } },
          { appid: 440, app_type: 1, local_per_client_data: { installed: false } },
          { appid: 1628350, app_type: 4, local_per_client_data: { installed: true } },
        ],
      },
    };
    expect(installedGameAppIds()).toEqual([730]);
  });

  it("builds local hero urls and reads the selected game", () => {
    expect(libraryHeroUrl(730)).toBe("https://steamloopback.host/assets/730/library_hero.jpg");
    expect(selectedAppIdFromHero("//steamloopback.host/assets/2514938415_library_hero_blur.jpg")).toBe("2514938415");
    expect(selectedAppIdFromHero("https://steamloopback.host/assets/413150/library_hero_blur.jpg?c=1")).toBe("413150");
    expect(selectedAppIdFromHero("https://x/other.png")).toBeNull();
  });

  it("the focused tile names the selected game, never the hero still fading out", () => {
    const home = document.createElement("div");
    home.innerHTML = '<img src="https://steamloopback.host/assets/1245620/library_hero_blur.jpg"><img src="https://steamloopback.host/assets/1912410/x/library_hero_blur.jpg"><div class="gpfocus"><img src="https://steamloopback.host/assets/1912410/h/library_capsule.jpg"></div>';
    expect(selectedAppIdIn(home)).toBe("1912410");
    home.querySelector(".gpfocus")!.innerHTML = "<span>No art</span>";
    expect(selectedAppIdIn(home)).toBeNull();
    home.querySelector(".gpfocus")!.innerHTML = '<img src="https://steamloopback.host/customimages/3141592653p.png">';
    expect(selectedAppIdIn(home)).toBe("3141592653");
  });

  it("tells store games from non-Steam shortcuts", () => {
    expect(isStoreApp("1245620")).toBe(true);
    expect(isStoreApp("3141592653")).toBe(false);
  });
});

describe("neighborAppIdsIn", () => {
  it("returns the games on each side of the focused tile, the next one first", () => {
    const row = document.createElement("div");
    row.innerHTML = ["10", "20", "30"].map((id) => `<div role="listitem"${id === "20" ? ' class="gpfocus"' : ""}><img src="https://steamloopback.host/assets/${id}/library_600x900.jpg"></div>`).join("");
    expect(neighborAppIdsIn(row)).toEqual(["30", "10"]);
  });

  it("returns nothing without a focused tile", () => {
    expect(neighborAppIdsIn(document.createElement("div"))).toEqual([]);
  });
});
