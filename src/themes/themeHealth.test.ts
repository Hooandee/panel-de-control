import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import {
  cleanupNeeded,
  cleanupPlan,
  countCssLoaderStyles,
  diagnoseThemeHealth,
  hooandeeNames,
  parseThemeHealth,
  readSteamSettings,
  removeCssLoaderStyles,
  steamDisplayState,
  type SteamDisplayState,
  type ThemeHealthBackend,
} from "./themeHealth";

const CLEAN_DISPLAY: SteamDisplayState = {
  scale: 1, autoScale: 1, usingAutoScale: true, external: false, beta: false,
  pixelRatio: 1, width: 1280, height: 800, cssLoaderStyles: 3,
};

function theme(name: string, enabled: boolean) {
  return { id: name, name, displayName: name, version: "1", author: "", enabled, patches: [] };
}

function backend(overrides: Partial<ThemeHealthBackend> = {}): ThemeHealthBackend {
  return {
    folders: [{ folder: "Eclipse", name: "Eclipse", kind: "hooandee", active: true }],
    panel: { width: 1280, height: 800 },
    undo: { available: false, moved: 0, disabled: 0 },
    ...overrides,
  };
}

const NO_STYLES: SteamDisplayState = { ...CLEAN_DISPLAY, cssLoaderStyles: 0 };

const ready = (...themes: ReturnType<typeof theme>[]): CssLoaderSnapshot => ({ status: "ready", themes });

describe("diagnoseThemeHealth", () => {
  it("is clean with only Hooandee themes on the stock display", () => {
    const health = backend();
    const keep = hooandeeNames(health, []);

    expect(diagnoseThemeHealth(ready(theme("Eclipse", true)), health, CLEAN_DISPLAY, keep)).toEqual([]);
  });

  it("separates other themes from profiles and lists folders to set aside", () => {
    const health = backend({
      folders: [
        { folder: "Eclipse", name: "Eclipse", kind: "hooandee", active: true },
        { folder: "Other", name: "Other", kind: "third_party", active: true },
        { folder: "Mine.profile", name: "Mine.profile", kind: "profile", active: true },
        { folder: "Old", name: "Old", kind: "legacy", active: true },
        { folder: "Residue", name: "Residue", kind: "leftover", active: false },
      ],
    });
    const snapshot = ready(theme("Eclipse", true), theme("Other", true), theme("Mine.profile", true), theme("Old", true));

    const findings = diagnoseThemeHealth(snapshot, health, CLEAN_DISPLAY, hooandeeNames(health, []));

    expect(findings).toEqual([
      { id: "other_active", severity: "problem", names: ["Other"] },
      { id: "profile_active", severity: "problem", names: ["Mine.profile"] },
      {
        id: "set_aside",
        severity: "problem",
        folders: [{ folder: "Old", kind: "legacy" }, { folder: "Residue", kind: "leftover" }],
      },
    ]);
    expect(cleanupPlan(snapshot, findings, hooandeeNames(health, []))).toEqual({
      disable: ["Other", "Mine.profile", "Old"],
      chooseOne: [],
      setAside: 2,
      ghostStyles: false,
    });
  });

  it("flags styles that survive with no theme enabled", () => {
    const findings = diagnoseThemeHealth(ready(theme("Eclipse", false)), backend(), CLEAN_DISPLAY, new Set(["Eclipse"]));

    expect(findings).toEqual([{ id: "ghost_styles", severity: "problem", count: 3 }]);
    expect(cleanupNeeded(cleanupPlan(ready(), findings, new Set()))).toBe(true);
  });

  it("treats every CSS Loader style as left behind once CSS Loader is off or removed", () => {
    for (const status of ["disabled", "missing"] as const) {
      expect(diagnoseThemeHealth({ status, themes: [] }, backend(), CLEAN_DISPLAY, new Set())).toEqual([
        { id: "css_loader", severity: "problem", status },
        { id: "ghost_styles", severity: "problem", count: 3 },
      ]);
    }
  });

  it("does not guess about styles while CSS Loader cannot be read", () => {
    const findings = diagnoseThemeHealth({ status: "error", themes: [] }, backend(), CLEAN_DISPLAY, new Set());

    expect(findings).toEqual([{ id: "css_loader", severity: "problem", status: "error" }]);
  });

  it("reports a manual Steam scale, a resolution off the panel, and the beta channel", () => {
    const display = { ...NO_STYLES, scale: 1.25, usingAutoScale: false, width: 1024, height: 640, beta: true };

    expect(diagnoseThemeHealth(ready(), backend(), display, new Set())).toEqual([
      { id: "steam_scale", severity: "setting", scale: 1.25, autoScale: 1 },
      { id: "resolution", severity: "setting", width: 1024, height: 640, panelWidth: 1280, panelHeight: 800 },
      { id: "steam_beta", severity: "setting" },
    ]);
  });

  it("compares a portrait panel in landscape and skips the panel check on an external display", () => {
    const portrait = backend({ panel: { width: 800, height: 1280 } });

    expect(diagnoseThemeHealth(ready(), portrait, NO_STYLES, new Set())).toEqual([]);
    expect(diagnoseThemeHealth(ready(), portrait, { ...NO_STYLES, external: true, width: 3840, height: 2160 }, new Set()))
      .toEqual([{ id: "external_display", severity: "info" }]);
  });

  it("accepts the rounded viewport of a Deck LCD at its stock 1.5 scale", () => {
    const deckLcd = backend({ panel: { width: 800, height: 1280 } });
    const display = { ...NO_STYLES, scale: 1.5, autoScale: 1.5, pixelRatio: 1.5, width: 1281, height: 801 };

    expect(diagnoseThemeHealth(ready(), deckLcd, display, new Set())).toEqual([]);
  });

  it("stays silent about settings Steam did not report", () => {
    const unknown = { ...NO_STYLES, scale: null, autoScale: null, usingAutoScale: null, beta: null, width: null, height: null };

    expect(diagnoseThemeHealth(ready(), backend(), unknown, new Set())).toEqual([]);
  });

  it("asks to narrow several active Hooandee themes down to one", () => {
    const findings = diagnoseThemeHealth(
      ready(theme("Eclipse", true), theme("Hooandee Gallery", true)),
      backend(),
      CLEAN_DISPLAY,
      new Set(["Eclipse", "Hooandee Gallery"]),
    );

    const themes = [{ name: "Eclipse", label: "Eclipse" }, { name: "Hooandee Gallery", label: "Hooandee Gallery" }];
    expect(findings).toEqual([{ id: "several_hooandee", severity: "problem", names: ["Eclipse", "Hooandee Gallery"], themes }]);
    expect(cleanupPlan(ready(), findings, new Set()).chooseOne).toEqual(themes);
    expect(cleanupNeeded(cleanupPlan(ready(), findings, new Set()))).toBe(true);
  });
});

describe("several Hooandee themes", () => {
  it("leaves local keyboard or sound themes next to an interface theme alone", () => {
    const keep = new Set(["Eclipse", "Hooandee Lobo Blanco"]);

    expect(diagnoseThemeHealth(
      ready(theme("Eclipse", true), theme("Hooandee Lobo Blanco", true)),
      backend(),
      NO_STYLES,
      keep,
      new Set(["Eclipse"]),
    )).toEqual([]);
  });
});

describe("parseThemeHealth", () => {
  it("drops malformed folders and unknown kinds", () => {
    expect(parseThemeHealth({
      folders: [
        { folder: "A", name: "A", kind: "legacy", active: false },
        { folder: "B", name: "B", kind: "alien", active: false },
        "junk",
      ],
      panel: { width: 0, height: 800 },
      undo: { available: true, moved: 2, disabled: "x" },
    })).toEqual({
      folders: [{ folder: "A", name: "A", kind: "legacy", active: false }],
      panel: null,
      undo: { available: true, moved: 2, disabled: 0 },
    });
  });

  it("rejects a response without folders", () => {
    expect(() => parseThemeHealth({})).toThrow();
  });
});

describe("Steam display", () => {
  it("reads the settings Steam sends on registration and unregisters", async () => {
    const unregister = vi.fn();
    const settings = await readSteamSettings({
      RegisterForSettingsChanges: (callback) => {
        callback({ flCurrentDisplayScaleFactor: 1.5, bIsInClientBeta: false });
        return { unregister };
      },
    });

    expect(settings).toEqual({ flCurrentDisplayScaleFactor: 1.5, bIsInClientBeta: false });
    expect(unregister).toHaveBeenCalled();
  });

  it("gives up when Steam never answers", async () => {
    vi.useFakeTimers();
    const pending = readSteamSettings({ RegisterForSettingsChanges: () => ({ unregister: () => {} }) }, 100);
    vi.advanceTimersByTime(100);
    await expect(pending).resolves.toBeNull();
    vi.useRealTimers();
    await expect(readSteamSettings(undefined)).resolves.toBeNull();
  });

  it("derives the drawn size from the Big Picture window and counts CSS Loader styles", () => {
    const document = { querySelectorAll: (selector: string) => ({ length: selector === "style.css-loader-style" ? 2 : 0 }) };

    expect(steamDisplayState(
      { flCurrentDisplayScaleFactor: 1.25, flAutoDisplayScaleFactor: 1, bDisplayIsUsingAutoScale: false, bDisplayIsExternal: false, bIsInClientBeta: true },
      { devicePixelRatio: 1.25, innerWidth: 1024, innerHeight: 640 },
      [document as unknown as Document, document as unknown as Document],
    )).toEqual({
      scale: 1.25, autoScale: 1, usingAutoScale: false, external: false, beta: true,
      pixelRatio: 1.25, width: 1280, height: 800, cssLoaderStyles: 4,
    });
  });
});

describe("CSS Loader styles", () => {
  it("counts and removes them only from documents that answer", () => {
    const style = () => ({ remove: vi.fn() });
    const styles = [style(), style()];
    const reachable = { querySelectorAll: () => styles } as unknown as Document;
    const gone = { querySelectorAll: () => { throw new Error("detached"); } } as unknown as Document;

    expect(countCssLoaderStyles([gone])).toBeNull();
    expect(countCssLoaderStyles([reachable, gone])).toBe(2);
    expect(removeCssLoaderStyles([reachable, gone])).toBe(2);
    expect(styles.every((item) => item.remove.mock.calls.length === 1)).toBe(true);
  });
});
