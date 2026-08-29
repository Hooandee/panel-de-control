// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { HORIZON_DOSSIER_CSS } from "./horizonDossierCss";
import { startHorizonDossier } from "./horizonDossier";

describe("Horizon dossier CSS", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-pdc-theme-runtime");
    document.documentElement.removeAttribute("data-pdc-steam-surface");
    document.documentElement.removeAttribute("data-pdc-motion");
    document.body.innerHTML = "";
    document.head.innerHTML = "";
  });

  it("wins over the verified CSS Loader detail rules without touching unmarked controls", () => {
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcSteamSurface = "game-details";
    document.body.innerHTML = `
      <main id="Main" data-pdc-horizon-dossier="true">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <div role="button" class="gpfocus">Play</div>
        <section role="tabpanel">
          <div role="button">Marked</div>
        </section>
        <div role="button" id="unmarked">Native</div>
      </main>`;
    const runtime = document.createElement("style");
    runtime.textContent = HORIZON_DOSSIER_CSS;
    document.head.append(runtime);
    const cssLoader = document.createElement("style");
    cssLoader.textContent = `
      html:root:has(#Main [role="tab"][aria-controls$="GameInfo_Content"]) #Main {
        background: linear-gradient(90deg, red, blue) !important;
      }
      #Main:has([role="tab"][aria-controls$="GameInfo_Content"]) [role="button"]:not(#header *) {
        background: linear-gradient(145deg, red, blue) !important;
      }
      #Main:has([role="tab"][aria-controls$="GameInfo_Content"]) [role="button"].gpfocus:not(#header *) {
        background: linear-gradient(112deg, red, blue) !important;
      }
    `;
    document.head.append(cssLoader);
    const main = document.getElementById("Main") as HTMLElement;
    const rail = main.querySelector("nav") as HTMLElement;
    const play = main.querySelector(".gpfocus") as HTMLElement;
    rail.getBoundingClientRect = () => new DOMRect(198, 364, 626, 58);
    play.getBoundingClientRect = () => new DOMRect(29, 298, 210, 48);
    const dossier = startHorizonDossier(document);
    expect(dossier.show(main, "https://cdn.example/selected.jpg")).toBe(true);

    expect(getComputedStyle(main).backgroundImage).toContain("180deg");
    expect(getComputedStyle(document.querySelector('[data-pdc-dossier-primary-action]')!).backgroundImage).toContain("108deg");
    expect(getComputedStyle(document.querySelector('[data-pdc-dossier-card]')!).backgroundImage).toContain("112deg");
    expect(getComputedStyle(document.getElementById("unmarked")!).backgroundImage).toContain("145deg");
    dossier.dispose();
  });

  it("removes dossier duration and delay when Steam requests reduced motion", () => {
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcSteamSurface = "game-details";
    document.documentElement.dataset.pdcMotion = "reduced";
    document.body.innerHTML = `
      <main id="Main">
        <img src="https://cdn.example/library_hero.jpg">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <div role="button">Play</div>
        <section role="tabpanel"><div role="button">Activity</div></section>
      </main>`;
    const runtime = document.createElement("style");
    runtime.textContent = HORIZON_DOSSIER_CSS;
    document.head.append(runtime);
    const cssLoader = document.createElement("style");
    cssLoader.textContent = `
      html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-steam-surface="game-details"]
      #Main[data-pdc-horizon-dossier="true"] [data-pdc-dossier-hero="true"] {
        animation-delay: 80ms !important;
        animation-duration: 220ms !important;
      }
    `;
    document.head.append(cssLoader);
    const main = document.getElementById("Main") as HTMLElement;
    const rail = main.querySelector("nav") as HTMLElement;
    const play = main.querySelector('[role="button"]') as HTMLElement;
    rail.getBoundingClientRect = () => new DOMRect(198, 364, 626, 58);
    play.getBoundingClientRect = () => new DOMRect(29, 298, 210, 48);
    const dossier = startHorizonDossier(document);
    expect(dossier.show(main)).toBe(true);

    const animated = [
      main,
      document.querySelector('[data-pdc-dossier-hero]'),
      document.querySelector('[data-pdc-dossier-tabs]'),
      document.querySelector('[data-pdc-dossier-primary-action]'),
      document.querySelector('[data-pdc-dossier-content]'),
    ];
    for (const element of animated) {
      const style = getComputedStyle(element!);
      expect(
        parseFloat(style.animationDuration),
        element?.getAttribute("data-pdc-dossier-hero") !== null ? "hero" : element?.id || element?.tagName,
      ).toBeLessThanOrEqual(.001);
      expect(parseFloat(style.animationDelay)).toBe(0);
    }
    dossier.dispose();
  });

  it("removes native full-panel compositing filters inside the dossier", () => {
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcSteamSurface = "game-details";
    document.body.innerHTML = `
      <main id="Main" data-pdc-horizon-dossier="true">
        <img id="native-backdrop" alt="" style="backdrop-filter: blur(24px); filter: saturate(1)">
      </main>`;
    const runtime = document.createElement("style");
    runtime.textContent = HORIZON_DOSSIER_CSS;
    document.head.append(runtime);

    const style = getComputedStyle(document.getElementById("native-backdrop")!);
    expect(style.backdropFilter).toBe("none");
    expect(style.filter).toBe("none");
  });
});
