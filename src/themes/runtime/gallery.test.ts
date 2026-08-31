// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CssLoaderTheme } from "../cssLoaderTypes";
import type { ThemeRuntimeSurface } from "../types";
import { createGalleryRuntime, GALLERY_SURFACE_MARKERS } from "./gallery";

interface FakeObserver {
  callback: MutationCallback;
  observe: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
}

type GalleryFeature = "downloads" | "media";

function runtimeTheme(): CssLoaderTheme {
  return {
    id: "Hooandee Gallery",
    name: "Hooandee Gallery",
    displayName: "Hooandee Gallery",
    version: "v0.6.0",
    author: "Hooandee",
    enabled: true,
    patches: [],
  };
}

function addGallerySheet(
  surface: ThemeRuntimeSurface,
  disabled = false,
  shared = false,
): CSSStyleSheet {
  const style = document.createElement("style");
  style.className = "css-loader-style";
  style.textContent = [
    GALLERY_SURFACE_MARKERS[surface],
    shared ? "/* pdc-gallery-runtime: shared */" : "",
    `:root { --fixture-${surface}: 1; }`,
  ].filter(Boolean).join("\n");
  document.head.append(style);
  if (!style.sheet) throw new Error("Fixture stylesheet was not created");
  style.sheet.disabled = disabled;
  return style.sheet;
}

function addThirdPartySheet(): CSSStyleSheet {
  const style = document.createElement("style");
  style.className = "css-loader-style";
  style.textContent = ":root { --third-party: 1; }";
  document.head.append(style);
  if (!style.sheet) throw new Error("Fixture stylesheet was not created");
  return style.sheet;
}

function addGalleryFeatureSheet(
  feature: GalleryFeature,
  disabled = false,
): CSSStyleSheet {
  const style = document.createElement("style");
  style.className = "css-loader-style";
  style.textContent = [
    `/* pdc-gallery-feature: ${feature}:v1 */`,
    `:root { --fixture-${feature}: 1; }`,
  ].join("\n");
  document.head.append(style);
  if (!style.sheet) throw new Error("Fixture stylesheet was not created");
  style.sheet.disabled = disabled;
  return style.sheet;
}

function addGalleryStaticSheet(): CSSStyleSheet {
  const style = document.createElement("style");
  style.className = "css-loader-style";
  style.textContent = [
    "/* pdc-gallery-static: achievements */",
    ":root { --fixture-achievements: 1; }",
  ].join("\n");
  document.head.append(style);
  if (!style.sheet) throw new Error("Fixture stylesheet was not created");
  return style.sheet;
}

function sessionFor(surface: ThemeRuntimeSurface | null) {
  return vi.fn(({ onSurface }: {
    onSurface(next: ThemeRuntimeSurface | null, main: Element | null): void;
  }) => {
    onSurface(surface, document.getElementById("Main"));
    return vi.fn();
  });
}

describe("Gallery runtime", () => {
  afterEach(() => {
    document.head.querySelectorAll("style").forEach((style) => style.remove());
    document.body.innerHTML = "";
    document.documentElement.removeAttribute("data-pdc-theme-runtime");
    document.documentElement.removeAttribute("data-pdc-gallery-grid-motion");
  });

  it("disables only cold Gallery route sheets and restores their prior state", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings", true);
    const thirdParty = addThirdPartySheet();
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("library"),
    }).mount(runtimeTheme());

    expect(home.disabled).toBe(false);
    expect(grid.disabled).toBe(true);
    expect(details.disabled).toBe(true);
    expect(settings.disabled).toBe(true);
    expect(thirdParty.disabled).toBe(false);
    expect(document.documentElement.dataset.pdcThemeRuntime).toBe("gallery");

    stop();
    expect(home.disabled).toBe(false);
    expect(grid.disabled).toBe(false);
    expect(details.disabled).toBe(false);
    expect(settings.disabled).toBe(true);
    expect(thirdParty.disabled).toBe(false);
    expect(document.documentElement.hasAttribute("data-pdc-theme-runtime")).toBe(false);
  });

  it("disables cold feature sheets on a known route and restores their prior state", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media", true);
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("library"),
    }).mount(runtimeTheme());

    expect(downloads.disabled).toBe(true);
    expect(media.disabled).toBe(true);

    stop();
    expect(downloads.disabled).toBe(false);
    expect(media.disabled).toBe(true);
  });

  it("keeps the union of route sheets enabled while Steam mounts both surfaces", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="listitem" data-id="GoToLibrary"></div>
        <div role="tab" aria-controls="Tabs_GameInfo_Content"></div>
      </main>`;
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("game-details"),
    }).mount(runtimeTheme());

    expect(home.disabled).toBe(false);
    expect(details.disabled).toBe(false);
    expect(grid.disabled).toBe(true);
    expect(settings.disabled).toBe(true);
    stop();
  });

  it("keeps explicitly shared Gallery rules active outside their owning surface", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    const home = addGallerySheet("library");
    const sharedGrid = addGallerySheet("library-grid", false, true);
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("library"),
    }).mount(runtimeTheme());

    expect(home.disabled).toBe(false);
    expect(sharedGrid.disabled).toBe(false);
    expect(details.disabled).toBe(true);
    expect(settings.disabled).toBe(true);
    stop();
  });

  it("ignores always-on declarative sheets without disabling route isolation", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const achievements = addGalleryStaticSheet();
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("library"),
    }).mount(runtimeTheme());

    expect(home.disabled).toBe(false);
    expect(grid.disabled).toBe(true);
    expect(details.disabled).toBe(true);
    expect(settings.disabled).toBe(true);
    expect(achievements.disabled).toBe(false);

    stop();
    expect(achievements.disabled).toBe(false);
  });

  it("enables an overlapping route sheet before the deferred surface refresh", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    addGallerySheet("settings");
    let onBeforeRefresh: ((records: readonly MutationRecord[]) => void) | undefined;
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        options.onSurface("library", document.getElementById("Main"));
        onBeforeRefresh = Reflect.get(options, "onBeforeRefresh") as typeof onBeforeRefresh;
        return vi.fn();
      }),
    }).mount(runtimeTheme());
    const main = document.getElementById("Main")!;
    const sentinel = document.createElement("div");
    sentinel.setAttribute("role", "tab");
    sentinel.setAttribute("aria-controls", "Tabs_GameInfo_Content");
    main.append(sentinel);

    expect(details.disabled).toBe(true);
    onBeforeRefresh?.([{
      addedNodes: [sentinel],
      removedNodes: [],
    } as unknown as MutationRecord]);
    expect(details.disabled).toBe(false);

    sentinel.remove();
    const unrelated = document.createElement("span");
    onBeforeRefresh?.([{
      addedNodes: [unrelated],
      removedNodes: [],
    } as unknown as MutationRecord]);
    expect(details.disabled).toBe(false);
    onBeforeRefresh?.([{
      addedNodes: [],
      removedNodes: [sentinel],
    } as unknown as MutationRecord]);
    expect(details.disabled).toBe(true);
    stop();
  });

  it("does not rewrite CSSOM when the active surface state is already reconciled", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    const sheets = [
      addGallerySheet("library"),
      addGallerySheet("library-grid", false, true),
      addGallerySheet("game-details"),
      addGallerySheet("settings"),
    ];
    let writes = 0;
    for (const sheet of sheets) {
      let disabled = sheet.disabled;
      Object.defineProperty(sheet, "disabled", {
        configurable: true,
        get: () => disabled,
        set: (value: boolean) => {
          writes += 1;
          disabled = value;
        },
      });
    }
    let onSurface: ((surface: ThemeRuntimeSurface | null, main: Element | null) => void) | undefined;
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        onSurface = options.onSurface;
        options.onSurface("library", document.getElementById("Main"));
        return vi.fn();
      }),
    }).mount(runtimeTheme());

    writes = 0;
    onSurface?.("library", document.getElementById("Main"));

    expect(writes).toBe(0);
    stop();
  });

  it("reclassifies a CSS Loader sheet when its marker changes in place", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="tab" aria-controls="Tabs_GameInfo_Content"></div>
      </main>`;
    addGallerySheet("library");
    addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const styles = [...document.head.querySelectorAll<HTMLStyleElement>("style.css-loader-style")];
    const detailsStyle = styles.find((style) => style.textContent?.startsWith(
      GALLERY_SURFACE_MARKERS["game-details"],
    ))!;
    const settingsStyle = styles.find((style) => style.textContent?.startsWith(
      GALLERY_SURFACE_MARKERS.settings,
    ))!;
    let detailsText = detailsStyle.textContent ?? "";
    let settingsText = settingsStyle.textContent ?? "";
    Object.defineProperty(detailsStyle, "textContent", {
      configurable: true,
      get: () => detailsText,
    });
    Object.defineProperty(settingsStyle, "textContent", {
      configurable: true,
      get: () => settingsText,
    });
    let onSurface!: (surface: ThemeRuntimeSurface | null, main: Element | null) => void;
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        onSurface = options.onSurface;
        onSurface("game-details", document.getElementById("Main"));
        return vi.fn();
      }),
    }).mount(runtimeTheme());

    expect(details.disabled).toBe(false);
    expect(settings.disabled).toBe(true);
    detailsText = detailsText.replace(
      GALLERY_SURFACE_MARKERS["game-details"],
      GALLERY_SURFACE_MARKERS.settings,
    );
    settingsText = settingsText.replace(
      GALLERY_SURFACE_MARKERS.settings,
      GALLERY_SURFACE_MARKERS["game-details"],
    );
    onSurface("game-details", document.getElementById("Main"));

    expect(details.disabled).toBe(true);
    expect(settings.disabled).toBe(false);
    stop();
    expect(details.disabled).toBe(false);
    expect(settings.disabled).toBe(false);
  });

  it("fails open for unknown surfaces, missing markers, and duplicate markers", () => {
    document.body.innerHTML = '<main id="Main"></main>';
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const duplicateDetails = addGallerySheet("game-details");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor(null),
    }).mount(runtimeTheme());

    expect([home, grid, details, duplicateDetails].every((sheet) => !sheet.disabled)).toBe(true);
    stop();
  });

  it("reconciles CSS Loader replacements once per frame and cleans up the head observer", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const observers: FakeObserver[] = [];
    let frameCallback: FrameRequestCallback | undefined;
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      frameCallback = callback;
      return 17;
    });
    const cancelAnimationFrame = vi.fn();
    const stopSurface = vi.fn();
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn(({ onSurface }) => {
        onSurface("library", document.getElementById("Main"));
        return stopSurface;
      }),
      createObserver(callback) {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame,
      cancelAnimationFrame,
    }).mount(runtimeTheme());

    expect(observers).toHaveLength(1);
    expect(observers[0].observe).toHaveBeenCalledWith(document.head, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    observers[0].callback([], observers[0] as unknown as MutationObserver);
    observers[0].callback([], observers[0] as unknown as MutationObserver);
    expect(requestAnimationFrame).toHaveBeenCalledOnce();

    const replacement = addGallerySheet("settings");
    frameCallback?.(0);
    expect(replacement.disabled).toBe(false);

    observers[0].callback([], observers[0] as unknown as MutationObserver);
    stop();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(17);
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(stopSurface).toHaveBeenCalledOnce();
  });

  it("bounds virtualized grid bursts and restores the idle paint budget after quiescence or unload", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="tab" id="Library_AllGames"></div>
        <div role="tab" id="Library_Soundtracks"></div>
        <div role="grid"></div>
      </main>`;
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    let onBeforeRefresh: ((records: readonly MutationRecord[]) => void) | undefined;
    const timers = new Map<number, () => void>();
    let nextTimer = 10;
    const clearTimeout = vi.fn((handle: number) => {
      timers.delete(handle);
    });
    const setTimeout = vi.fn((callback: () => void) => {
      const handle = nextTimer++;
      timers.set(handle, () => {
        timers.delete(handle);
        callback();
      });
      return handle;
    });
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        options.onSurface("library-grid", document.getElementById("Main"));
        onBeforeRefresh = Reflect.get(options, "onBeforeRefresh") as typeof onBeforeRefresh;
        return vi.fn();
      }),
      setTimeout,
      clearTimeout,
    }).mount(runtimeTheme());
    const card = document.createElement("div");
    const setAttribute = vi.spyOn(document.documentElement, "setAttribute");
    try {
      onBeforeRefresh?.([{
        addedNodes: [card],
        removedNodes: [],
      } as unknown as MutationRecord]);
      expect(document.documentElement.dataset.pdcGalleryGridMotion).toBe("busy");
      expect(timers.size).toBe(1);

      onBeforeRefresh?.([{
        addedNodes: [],
        removedNodes: [card],
      } as unknown as MutationRecord]);
      expect(clearTimeout).toHaveBeenCalledOnce();
      expect(timers.size).toBe(1);
      expect(setAttribute.mock.calls.filter(([name]) => (
        name === "data-pdc-gallery-grid-motion"
      ))).toHaveLength(1);

      timers.values().next().value?.();
      expect(document.documentElement.hasAttribute("data-pdc-gallery-grid-motion")).toBe(false);

      onBeforeRefresh?.([{
        addedNodes: [card],
        removedNodes: [],
      } as unknown as MutationRecord]);
      stop();
      expect(document.documentElement.hasAttribute("data-pdc-gallery-grid-motion")).toBe(false);
      expect(timers.size).toBe(0);
    } finally {
      stop();
    }
  });

  it("restores sheets and runtime ownership when setup fails", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    document.documentElement.dataset.pdcThemeRuntime = "previous";

    expect(() => createGalleryRuntime(document, {
      startSurfaceSession: () => { throw new Error("surface setup failed"); },
    }).mount(runtimeTheme()))
      .toThrow("surface setup failed");

    expect([home, grid, details, settings].every((sheet) => !sheet.disabled)).toBe(true);
    expect(document.documentElement.dataset.pdcThemeRuntime).toBe("previous");
  });

  it("shares one document owner across overlapping mounts and restores on the final release", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    addGalleryFeatureSheet("media");
    const stopSurface = vi.fn();
    const startSurfaceSession = vi.fn(({ onSurface }) => {
      onSurface("library", document.getElementById("Main"));
      return stopSurface;
    });

    const firstStop = createGalleryRuntime(document, { startSurfaceSession }).mount(runtimeTheme());
    const secondStop = createGalleryRuntime(document, { startSurfaceSession }).mount(runtimeTheme());

    expect(startSurfaceSession).toHaveBeenCalledOnce();
    expect(grid.disabled).toBe(true);
    expect(downloads.disabled).toBe(true);

    firstStop();
    expect(grid.disabled).toBe(true);
    expect(downloads.disabled).toBe(true);
    expect(stopSurface).not.toHaveBeenCalled();

    secondStop();
    expect(grid.disabled).toBe(false);
    expect(downloads.disabled).toBe(false);
    expect(stopSurface).toHaveBeenCalledOnce();
  });

  it("fails open only for the feature whose marker inventory is invalid", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const duplicateMedia = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("library"),
    }).mount(runtimeTheme());

    expect(grid.disabled).toBe(true);
    expect(downloads.disabled).toBe(true);
    expect(media.disabled).toBe(false);
    expect(duplicateMedia.disabled).toBe(false);
    stop();
  });

  it("treats the Downloads signature as a known context without touching shared rules", () => {
    document.body.innerHTML = `
      <main id="Main">
        <section class="Panel"><div role="list" data-rbd-droppable-context-id="0"></div></section>
      </main>`;
    const home = addGallerySheet("library");
    const sharedGrid = addGallerySheet("library-grid", false, true);
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor(null),
    }).mount(runtimeTheme());

    expect(home.disabled).toBe(true);
    expect(sharedGrid.disabled).toBe(false);
    expect(details.disabled).toBe(true);
    expect(settings.disabled).toBe(true);
    expect(downloads.disabled).toBe(false);
    expect(media.disabled).toBe(true);
    stop();
  });

  it("recognizes Steam's semantic media grid without relying on hashed classes", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="grid"><div role="row"><div role="gridcell"><div><div role="button">
          <img src="https://steamusercontent.com/ugc/fixture" alt="">
        </div></div></div></div></div>
      </main>`;
    const home = addGallerySheet("library");
    const grid = addGallerySheet("library-grid");
    const details = addGallerySheet("game-details");
    const settings = addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor(null),
    }).mount(runtimeTheme());

    expect([home, grid, details, settings].every((sheet) => sheet.disabled)).toBe(true);
    expect(downloads.disabled).toBe(true);
    expect(media.disabled).toBe(false);
    stop();
  });

  it("fails open for an unknown generic grid without Gallery media evidence", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="grid"><div role="row"><div role="button"></div></div></div>
      </main>`;
    const routes = [
      addGallerySheet("library"),
      addGallerySheet("library-grid"),
      addGallerySheet("game-details"),
      addGallerySheet("settings"),
    ];
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor(null),
    }).mount(runtimeTheme());

    expect(routes.every((sheet) => !sheet.disabled)).toBe(true);
    expect(downloads.disabled).toBe(false);
    expect(media.disabled).toBe(false);
    stop();
  });

  it("keeps media styles ready on game details for community overlays outside Main", () => {
    document.body.innerHTML = `
      <main id="Main">
        <div role="tab" aria-controls="Tabs_GameInfo_Content"></div>
      </main>`;
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor("game-details"),
    }).mount(runtimeTheme());

    expect(downloads.disabled).toBe(true);
    expect(media.disabled).toBe(false);
    stop();
  });

  it("recognizes the semantic soundtrack track-list signature", () => {
    document.body.innerHTML = `
      <main id="Main"><div>
        <div>Album</div>
        <div role="button">1</div><div role="button">2</div>
        <div role="button">3</div><div role="button">4</div>
        <div role="button">5</div><div role="button">6</div>
        <div role="button">7</div><div role="button">8</div>
        <div role="button">9</div><div role="button">10</div>
      </div></main>`;
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    const downloads = addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: sessionFor(null),
    }).mount(runtimeTheme());

    expect(downloads.disabled).toBe(true);
    expect(media.disabled).toBe(false);
    stop();
  });

  it("reactivates media before refresh for a global UGC overlay outside Main", () => {
    document.body.innerHTML = `
      <div id="GamepadUI_Full_Root">
        <main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>
      </div>`;
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    let onBeforeRefresh: ((records: readonly MutationRecord[]) => void) | undefined;
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        options.onSurface("library", document.getElementById("Main"));
        onBeforeRefresh = Reflect.get(options, "onBeforeRefresh") as typeof onBeforeRefresh;
        return vi.fn();
      }),
    }).mount(runtimeTheme());
    const overlay = document.createElement("div");
    overlay.className = "FullModalOverlay";
    overlay.innerHTML = `
      <div class="ModalOverlayContent active">
        <img src="https://steamusercontent.com/ugc/fixture" alt="">
      </div>`;
    document.getElementById("GamepadUI_Full_Root")!.append(overlay);

    expect(media.disabled).toBe(true);
    onBeforeRefresh?.([{
      addedNodes: [overlay],
      removedNodes: [],
    } as unknown as MutationRecord]);
    expect(media.disabled).toBe(false);

    overlay.remove();
    onBeforeRefresh?.([{
      addedNodes: [],
      removedNodes: [overlay],
    } as unknown as MutationRecord]);
    expect(media.disabled).toBe(true);
    stop();
  });

  it("enables and retires a feature sheet before the deferred surface refresh", () => {
    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    addGallerySheet("library");
    addGallerySheet("library-grid");
    addGallerySheet("game-details");
    addGallerySheet("settings");
    addGalleryFeatureSheet("downloads");
    const media = addGalleryFeatureSheet("media");
    let onBeforeRefresh: ((records: readonly MutationRecord[]) => void) | undefined;
    const stop = createGalleryRuntime(document, {
      startSurfaceSession: vi.fn((options) => {
        options.onSurface("library", document.getElementById("Main"));
        onBeforeRefresh = Reflect.get(options, "onBeforeRefresh") as typeof onBeforeRefresh;
        return vi.fn();
      }),
    }).mount(runtimeTheme());
    const viewer = document.createElement("div");
    viewer.className = "OpenedItemContainer";
    document.getElementById("Main")!.append(viewer);

    expect(media.disabled).toBe(true);
    onBeforeRefresh?.([{
      addedNodes: [viewer],
      removedNodes: [],
    } as unknown as MutationRecord]);
    expect(media.disabled).toBe(false);

    viewer.remove();
    onBeforeRefresh?.([{
      addedNodes: [],
      removedNodes: [viewer],
    } as unknown as MutationRecord]);
    expect(media.disabled).toBe(true);
    stop();
  });
});
