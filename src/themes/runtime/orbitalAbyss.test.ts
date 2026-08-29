// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { Window } from "happy-dom";

import { startOrbitalAbyss } from "./orbitalAbyss";
import { ORBITAL_ABYSS_CSS } from "./orbitalAbyssCss";

function libraryShelf(size = 11): HTMLElement[] {
  document.body.innerHTML = `
    <main id="Main">
      <div class="ReactVirtualized__Grid" data-preserve="viewport">
        <div role="list" class="ReactVirtualized__Grid__innerScrollContainer" data-preserve="list">
          ${Array.from({ length: size }, (_, index) => `
            <div role="listitem" data-id="game-${index}" style="--pdc-orbit-x: legacy-${index}">
              <div role="link" tabindex="0"><img src="https://cdn.example/${index}.jpg"></div>
            </div>`).join("")}
        </div>
      </div>
      <section data-steam-details>Steam details below the shelf</section>
    </main>`;
  return [...document.querySelectorAll<HTMLElement>('[role="listitem"]')];
}

function addSteamCopy(card: HTMLElement, title: string, meta: string): { title: HTMLElement; meta: HTMLElement } {
  card.insertAdjacentHTML("beforeend", `
    <div>
      <div data-fixture-title style="display: flex; font-size: 18px; font-weight: 800; visibility: visible">${title}</div>
      <div data-fixture-meta style="display: block; font-size: 12px; font-weight: 700; visibility: visible">${meta}</div>
    </div>`);
  const titles = card.querySelectorAll<HTMLElement>("[data-fixture-title]");
  const metas = card.querySelectorAll<HTMLElement>("[data-fixture-meta]");
  return {
    title: titles[titles.length - 1],
    meta: metas[metas.length - 1],
  };
}

function nextFrame(): Promise<void> {
  return new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
}

async function nextMutationFrame(): Promise<void> {
  await Promise.resolve();
  await nextFrame();
}

describe("startOrbitalAbyss", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
    document.documentElement.removeAttribute("data-pdc-orbit-active");
    document.documentElement.removeAttribute("data-pdc-theme-runtime");
    document.documentElement.removeAttribute("data-pdc-grid-scene");
    document.head.querySelectorAll("style").forEach((style) => style.remove());
  });

  it("turns the focused Steam shelf into a nine-card orbital scene", () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    expect(scene.moveTo(cards[5])).toBe(true);

    expect(document.documentElement.dataset.pdcOrbitActive).toBe("true");
    expect(document.getElementById("pdc-orbital-abyss")).toBeTruthy();
    expect(document.querySelectorAll("[data-pdc-orbit-ring]")).toHaveLength(3);
    expect(document.querySelector("[data-pdc-orbit-core]")).toBeNull();
    expect(document.querySelector("[data-pdc-orbit-horizon]")).toBeTruthy();
    expect(document.querySelector('[role="list"]')?.getAttribute("data-pdc-orbit-list")).toBe("true");
    expect(document.querySelector(".ReactVirtualized__Grid")?.getAttribute("data-pdc-orbit-viewport")).toBe("true");
    expect(document.querySelectorAll('[data-pdc-orbit-visible="true"]')).toHaveLength(9);
    expect(cards[5].dataset.pdcOrbitSelected).toBe("true");
    expect(cards[5].style.getPropertyValue("--pdc-orbit-x")).toBe("50%");
    expect(cards[5].style.getPropertyValue("--pdc-orbit-y")).toBe("60%");
    expect(cards[0].dataset.pdcOrbitVisible).toBe("false");
  });

  it("gives arriving and departing cards separate rear gates", () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    expect(cards[1].dataset.pdcOrbitDistance).toBe("-4");
    expect(cards[1].style.getPropertyValue("--pdc-orbit-x")).toBe("42%");
    expect(cards[9].dataset.pdcOrbitDistance).toBe("4");
    expect(cards[9].style.getPropertyValue("--pdc-orbit-x")).toBe("58%");
  });

  it("hides only Steam's verified footer while the orbital scene is active", () => {
    const cards = libraryShelf();
    document.body.insertAdjacentHTML("beforeend", `
      <div id="Footer" data-preserve="steam-footer" style="visibility: visible">Controller hints</div>
      <div id="Footer-preview">Theme preview footer</div>`);
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    const footer = document.getElementById("Footer")!;
    expect(footer.dataset.pdcOrbitFooter).toBe("true");
    expect(getComputedStyle(footer).visibility).toBe("hidden");
    expect(document.getElementById("Footer-preview")?.hasAttribute("data-pdc-orbit-footer")).toBe(false);

    scene.clear();
    expect(footer.hasAttribute("data-pdc-orbit-footer")).toBe(false);
    expect(getComputedStyle(footer).visibility).toBe("visible");
    style.remove();
  });

  it("replaces Steam's rectangular focus outline with a rounded visible halo", () => {
    const cards = libraryShelf();
    const focus = cards[5].querySelector<HTMLElement>('[role="link"]')!;
    focus.classList.add("gpfocus");
    focus.style.setProperty("outline", "2px solid white");
    focus.style.setProperty("border-radius", "0px");
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    const focusedStyle = getComputedStyle(focus);
    expect(focusedStyle.outlineStyle).toBe("none");
    expect(focusedStyle.borderRadius).toBe("20px");
    expect(focusedStyle.boxShadow).toContain("rgba(98,247,255");

    scene.clear();
    expect(getComputedStyle(focus).outlineStyle).toBe("solid");
    style.remove();
  });

  it("neutralizes the base theme accent bar while the orbital scene is active", () => {
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);

    const selectedPseudoRule = [...(style.sheet?.cssRules ?? [])]
      .filter((rule): rule is CSSStyleRule => rule instanceof CSSStyleRule)
      .find((rule) => rule.selectorText.includes('[data-pdc-orbit-selected="true"]::after'));

    expect(selectedPseudoRule?.style.content).toBe("none");
    expect(selectedPseudoRule?.style.display).toBe("none");
    expect(selectedPseudoRule?.style.background).toBe("");
  });

  it("keeps the galaxy without the Obsidian heading", () => {
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);

    const stagePseudoRules = [...(style.sheet?.cssRules ?? [])]
      .filter((rule): rule is CSSStyleRule => rule instanceof CSSStyleRule)
      .filter((rule) => rule.selectorText.includes("#pdc-orbital-abyss::"));

    expect(stagePseudoRules.some((rule) => rule.selectorText.endsWith("::before"))).toBe(true);
    expect(stagePseudoRules.some((rule) => rule.selectorText.endsWith("::after"))).toBe(false);
  });

  it("clips every orbital capsule to rounded corners instead of only rounding its image", () => {
    const cards = libraryShelf();
    const peerLink = cards[4].querySelector<HTMLElement>('[role="link"]')!;
    peerLink.style.setProperty("border-radius", "0px");
    peerLink.style.setProperty("overflow", "visible");
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    expect(getComputedStyle(peerLink).borderRadius).toBe("18px");
    expect(getComputedStyle(peerLink).overflow).toBe("hidden");
  });

  it("renders the selected Steam copy in a centered orbital caption", () => {
    const cards = libraryShelf();
    const native = addSteamCopy(cards[5], "Final Fantasy VII Remake", "Tiempo de juego: 42,9 h");
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    const title = document.querySelector<HTMLElement>('[data-pdc-orbit-caption-title="true"]');
    const meta = document.querySelector<HTMLElement>('[data-pdc-orbit-caption-meta="true"]');
    expect(title).toBeTruthy();
    expect(meta).toBeTruthy();
    if (!title || !meta) return;
    expect(title.textContent).toBe("Final Fantasy VII Remake");
    expect(meta.textContent).toBe("Tiempo de juego: 42,9 h");
    expect(getComputedStyle(title).textAlign).toBe("center");
    expect(getComputedStyle(title).fontFamily).toContain("PDC Oxanium");
    expect(getComputedStyle(title).overflowWrap).toBe("anywhere");
    expect(native.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(native.meta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(getComputedStyle(native.title).visibility).toBe("visible");
    expect(getComputedStyle(native.title).opacity).toBe("0");
  });

  it.each([
    ["play", "play"],
    ["download", "download"],
    [null, undefined],
  ] as const)("renders the verified %s action before the title", (action, expected) => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Action game", "Ready");
    const scene = startOrbitalAbyss(document, { resolveAction: () => action });

    scene.moveTo(cards[5]);

    const title = document.querySelector<HTMLElement>('[data-pdc-orbit-caption-title="true"]')!;
    const icon = title.querySelector<SVGElement>('[data-pdc-orbit-caption-icon="true"]');
    const label = title.querySelector<HTMLElement>('[data-pdc-orbit-caption-label="true"]');
    expect(label?.textContent).toBe("Action game");
    expect(title.firstElementChild).toBe(icon);
    expect(icon?.dataset.pdcOrbitCaptionAction).toBe(expected);
    expect(icon?.getAttribute("aria-hidden")).toBe("true");
    expect(icon?.hasAttribute("tabindex")).toBe(false);
    expect(icon?.hasAttribute("hidden")).toBe(action === null);
  });

  it.each([
    [
      "play",
      `<div data-native-action style="display: flex">
        <svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg>
      </div>`,
    ],
    [
      "download",
      `<div data-native-action style="display: flex">
        <svg viewBox="0 0 36 36">
          <path d="M29 23V27H7V23H2V32H34V23H29Z"></path>
          <path d="M20 14.1716L24.5858 9.58578L27.4142 12.4142L18 21.8284L8.58582 12.4142L11.4142 9.58578L16 14.1715V2H20V14.1716Z"></path>
        </svg>
      </div>`,
    ],
  ] as const)("removes Steam's verified native %s footprint and restores it on clear", (action, fixture) => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Native action game", "Ready");
    cards[5].insertAdjacentHTML("beforeend", fixture);
    cards[5].insertAdjacentHTML("beforeend", `
      <div data-unrelated-badge style="display: flex">
        <svg viewBox="0 0 36 36"><path d="M1 1H35V35H1Z"></path></svg>
      </div>`);
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const nativeAction = cards[5].querySelector<HTMLElement>("[data-native-action]")!;
    const nativePayload = nativeAction.querySelector<SVGElement>("svg")!;
    const unrelatedBadge = cards[5].querySelector<HTMLElement>("[data-unrelated-badge]")!;
    const scene = startOrbitalAbyss(document, { resolveAction: () => action });

    scene.moveTo(cards[5]);

    expect(nativePayload.getAttribute("data-pdc-orbit-native-action")).toBe("true");
    expect(getComputedStyle(nativePayload).display).toBe("none");
    expect(nativeAction.getAttribute("data-pdc-orbit-native-action")).toBe("true");
    expect(nativeAction.getAttribute("role")).toBeNull();
    expect(getComputedStyle(nativeAction).display).toBe("none");
    expect(unrelatedBadge.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(getComputedStyle(unrelatedBadge).display).toBe("flex");

    scene.clear();
    expect(nativePayload.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(getComputedStyle(nativePayload).display).not.toBe("none");
  });

  it("removes the decorative download footprint when Steam also renders an interactive duplicate", () => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Duplicated download action", "Ready");
    cards[5].insertAdjacentHTML("beforeend", `
      <div role="button" data-download-button class="Focusable" style="display: none; opacity: 0">
        <svg viewBox="0 0 36 36">
          <path d="M29 23V27H7V23H2V32H34V23H29Z"></path>
          <path d="M20 14.1716L24.5858 9.58578L27.4142 12.4142L18 21.8284L8.58582 12.4142L11.4142 9.58578L16 14.1715V2H20V14.1716Z"></path>
        </svg>
      </div>
      <div data-download-row style="display: flex">
        <div data-download-status style="display: block">
          <svg viewBox="0 0 36 36">
            <path d="M29 23V27H7V23H2V32H34V23H29Z"></path>
            <path d="M20 14.1716L24.5858 9.58578L27.4142 12.4142L18 21.8284L8.58582 12.4142L11.4142 9.58578L16 14.1715V2H20V14.1716Z"></path>
          </svg>
        </div>
      </div>`);
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    const interactive = cards[5].querySelector<HTMLElement>("[data-download-button]")!;
    const interactiveSvg = interactive.querySelector<SVGElement>("svg")!;
    const decorative = cards[5].querySelector<HTMLElement>("[data-download-status]")!;
    const decorativeSvg = decorative.querySelector<SVGElement>("svg")!;
    const scene = startOrbitalAbyss(document, { resolveAction: () => "download" });

    scene.moveTo(cards[5]);

    expect(interactive.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(interactiveSvg.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(interactive.getAttribute("role")).toBe("button");
    expect(decorative.getAttribute("data-pdc-orbit-native-action")).toBe("true");
    expect(decorativeSvg.getAttribute("data-pdc-orbit-native-action")).toBe("true");
    expect(getComputedStyle(decorative).display).toBe("none");

    scene.clear();
    expect(decorative.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(decorativeSvg.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(getComputedStyle(decorative).display).toBe("block");
  });

  it("removes a verified native action that Steam inserts after focus settles", async () => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Late native action", "Ready");
    const scene = startOrbitalAbyss(document, { resolveAction: () => "play" });

    scene.moveTo(cards[5]);
    for (let frame = 0; frame < 6; frame += 1) await nextFrame();
    cards[5].insertAdjacentHTML("beforeend", `
      <div data-native-action>
        <svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg>
      </div>`);
    await nextMutationFrame();

    expect(cards[5].querySelector<SVGElement>("[data-native-action] svg")?.dataset.pdcOrbitNativeAction)
      .toBe("true");
  });

  it("fails open when Steam renders more than one matching native action", () => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Ambiguous native action", "Ready");
    const fixture = `
      <div data-native-action>
        <svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg>
      </div>`;
    cards[5].insertAdjacentHTML("beforeend", fixture + fixture);
    const scene = startOrbitalAbyss(document, { resolveAction: () => "play" });

    scene.moveTo(cards[5]);

    expect(cards[5].querySelector("[data-pdc-orbit-native-action]")).toBeNull();
  });

  it.each([
    ["button", '<button data-native-wrapper><svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg></button>'],
    ["link", '<a href="#details" data-native-wrapper><svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg></a>'],
    ["focusable div", '<div role="button" tabindex="0" data-native-wrapper><svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg></div>'],
    ["Steam Focusable div", '<div class="Focusable" data-native-wrapper><svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg></div>'],
  ] as const)("preserves an implicitly interactive native play %s", (_kind, fixture) => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Interactive native action", "Ready");
    cards[5].insertAdjacentHTML("beforeend", fixture);
    const wrapper = cards[5].querySelector<HTMLElement>("[data-native-wrapper]")!;
    const svg = wrapper.querySelector<SVGElement>("svg")!;
    const scene = startOrbitalAbyss(document, { resolveAction: () => "play" });

    scene.moveTo(cards[5]);

    expect(wrapper.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
    expect(svg.getAttribute("data-pdc-orbit-native-action")).toBe("true");
  });

  it("fails open when Steam makes the verified download SVG itself interactive", () => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Interactive download action", "Ready");
    cards[5].insertAdjacentHTML("beforeend", `
      <div role="button">
        <svg role="button" tabindex="0" viewBox="0 0 36 36">
          <path d="M29 23V27H7V23H2V32H34V23H29Z"></path>
          <path d="M20 14.1716L24.5858 9.58578L27.4142 12.4142L18 21.8284L8.58582 12.4142L11.4142 9.58578L16 14.1715V2H20V14.1716Z"></path>
        </svg>
      </div>`);
    const scene = startOrbitalAbyss(document, { resolveAction: () => "download" });

    scene.moveTo(cards[5]);

    expect(cards[5].querySelector("[data-pdc-orbit-native-action]")).toBeNull();
  });

  it("restores a native action marker when Steam changes its verified geometry", async () => {
    const cards = libraryShelf();
    cards[5].dataset.id = "123";
    addSteamCopy(cards[5], "Reused native action", "Ready");
    cards[5].insertAdjacentHTML("beforeend", `
      <div data-native-action>
        <svg viewBox="0 0 36 36"><path d="M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z"></path></svg>
      </div>`);
    const nativeAction = cards[5].querySelector<SVGElement>("[data-native-action] svg")!;
    const scene = startOrbitalAbyss(document, { resolveAction: () => "play" });

    scene.moveTo(cards[5]);
    expect(nativeAction.dataset.pdcOrbitNativeAction).toBe("true");
    nativeAction.querySelector("path")?.setAttribute("d", "M1 1H35V35H1Z");
    await nextMutationFrame();

    expect(nativeAction.hasAttribute("data-pdc-orbit-native-action")).toBe(false);
  });

  it.each([
    [true, "play"],
    [false, "download"],
    [undefined, undefined],
  ] as const)("maps Steam's installed=%s state without guessing", (installed, expected) => {
    const previousAppStore = Object.getOwnPropertyDescriptor(window, "appStore");
    Object.defineProperty(window, "appStore", {
      configurable: true,
      value: {
        m_mapApps: {
          get: (appid: number) => appid === 123 ? { local_per_client_data: { installed } } : undefined,
        },
      },
    });
    try {
      const cards = libraryShelf();
      cards[5].dataset.id = "123";
      addSteamCopy(cards[5], "Steam state game", "Ready");
      const scene = startOrbitalAbyss(document);

      scene.moveTo(cards[5]);

      const icon = document.querySelector<SVGElement>('[data-pdc-orbit-caption-icon="true"]');
      expect(icon?.dataset.pdcOrbitCaptionAction).toBe(expected);
      expect(icon?.hasAttribute("hidden")).toBe(expected === undefined);
    } finally {
      if (previousAppStore) Object.defineProperty(window, "appStore", previousAppStore);
      else delete (window as unknown as { appStore?: unknown }).appStore;
    }
  });

  it.each([
    [{ app_type: 1, local_per_client_data: { is_available_on_current_platform: true } }, "download"],
    [{ app_type: 4, local_per_client_data: { is_available_on_current_platform: true } }, undefined],
    [{ app_type: 1, local_per_client_data: { is_available_on_current_platform: false } }, undefined],
  ] as const)("maps Steam's verified uninstalled overview without mislabelling tools", (overview, expected) => {
    const previousAppStore = Object.getOwnPropertyDescriptor(window, "appStore");
    Object.defineProperty(window, "appStore", {
      configurable: true,
      value: { m_mapApps: { get: () => overview } },
    });
    try {
      const cards = libraryShelf();
      cards[5].dataset.id = "123";
      addSteamCopy(cards[5], "Steam overview game", "Ready");
      const scene = startOrbitalAbyss(document);

      scene.moveTo(cards[5]);

      const icon = document.querySelector<SVGElement>('[data-pdc-orbit-caption-icon="true"]');
      expect(icon?.dataset.pdcOrbitCaptionAction).toBe(expected);
      expect(icon?.hasAttribute("hidden")).toBe(expected === undefined);
    } finally {
      if (previousAppStore) Object.defineProperty(window, "appStore", previousAppStore);
      else delete (window as unknown as { appStore?: unknown }).appStore;
    }
  });

  it("hides every verified Steam title copy, including off-screen duplicates", () => {
    const cards = libraryShelf();
    const first = addSteamCopy(cards[5], "Duplicated game", "Played recently");
    const duplicate = addSteamCopy(cards[5], "Duplicated game", "Played recently");
    duplicate.title.style.display = "none";
    duplicate.title.style.fontSize = "14px";
    duplicate.title.style.fontWeight = "400";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);

    expect(first.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(duplicate.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(first.meta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(duplicate.meta.dataset.pdcOrbitNativeCopy).toBe("true");
  });

  it("hides a duplicate title Steam adds after the scene is already stable", async () => {
    const cards = libraryShelf();
    addSteamCopy(cards[5], "Stable game", "Stable metadata");
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    for (let frame = 0; frame < 6; frame += 1) await nextFrame();
    const duplicate = addSteamCopy(cards[5], "Stable game", "Stable metadata");
    await nextMutationFrame();

    expect(duplicate.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(duplicate.meta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Stable game");
  });

  it("updates the orbital caption without leaving the previous Steam copy hidden", () => {
    const cards = libraryShelf();
    const first = addSteamCopy(cards[5], "First game", "Played first");
    const second = addSteamCopy(cards[6], "Second game", "Played second");
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    scene.moveTo(cards[6]);

    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent).toBe("Second game");
    expect(first.title.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
    expect(first.meta.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
    expect(second.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(second.meta.dataset.pdcOrbitNativeCopy).toBe("true");

    scene.clear();
    expect(document.querySelector("[data-pdc-orbit-caption]")).toBeNull();
    expect(second.title.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
    expect(second.meta.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
  });

  it("captures Steam copy rendered just after the focus event", async () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    const native = addSteamCopy(cards[5], "Late Steam title", "Late Steam metadata");
    for (let frame = 0; frame < 4; frame += 1) await nextFrame();

    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Late Steam title");
    expect(native.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(native.meta.dataset.pdcOrbitNativeCopy).toBe("true");
  });

  it("captures Steam copy inserted after the bounded startup retries", async () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    for (let frame = 0; frame < 6; frame += 1) await nextFrame();
    const native = addSteamCopy(cards[5], "Very late Steam title", "Very late metadata");
    await nextMutationFrame();

    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Very late Steam title");
    expect(native.title.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(native.meta.dataset.pdcOrbitNativeCopy).toBe("true");
  });

  it("tracks character data changes in the selected Steam card", async () => {
    const cards = libraryShelf();
    const native = addSteamCopy(cards[5], "Original title", "Original metadata");
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    native.title.firstChild!.textContent = "Updated title";
    native.meta.firstChild!.textContent = "Updated metadata";
    await nextMutationFrame();

    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Updated title");
    expect(document.querySelector('[data-pdc-orbit-caption-meta="true"]')?.textContent)
      .toBe("Updated metadata");
  });

  it("disconnects the previous card observer when focus moves", async () => {
    const cards = libraryShelf();
    addSteamCopy(cards[5], "First observed", "First metadata");
    addSteamCopy(cards[6], "Second observed", "Second metadata");
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    scene.moveTo(cards[6]);
    const stale = addSteamCopy(cards[5], "Stale mutation", "Must stay visible");
    await nextMutationFrame();

    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Second observed");
    expect(stale.title.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
    expect(stale.meta.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
  });

  it("coalesces a burst of selected-card mutations into one animation frame", async () => {
    const cards = libraryShelf();
    const native = addSteamCopy(cards[5], "Burst title", "Burst metadata");
    const queued: FrameRequestCallback[] = [];
    const requestFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      queued.push(callback);
      return queued.length;
    });
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    for (let index = 0; index < 100; index += 1) native.title.firstChild!.textContent = `Burst ${index}`;
    await Promise.resolve();

    expect(queued).toHaveLength(1);
    queued[0](performance.now());
    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent).toBe("Burst 99");
    requestFrame.mockRestore();
  });

  it("keeps the scene usable when the card observer cannot be activated", () => {
    const NativeObserver = window.MutationObserver;
    class RejectingObserver {
      disconnect(): void {}
      observe(): void {
        throw new Error("observer rejected");
      }
      takeRecords(): MutationRecord[] {
        return [];
      }
    }
    Object.defineProperty(window, "MutationObserver", { configurable: true, value: RejectingObserver });
    try {
      const cards = libraryShelf();
      const native = addSteamCopy(cards[5], "Fallback title", "Fallback metadata");
      const scene = startOrbitalAbyss(document);

      expect(scene.moveTo(cards[5])).toBe(true);
      expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
        .toBe("Fallback title");
      expect(native.title.dataset.pdcOrbitNativeCopy).toBe("true");
    } finally {
      Object.defineProperty(window, "MutationObserver", { configurable: true, value: NativeObserver });
    }
  });

  it("keeps syncing when Steam renders metadata after the title", async () => {
    const cards = libraryShelf();
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    cards[5].insertAdjacentHTML("beforeend", `
      <div><div data-fixture-title style="display: flex; font-size: 18px; font-weight: 800; visibility: visible">
        Title before metadata
      </div></div>`);
    const nativeTitle = cards[5].querySelector<HTMLElement>("[data-fixture-title]")!;
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    await nextFrame();
    expect(document.querySelector('[data-pdc-orbit-caption-title="true"]')?.textContent)
      .toBe("Title before metadata");
    nativeTitle.insertAdjacentHTML("afterend", `
      <div data-fixture-meta style="display: block; font-size: 12px; font-weight: 700; visibility: visible">
        Metadata one frame later
      </div>`);
    for (let frame = 0; frame < 3; frame += 1) await nextFrame();

    const nativeMeta = cards[5].querySelector<HTMLElement>("[data-fixture-meta]")!;
    expect(document.querySelector('[data-pdc-orbit-caption-meta="true"]')?.textContent)
      .toBe("Metadata one frame later");
    expect(nativeTitle.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(nativeMeta.dataset.pdcOrbitNativeCopy).toBe("true");
  });

  it("hides metadata Steam inserts before the next paint", async () => {
    const cards = libraryShelf();
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    cards[5].insertAdjacentHTML("beforeend", `
      <div><div data-fixture-title style="display: flex; font-size: 18px; font-weight: 800; visibility: visible">
        Immediate title
      </div></div>`);
    const nativeTitle = cards[5].querySelector<HTMLElement>("[data-fixture-title]")!;
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    const queued: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      queued.push(callback);
      return queued.length;
    });
    nativeTitle.insertAdjacentHTML("afterend", `
      <div data-fixture-meta style="display: block; font-size: 12px; font-weight: 700; visibility: visible">
        Immediate metadata
      </div>`);
    await Promise.resolve();

    const nativeMeta = cards[5].querySelector<HTMLElement>("[data-fixture-meta]")!;
    expect(queued).toHaveLength(1);
    expect(nativeMeta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(getComputedStyle(nativeMeta).opacity).toBe("0");

    nativeMeta.insertAdjacentHTML("afterend", `
      <div data-fixture-meta style="display: block; font-size: 12px; font-weight: 700; visibility: visible">
        Immediate metadata
      </div>`);
    await Promise.resolve();

    const duplicateMeta = cards[5].querySelectorAll<HTMLElement>("[data-fixture-meta]")[1];
    expect(queued).toHaveLength(1);
    expect(duplicateMeta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(getComputedStyle(duplicateMeta).opacity).toBe("0");
  });

  it("hides metadata when Steam reveals an existing node", async () => {
    const cards = libraryShelf();
    const style = document.createElement("style");
    style.textContent = `${ORBITAL_ABYSS_CSS}
      .fixture-meta-hidden { display: none; }
      .fixture-meta-visible { display: block; }`;
    document.head.append(style);
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcGridScene = "abyss";
    cards[5].insertAdjacentHTML("beforeend", `
      <div>
        <div data-fixture-title style="display: flex; font-size: 18px; font-weight: 800; visibility: visible">
          Revealed metadata game
        </div>
        <div data-fixture-meta class="fixture-meta-hidden" style="font-size: 12px; font-weight: 700; visibility: visible">
          Revealed metadata
        </div>
      </div>`);
    const nativeMeta = cards[5].querySelector<HTMLElement>("[data-fixture-meta]")!;
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    const queued: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      queued.push(callback);
      return queued.length;
    });
    nativeMeta.className = "fixture-meta-visible";
    await Promise.resolve();

    expect(queued).toHaveLength(1);
    expect(nativeMeta.dataset.pdcOrbitNativeCopy).toBe("true");
    expect(getComputedStyle(nativeMeta).opacity).toBe("0");
  });

  it("reapplies orbital geometry before reading Steam copy styles", () => {
    const cards = libraryShelf();
    addSteamCopy(cards[5], "First geometry", "First metadata");
    const second = addSteamCopy(cards[6], "Second geometry", "Second metadata");
    const scene = startOrbitalAbyss(document);
    const nativeGetComputedStyle = window.getComputedStyle.bind(window);
    const selectedGeometryAtRead: string[] = [];
    const computedStyle = vi.spyOn(window, "getComputedStyle").mockImplementation((element) => {
      if (element === second.title) {
        selectedGeometryAtRead.push(cards[6].style.getPropertyValue("--pdc-orbit-x"));
      }
      return nativeGetComputedStyle(element);
    });

    scene.moveTo(cards[5]);
    scene.moveTo(cards[6]);

    expect(selectedGeometryAtRead[0]).toBe("50%");
    computedStyle.mockRestore();
  });

  it("cancels delayed caption work when the scene is cleared", async () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    scene.clear();
    const native = addSteamCopy(cards[5], "Never copied", "Never hidden");
    for (let frame = 0; frame < 4; frame += 1) await nextFrame();

    expect(document.querySelector("[data-pdc-orbit-caption]")).toBeNull();
    expect(native.title.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
    expect(native.meta.hasAttribute("data-pdc-orbit-native-copy")).toBe(false);
  });

  it("rotates the same ring instead of recreating its stage on every focus move", () => {
    const cards = libraryShelf();
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    const stage = document.getElementById("pdc-orbital-abyss");
    const firstPhase = stage?.style.getPropertyValue("--pdc-orbit-phase");
    expect(stage?.style.getPropertyValue("--pdc-orbit-phase-reverse")).toBe("249deg");
    expect(stage?.style.getPropertyValue("--pdc-orbit-phase-offset")).toBe("-167deg");
    scene.moveTo(cards[6]);

    expect(document.getElementById("pdc-orbital-abyss")).toBe(stage);
    expect(stage?.style.getPropertyValue("--pdc-orbit-phase")).not.toBe(firstPhase);
    expect(cards[5].dataset.pdcOrbitSelected).toBeUndefined();
    expect(cards[6].dataset.pdcOrbitSelected).toBe("true");
  });

  it("switches shelves without leaving mutations on the previous virtualized list", () => {
    const first = libraryShelf(7);
    const main = document.getElementById("Main")!;
    main.insertAdjacentHTML("beforeend", `
      <div class="ReactVirtualized__Grid" id="second-viewport">
        <div role="list" id="second-list">
          ${Array.from({ length: 7 }, (_, index) => `<div role="listitem" data-id="other-${index}"></div>`).join("")}
        </div>
      </div>`);
    const second = [...document.querySelectorAll<HTMLElement>('#second-list > [role="listitem"]')];
    const scene = startOrbitalAbyss(document);

    scene.moveTo(first[3]);
    scene.moveTo(second[3]);

    expect(first.every((card) => !card.hasAttribute("data-pdc-orbit-card"))).toBe(true);
    expect(document.querySelector('[data-preserve="list"]')?.hasAttribute("data-pdc-orbit-list")).toBe(false);
    expect(second[3].dataset.pdcOrbitSelected).toBe("true");
    expect(document.getElementById("second-viewport")?.dataset.pdcOrbitViewport).toBe("true");
  });

  it("suppresses lower Steam shelves only while the orbital scene is active", () => {
    const cards = libraryShelf();
    document.getElementById("Main")?.insertAdjacentHTML("beforeend", `
      <div class="ReactVirtualized__Grid" id="news-shelf"><div role="list">
        <div role="listitem" data-id="news"></div>
      </div></div>`);
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    expect(document.getElementById("Main")?.dataset.pdcOrbitMain).toBe("true");
    expect(document.getElementById("news-shelf")?.dataset.pdcOrbitSuppressed).toBe("true");

    scene.clear();
    expect(document.getElementById("Main")?.hasAttribute("data-pdc-orbit-main")).toBe(false);
    expect(document.getElementById("news-shelf")?.hasAttribute("data-pdc-orbit-suppressed")).toBe(false);
  });

  it("restores every attribute and custom property exactly on clear and disposal", () => {
    const cards = libraryShelf();
    cards[5].dataset.pdcOrbitCard = "pre-existing";
    const scene = startOrbitalAbyss(document);

    scene.moveTo(cards[5]);
    scene.clear();

    expect(document.getElementById("pdc-orbital-abyss")).toBeNull();
    expect(document.documentElement.hasAttribute("data-pdc-orbit-active")).toBe(false);
    expect(cards[5].dataset.pdcOrbitCard).toBe("pre-existing");
    expect(cards[5].style.getPropertyValue("--pdc-orbit-x")).toBe("legacy-5");
    expect(document.querySelector('[data-preserve="list"]')?.getAttribute("data-preserve")).toBe("list");
    expect(document.querySelector('[data-preserve="list"]')?.hasAttribute("data-pdc-orbit-list")).toBe(false);

    scene.moveTo(cards[4]);
    scene.dispose();
    expect(document.getElementById("pdc-orbital-abyss")).toBeNull();
    expect(cards[4].style.getPropertyValue("--pdc-orbit-x")).toBe("legacy-4");
  });

  it("fails closed when focus is not backed by a Steam list or grid", () => {
    document.body.innerHTML = '<main id="Main"><button id="loose">Loose</button></main>';
    const scene = startOrbitalAbyss(document);

    expect(scene.moveTo(document.getElementById("loose")!)).toBe(false);
    expect(document.getElementById("pdc-orbital-abyss")).toBeNull();
    expect(document.documentElement.hasAttribute("data-pdc-orbit-active")).toBe(false);
  });

  it("supports Steam's all-games grid cells as well as home shelves", () => {
    document.body.innerHTML = `
      <main id="Main"><div role="grid">
        <div role="gridcell" data-id="one"></div>
        <div role="gridcell" data-id="two"><button>Two</button></div>
        <div role="gridcell" data-id="three"></div>
      </div></main>`;
    const scene = startOrbitalAbyss(document);

    expect(scene.moveTo(document.querySelector('[data-id="two"]')!)).toBe(true);
    expect(document.querySelector('[data-id="two"]')?.getAttribute("data-pdc-orbit-selected")).toBe("true");
    scene.dispose();
  });

  it("renders Download from Steam's real all-games grid semantics", () => {
    const previousAppStore = Object.getOwnPropertyDescriptor(window, "appStore");
    Object.defineProperty(window, "appStore", {
      configurable: true,
      value: {
        m_mapApps: {
          get: (appid: number) => appid === 1887840
            ? { app_type: 1, local_per_client_data: { is_available_on_current_platform: true } }
            : undefined,
        },
      },
    });
    try {
      document.body.innerHTML = `
        <main id="Main"><div role="grid">
          <div role="gridcell"><div role="link"><img src="/assets/10/library_600x900.jpg"></div></div>
          <div role="gridcell">
            <div role="link" aria-labelledby="grid-title grid-meta">
              <img src="/assets/1887840/library_600x900.jpg">
              <img role="presentation" src="/assets/1887840/library_600x900.jpg">
              <div id="grid-title" style="font-size: 14px; font-weight: 400">Another Crab's Treasure</div>
              <div id="grid-meta">Compatible con SteamOS</div>
            </div>
          </div>
          <div role="gridcell"><div role="link"><img src="/assets/30/library_600x900.jpg"></div></div>
        </div></main>`;
      const selected = document.querySelectorAll<HTMLElement>('[role="gridcell"]')[1];
      const scene = startOrbitalAbyss(document);

      expect(scene.moveTo(selected)).toBe(true);

      expect(document.querySelector('[data-pdc-orbit-caption-label="true"]')?.textContent)
        .toBe("Another Crab's Treasure");
      expect(document.querySelector<SVGElement>('[data-pdc-orbit-caption-icon="true"]')
        ?.dataset.pdcOrbitCaptionAction).toBe("download");
      expect(document.getElementById("grid-title")?.dataset.pdcOrbitNativeCopy).toBe("true");
    } finally {
      if (previousAppStore) Object.defineProperty(window, "appStore", previousAppStore);
      else delete (window as unknown as { appStore?: unknown }).appStore;
    }
  });

  it("does not resolve a grid app when its asset paths disagree", () => {
    document.body.innerHTML = `
      <main id="Main"><div role="grid">
        <div role="gridcell"></div>
        <div role="gridcell"><div role="link" aria-labelledby="ambiguous-title">
          <img src="/assets/111/library_600x900.jpg">
          <img src="/assets/222/library_600x900.jpg">
          <div id="ambiguous-title">Ambiguous game</div>
        </div></div>
        <div role="gridcell"></div>
      </div></main>`;
    const resolveAction = vi.fn(() => "play" as const);
    const scene = startOrbitalAbyss(document, { resolveAction });

    scene.moveTo(document.querySelectorAll('[role="gridcell"]')[1]);

    expect(resolveAction).not.toHaveBeenCalled();
    expect(document.querySelector('[data-pdc-orbit-caption-label="true"]')?.textContent)
      .toBe("Ambiguous game");
    expect(document.querySelector('[data-pdc-orbit-caption-icon="true"]')?.hasAttribute("hidden")).toBe(true);
  });

  it("accepts cards from Steam's separate Big Picture window realm", () => {
    const steamWindow = new Window();
    steamWindow.document.body.innerHTML = `
      <main id="Main"><div class="ReactVirtualized__Grid"><div role="list">
        <div role="listitem" data-id="one"></div>
        <div role="listitem" data-id="two"></div>
        <div role="listitem" data-id="three"></div>
      </div></div></main>`;
    const cards = [...steamWindow.document.querySelectorAll('[role="listitem"]')];
    const scene = startOrbitalAbyss(steamWindow.document as unknown as Document);
    const hostHTMLElement = globalThis.HTMLElement;
    Object.defineProperty(globalThis, "HTMLElement", {
      configurable: true,
      value: class HostRealmHTMLElement {},
    });
    try {
      expect(scene.moveTo(cards[1] as unknown as Element)).toBe(true);
      expect(steamWindow.document.getElementById("pdc-orbital-abyss")).toBeTruthy();
      scene.dispose();
    } finally {
      Object.defineProperty(globalThis, "HTMLElement", { configurable: true, value: hostHTMLElement });
      steamWindow.close();
    }
  });

  it("settles a restored orbit without replaying card movement from native geometry", () => {
    document.documentElement.dataset.pdcThemeRuntime = "obsidian-bloom";
    document.documentElement.dataset.pdcOrbitActive = "true";
    document.documentElement.dataset.pdcOrbitRestoring = "true";
    const style = document.createElement("style");
    style.textContent = ORBITAL_ABYSS_CSS;
    document.head.append(style);
    const card = document.createElement("div");
    card.dataset.pdcOrbitCard = "true";
    document.body.append(card);

    const settlementRule = Array.from(style.sheet?.cssRules ?? [])
      .find((rule): rule is CSSStyleRule => (
        rule instanceof CSSStyleRule && rule.selectorText.includes('[data-pdc-orbit-restoring="true"]')
      ));
    expect(settlementRule?.style.transition).toBe("none");

    style.remove();
    document.documentElement.removeAttribute("data-pdc-theme-runtime");
    document.documentElement.removeAttribute("data-pdc-orbit-active");
    document.documentElement.removeAttribute("data-pdc-orbit-restoring");
  });
});
