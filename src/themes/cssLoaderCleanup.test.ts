import { describe, expect, it } from "vitest";

import { CssLoaderAdapter, CssLoaderOperationError, type CssLoaderHost } from "./cssLoaderAdapter";

interface FakeTheme {
  enabled: boolean;
  dependencies?: string[];
  patch?: string;
}

// Mirrors CSS Loader: disabling a theme also disables dependencies no other enabled theme uses.
function cssLoader(themes: Record<string, FakeTheme>, options: { ignoreDisable?: string } = {}) {
  const calls: unknown[][] = [];
  const raw = (name: string) => ({
    id: name,
    name,
    display_name: name,
    version: "1.0.0",
    author: "",
    enabled: themes[name].enabled,
    patches: themes[name].patch === undefined ? [] : [{
      name: "Accent", default: "A", value: themes[name].patch, options: ["A", "B"], type: "dropdown", components: [],
    }],
  });
  const disable = (name: string) => {
    themes[name].enabled = false;
    for (const dependency of themes[name].dependencies ?? []) {
      const used = Object.values(themes).some((theme) => theme.enabled && theme.dependencies?.includes(dependency));
      if (!used && themes[dependency]) disable(dependency);
    }
  };
  const host: CssLoaderHost = {
    inventory: () => [{ name: "CSS Loader", disabled: false }],
    call: async (method, ...args) => {
      calls.push([method, ...args]);
      if (method === "get_themes") return Object.keys(themes).map(raw);
      if (method === "reset") return { fails: [] };
      if (method === "set_theme_state") {
        const [name, enabled] = args as [string, boolean];
        if (enabled) themes[name].enabled = true;
        else if (name !== options.ignoreDisable) disable(name);
        return { success: true, message: "Success" };
      }
      if (method === "set_patch_of_theme") {
        const [name, , value] = args as [string, string, string];
        themes[name].patch = value;
        return { success: true, message: "Success" };
      }
      throw new Error(`Unexpected ${method}`);
    },
  };
  return { host, calls, themes };
}

describe("CssLoaderAdapter cleanup", () => {
  it("reloads first, turns off every other theme and keeps Hooandee themes as they were", async () => {
    const loader = cssLoader({
      Eclipse: { enabled: true, patch: "B" },
      Gallery: { enabled: false },
      Other: { enabled: true },
      Dependency: { enabled: true },
    });
    const adapter = new CssLoaderAdapter(loader.host);
    const before = await adapter.requireReady();

    const after = await adapter.disableAllExcept(before, new Set(["Eclipse", "Gallery"]));

    expect(loader.calls.filter(([method]) => method !== "get_themes")[0]).toEqual(["reset"]);
    expect(after.themes.filter((theme) => theme.enabled).map((theme) => theme.name)).toEqual(["Eclipse"]);
    expect(loader.themes.Eclipse.patch).toBe("B");
  });

  it("turns a Hooandee theme back on when a profile took it down with it", async () => {
    const loader = cssLoader({
      Eclipse: { enabled: true },
      "Mine.profile": { enabled: true, dependencies: ["Eclipse"] },
    });
    const adapter = new CssLoaderAdapter(loader.host);
    const before = await adapter.requireReady();

    const after = await adapter.disableAllExcept(before, new Set(["Eclipse"]));

    expect(after.themes.find((theme) => theme.name === "Eclipse")?.enabled).toBe(true);
    expect(after.themes.find((theme) => theme.name === "Mine.profile")?.enabled).toBe(false);
  });

  it("fails verification when CSS Loader keeps another theme enabled", async () => {
    const loader = cssLoader({ Eclipse: { enabled: true }, Stubborn: { enabled: true } }, { ignoreDisable: "Stubborn" });
    const adapter = new CssLoaderAdapter(loader.host);
    const before = await adapter.requireReady();

    const failure = await adapter.disableAllExcept(before, new Set(["Eclipse"])).catch((error) => error);

    expect(failure).toBeInstanceOf(CssLoaderOperationError);
    expect(failure.code).toBe("verification_failed");
  });

  it("turns recorded themes back on, skipping ones that no longer exist and never touching kept ones", async () => {
    const loader = cssLoader({ Eclipse: { enabled: true }, Other: { enabled: false } });
    const adapter = new CssLoaderAdapter(loader.host);
    const before = await adapter.requireReady();

    const after = await adapter.enableAgain(before, new Set(["Eclipse"]), ["Other", "Gone", "Eclipse"]);

    expect(after.themes.map((theme) => [theme.name, theme.enabled])).toEqual([["Eclipse", true], ["Other", true]]);
    expect(loader.calls.filter(([method]) => method === "set_theme_state")).toEqual([
      ["set_theme_state", "Other", true, false, false],
    ]);
  });
});
