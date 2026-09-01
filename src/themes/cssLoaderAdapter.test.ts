import { describe, expect, it, vi } from "vitest";

import {
  CssLoaderAdapter,
  CssLoaderOperationError,
  type CssLoaderHost,
} from "./cssLoaderAdapter";

const RAW_THEME = {
  id: "Example Theme",
  name: "Example Theme",
  display_name: "Example Theme",
  version: "0.1.0",
  author: "Example Author",
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
      id: "Example Theme",
      name: "Example Theme",
      displayName: "Example Theme",
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

  it("fails closed when CSS Loader returns ambiguous theme or patch names", async () => {
    const duplicateTheme = new CssLoaderAdapter(host({
      call: vi.fn(async (method: string) => method === "get_backend_version"
        ? 9
        : [RAW_THEME, { ...RAW_THEME, id: "duplicate-id" }]),
    }));
    const duplicatePatch = new CssLoaderAdapter(host({
      call: vi.fn(async (method: string) => method === "get_backend_version"
        ? 9
        : [{
          ...RAW_THEME,
          patches: [RAW_THEME.patches[0], { ...RAW_THEME.patches[0] }],
        }]),
    }));

    await expect(duplicateTheme.inspect()).resolves.toMatchObject({
      status: "error",
      error: { code: "malformed_response" },
    });
    await expect(duplicatePatch.inspect()).resolves.toMatchObject({
      status: "error",
      error: { code: "malformed_response" },
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
  it("reloads CSS Loader and verifies the exact installed theme version", async () => {
    let version = "0.5.0";
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [{ ...RAW_THEME, version }];
      if (method === "reset") {
        version = "0.6.0";
        return { fails: [] };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));

    const before = await adapter.requireReady();
    const result = await adapter.reloadTheme("Example Theme", "0.6.0", before);

    expect(result.themes.find((theme) => theme.name === "Example Theme")?.version).toBe("0.6.0");
    expect(call.mock.calls.map(([method]) => method)).toEqual([
      "get_backend_version",
      "get_themes",
      "reset",
      "get_backend_version",
      "get_themes",
      "get_backend_version",
      "get_themes",
    ]);
  });

  it("rejects a reload when CSS Loader reports a different installed version", async () => {
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [{ ...RAW_THEME, version: "0.5.0" }];
      if (method === "reset") return { fails: [] };
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));

    const before = await adapter.requireReady();
    await expect(adapter.reloadTheme("Example Theme", "0.6.0", before)).rejects.toEqual(
      new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader did not register Example Theme v0.6.0",
      ),
    );
  });

  it("fails closed when CSS Loader returns a malformed reset result", async () => {
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [{ ...RAW_THEME, version: "0.6.0" }];
      if (method === "reset") return { success: true, message: "not the reset contract" };
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));

    const before = await adapter.requireReady();
    await expect(adapter.reloadTheme("Example Theme", "0.6.0", before)).rejects.toEqual(
      new CssLoaderOperationError(
        "malformed_response",
        "CSS Loader returned an invalid result for reset",
      ),
    );
  });

  it("rejects a reset that reports any theme load failure", async () => {
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [{ ...RAW_THEME, version: "0.5.0" }];
      if (method === "reset") return { fails: [["Third Party Theme", "invalid manifest"]] };
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    await expect(adapter.reloadTheme("Example Theme", "0.6.0", before)).rejects.toMatchObject({
      code: "mutation_failed",
      message: "CSS Loader could not reload Third Party Theme: invalid manifest",
    });
  });

  it("verifies that activation, compatible patches, and third-party themes survive reload", async () => {
    const themeBefore = {
      ...RAW_THEME,
      version: "0.5.0",
      enabled: true,
      patches: [{ ...RAW_THEME.patches[0], value: "No" }],
    };
    const thirdParty = { ...RAW_THEME, id: "Other", name: "Other", version: "1.4.0", enabled: false };
    let themes = [themeBefore, thirdParty];
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return structuredClone(themes);
      if (method === "reset") {
        themes = [{ ...themeBefore, version: "0.6.0" }, thirdParty];
        return { fails: [] };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    await expect(adapter.reloadTheme("Example Theme", "0.6.0", before)).resolves.toMatchObject({
      status: "ready",
    });
  });

  it("fails when reload changes a third-party theme or a preserved theme setting", async () => {
    const themeBefore = { ...RAW_THEME, version: "0.5.0", enabled: true };
    const thirdParty = { ...RAW_THEME, id: "Other", name: "Other", version: "1.4.0", enabled: false };
    let reset = false;
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return reset
        ? [{ ...themeBefore, version: "0.6.0", enabled: false }, { ...thirdParty, enabled: true }]
        : [themeBefore, thirdParty];
      if (method === "reset") {
        reset = true;
        return { fails: [] };
      }
      if (method === "set_theme_state" || method === "set_patch_of_theme") {
        return { success: true, message: "" };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    await expect(adapter.reloadTheme("Example Theme", "0.6.0", before)).rejects.toMatchObject({
      code: "verification_failed",
    });
  });

  it("can reset and verify the exact pre-install snapshot after rollback", async () => {
    const original = { ...RAW_THEME, version: "0.5.0" };
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return [original];
      if (method === "reset") return { fails: [] };
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    await expect(adapter.restoreThemeSnapshot(before)).resolves.toEqual(before);
  });

  it("restores compatible settings and unrelated activation changed by reset", async () => {
    const original = {
      ...RAW_THEME,
      version: "0.5.0",
      enabled: true,
      patches: [{ ...RAW_THEME.patches[0], value: "No" }],
    };
    const thirdParty = {
      ...RAW_THEME,
      id: "Other",
      name: "Other",
      version: "1.4.0",
      enabled: false,
      patches: [{ ...RAW_THEME.patches[0], value: "Yes" }],
    };
    let themes = structuredClone([original, thirdParty]);
    const call = vi.fn(async (method: string, ...args: unknown[]) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return structuredClone(themes);
      if (method === "reset") {
        themes[0].enabled = false;
        themes[0].patches[0].value = "Yes";
        themes[1].enabled = true;
        return { fails: [] };
      }
      if (method === "set_theme_state") {
        const target = themes.find((theme) => theme.name === args[0]);
        if (target) target.enabled = args[1] as boolean;
        return { success: true, message: "" };
      }
      if (method === "set_patch_of_theme") {
        const target = themes.find((theme) => theme.name === args[0]);
        const patch = target?.patches.find((candidate) => candidate.name === args[1]);
        if (patch) patch.value = args[2] as string;
        return { success: true, message: "" };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    await expect(adapter.restoreThemeSnapshot(before)).resolves.toEqual(before);
    expect(call).toHaveBeenCalledWith("set_theme_state", "Example Theme", true, false, false);
    expect(call).toHaveBeenCalledWith("set_patch_of_theme", "Example Theme", "Animated grid", "No");
    expect(call).toHaveBeenCalledWith("set_theme_state", "Other", false, false, false);
  });

  it("quarantines writes after a timed-out reset until the original call settles", async () => {
    vi.useFakeTimers();
    try {
      let settleReset!: (value: { fails: never[] }) => void;
      let resetCalls = 0;
      const call = vi.fn((method: string) => {
        if (method === "get_backend_version") return Promise.resolve(9);
        if (method === "get_themes") return Promise.resolve([{ ...RAW_THEME, version: "0.5.0" }]);
        if (method === "reset") {
          resetCalls += 1;
          if (resetCalls === 1) {
            return new Promise<{ fails: never[] }>((done) => { settleReset = done; });
          }
          return Promise.resolve({ fails: [] });
        }
        return Promise.reject(new Error(`Unexpected method: ${method}`));
      });
      const adapter = new CssLoaderAdapter(host({ call }), { reloadTimeoutMs: 50 });
      const before = await adapter.requireReady();

      const reload = adapter.reloadTheme("Example Theme", "0.6.0", before);
      const reloadFailure = expect(reload).rejects.toMatchObject({ code: "timeout" });
      await vi.advanceTimersByTimeAsync(50);
      await reloadFailure;
      await expect(adapter.restoreThemeSnapshot(before)).rejects.toMatchObject({ code: "timeout" });
      expect(resetCalls).toBe(1);

      settleReset({ fails: [] });
      await vi.advanceTimersByTimeAsync(0);

      await expect(adapter.restoreThemeSnapshot(before)).resolves.toEqual(before);
      expect(resetCalls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reconciles a durable rollback after restart and protects every unrelated theme", async () => {
    const themeNew = { ...RAW_THEME, version: "0.6.0" };
    const themeOld = { ...themeNew, version: "0.5.0" };
    const thirdParty = { ...RAW_THEME, id: "Other", name: "Other", version: "1.4.0" };
    let reset = false;
    const call = vi.fn(async (method: string) => {
      if (method === "get_backend_version") return 9;
      if (method === "get_themes") return reset
        ? [themeOld, thirdParty]
        : [themeNew, thirdParty];
      if (method === "reset") {
        reset = true;
        return { fails: [] };
      }
      throw new Error(`Unexpected method: ${method}`);
    });
    const adapter = new CssLoaderAdapter(host({ call }));
    const before = await adapter.requireReady();

    const after = await adapter.reconcileRecoveredThemes([{
      themeName: "Example Theme",
      previousVersion: "0.5.0",
    }], before);

    expect(after.themes.find((theme) => theme.name === "Example Theme")?.version).toBe("0.5.0");
  });

  it.each(["activation", "patch"] as const)(
    "rejects durable recovery when CSS Loader changes the theme %s state",
    async (changedState) => {
      const themeNew = {
        ...RAW_THEME,
        version: "0.6.0",
        enabled: true,
        patches: [{ ...RAW_THEME.patches[0], value: "No" }],
      };
      const themeOld = {
        ...themeNew,
        version: "0.5.0",
        ...(changedState === "activation"
          ? { enabled: false }
          : { patches: [{ ...RAW_THEME.patches[0], value: "Yes" }] }),
      };
      let reset = false;
      const call = vi.fn(async (method: string) => {
        if (method === "get_backend_version") return 9;
        if (method === "get_themes") return reset ? [themeOld] : [themeNew];
        if (method === "reset") {
          reset = true;
          return { fails: [] };
        }
        if (method === "set_theme_state" || method === "set_patch_of_theme") {
          return { success: true, message: "" };
        }
        throw new Error(`Unexpected method: ${method}`);
      });
      const adapter = new CssLoaderAdapter(host({ call }));
      const before = await adapter.requireReady();

      await expect(adapter.reconcileRecoveredThemes([{
        themeName: "Example Theme",
        previousVersion: "0.5.0",
      }], before)).rejects.toMatchObject({ code: "verification_failed" });
    },
  );

  it.each([
    ["Animated grid", "No"],
    ["Motion intensity", "Full"],
  ])("writes %s and returns only after a verified refetch", async (patchName, value) => {
    const fake = mutableHost();
    const adapter = new CssLoaderAdapter(fake.host);

    const snapshot = await adapter.setPatchValue("Example Theme", patchName, value);

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
      "Example Theme",
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

    const snapshot = await adapter.setThemeState("Example Theme", false);

    expect(snapshot.themes[0].enabled).toBe(false);
    expect(fake.call).toHaveBeenCalledWith(
      "set_theme_state",
      "Example Theme",
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

    await expect(adapter.setThemeState("Example Theme", false)).rejects.toEqual(
      new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader did not confirm Example Theme as disabled",
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
      "Example Theme",
      "Animated grid",
      "No",
    )).rejects.toEqual(new CssLoaderOperationError("mutation_failed", "Patch rejected"));
  });
});
