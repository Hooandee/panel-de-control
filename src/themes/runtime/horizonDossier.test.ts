// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import { startHorizonDossier } from "./horizonDossier";

function detailsMain(): HTMLElement {
  document.body.innerHTML = `
    <main id="Main">
      <section data-hero><img src="https://cdn.example/library_hero.jpg"></section>
      <section data-actions><div role="button" class="gpfocus" aria-label="Play" tabindex="0">Play</div></section>
      <nav data-tabs>
        <div role="tab" aria-controls="Tabs_WhatsNew_Content" aria-selected="true" tabindex="0">Activity</div>
        <div role="tab" aria-controls="Tabs_GameInfo_Content" aria-selected="false" tabindex="-1">Details</div>
      </nav>
      <div role="button" data-utility style="backdrop-filter: blur(14px)">Utility</div>
      <section role="tabpanel">
        <div role="button" tabindex="0">Activity card</div>
      </section>
    </main>`;
  const main = document.getElementById("Main") as HTMLElement;
  const rail = main.querySelector("[data-tabs]") as HTMLElement;
  const primary = main.querySelector("[data-actions] [role=button]") as HTMLElement;
  rail.getBoundingClientRect = () => new DOMRect(198, 364, 626, 58);
  primary.getBoundingClientRect = () => new DOMRect(29, 298, 210, 48);
  return main;
}

describe("Horizon dossier", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("marks a verified Steam details surface without changing its controls", () => {
    const main = detailsMain();
    const play = main.querySelector('[aria-label="Play"]') as HTMLElement;
    const infoTab = main.querySelector('[aria-controls$="GameInfo_Content"]') as HTMLElement;
    const utility = main.querySelector("[data-utility]") as HTMLElement;
    const playParent = play.parentElement;
    const tabParent = infoTab.parentElement;
    const dossier = startHorizonDossier(document);

    expect(dossier.show(main)).toBe(true);

    const host = document.getElementById("pdc-horizon-dossier");
    expect(host?.getAttribute("aria-hidden")).toBe("true");
    expect(getComputedStyle(host!).pointerEvents).toBe("none");
    expect(host?.querySelector('[data-pdc-dossier-cover="true"]')).toBeTruthy();
    expect(host?.querySelector('[data-pdc-dossier-panel-frame="true"]')).toBeTruthy();
    expect(host?.querySelectorAll("[data-pdc-dossier-orbit-node]")).toHaveLength(3);
    expect(host?.style.getPropertyValue("--pdc-dossier-artwork")).toContain("library_hero.jpg");
    expect(main.dataset.pdcHorizonDossier).toBe("true");
    expect(main.querySelector("[data-hero]")?.querySelector("img")?.dataset.pdcDossierHero).toBe("true");
    expect(main.querySelector("[data-tabs]")?.getAttribute("data-pdc-dossier-tabs")).toBe("true");
    expect(play.dataset.pdcDossierPrimaryAction).toBe("true");
    expect(main.querySelector('[role="tabpanel"]')?.getAttribute("data-pdc-dossier-content")).toBe("true");
    expect(main.querySelector('[role="tabpanel"] [role="button"]')?.getAttribute("data-pdc-dossier-card")).toBe("true");
    expect(play.parentElement).toBe(playParent);
    expect(infoTab.parentElement).toBe(tabParent);
    expect(play.getAttribute("role")).toBe("button");
    expect(play.getAttribute("tabindex")).toBe("0");
    expect(infoTab.getAttribute("aria-selected")).toBe("false");
    expect(utility.style.getPropertyValue("backdrop-filter")).toBe("none");
    expect(utility.style.getPropertyPriority("backdrop-filter")).toBe("important");

    dossier.clear();
    expect(document.getElementById("pdc-horizon-dossier")).toBeNull();
    expect(main.querySelector("[data-pdc-dossier-hero]")).toBeNull();
    expect(main.hasAttribute("data-pdc-horizon-dossier")).toBe(false);
    expect(play.parentElement).toBe(playParent);
    expect(utility.style.getPropertyValue("backdrop-filter")).toBe("blur(14px)");
    expect(utility.style.getPropertyPriority("backdrop-filter")).toBe("");
    dossier.dispose();
  });

  it("uses a verified selected artwork and preserves Steam's own animation style", () => {
    const main = detailsMain();
    main.style.animation = "steam-native 180ms ease";
    const dossier = startHorizonDossier(document);

    expect(dossier.show(main, "https://cdn.example/selected.jpg")).toBe(true);
    expect(document.getElementById("pdc-horizon-dossier")?.style.getPropertyValue("--pdc-dossier-artwork"))
      .toContain("selected.jpg");
    expect(main.style.animation).toBe("steam-native 180ms ease");

    dossier.dispose();
    expect(main.style.animation).toBe("steam-native 180ms ease");
  });

  it("fails open when neither selected artwork nor a safe native hero is available", () => {
    const main = detailsMain();
    main.querySelector("img")?.remove();
    const dossier = startHorizonDossier(document);

    expect(dossier.show(main, "javascript:alert(1)")).toBe(false);
    expect(document.getElementById("pdc-horizon-dossier")).toBeNull();
    expect(main.hasAttribute("data-pdc-horizon-dossier")).toBe(false);
    dossier.dispose();
  });

  it("fails open for partial or ambiguous Steam details markup", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="tab" aria-controls="A_GameInfo_Content"></div>
        <div role="tab" aria-controls="B_GameInfo_Content"></div>
      </main>`;
    const main = document.getElementById("Main") as HTMLElement;
    const dossier = startHorizonDossier(document);

    expect(dossier.show(main)).toBe(false);
    expect(document.getElementById("pdc-horizon-dossier")).toBeNull();
    expect(main.attributes).toHaveLength(1);
    dossier.dispose();
  });

  it("moves cleanly to a replacement Main and never duplicates its host", () => {
    const first = detailsMain();
    const second = first.cloneNode(true) as HTMLElement;
    const dossier = startHorizonDossier(document);
    expect(dossier.show(first)).toBe(true);
    expect(dossier.show(first)).toBe(true);
    expect(document.querySelectorAll("#pdc-horizon-dossier")).toHaveLength(1);

    first.replaceWith(second);
    expect(dossier.show(second)).toBe(true);
    expect(first.hasAttribute("data-pdc-horizon-dossier")).toBe(false);
    expect(second.dataset.pdcHorizonDossier).toBe("true");
    expect(document.querySelectorAll("#pdc-horizon-dossier")).toHaveLength(1);
    dossier.dispose();
    expect(second.hasAttribute("data-pdc-horizon-dossier")).toBe(false);
  });

  it("accepts the separate element realm used by Steam Big Picture", () => {
    const steamWindow = new Window();
    steamWindow.document.body.innerHTML = `
      <main id="Main">
        <img src="https://cdn.example/library_hero.jpg">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <section role="tabpanel"><div role="button">Activity</div></section>
      </main>`;
    const hostHTMLElement = globalThis.HTMLElement;
    Object.defineProperty(globalThis, "HTMLElement", {
      configurable: true,
      value: class HostRealmHTMLElement {},
    });
    try {
      const dossier = startHorizonDossier(steamWindow.document as unknown as Document);
      expect(dossier.show(steamWindow.document.getElementById("Main")!)).toBe(true);
      expect(steamWindow.document.getElementById("pdc-horizon-dossier")).toBeTruthy();
      dossier.dispose();
    } finally {
      Object.defineProperty(globalThis, "HTMLElement", { configurable: true, value: hostHTMLElement });
      steamWindow.close();
    }
  });
});
