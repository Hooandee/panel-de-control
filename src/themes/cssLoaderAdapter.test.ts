import { describe, expect, it, vi } from "vitest";

import {
  CssLoaderAdapter,
  CssLoaderOperationError,
  type CssLoaderHost,
} from "./cssLoaderAdapter";

const RAW_THEME = {
  id: "Hooandee Obsidian Bloom",
  name: "Hooandee Obsidian Bloom",
  display_name: "Obsidian Bloom",
  version: "0.1.0",
  author: "Hooandee",
  enabled: true,
  bundled: false,
  require: 9,
  dependencies: {},
  flags: ["REQUIRE_NAV_PATCH"],
  created: 1,
  modified: 2,
  patches: [
    {
      name: "Animated grid",
      default: "Yes",
      value: "Yes",
      options: ["No", "Yes"],
      type: "checkbox",
      components: [],
    },
    {
      name: "Motion intensity",
      default: "Balanced",
      value: "Balanced",
      options: ["Reduced", "Balanced", "Full"],
      type: "slider",
      components: [],
    },
    {
      name: "Future control",
      default: "Auto",
      value: "Auto",
      options: ["Auto"],
      type: "future-type",
      components: [],
    },
  ],
};

function host(overrides: Partial<CssLoaderHost> = {}): CssLoaderHost {
  return {
    inventory: () => [{ name: "CSS Loader", version: "2.1.2", disabled: false }],
    call: vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [RAW_THEME];
      throw new Error(`Unexpected method: ${method}`);
    }),
    ...overrides,
  };
}

describe("CssLoaderAdapter.inspect", () => {
  it("reports missing without calling a plugin backend", async () => {
    const call = vi.fn();
    const adapter = new CssLoaderAdapter(host({ inventory: () => [], call }));

    const snapshot = await adapter.inspect();

    expect(snapshot).toEqual({ status: "missing", themes: [] });
    expect(call).not.toHaveBeenCalled();
  });

  it("reports disabled without calling a disabled backend", async () => {
    const call = vi.fn();
    const adapter = new CssLoaderAdapter(host({
      inventory: () => [{ name: "CSS Loader", version: "2.1.2", disabled: true }],
      call,
    }));

    const snapshot = await adapter.inspect();

    expect(snapshot).toEqual({ status: "disabled", pluginVersion: "2.1.2", themes: [] });
    expect(call).not.toHaveBeenCalled();
  });

  it("reports incompatible before reading themes", async () => {
    const call = vi.fn(async () => 8);
    const adapter = new CssLoaderAdapter(host({ call }), { minimumBackendVersion: 9 });

    const snapshot = await adapter.inspect();

    expect(snapshot).toEqual({
      status: "incompatible",
      pluginVersion: "2.1.2",
      backendVersion: 8,
      requiredBackendVersion: 9,
      themes: [],
    });
    expect(call).toHaveBeenCalledOnce();
  });

  it("normalizes ready themes and keeps unknown patch types read-only", async () => {
    const adapter = new CssLoaderAdapter(host());

    const snapshot = await adapter.inspect();

    expect(snapshot.status).toBe("ready");
    expect(snapshot.pluginVersion).toBe("2.1.2");
    expect(snapshot.backendVersion).toBe(9);
    expect(snapshot.themes[0]).toMatchObject({
      id: "Hooandee Obsidian Bloom",
      name: "Hooandee Obsidian Bloom",
      displayName: "Obsidian Bloom",
      version: "0.1.0",
      enabled: true,
    });
    expect(snapshot.themes[0].patches.map((patch) => patch.type)).toEqual([
      "checkbox",
      "slider",
      "unsupported",
    ]);
  });

  it("fails closed when CSS Loader returns malformed themes", async () => {
    const adapter = new CssLoaderAdapter(host({
      call: vi.fn(async (method: string) => method === "get_backend_version" ? 9 : [{ name: 42 }]),
    }));

    const snapshot = await adapter.inspect();

    expect(snapshot).toEqual({
      status: "error",
      pluginVersion: "2.1.2",
      backendVersion: 9,
      themes: [],
      error: { code: "malformed_response", message: "CSS Loader returned an invalid theme at index 0" },
    });
  });

  it("turns transport failures into an honest error state", async () => {
    const adapter = new CssLoaderAdapter(host({
      call: vi.fn(async () => { throw new Error("backend unavailable"); }),
    }));

    const snapshot = await adapter.inspect();

    expect(snapshot).toEqual({
      status: "error",
      pluginVersion: "2.1.2",
      themes: [],
      error: { code: "transport", message: "backend unavailable" },
    });
  });

  it("times out calls that never settle", async () => {
    vi.useFakeTimers();
    try {
      const adapter = new CssLoaderAdapter(host({
        call: vi.fn(() => new Promise(() => {})),
      }), { timeoutMs: 50 });

      const pending = adapter.inspect();
      await vi.advanceTimersByTimeAsync(50);

      await expect(pending).resolves.toEqual({
        status: "error",
        pluginVersion: "2.1.2",
        themes: [],
        error: { code: "timeout", message: "CSS Loader get_backend_version timed out" },
      });
    } finally {
      vi.useRealTimers();
    }
  });
});

function mutableHost(): { host: CssLoaderHost; call: ReturnType<typeof vi.fn> } {
  let theme = structuredClone(RAW_THEME);
  const call = vi.fn(async (method: string, ...args: unknown[]) => {
    if (method === "get_backend_version") return 9;
    if (method === "get_themes") return [structuredClone(theme)];
    if (method === "set_patch_of_theme") {
      const [, patchName, value] = args;
      const patch = theme.patches.find((item) => item.name === patchName);
      if (patch && typeof value === "string") patch.value = value;
      return { success: true, message: "" };
    }
    if (method === "set_theme_state") {
      theme.enabled = args[1] as boolean;
      return { success: true, message: "" };
    }
    throw new Error(`Unexpected method: ${method}`);
  });
  return { host: host({ call }), call };
}

describe("CssLoaderAdapter mutations", () => {
  it("downloads only from an HTTPS catalog source and verifies CSS Loader registered the theme", async () => {
    let installed = false;
    const call = vi.fn(async (method: string, ...args: unknown[]) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return installed ? [RAW_THEME] : [];
      if (method === "download_theme_from_url") {
        expect(args).toEqual(["obsidian-bloom", "https://themes.hooandee.example/v1/"]);
        installed = true;
        return { success: true, message: "" };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));

    const result = await adapter.installTheme(
      { kind: "css-loader-api", themeId: "obsidian-bloom", baseUrl: "https://themes.hooandee.example/v1/" },
      "Hooandee Obsidian Bloom",
    );

    expect(result.themes.some((theme) => theme.name === "Hooandee Obsidian Bloom")).toBe(true);
    expect(call.mock.calls.map(([method]) => method)).toEqual([
      "get_backend_version",
      "get_themes",
      "download_theme_from_url",
      "get_backend_version",
      "get_themes",
    ]);
  });

  it("rejects a non-HTTPS install source before contacting CSS Loader", async () => {
    const fake = mutableHost();
    const adapter = new CssLoaderAdapter(fake.host);

    await expect(adapter.installTheme(
      { kind: "css-loader-api", themeId: "obsidian-bloom", baseUrl: "http://themes.example/" },
      "Hooandee Obsidian Bloom",
    )).rejects.toMatchObject({ code: "mutation_failed" });
    expect(fake.call).not.toHaveBeenCalled();
  });

  it("uses a dedicated bounded timeout for a theme download", async () => {
    vi.useFakeTimers();
    try {
      let installed = false;
      const call = vi.fn(async (method: string) => {
        if (method === "get_backend_version") return 9;
        if (method === "get_themes") return installed ? [RAW_THEME] : [];
        if (method === "download_theme_from_url") {
          await new Promise((resolve) => setTimeout(resolve, 100));
          installed = true;
          return { success: true, message: "" };
        }
        throw new Error(`Unexpected method: ${method}`);
      });
      const adapter = new CssLoaderAdapter(host({ call }), {
        timeoutMs: 50,
        installTimeoutMs: 200,
      });

      const pending = adapter.installTheme(
        { kind: "css-loader-api", themeId: "obsidian-bloom", baseUrl: "https://themes.example/" },
        "Hooandee Obsidian Bloom",
      );
      await vi.advanceTimersByTimeAsync(100);

      await expect(pending).resolves.toMatchObject({ status: "ready" });
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ["Animated grid", "No"],
    ["Motion intensity", "Full"],
  ])("writes %s and returns only after a verified refetch", async (patchName, value) => {
    const fake = mutableHost();
    const adapter = new CssLoaderAdapter(fake.host);

    const snapshot = await adapter.setPatchValue("Hooandee Obsidian Bloom", patchName, value);

    expect(snapshot.status).toBe("ready");
    expect(snapshot.themes[0].patches.find((patch) => patch.name === patchName)?.value).toBe(value);
    expect(fake.call.mock.calls.map(([method]) => method)).toEqual([
      "get_backend_version",
      "get_themes",
      "set_patch_of_theme",
      "get_backend_version",
      "get_themes",
    ]);
  });

  it("rejects values that CSS Loader did not advertise", async () => {
    const fake = mutableHost();
    const adapter = new CssLoaderAdapter(fake.host);

    await expect(adapter.setPatchValue(
      "Hooandee Obsidian Bloom",
      "Motion intensity",
      "Dangerously fast",
    )).rejects.toMatchObject({
      code: "mutation_failed",
      message: "CSS Loader did not advertise value Dangerously fast for Motion intensity",
    });
    expect(fake.call.mock.calls.map(([method]) => method)).toEqual([
      "get_backend_version",
      "get_themes",
    ]);
  });

  it("activates without dependency propagation and verifies the result", async () => {
    const fake = mutableHost();
    const adapter = new CssLoaderAdapter(fake.host);

    const snapshot = await adapter.setThemeState("Hooandee Obsidian Bloom", false);

    expect(snapshot.themes[0].enabled).toBe(false);
    expect(fake.call).toHaveBeenCalledWith(
      "set_theme_state",
      "Hooandee Obsidian Bloom",
      false,
      false,
      false,
    );
  });

  it("rejects a successful mutation call when refetch contradicts it", async () => {
    const adapter = new CssLoaderAdapter(host({
      call: vi.fn(async (method: string) => {
        if (method === "get_backend_version") return 9;
        if (method === "get_themes") return [RAW_THEME];
        if (method === "set_theme_state") return { success: true, message: "" };
        throw new Error(`Unexpected method: ${method}`);
      }),
    }));

    await expect(adapter.setThemeState("Hooandee Obsidian Bloom", false)).rejects.toEqual(
      new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader did not confirm Hooandee Obsidian Bloom as disabled",
      ),
    );
  });

  it("preserves a typed CSS Loader mutation failure", async () => {
    const adapter = new CssLoaderAdapter(host({
      call: vi.fn(async (method: string) => {
        if (method === "get_backend_version") return 9;
        if (method === "get_themes") return [RAW_THEME];
        if (method === "set_patch_of_theme") return { success: false, message: "Patch rejected" };
        throw new Error(`Unexpected method: ${method}`);
      }),
    }));

    await expect(adapter.setPatchValue(
      "Hooandee Obsidian Bloom",
      "Animated grid",
      "No",
    )).rejects.toEqual(new CssLoaderOperationError("mutation_failed", "Patch rejected"));
  });
});
