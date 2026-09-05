import { describe, expect, it, vi } from "vitest";

import { configureDeckyCssLoaderHost, createDeckyCssLoaderHost } from "./deckyCssLoaderHost";

describe("createDeckyCssLoaderHost", () => {
  it("binds inventory and calls to the CSS Loader plugin identity", async () => {
    const call = vi.fn(async () => ({ success: true, result: 9 }));
    const host = createDeckyCssLoaderHost({
      DeckyPluginLoader: {
        deckyState: {
          publicState: () => ({
            installedPlugins: [{ name: "CSS Loader", version: "2.1.2" }],
            disabledPlugins: [],
          }),
        },
      },
      DeckyBackend: { call },
    });

    expect(host.inventory()).toEqual([
      { name: "CSS Loader", version: "2.1.2", disabled: false },
    ]);
    await expect(host.call("get_backend_version")).resolves.toBe(9);
    expect(call).toHaveBeenCalledWith(
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "get_backend_version",
      {},
    );
  });

  it("translates the adapter's typed operations into CSS Loader's legacy keyword contract", async () => {
    const call = vi.fn(async () => ({ success: true, result: { success: true, message: "ok" } }));
    const host = createDeckyCssLoaderHost({
      DeckyPluginLoader: { deckyState: { publicState: () => ({ installedPlugins: [], disabledPlugins: [] }) } },
      DeckyBackend: { call },
    });

    await host.call("set_theme_state", "Example Theme", true, false, false);
    await host.call("set_patch_of_theme", "Example Theme", "Motion", "Reduced");
    await host.call("reset");

    expect(call).toHaveBeenNthCalledWith(
      1,
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "set_theme_state",
      { name: "Example Theme", state: true, set_deps: false, set_deps_value: false },
    );
    expect(call).toHaveBeenNthCalledWith(
      2,
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "set_patch_of_theme",
      { themeName: "Example Theme", patchName: "Motion", value: "Reduced" },
    );
    expect(call).toHaveBeenNthCalledWith(
      3,
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "reset",
      {},
    );
  });

  it("passes delete_theme through the exact CSS Loader keyword contract", async () => {
    const call = vi.fn(async () => ({
      success: true,
      result: { success: true, message: "Success" },
    }));
    const host = createDeckyCssLoaderHost({
      DeckyPluginLoader: { deckyState: { publicState: () => ({ installedPlugins: [], disabledPlugins: [] }) } },
      DeckyBackend: { call },
    });

    await expect(host.call("delete_theme", "Example Theme")).resolves.toEqual({
      success: true,
      message: "Success",
    });
    expect(call).toHaveBeenCalledWith(
      "loader/call_legacy_plugin_method",
      "CSS Loader",
      "delete_theme",
      { themeName: "Example Theme" },
    );
  });

  it("rejects every unsupported delete_theme arity before calling Decky", () => {
    const call = vi.fn();
    const host = createDeckyCssLoaderHost({ DeckyBackend: { call } });

    expect(() => host.call("delete_theme")).toThrow(
      "Unsupported CSS Loader call shape: delete_theme",
    );
    expect(() => host.call("delete_theme", "Example Theme", "extra")).toThrow(
      "Unsupported CSS Loader call shape: delete_theme",
    );
    expect(call).not.toHaveBeenCalled();
  });

  it("keeps using the Decky realm captured during plugin initialization", async () => {
    const call = vi.fn(async () => ({ success: true, result: 9 }));
    const deckyRealm = {
      DeckyPluginLoader: {
        deckyState: {
          publicState: () => ({
            installedPlugins: [{ name: "CSS Loader", version: "2.1.2" }],
            disabledPlugins: [],
          }),
        },
      },
      DeckyBackend: { call },
    };
    const release = configureDeckyCssLoaderHost(deckyRealm);

    try {
      const host = createDeckyCssLoaderHost();
      expect(host.inventory()).toEqual([
        { name: "CSS Loader", version: "2.1.2", disabled: false },
      ]);
      await host.call("get_backend_version");
      expect(call).toHaveBeenCalledWith(
        "loader/call_legacy_plugin_method",
        "CSS Loader",
        "get_backend_version",
        {},
      );
    } finally {
      release();
    }
  });
});
