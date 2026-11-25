// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "../cssLoaderAdapter";
import type { CssLoaderPatch, CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type { ThemePublicationState } from "../remotePublication";
import type { ThemeExtensionDescriptor } from "../themeExtensionClient";
import { ThemesClient, type ThemesDependencies } from "../themesClient";
import {
  ThemeExtensionRuntimeHost,
  type ThemeExtensionExport,
  type ThemeExtensionMountContext,
} from "./extensionHost";
import { ThemeOptionsChannel, themesClientOptionsWriter, type ThemeOptionsWriter } from "./themeOptions";

function patch(name: string, value: string, options: string[], type: CssLoaderPatch["type"] = "dropdown"): CssLoaderPatch {
  return { name, value, defaultValue: options[0] ?? "", options, type, rawType: type };
}

function vida(values: Partial<Record<string, string>> = {}, overrides: Partial<CssLoaderTheme> = {}): CssLoaderTheme {
  return {
    id: "Hooandee Vida", name: "Hooandee Vida", displayName: "Vida", version: "0.4.0", author: "Hooandee", enabled: true,
    patches: [
      patch("Burbujas", "", [], "none"),
      patch("Halo", values.Halo ?? "Azul", ["Azul", "Rosa", "Verde"]),
      patch("Intensidad del halo", values["Intensidad del halo"] ?? "50", ["0", "25", "50", "75", "100"], "slider"),
      patch("Burbujas flotantes", values["Burbujas flotantes"] ?? "Yes", ["No", "Yes"], "checkbox"),
      patch("Estilizar Inicio", values["Estilizar Inicio"] ?? "Yes", ["No", "Yes"], "checkbox"),
    ],
    ...overrides,
  };
}

const OTHER: CssLoaderTheme = {
  id: "Other", name: "Other", displayName: "Other", version: "1.0.0", author: "Someone", enabled: false,
  patches: [patch("Accent", "Red", ["Red", "Blue"])],
};

function ready(...themes: CssLoaderTheme[]): CssLoaderSnapshot {
  return { status: "ready", themes };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

async function flush(times = 6): Promise<void> {
  for (let i = 0; i < times; i += 1) await Promise.resolve();
}

describe("ThemeOptionsChannel", () => {
  function channel(writer: Partial<ThemeOptionsWriter> = {}) {
    const log = vi.fn();
    const full: ThemeOptionsWriter = { setPatches: vi.fn(async () => true), ...writer };
    const options = new ThemeOptionsChannel(full, log, () => Promise.resolve());
    options.update(ready(vida(), OTHER));
    const mount = options.forMount("hooandee-vida", "Hooandee Vida");
    return { options, writer: full, log, mount };
  }

  it("returns the theme's own editable options with current and allowed values", () => {
    const { mount } = channel();
    const values = mount.access.get();
    expect(Object.keys(values)).toEqual(["Halo", "Intensidad del halo", "Burbujas flotantes", "Estilizar Inicio"]);
    expect(values.Halo).toEqual({ value: "Azul", values: ["Azul", "Rosa", "Verde"], type: "dropdown" });
    expect(values["Intensidad del halo"].type).toBe("slider");
    expect(Object.isFrozen(values) && Object.isFrozen(values.Halo)).toBe(true);
  });

  it("get() follows every new snapshot instead of the mount-time copy", () => {
    const { options, mount } = channel();
    options.update(ready(vida({ Halo: "Rosa" }), OTHER));
    expect(mount.access.get().Halo.value).toBe("Rosa");
  });

  it("rejects patches and values that are not the theme's own, and never touches another theme", async () => {
    const { writer, mount } = channel();
    await expect(mount.access.set("Halo", "Morado")).resolves.toBe(false);
    await expect(mount.access.set("Accent", "Blue")).resolves.toBe(false);
    await expect(mount.access.set("Burbujas", "")).resolves.toBe(false);
    await expect(mount.access.set("Halo", 3 as unknown as string)).resolves.toBe(false);
    await expect(mount.access.setMany!({ Halo: "Rosa", Accent: "Blue" })).resolves.toBe(false);
    await expect(mount.access.set("Estilizar Inicio", "No")).resolves.toBe(false);
    expect(writer.setPatches).not.toHaveBeenCalled();
  });

  it("writes a valid value under the theme's catalog id and skips a value already set", async () => {
    const { writer, mount } = channel();
    await expect(mount.access.set("Halo", "Rosa")).resolves.toBe(true);
    expect(writer.setPatches).toHaveBeenCalledWith("hooandee-vida", { Halo: "Rosa" });
    await expect(mount.access.set("Intensidad del halo", "50")).resolves.toBe(true);
    expect(writer.setPatches).toHaveBeenCalledOnce();
  });

  it("serializes writes and coalesces a dragged slider to the newest value", async () => {
    const first = deferred<boolean>();
    const setPatches = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
    const { mount } = channel({ setPatches });
    const results = [
      mount.access.set("Intensidad del halo", "0"),
      mount.access.set("Intensidad del halo", "25"),
    ];
    await flush();
    expect(setPatches).toHaveBeenCalledOnce();
    results.push(mount.access.set("Intensidad del halo", "75"), mount.access.set("Intensidad del halo", "100"));
    await flush();
    expect(setPatches).toHaveBeenCalledOnce();
    first.resolve(true);
    await expect(Promise.all(results)).resolves.toEqual([true, true, true, true]);
    expect(setPatches.mock.calls.map((call) => call[1]["Intensidad del halo"])).toEqual(["25", "100"]);
  });

  it("setMany sends the changed values as one batch", async () => {
    const { writer, mount } = channel();
    await expect(mount.access.setMany!({ Halo: "Verde", "Burbujas flotantes": "No", "Intensidad del halo": "50" })).resolves.toBe(true);
    expect(writer.setPatches).toHaveBeenCalledOnce();
    expect(writer.setPatches).toHaveBeenCalledWith("hooandee-vida", { Halo: "Verde", "Burbujas flotantes": "No" });
  });

  it("retries a write Panel refused because another theme operation held the lock, and logs a real failure", async () => {
    const setPatches = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
    const retried = channel({ setPatches, busy: () => true });
    await expect(retried.mount.access.set("Halo", "Rosa")).resolves.toBe(true);
    expect(setPatches).toHaveBeenCalledTimes(2);

    const failing = channel({ setPatches: vi.fn(async () => false), busy: () => false });
    await expect(failing.mount.access.set("Halo", "Rosa")).resolves.toBe(false);
    expect(failing.writer.setPatches).toHaveBeenCalledOnce();
    expect(failing.log).toHaveBeenCalledWith("options_write_failed");
  });

  it("notifies only when this theme's values change and stops after release", () => {
    const { options, mount, log } = channel();
    const listener = vi.fn();
    const throwing = vi.fn(() => { throw new Error("theme bug"); });
    mount.access.subscribe(listener);
    mount.access.subscribe(throwing);
    options.update(ready(vida(), { ...OTHER, patches: [patch("Accent", "Blue", ["Red", "Blue"])] }));
    expect(listener).not.toHaveBeenCalled();
    options.update(ready(vida({ Halo: "Verde" }), OTHER));
    expect(listener).toHaveBeenCalledOnce();
    expect(log).toHaveBeenCalledWith("options_listener_failed");
    mount.release();
    options.update(ready(vida({ Halo: "Rosa" }), OTHER));
    expect(listener).toHaveBeenCalledOnce();
  });

  it("follows options only while a subscription is held", () => {
    const { mount } = channel();
    const listener = vi.fn();
    expect(mount.follows()).toBe(false);
    const first = mount.access.subscribe(listener);
    const second = mount.access.subscribe(listener);
    first();
    expect(mount.follows()).toBe(true);
    second();
    second();
    expect(mount.follows()).toBe(false);
  });

  it("refuses writes after the mount is released", async () => {
    const { writer, mount } = channel();
    mount.release();
    await expect(mount.access.set("Halo", "Rosa")).resolves.toBe(false);
    expect(writer.setPatches).not.toHaveBeenCalled();
  });
});

describe("theme options through Panel's Temas path", () => {
  const DESCRIPTOR: ThemeExtensionDescriptor = {
    catalogId: "hooandee-vida", cssLoaderName: "Hooandee Vida", version: "0.4.0", abiVersion: 2, sha256: "b".repeat(64),
  };
  const PUBLICATION: ThemePublicationState = {
    status: "published",
    checkedAt: 1,
    themes: [{
      catalogId: "hooandee-vida", cssLoaderName: "Hooandee Vida", publishedVersion: "0.4.0",
      displayName: { es: "Vida", en: "Vida", it: "Vida" }, description: { es: "", en: "", it: "" },
      author: "Hooandee", tags: [], notes: {}, compatibility: "compatible", exclusiveGroup: "interface",
    }],
  };

  function world() {
    let current = vida();
    const others = [OTHER];
    const snapshot = (): CssLoaderReadySnapshot => ({ status: "ready", themes: [structuredClone(current), ...others] });
    const setPatchValue = vi.fn(async (themeName: string, patchName: string, value: string) => {
      if (themeName !== "Hooandee Vida") throw new Error("wrong theme");
      current = { ...current, patches: current.patches.map((p) => p.name === patchName ? { ...p, value } : p) };
      return snapshot();
    });
    const deps: ThemesDependencies = {
      adapter: {
        inspect: vi.fn(async () => snapshot()),
        requireReady: vi.fn(async () => snapshot()),
        reloadTheme: vi.fn(async () => snapshot()),
        restoreThemeSnapshot: vi.fn(async () => snapshot()),
        reconcileRecoveredThemes: vi.fn(async () => snapshot()),
        setPatchValue,
        deleteTheme: vi.fn(async () => snapshot()),
      },
      installer: {
        prepare: vi.fn(), commit: vi.fn(), discardReceipt: vi.fn(), rollback: vi.fn(),
        pendingRecoveries: vi.fn(async () => []), acknowledgeRollback: vi.fn(),
      },
      activator: { activate: vi.fn(async () => snapshot()), deactivate: vi.fn(async () => snapshot()) },
      publication: { check: vi.fn(async () => PUBLICATION) },
      reportFailure: vi.fn(),
    };
    return { deps, setPatchValue, value: (name: string) => current.patches.find((p) => p.name === name)!.value };
  }

  async function mounted(subscribe: boolean) {
    const { deps, setPatchValue, value } = world();
    const reportFailure = deps.reportFailure;
    const themes = new ThemesClient(deps);
    await themes.refresh();
    await themes.refreshPublication();
    const contexts: ThemeExtensionMountContext[] = [];
    const stops: number[] = [];
    const changes = vi.fn();
    const unsubscribes: (() => void)[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: {
        list: vi.fn(async () => [DESCRIPTOR]),
        load: vi.fn(async () => ({ ...DESCRIPTOR, source: "" })),
      },
      doc: document,
      qam: { getDocument: () => null, subscribe: () => () => {} },
      options: themesClientOptionsWriter(themes),
      evaluate: () => Object.freeze({
        abiVersion: 2 as const,
        mount(context: ThemeExtensionMountContext) {
          contexts.push(context);
          if (subscribe) unsubscribes.push(context.options!.subscribe(changes));
          return () => { stops.push(contexts.indexOf(context)); };
        },
      }) as ThemeExtensionExport,
    });
    const unsubscribe = themes.subscribe(() => host.reconcile(themes.getSnapshot().snapshot), 60_000);
    host.reconcile(themes.getSnapshot().snapshot);
    await flush(12);
    return { themes, host, contexts, stops, changes, setPatchValue, value, reportFailure, unsubscribeOptions: () => unsubscribes.forEach((off) => off()), dispose: () => { unsubscribe(); host.dispose(); } };
  }

  it("writes through the same ThemesClient as the Temas screen, which then shows the new value", async () => {
    const world = await mounted(true);
    const options = world.contexts[0].options!;
    await expect(options.set("Halo", "Rosa")).resolves.toBe(true);
    expect(world.setPatchValue).toHaveBeenCalledWith("Hooandee Vida", "Halo", "Rosa");
    const shown = world.themes.getSnapshot().snapshot.themes.find((t) => t.name === "Hooandee Vida")!;
    expect(shown.patches.find((p) => p.name === "Halo")!.value).toBe("Rosa");
    expect(options.get().Halo.value).toBe("Rosa");
    expect(world.changes).toHaveBeenCalled();
    world.dispose();
  });

  it("sees a change made from the Temas screen, and keeps a runtime that follows its options mounted", async () => {
    const world = await mounted(true);
    await expect(world.themes.setPatch("hooandee-vida", "Intensidad del halo", "100")).resolves.toBe(true);
    await flush(12);
    expect(world.changes).toHaveBeenCalledOnce();
    expect(world.contexts[0].options!.get()["Intensidad del halo"].value).toBe("100");
    expect(world.contexts).toHaveLength(1);
    expect(world.stops).toEqual([]);
    expect(world.contexts[0].theme.patches.find((p) => p.name === "Intensidad del halo")!.value).toBe("50");
    world.dispose();
  });

  it("refuses a runtime's section switch, and still remounts a following runtime when the user switches one", async () => {
    const world = await mounted(true);
    await expect(world.contexts[0].options!.set("Estilizar Inicio", "No")).resolves.toBe(false);
    await expect(world.themes.setRuntimePatches("hooandee-vida", { "Estilizar Inicio": "No" })).resolves.toBe(false);
    expect(world.setPatchValue).not.toHaveBeenCalled();
    await expect(world.themes.setPatch("hooandee-vida", "Estilizar Inicio", "No")).resolves.toBe(true);
    await flush(12);
    expect(world.stops).toEqual([0]);
    world.dispose();
  });

  it("writes quietly: no operation on the Temas screen, and a failure is not the user's error", async () => {
    const world = await mounted(true);
    const operations: unknown[] = [];
    const off = world.themes.subscribe(() => operations.push(world.themes.getSnapshot().operation), 60_000);
    await expect(world.contexts[0].options!.set("Halo", "Rosa")).resolves.toBe(true);
    world.setPatchValue.mockRejectedValueOnce(new Error("css loader"));
    await expect(world.contexts[0].options!.set("Halo", "Verde")).resolves.toBe(false);
    expect(operations.filter((operation) => operation !== null)).toEqual([]);
    expect(world.themes.getSnapshot().error).toBeNull();
    expect(world.reportFailure).not.toHaveBeenCalled();
    off();
    world.dispose();
  });

  it("remounts a runtime again once it drops its options subscription", async () => {
    const world = await mounted(true);
    world.unsubscribeOptions();
    await expect(world.themes.setPatch("hooandee-vida", "Halo", "Verde")).resolves.toBe(true);
    await flush(12);
    expect(world.stops).toEqual([0]);
    expect(world.contexts).toHaveLength(2);
    world.dispose();
  });

  it("remounts a runtime that never subscribed, as before", async () => {
    const world = await mounted(false);
    await expect(world.contexts[0].options!.set("Halo", "Verde")).resolves.toBe(true);
    await flush(12);
    expect(world.stops).toEqual([0]);
    expect(world.contexts).toHaveLength(2);
    expect(world.contexts[1].theme.patches.find((p) => p.name === "Halo")!.value).toBe("Verde");
    world.dispose();
  });

  it("restores defaults in one Panel operation and waits for a Temas save in progress", async () => {
    const world = await mounted(true);
    const options = world.contexts[0].options!;
    await options.set("Halo", "Verde");
    const temas = world.themes.setPatch("hooandee-vida", "Burbujas flotantes", "No");
    const restore = options.setMany!({ Halo: "Azul", "Intensidad del halo": "0" });
    await expect(temas).resolves.toBe(true);
    await expect(restore).resolves.toBe(true);
    expect(world.value("Halo")).toBe("Azul");
    expect(world.value("Intensidad del halo")).toBe("0");
    expect(world.value("Burbujas flotantes")).toBe("No");
    world.dispose();
  });

  it("lets a Temas save made during a runtime write wait for it instead of being refused", async () => {
    const world = await mounted(true);
    const gate = deferred<void>();
    const write = world.setPatchValue.getMockImplementation()!;
    world.setPatchValue.mockImplementationOnce(async (...args) => { await gate.promise; return write(...args); });
    const runtime = world.contexts[0].options!.set("Halo", "Rosa");
    await flush();
    const temas = world.themes.setPatch("hooandee-vida", "Burbujas flotantes", "No");
    gate.resolve();
    await expect(runtime).resolves.toBe(true);
    await expect(temas).resolves.toBe(true);
    expect(world.value("Halo")).toBe("Rosa");
    expect(world.value("Burbujas flotantes")).toBe("No");
    world.dispose();
  });

  it("is absent when Panel offers no writer (Windows host)", async () => {
    let seen: ThemeExtensionMountContext | undefined;
    const host = new ThemeExtensionRuntimeHost({
      client: { list: vi.fn(async () => [{ ...DESCRIPTOR, abiVersion: 1 as const }]), load: vi.fn(async () => ({ ...DESCRIPTOR, abiVersion: 1 as const, source: "" })) },
      doc: document,
      evaluate: () => Object.freeze({ abiVersion: 1 as const, mount: (context: ThemeExtensionMountContext) => { seen = context; return () => {}; } }),
    });
    host.reconcile(ready(vida()));
    await flush(12);
    expect(seen).toBeDefined();
    expect(seen && "options" in seen).toBe(false);
    host.dispose();
  });
});

describe("ThemesClient.setPatches", () => {
  it("applies every value in one operation and reports an unknown theme", async () => {
    const theme = vida();
    const deps = {
      adapter: {
        inspect: vi.fn(async () => ready(theme)), requireReady: vi.fn(async () => ready(theme) as CssLoaderReadySnapshot),
        reloadTheme: vi.fn(), restoreThemeSnapshot: vi.fn(), reconcileRecoveredThemes: vi.fn(), deleteTheme: vi.fn(),
        setPatchValue: vi.fn(async () => ready(theme)),
      },
      installer: { prepare: vi.fn(), commit: vi.fn(), discardReceipt: vi.fn(), rollback: vi.fn(), pendingRecoveries: vi.fn(async () => []), acknowledgeRollback: vi.fn() },
      activator: { activate: vi.fn(), deactivate: vi.fn() },
      publication: { check: vi.fn(async () => ({ status: "published" as const, checkedAt: 1, themes: [{
        catalogId: "hooandee-vida", cssLoaderName: "Hooandee Vida", publishedVersion: "0.4.0",
        displayName: { es: "Vida", en: "Vida", it: "Vida" }, description: { es: "", en: "", it: "" },
        author: "Hooandee", tags: [], notes: {}, compatibility: "compatible" as const, exclusiveGroup: "interface",
      }] })) },
      reportFailure: vi.fn(),
    } as unknown as ThemesDependencies;
    const client = new ThemesClient(deps);
    await client.refresh();
    await client.refreshPublication();
    const operations: unknown[] = [];
    client.subscribe(() => operations.push(client.getSnapshot().operation), 60_000);
    await expect(client.setPatches("hooandee-vida", { Halo: "Rosa", "Burbujas flotantes": "No" })).resolves.toBe(true);
    expect(deps.adapter.setPatchValue).toHaveBeenNthCalledWith(1, "Hooandee Vida", "Halo", "Rosa");
    expect(deps.adapter.setPatchValue).toHaveBeenNthCalledWith(2, "Hooandee Vida", "Burbujas flotantes", "No");
    expect(operations.filter((operation) => operation !== null)).toEqual(
      expect.arrayContaining([{ kind: "saving", themeId: "hooandee-vida", patchNames: ["Halo", "Burbujas flotantes"] }]),
    );
    expect(new Set(operations.filter((operation) => operation !== null)).size).toBe(1);
    await expect(client.setPatches("unknown", { Halo: "Rosa" })).resolves.toBe(false);
    expect(deps.reportFailure).toHaveBeenCalledWith(expect.objectContaining({ code: "unknown_theme" }));
  });
});
