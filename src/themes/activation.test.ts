import { describe, expect, it } from "vitest";

import { ThemeActivator, type ThemeActivationAdapter } from "./activation";
import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedThemeRelease } from "./remotePublication";

function release(catalogId: string, cssLoaderName: string): PublishedThemeRelease {
  return {
    catalogId,
    cssLoaderName,
    publishedVersion: "1.0.0",
    displayName: { es: cssLoaderName, en: cssLoaderName, it: cssLoaderName },
    description: { es: "Description", en: "Description", it: "Description" },
    author: "Example Author",
    tags: [],
    notes: {},
    compatibility: "compatible",
    exclusiveGroup: "interface",
  };
}

function theme(name: string, enabled: boolean): CssLoaderTheme {
  return { id: name, name, displayName: name, version: "1.0.0", author: "Author", enabled, patches: [] };
}

class Adapter implements ThemeActivationAdapter {
  writes: Array<[string, boolean]> = [];
  constructor(readonly themes: CssLoaderTheme[]) {}
  async inspect(): Promise<CssLoaderSnapshot> {
    return { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: structuredClone(this.themes) };
  }
  async setThemeState(name: string, enabled: boolean): Promise<CssLoaderSnapshot> {
    this.writes.push([name, enabled]);
    const current = this.themes.find((candidate) => candidate.name === name);
    if (!current) throw new Error("missing theme");
    current.enabled = enabled;
    return this.inspect();
  }
}

const CATALOG = [release("example-theme", "Example Theme"), release("second-theme", "Second Theme")];

describe("ThemeActivator", () => {
  it("uses the current dynamic catalog and preserves third-party state", async () => {
    const adapter = new Adapter([
      theme("Example Theme", true), theme("Second Theme", false), theme("Third Party", true),
    ]);
    const activator = new ThemeActivator(adapter);

    const snapshot = await activator.activate("second-theme", CATALOG);

    expect(adapter.writes).toEqual([["Example Theme", false], ["Second Theme", true]]);
    expect(snapshot.themes.find((item) => item.name === "Third Party")?.enabled).toBe(true);
  });

  it("rejects identities that disappeared from the latest publication", async () => {
    const activator = new ThemeActivator(new Adapter([theme("Example Theme", true)]));

    await expect(activator.deactivate("example-theme", [])).rejects.toMatchObject({ code: "unknown_theme" });
  });

  it("deactivates only the selected published theme", async () => {
    const adapter = new Adapter([theme("Example Theme", true), theme("Third Party", true)]);
    const snapshot = await new ThemeActivator(adapter).deactivate("example-theme", CATALOG);

    expect(adapter.writes).toEqual([["Example Theme", false]]);
    expect(snapshot.themes.find((item) => item.name === "Third Party")?.enabled).toBe(true);
  });
});
