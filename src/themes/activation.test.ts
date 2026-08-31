import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import {
  ThemeActivationError,
  ThemeActivator,
  type ThemeActivationAdapter,
} from "./activation";
import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";

function cssTheme(name: string, enabled: boolean): CssLoaderTheme {
  return {
    id: name,
    name,
    displayName: name,
    version: "1.0.0",
    author: name.startsWith("Hooandee") ? "Hooandee" : "Someone else",
    enabled,
    patches: [],
  };
}

class FakeActivationAdapter implements ThemeActivationAdapter {
  readonly writes: Array<[string, boolean]> = [];
  failOn: ((name: string, enabled: boolean, attempt: number) => boolean) | undefined;
  failAfterWrite: ((name: string, enabled: boolean, attempt: number) => boolean) | undefined;
  beforeWrite: (() => Promise<void>) | undefined;
  afterWrite: (() => void) | undefined;
  private attempts = 0;

  constructor(readonly themes: CssLoaderTheme[]) {}

  async inspect(): Promise<CssLoaderSnapshot> {
    return {
      status: "ready",
      pluginVersion: "2.1.2",
      backendVersion: 9,
      themes: structuredClone(this.themes),
    };
  }

  async setThemeState(name: string, enabled: boolean): Promise<CssLoaderSnapshot> {
    this.attempts += 1;
    await this.beforeWrite?.();
    this.writes.push([name, enabled]);
    if (this.failOn?.(name, enabled, this.attempts)) {
      throw new Error(`failed ${name} ${enabled}`);
    }
    const theme = this.themes.find((candidate) => candidate.name === name);
    if (!theme) throw new Error(`missing ${name}`);
    theme.enabled = enabled;
    this.afterWrite?.();
    if (this.failAfterWrite?.(name, enabled, this.attempts)) {
      throw new Error(`failed after write ${name} ${enabled}`);
    }
    return this.inspect();
  }
}

describe("ThemeActivator", () => {
  it("disables only conflicting Hooandee themes and preserves third-party state", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Shattered Realms", false),
      cssTheme("Hooandee Obsidian Bloom", false),
      cssTheme("Third Party Theme", true),
    ]);
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    const snapshot = await activator.activate("hooandee-obsidian-bloom");

    expect(adapter.writes).toEqual([
      ["Hooandee Gallery", false],
      ["Hooandee Obsidian Bloom", true],
    ]);
    expect(snapshot.themes.find((theme) => theme.name === "Hooandee Obsidian Bloom")?.enabled).toBe(true);
    expect(snapshot.themes.find((theme) => theme.name === "Third Party Theme")?.enabled).toBe(true);
  });

  it("restores the Hooandee snapshot when target activation fails", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
      cssTheme("Third Party Theme", true),
    ]);
    adapter.failOn = (name, enabled) => name === "Hooandee Obsidian Bloom" && enabled;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });
    expect(adapter.writes).toEqual([
      ["Hooandee Gallery", false],
      ["Hooandee Obsidian Bloom", true],
      ["Hooandee Gallery", true],
    ]);
    expect(adapter.themes.find((theme) => theme.name === "Hooandee Gallery")?.enabled).toBe(true);
    expect(adapter.themes.find((theme) => theme.name === "Third Party Theme")?.enabled).toBe(true);
  });

  it("reports separately when rollback also fails", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
    ]);
    adapter.failOn = (name, enabled) =>
      (name === "Hooandee Obsidian Bloom" && enabled)
      || (name === "Hooandee Gallery" && enabled);
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toEqual(
      new ThemeActivationError(
        "rollback_failed",
        "Activation failed and the previous Hooandee state could not be restored",
        true,
      ),
    );
  });

  it("restores a mutation that CSS Loader applied before its verification failed", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
      cssTheme("Third Party Theme", true),
    ]);
    adapter.failAfterWrite = (name, enabled) => name === "Hooandee Obsidian Bloom" && enabled;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });
    expect(adapter.themes.map((theme) => [theme.name, theme.enabled])).toEqual([
      ["Hooandee Gallery", true],
      ["Hooandee Obsidian Bloom", false],
      ["Third Party Theme", true],
    ]);
    expect(adapter.writes).not.toContainEqual(["Third Party Theme", true]);
  });

  it("detects an external theme change without ever writing that third-party theme", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
      cssTheme("Third Party Theme", true),
    ]);
    adapter.afterWrite = () => {
      const thirdParty = adapter.themes.find((theme) => theme.name === "Third Party Theme");
      if (thirdParty) thirdParty.enabled = false;
      adapter.afterWrite = undefined;
    };
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toMatchObject({
      code: "activation_failed",
    });
    expect(adapter.writes.every(([name]) => name.startsWith("Hooandee"))).toBe(true);
  });

  it("rejects and restores an unrelated catalog theme changed during activation", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Shattered Realms", false),
      cssTheme("Hooandee Obsidian Bloom", false),
    ]);
    adapter.afterWrite = () => {
      const unrelated = adapter.themes.find((theme) => theme.name === "Hooandee Shattered Realms");
      if (unrelated) unrelated.enabled = true;
      adapter.afterWrite = undefined;
    };
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });
    expect(adapter.themes.map((theme) => [theme.name, theme.enabled])).toEqual([
      ["Hooandee Gallery", true],
      ["Hooandee Shattered Realms", false],
      ["Hooandee Obsidian Bloom", false],
    ]);
  });

  it("rejects a second activation while one is still running", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
    ]);
    adapter.beforeWrite = () => gate;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    const first = activator.activate("hooandee-obsidian-bloom");
    await Promise.resolve();
    await expect(activator.activate("hooandee-gallery")).rejects.toMatchObject({ code: "busy" });

    release?.();
    await first;
  });

  it("deactivates only the selected catalog theme and verifies third-party state", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
      cssTheme("Third Party Theme", true),
    ]);
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);
    const snapshot = await activator.deactivate("hooandee-gallery");

    expect(adapter.writes).toEqual([["Hooandee Gallery", false]]);
    expect(snapshot.themes.find((theme) => theme.name === "Hooandee Gallery")?.enabled).toBe(false);
    expect(snapshot.themes.find((theme) => theme.name === "Third Party Theme")?.enabled).toBe(true);
  });

  it("restores an active theme when deactivation fails after the write", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Third Party Theme", true),
    ]);
    adapter.failAfterWrite = (name, enabled) => name === "Hooandee Gallery" && !enabled;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.deactivate("hooandee-gallery")).rejects.toMatchObject({
      code: "deactivation_failed",
      restorationFailed: false,
    });
    expect(adapter.writes).toEqual([
      ["Hooandee Gallery", false],
      ["Hooandee Gallery", true],
    ]);
    expect(adapter.themes.find((theme) => theme.name === "Hooandee Gallery")?.enabled).toBe(true);
  });

  it("reports when a failed deactivation cannot restore the active theme", async () => {
    const adapter = new FakeActivationAdapter([cssTheme("Hooandee Gallery", true)]);
    adapter.failAfterWrite = (name, enabled) => name === "Hooandee Gallery" && !enabled;
    adapter.failOn = (name, enabled) => name === "Hooandee Gallery" && enabled;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.deactivate("hooandee-gallery")).rejects.toMatchObject({
      code: "rollback_failed",
      restorationFailed: true,
    });
  });

  it("rolls back without writing a third-party theme changed concurrently", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Third Party Theme", true),
    ]);
    adapter.afterWrite = () => {
      const thirdParty = adapter.themes.find((theme) => theme.name === "Third Party Theme");
      if (thirdParty) thirdParty.enabled = false;
      adapter.afterWrite = undefined;
    };
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.deactivate("hooandee-gallery")).rejects.toMatchObject({
      code: "deactivation_failed",
    });
    expect(adapter.writes.every(([name]) => name.startsWith("Hooandee"))).toBe(true);
    expect(adapter.themes.find((theme) => theme.name === "Hooandee Gallery")?.enabled).toBe(true);
  });

  it("rejects and restores an unrelated catalog theme changed during deactivation", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
    ]);
    adapter.afterWrite = () => {
      const unrelated = adapter.themes.find((theme) => theme.name === "Hooandee Obsidian Bloom");
      if (unrelated) unrelated.enabled = true;
      adapter.afterWrite = undefined;
    };
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    await expect(activator.deactivate("hooandee-gallery")).rejects.toMatchObject({
      code: "deactivation_failed",
      restorationFailed: false,
    });
    expect(adapter.themes.map((theme) => [theme.name, theme.enabled])).toEqual([
      ["Hooandee Gallery", true],
      ["Hooandee Obsidian Bloom", false],
    ]);
  });

  it("shares its busy lock between activation and deactivation", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", true),
      cssTheme("Hooandee Obsidian Bloom", false),
    ]);
    adapter.beforeWrite = () => gate;
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    const deactivation = activator.deactivate("hooandee-gallery");
    await Promise.resolve();
    await expect(activator.activate("hooandee-obsidian-bloom")).rejects.toMatchObject({ code: "busy" });

    release?.();
    await deactivation;
  });

  it("does not write when the selected theme is already inactive", async () => {
    const adapter = new FakeActivationAdapter([
      cssTheme("Hooandee Gallery", false),
      cssTheme("Third Party Theme", true),
    ]);
    const activator = new ThemeActivator(adapter, LOCAL_THEME_CATALOG);

    const snapshot = await activator.deactivate("hooandee-gallery");

    expect(adapter.writes).toEqual([]);
    expect(snapshot.themes.find((theme) => theme.name === "Hooandee Gallery")?.enabled).toBe(false);
  });
});
