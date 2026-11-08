// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { installedGameAppIds, isStoreApp, libraryHeroUrl, neighborAppIdsIn, selectedAppIdFromHero, selectedAppIdIn } from "./librarySources";

describe("library sources", () => {
  afterEach(() => {
    delete (globalThis as { collectionStore?: unknown }).collectionStore;
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
    document.body.append(home);
    expect(selectedAppIdIn(home)).toBe("1912410");
    home.querySelector(".gpfocus")!.innerHTML = "<span>No art</span>";
    expect(selectedAppIdIn(home)).toBeNull();
    home.querySelector(".gpfocus")!.innerHTML = '<img src="https://steamloopback.host/customimages/3141592653p.png">';
    expect(selectedAppIdIn(home)).toBe("3141592653");
  });

  it("a carousel hidden under a theme's own Home selects nothing", () => {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = '<div class="carousel"><img src="https://steamloopback.host/assets/413150/library_hero_blur.jpg"></div>';
    document.body.append(wrapper);
    const carousel = wrapper.querySelector(".carousel");
    expect(selectedAppIdIn(carousel)).toBe("413150");
    for (const hide of ["opacity: 0", "visibility: hidden", "display: none"]) {
      wrapper.setAttribute("style", hide);
      expect(selectedAppIdIn(carousel)).toBeNull();
    }
    wrapper.remove();
    expect(selectedAppIdIn(carousel)).toBeNull();
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
