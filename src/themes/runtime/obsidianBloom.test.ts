// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";

import type { CssLoaderPatch, CssLoaderTheme } from "../cssLoaderTypes";
import { createObsidianBloomRuntime, safeArtworkUrl } from "./obsidianBloom";

function runtimeTheme(overrides: CssLoaderPatch[] = []): CssLoaderTheme {
  const values: CssLoaderPatch[] = [
    { name: "Animaciones de parrilla", defaultValue: "Yes", value: "Yes", options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" },
    { name: "Intensidad de movimiento", defaultValue: "Equilibrada", value: "Equilibrada", options: ["Reducida", "Equilibrada", "Total"], type: "slider", rawType: "slider" },
    { name: "Fondo adaptativo", defaultValue: "Cinemático", value: "Cinemático", options: ["Sutil", "Cinemático", "Inmersivo"], type: "dropdown", rawType: "dropdown" },
    { name: "Modo de rendimiento", defaultValue: "No", value: "No", options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" },
    { name: "Escena de biblioteca", defaultValue: "Atmosférica", value: "Atmosférica", options: ["Esencial", "Atmosférica", "Inmersiva"], type: "dropdown", rawType: "dropdown" },
    { name: "Escena de parrilla", defaultValue: "Abismo orbital", value: "Abismo orbital", options: ["Directa", "Órbita", "Constelación", "Abismo orbital"], type: "dropdown", rawType: "dropdown" },
    { name: "Transición al detalle", defaultValue: "Portal", value: "Portal", options: ["Ninguna", "Fundido", "Portal"], type: "dropdown", rawType: "dropdown" },
    { name: "Estilo de ajustes", defaultValue: "Cometa", value: "Cometa", options: ["Steam", "Cristal", "Cometa"], type: "dropdown", rawType: "dropdown" },
  ];
  const replacement = new Map(overrides.map((patch) => [patch.name, patch]));
  return {
    id: "Hooandee Obsidian Bloom",
    name: "Hooandee Obsidian Bloom",
    displayName: "Obsidian Bloom",
    version: "v0.2.0",
    author: "Hooandee",
    enabled: true,
    patches: values.map((patch) => replacement.get(patch.name) ?? patch),
  };
}

describe("Obsidian Bloom runtime", () => {
  afterEach(() => {
    document.documentElement.removeAttribute("data-pdc-theme-runtime");
    document.documentElement.removeAttribute("data-pdc-steam-surface");
    document.documentElement.removeAttribute("data-pdc-motion");
    document.documentElement.removeAttribute("data-pdc-orbit-restoring");
    document.documentElement.removeAttribute("data-pdc-portal-phase");
    document.documentElement.style.removeProperty("--pdc-obsidian-artwork");
    document.body.innerHTML = "";
  });

  it("marks detected surfaces, reacts to focused artwork and restores every mutation", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell" data-id="41"><a role="link"><img src="https://cdn.example/one.jpg"><button>One</button></a></div>
          <div role="gridcell" data-id="42"><a role="link"><img src="https://cdn.example/game.jpg"><button>Game</button></a></div>
          <div role="gridcell" data-id="43"><a role="link"><img src="https://cdn.example/three.jpg"><button>Three</button></a></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());

    expect(document.documentElement.dataset.pdcThemeRuntime).toBe("obsidian-bloom");
    expect(document.documentElement.dataset.pdcSteamSurface).toBe("library-grid");
    expect(document.documentElement.dataset.pdcGridScene).toBe("abyss");
    expect(document.documentElement.dataset.pdcLibraryScene).toBe("atmospheric");
    expect(document.documentElement.dataset.pdcDetailTransition).toBe("portal");
    expect(document.documentElement.dataset.pdcSettingsScene).toBe("comet");
    expect(document.documentElement.dataset.pdcEngineBudget).toBe("cinematic");
    expect(document.getElementById("pdc-obsidian-runtime-style")).toBeTruthy();
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent).not.toContain("z-index: -1");
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent).toContain("#GamepadUI_Full_Root");
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .toContain('#pdc-obsidian-portal::after');
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .not.toContain("--pdc-portal-target-scale-x");
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .not.toContain("--pdc-portal-target-scale-y");
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .toContain('[data-pdc-portal-phase="exit"] [data-pdc-orbit-selected="true"]');
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .toContain('.ReactVirtualized__Grid:not([data-pdc-orbit-viewport="true"])');
    expect(document.querySelectorAll("[data-pdc-bloom-layer]")).toHaveLength(2);

    const focusedCard = document.querySelector('[data-id="42"]') as HTMLElement;
    focusedCard.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    focusedCard.querySelector("button")?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect({
      selected: document.querySelector('[data-id="42"]')?.getAttribute("data-pdc-orbit-selected"),
      stage: Boolean(document.getElementById("pdc-orbital-abyss")),
      orbitActive: document.documentElement.dataset.pdcOrbitActive,
      focused: document.querySelector('[data-pdc-obsidian-focus]')?.getAttribute("data-id"),
    }).toEqual({ selected: "true", stage: true, orbitActive: "true", focused: undefined });
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-artwork")).toContain("https://cdn.example/game.jpg");
    expect(document.querySelector('[data-pdc-bloom-active="true"]')?.getAttribute("style")).toContain("game.jpg");

    const main = document.getElementById("Main");
    if (main) main.innerHTML = '<div role="tab" aria-controls="Tabs_GameInfo_Content"></div>';
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    expect(document.documentElement.dataset.pdcSteamSurface).toBe("game-details");
    expect(document.getElementById("pdc-obsidian-portal")?.getAttribute("aria-hidden")).toBe("true");
    expect(document.getElementById("pdc-obsidian-portal")?.getAttribute("style")).toContain("game.jpg");

    const unrelated = document.createElement("a");
    unrelated.setAttribute("role", "link");
    unrelated.textContent = "Unrelated";
    document.body.append(unrelated);
    unrelated.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(document.querySelector("[data-pdc-obsidian-focus]")).toBeNull();
    expect(unrelated.hasAttribute("data-pdc-obsidian-focus")).toBe(false);

    stop();
    expect(document.documentElement.hasAttribute("data-pdc-theme-runtime")).toBe(false);
    expect(document.documentElement.hasAttribute("data-pdc-steam-surface")).toBe(false);
    expect(document.documentElement.hasAttribute("data-pdc-grid-scene")).toBe(false);
    expect(document.documentElement.hasAttribute("data-pdc-engine-budget")).toBe(false);
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-artwork")).toBe("");
    expect(document.querySelector("[data-pdc-obsidian-focus]")).toBeNull();
    expect(document.querySelector("[data-pdc-obsidian-distance]")).toBeNull();
    expect(document.getElementById("pdc-obsidian-runtime-style")).toBeNull();
    expect(document.getElementById("pdc-obsidian-bloom-stage")).toBeNull();
    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    expect(document.getElementById("pdc-orbital-abyss")).toBeNull();
  });

  it("never applies library focus effects to a grid rendered on another Steam surface", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div class="PageListColumn"><button role="tab" id="/settings/display">Display</button></div>
        <div role="grid"><div role="gridcell" data-id="store-card"><button>Store card</button></div></div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());

    document.querySelector('[data-id="store-card"] button')
      ?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));

    expect(document.documentElement.dataset.pdcSteamSurface).toBe("settings");
    expect(document.querySelector("[data-pdc-obsidian-focus]")).toBeNull();
    expect(document.querySelector("[data-pdc-orbit-card]")).toBeNull();
    expect(document.getElementById("pdc-orbital-abyss")).toBeNull();
    stop();
  });

  it("prearms the portal on the verified primary activation without waiting for details", () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    const button = document.querySelector("button.gpfocus") as HTMLElement;
    const card = button.closest('[role="gridcell"]') as HTMLElement;
    card.getBoundingClientRect = () => new DOMRect(140, 120, 158, 280);
    button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, button: 0 }));

    expect(document.documentElement.dataset.pdcSteamSurface).toBe("library-grid");
    expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalDirection).toBe("entry");
    expect(document.getElementById("pdc-obsidian-portal")?.style.getPropertyValue("--pdc-portal-x")).toBe("511px");
    expect(document.getElementById("pdc-obsidian-portal")?.style.getPropertyValue("--pdc-portal-y")).toBe("388px");
    expect(document.getElementById("pdc-obsidian-portal")?.style.getPropertyValue("--pdc-portal-width")).toBe("172px");
    expect(document.getElementById("pdc-obsidian-portal")?.style.getPropertyValue("--pdc-portal-height")).toBe("299px");
    stop();
  });

  it("hands off to the verified details scene without waiting for hero geometry", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    try {
      const button = document.querySelector("button.gpfocus") as HTMLElement;
      const card = button.closest('[role="gridcell"]') as HTMLElement;
      card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
      button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true, button: 0 }));

      const main = document.getElementById("Main") as HTMLElement;
      main.getBoundingClientRect = () => new DOMRect(0, 0, 1022, 639);
      main.innerHTML = `
        <img id="details-hero" src="https://cdn.example/library_hero.jpg">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <section role="tabpanel"><div role="button">Activity</div></section>`;
      const hero = document.getElementById("details-hero") as HTMLElement;
      let layout: [number, number, number, number] = [-26, -26, 1074, 691];
      Object.defineProperties(hero, {
        offsetParent: { configurable: true, get: () => main },
        offsetLeft: { configurable: true, get: () => layout[0] },
        offsetTop: { configurable: true, get: () => layout[1] },
        offsetWidth: { configurable: true, get: () => layout[2] },
        offsetHeight: { configurable: true, get: () => layout[3] },
      });
      hero.getBoundingClientRect = () => new DOMRect(-13, -25, 1066, 686);
      await Promise.resolve();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalEntryState).toBe("docked");
      await new Promise((resolve) => setTimeout(resolve, 280));
      expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalEntryState).toBe("revealing");

      layout = [0, 0, 1022, 284];
      main.append(document.createElement("span"));
      await Promise.resolve();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

      const portal = document.getElementById("pdc-obsidian-portal") as HTMLElement;
      expect(portal.dataset.pdcPortalEntryState).toBe("revealing");
      expect(portal.style.getPropertyValue("--pdc-portal-target-scale-x")).toBe("");
      expect(portal.style.getPropertyValue("--pdc-portal-target-scale-y")).toBe("");
    } finally {
      stop();
    }
  });

  it("ignores secondary clicks while prearming the portal", () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    const button = document.querySelector("button.gpfocus") as HTMLElement;
    const card = button.closest('[role="gridcell"]') as HTMLElement;
    card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    button.dispatchEvent(new MouseEvent("click", { bubbles: true, button: 2 }));

    expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    stop();
  });

  it("mounts the dossier only for verified details and restores it on exit", async () => {
    document.body.innerHTML = `
      <main id="Main">
        <img src="https://cdn.example/library_hero.jpg">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <section role="tabpanel"><div role="button">Activity</div></section>
      </main>`;
    const main = document.getElementById("Main") as HTMLElement;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());

    expect(document.documentElement.dataset.pdcSteamSurface).toBe("game-details");
    expect(main.dataset.pdcHorizonDossier).toBe("true");
    expect(document.getElementById("pdc-horizon-dossier")?.getAttribute("aria-hidden")).toBe("true");

    main.innerHTML = `
      <div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
      <div role="grid"><div role="gridcell"><button>One</button></div><div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Two</button></a></div><div role="gridcell"><button>Three</button></div></div>`;
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    expect(document.getElementById("pdc-horizon-dossier")).toBeNull();
    expect(main.hasAttribute("data-pdc-horizon-dossier")).toBe(false);
    stop();
  });

  it("holds the reverse veil and orbit settlement through the portal handoff", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    const button = document.querySelector("button.gpfocus") as HTMLElement;
    const card = button.closest('[role="gridcell"]') as HTMLElement;
    card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    const main = document.getElementById("Main") as HTMLElement;
    main.innerHTML = '<nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav><section role="tabpanel"></section>';
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalDirection).toBe("exit");
    expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");

    main.innerHTML = `
      <div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
      <div role="grid"><div role="gridcell"><button>One</button></div><div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Two</button></a></div><div role="gridcell"><button>Three</button></div></div>`;
    const restoredCard = main.querySelector("button.gpfocus")?.closest('[role="gridcell"]') as HTMLElement;
    restoredCard.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    expect(document.documentElement.dataset.pdcOrbitActive).toBe("true");
    expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
    expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalExitState).toBe("returning");
    await new Promise((resolve) => setTimeout(resolve, 850));
    expect(document.documentElement.hasAttribute("data-pdc-orbit-restoring")).toBe(false);
    stop();
  });

  it("keeps return settlement armed until delayed library focus is available", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    try {
      const button = document.querySelector("button.gpfocus") as HTMLElement;
      const card = button.closest('[role="gridcell"]') as HTMLElement;
      card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
      button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      const main = document.getElementById("Main") as HTMLElement;
      main.innerHTML = '<nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav><section role="tabpanel"></section>';
      await Promise.resolve();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

      main.innerHTML = `
        <div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid"><div role="gridcell"><button>One</button></div><div role="gridcell"><button id="late-focus">Two</button></div><div role="gridcell"><button>Three</button></div></div>`;
      await Promise.resolve();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");

      const lateFocus = document.getElementById("late-focus") as HTMLElement;
      lateFocus.classList.add("gpfocus");
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      expect(document.documentElement.dataset.pdcOrbitActive).toBe("true");
      expect(document.querySelectorAll('[data-pdc-orbit-selected="true"]')).toHaveLength(1);
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
      await new Promise((resolve) => setTimeout(resolve, 850));
      expect(document.documentElement.hasAttribute("data-pdc-orbit-restoring")).toBe(false);
    } finally {
      stop();
    }
  });

  it("expires a cancelled details exit so a later exit can arm again", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell"><button>One</button></div>
          <div role="gridcell"><a role="link"><img src="https://cdn.example/game.jpg"><button class="gpfocus">Game</button></a></div>
          <div role="gridcell"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    try {
      const button = document.querySelector("button.gpfocus") as HTMLElement;
      const card = button.closest('[role="gridcell"]') as HTMLElement;
      card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
      button.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
      const main = document.getElementById("Main") as HTMLElement;
      main.innerHTML = '<nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav><section role="tabpanel"></section>';
      await Promise.resolve();
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
      expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalDirection).toBe("exit");
      await new Promise((resolve) => setTimeout(resolve, 900));
      expect(document.documentElement.hasAttribute("data-pdc-orbit-restoring")).toBe(false);
      expect(document.getElementById("pdc-obsidian-portal")).toBeNull();

      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      expect(document.documentElement.dataset.pdcOrbitRestoring).toBe("true");
      expect(document.getElementById("pdc-obsidian-portal")?.dataset.pdcPortalDirection).toBe("exit");
    } finally {
      stop();
    }
  });

  it("leaves a details dialog Escape entirely to Steam", () => {
    document.body.innerHTML = `
      <main id="Main">
        <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
        <section role="tabpanel"></section>
        <div role="dialog"><button id="dialog-close">Close</button></div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    try {
      document.getElementById("dialog-close")?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

      expect(document.documentElement.hasAttribute("data-pdc-orbit-restoring")).toBe(false);
      expect(document.getElementById("pdc-obsidian-portal")).toBeNull();
    } finally {
      stop();
    }
  });

  it("does not rebuild the current orbit after an unrelated Steam mutation", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid">
          <div role="gridcell" data-id="41"><button>One</button></div>
          <div role="gridcell" data-id="42"><button class="gpfocus">Two</button></div>
          <div role="gridcell" data-id="43"><button>Three</button></div>
        </div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
    const selected = document.querySelector('[data-id="42"]')!;
    let selectionMutations = 0;
    const observer = new MutationObserver((records) => {
      selectionMutations += records.length;
    });
    observer.observe(selected, { attributes: true, attributeFilter: ["data-pdc-orbit-selected"] });

    document.getElementById("Main")?.setAttribute("data-unrelated-steam-update", "true");
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    await Promise.resolve();

    observer.disconnect();
    stop();
    expect(selectionMutations).toBe(0);
  });

  it("accepts only image-capable URL schemes for CSS custom properties", () => {
    expect(safeArtworkUrl("https://cdn.example/game.jpg")).toBe("https://cdn.example/game.jpg");
    expect(safeArtworkUrl("blob:https://steamloopback.host/id")).toBe("blob:https://steamloopback.host/id");
    expect(safeArtworkUrl("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
    expect(safeArtworkUrl("javascript:alert(1)")).toBeNull();
    expect(safeArtworkUrl("data:text/html,boom")).toBeNull();
  });

  it("honors verified CSS Loader performance and motion patches", () => {
    document.body.innerHTML = '<main id="Main"><div role="grid"><a role="link"><img src="https://cdn.example/game.jpg"></a></div></main>';
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme([
      { name: "Animaciones de parrilla", defaultValue: "Yes", value: "No", options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" },
      { name: "Modo de rendimiento", defaultValue: "No", value: "Yes", options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" },
    ]));

    expect(document.documentElement.dataset.pdcGridMotion).toBe("off");
    expect(document.documentElement.dataset.pdcPerformance).toBe("on");
    expect(document.documentElement.dataset.pdcEngineBudget).toBe("efficient");
    expect(document.getElementById("pdc-obsidian-bloom-stage")).toBeNull();
    document.querySelector("a")?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(document.documentElement.style.getPropertyValue("--pdc-obsidian-artwork")).toBe("");

    stop();
    expect(document.documentElement.hasAttribute("data-pdc-grid-motion")).toBe(false);
    expect(document.documentElement.hasAttribute("data-pdc-performance")).toBe(false);
  });

  it("lets the verified CSS Loader motion patch control the details fade duration", () => {
    document.body.innerHTML = '<main id="Main"><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></main>';
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme([
      { name: "Intensidad de movimiento", defaultValue: "Equilibrada", value: "Reducida", options: ["Reducida", "Equilibrada", "Total"], type: "slider", rawType: "slider" },
      { name: "Transición al detalle", defaultValue: "Portal", value: "Fundido", options: ["Ninguna", "Fundido", "Portal"], type: "dropdown", rawType: "dropdown" },
    ]));

    expect(document.documentElement.dataset.pdcMotionIntensity).toBe("reduced");
    expect(document.getElementById("pdc-obsidian-runtime-style")?.textContent)
      .toContain("animation: pdc-obsidian-arrive var(--hob-details-duration, 520ms)");
    stop();
  });

  it("keeps the details portal independent from the optional adaptive backdrop", async () => {
    document.body.innerHTML = `
      <main id="Main"><div role="tab" id="Library_AllGames"></div><div role="tab" id="Library_Soundtracks"></div>
        <div role="grid"><div role="gridcell"><img src="https://cdn.example/game.jpg"><button>Game</button></div></div>
      </main>`;
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme([
      { name: "Fondo adaptativo", defaultValue: "Apagado", value: "Apagado", options: ["Apagado", "Sutil", "Cinemático", "Inmersivo"], type: "dropdown", rawType: "dropdown" },
    ]));

    expect(document.getElementById("pdc-obsidian-bloom-stage")).toBeNull();
    const card = document.querySelector('[role="gridcell"]') as HTMLElement;
    card.getBoundingClientRect = () => new DOMRect(425, 238, 172, 299);
    card.querySelector("button")?.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    const main = document.getElementById("Main");
    if (main) main.innerHTML = `
      <nav><div role="tab" aria-controls="Tabs_WhatsNew_Content"></div><div role="tab" aria-controls="Tabs_GameInfo_Content"></div></nav>
      <section role="tabpanel"></section>`;
    await Promise.resolve();
    await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
    expect(document.getElementById("pdc-obsidian-portal")).toBeTruthy();
    expect(document.getElementById("pdc-horizon-dossier")?.style.getPropertyValue("--pdc-dossier-artwork"))
      .toContain("game.jpg");
    stop();
  });

  it("adds a non-interactive comet rail to controller focus in Steam settings", () => {
    document.body.innerHTML = `
      <main id="Main"><div class="PageListColumn">
        <button role="tab" id="/settings/display">Display</button>
      </div></main>`;
    const tab = document.querySelector('[role="tab"]') as HTMLElement;
    tab.getBoundingClientRect = () => new DOMRect(20, 60, 240, 44);
    const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());

    tab.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    expect(document.documentElement.dataset.pdcSettingsComet).toBe("active");
    expect(document.documentElement.style.getPropertyValue("--pdc-settings-comet-y")).toBe("82px");
    expect(document.querySelector("[data-pdc-settings-comet-host]")).toBeNull();
    stop();
    expect(document.documentElement.hasAttribute("data-pdc-settings-comet")).toBe(false);
  });

  it("does not leave partial DOM mutations when the observation capability is absent", () => {
    const original = window.MutationObserver;
    Object.defineProperty(window, "MutationObserver", { configurable: true, value: undefined });
    try {
      const stop = createObsidianBloomRuntime(document).mount(runtimeTheme());
      expect(document.documentElement.hasAttribute("data-pdc-theme-runtime")).toBe(false);
      expect(document.getElementById("pdc-obsidian-runtime-style")).toBeNull();
      stop();
    } finally {
      Object.defineProperty(window, "MutationObserver", { configurable: true, value: original });
    }
  });

  it("restores partial setup when Steam rejects DOM observation", () => {
    const original = window.MutationObserver;
    class RejectingObserver {
      observe() { throw new Error("observation rejected"); }
      disconnect() {}
    }
    Object.defineProperty(window, "MutationObserver", { configurable: true, value: RejectingObserver });
    try {
      expect(() => createObsidianBloomRuntime(document).mount(runtimeTheme())).toThrow("observation rejected");
      expect(document.documentElement.hasAttribute("data-pdc-theme-runtime")).toBe(false);
      expect(document.getElementById("pdc-obsidian-runtime-style")).toBeNull();
    } finally {
      Object.defineProperty(window, "MutationObserver", { configurable: true, value: original });
    }
  });
});
