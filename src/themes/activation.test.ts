import { describe, expect, it } from "vitest";

import {
  ThemeActivator,
  type DurableThemeActivationRecovery,
  type ThemeActivationAdapter,
  type ThemeActivationJournal,
} from "./activation";
import { CssLoaderAdapter } from "./cssLoaderAdapter";
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

function themeWithPatch(name: string, enabled: boolean, value: string): CssLoaderTheme {
  return {
    ...theme(name, enabled),
    patches: [{
      name: "Color",
      defaultValue: "Blue",
      value,
      options: ["Blue", "Red"],
      type: "dropdown",
      rawType: "dropdown",
    }],
  };
}

class Adapter implements ThemeActivationAdapter {
  writes: Array<[string, boolean]> = [];
  restores = 0;
  constructor(
    readonly themes: CssLoaderTheme[],
    private readonly afterWrite?: (name: string, enabled: boolean, themes: CssLoaderTheme[]) => void,
    private readonly restoreBehavior?: (
      expected: CssLoaderSnapshot & { status: "ready" },
      themes: CssLoaderTheme[],
      attempt: number,
    ) => void,
  ) {}
  async inspect(): Promise<CssLoaderSnapshot> {
    return { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: structuredClone(this.themes) };
  }
  async setThemeState(name: string, enabled: boolean): Promise<CssLoaderSnapshot> {
    this.writes.push([name, enabled]);
    const current = this.themes.find((candidate) => candidate.name === name);
    if (!current) throw new Error("missing theme");
    current.enabled = enabled;
    this.afterWrite?.(name, enabled, this.themes);
    return this.inspect();
  }
  async restoreThemeSnapshot(expected: CssLoaderSnapshot & { status: "ready" }) {
    this.restores += 1;
    if (this.restoreBehavior) {
      this.restoreBehavior(expected, this.themes, this.restores);
    } else {
      this.themes.splice(0, this.themes.length, ...structuredClone(expected.themes));
    }
    return this.inspect() as Promise<CssLoaderSnapshot & { status: "ready" }>;
  }
  hasPendingMutation(): boolean {
    return false;
  }
  async waitForPendingMutation(): Promise<void> {}
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

  it("restores an unrelated theme changed as a side effect before reporting failure", async () => {
    const adapter = new Adapter(
      [theme("Example Theme", true), theme("Second Theme", false), theme("Third Party", true)],
      (name, enabled, themes) => {
        if (name === "Second Theme" && enabled) {
          const unrelated = themes.find((candidate) => candidate.name === "Third Party");
          if (unrelated) unrelated.enabled = false;
        }
      },
    );
    const activator = new ThemeActivator(adapter);

    await expect(activator.activate("second-theme", CATALOG)).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });

    expect(adapter.writes).toEqual([
      ["Example Theme", false],
      ["Second Theme", true],
    ]);
    expect(adapter.restores).toBe(1);
    await expect(adapter.inspect()).resolves.toMatchObject({
      themes: expect.arrayContaining([
        expect.objectContaining({ name: "Third Party", enabled: true }),
      ]),
    });
  });

  it("restores a target patch changed as an activation side effect", async () => {
    const adapter = new Adapter(
      [themeWithPatch("Example Theme", false, "Red")],
      (_name, enabled, themes) => {
        if (enabled) themes[0].patches[0].value = "Blue";
      },
    );

    await expect(new ThemeActivator(adapter).activate("example-theme", CATALOG)).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });

    await expect(adapter.inspect()).resolves.toMatchObject({
      themes: [expect.objectContaining({
        name: "Example Theme",
        enabled: false,
        patches: [expect.objectContaining({ value: "Red" })],
      })],
    });
  });

  it("restores a third-party patch changed as an activation side effect", async () => {
    const adapter = new Adapter(
      [theme("Example Theme", false), themeWithPatch("Third Party", true, "Red")],
      (_name, enabled, themes) => {
        if (enabled) themes[1].patches[0].value = "Blue";
      },
    );

    await expect(new ThemeActivator(adapter).activate("example-theme", CATALOG)).rejects.toMatchObject({
      code: "activation_failed",
      restorationFailed: false,
    });

    await expect(adapter.inspect()).resolves.toMatchObject({
      themes: expect.arrayContaining([
        expect.objectContaining({
          name: "Third Party",
          enabled: true,
          patches: [expect.objectContaining({ value: "Red" })],
        }),
      ]),
    });
  });

  it("keeps recovery pending when a restore leaves patch schema changed", async () => {
    const adapter = new Adapter(
      [themeWithPatch("Example Theme", false, "Red")],
      (_name, enabled, themes) => {
        if (enabled) themes[0].patches[0].value = "Blue";
      },
      (expected, themes) => {
        themes.splice(0, themes.length, ...structuredClone(expected.themes));
        themes[0].patches[0].options = ["Blue", "Red", "Green"];
      },
    );
    const activator = new ThemeActivator(adapter);

    await expect(activator.activate("example-theme", CATALOG)).rejects.toMatchObject({
      code: "rollback_failed",
      restorationFailed: true,
    });
    await expect(activator.reconcilePendingRecovery()).rejects.toMatchObject({
      code: "rollback_failed",
      restorationFailed: true,
    });
    expect(adapter.restores).toBe(2);
  });

  it("recovers a timed-out mutation after restart with a newer compatible CSS Loader", async () => {
    let durable: DurableThemeActivationRecovery | null = null;
    const order: string[] = [];
    const journal: ThemeActivationJournal = {
      begin: async (snapshot) => {
        order.push("journal");
        durable = { transaction: "durable-token", snapshot: structuredClone(snapshot) };
        return "durable-token";
      },
      pending: async () => durable ? structuredClone(durable) : null,
      acknowledge: async (transaction) => {
        if (transaction !== durable?.transaction) throw new Error("mismatch");
        durable = null;
      },
    };
    const themes = [themeWithPatch("Example Theme", false, "Red")];
    const firstAdapter: ThemeActivationAdapter = {
      inspect: async () => ({
        status: "ready",
        pluginVersion: "2.1.2",
        backendVersion: 9,
        themes: structuredClone(themes),
      }),
      setThemeState: async () => {
        order.push("mutation");
        throw new Error("timed out");
      },
      restoreThemeSnapshot: async () => { throw new Error("old frontend unloaded"); },
      hasPendingMutation: () => true,
      waitForPendingMutation: () => new Promise(() => undefined),
    };

    await expect(new ThemeActivator(firstAdapter, journal).activate("example-theme", CATALOG))
      .rejects.toMatchObject({ code: "rollback_failed", restorationFailed: true });
    expect(durable).toMatchObject({
      transaction: "durable-token",
      snapshot: { themes: [expect.objectContaining({ enabled: false })] },
    });
    expect(order).toEqual(["journal", "mutation"]);

    themes[0].enabled = true;
    const restartedAdapter: ThemeActivationAdapter = {
      inspect: async () => ({
        status: "ready",
        pluginVersion: "2.2.0",
        backendVersion: 10,
        themes: structuredClone(themes),
      }),
      setThemeState: async () => restartedAdapter.inspect(),
      restoreThemeSnapshot: async (expected) => {
        themes.splice(0, themes.length, ...structuredClone(expected.themes));
        return restartedAdapter.inspect() as Promise<CssLoaderSnapshot & { status: "ready" }>;
      },
      hasPendingMutation: () => false,
      waitForPendingMutation: async () => undefined,
    };

    await expect(new ThemeActivator(restartedAdapter, journal).reconcilePendingRecovery())
      .resolves.toMatchObject({
        pluginVersion: "2.2.0",
        backendVersion: 10,
        themes: [expect.objectContaining({ enabled: false })],
      });
    expect(durable).toBeNull();
  });

  it("keeps recovery blocked until a timed-out activation settles and the full snapshot is restored", async () => {
    const rawThemes = [{
      id: "Example Theme",
      name: "Example Theme",
      display_name: "Example Theme",
      version: "1.0.0",
      author: "Author",
      enabled: false,
      patches: [{
        name: "Color",
        default: "Blue",
        value: "Red",
        options: ["Blue", "Red"],
        type: "dropdown",
        components: [],
      }],
    }];
    let releaseLateMutation: (() => void) | undefined;
    let deferStateMutation = true;
    const adapter = new CssLoaderAdapter({
      inventory: () => [{ name: "CSS Loader", version: "2.1.2", disabled: false }],
      call: async (method, ...args) => {
        if (method === "get_backend_version") return 9;
        if (method === "get_themes") return structuredClone(rawThemes);
        if (method === "reset") return { fails: [] };
        if (method === "set_patch_of_theme") {
          rawThemes[0].patches[0].value = args[2] as string;
          return { success: true, message: "" };
        }
        if (method === "set_theme_state") {
          const apply = () => {
            rawThemes[0].enabled = args[1] as boolean;
          };
          if (deferStateMutation) {
            deferStateMutation = false;
            return new Promise((resolve) => {
              releaseLateMutation = () => {
                apply();
                resolve({ success: true, message: "" });
              };
            });
          }
          apply();
          return { success: true, message: "" };
        }
        throw new Error(`Unexpected CSS Loader method: ${method}`);
      },
    }, { timeoutMs: 10, reloadTimeoutMs: 50 });
    const activator = new ThemeActivator(adapter);

    await expect(activator.activate("example-theme", CATALOG)).rejects.toMatchObject({
      code: "rollback_failed",
      restorationFailed: true,
    });
    await expect(activator.reconcilePendingRecovery()).rejects.toMatchObject({
      code: "rollback_failed",
      restorationFailed: true,
    });

    releaseLateMutation?.();
    await expect.poll(async () => {
      try {
        const recovered = await activator.reconcilePendingRecovery();
        return recovered?.themes[0]?.enabled;
      } catch {
        return "pending";
      }
    }).toBe(false);
    expect(rawThemes[0]).toMatchObject({
      enabled: false,
      patches: [expect.objectContaining({ value: "Red" })],
    });
  });
});
