// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type {
  ThemeExtensionClient,
  ThemeExtensionDescriptor,
  ThemeExtensionPayload,
} from "../themeExtensionClient";
import {
  evaluateThemeExtensionBundle,
  ThemeExtensionRuntimeHost,
  type ThemeExtensionExport,
  type ThemeExtensionMountContext,
} from "./extensionHost";

const DESCRIPTOR: ThemeExtensionDescriptor = {
  catalogId: "example-theme",
  cssLoaderName: "Example Theme",
  version: "1.2.3",
  abiVersion: 1,
  sha256: "a".repeat(64),
};

const SOURCE = `module.exports = Object.freeze({
  abiVersion: 1,
  mount(context) {
    context.document.documentElement.dataset.extensionMounted = context.theme.version;
    return () => { delete context.document.documentElement.dataset.extensionMounted; };
  }
});`;

function theme(overrides: Partial<CssLoaderTheme> = {}): CssLoaderTheme {
  return {
    id: "Example Theme", name: "Example Theme", displayName: "Example Theme", version: "1.2.3",
    author: "Example Author", enabled: true, patches: [], ...overrides,
  };
}

function snapshot(themes: CssLoaderTheme[] = [theme()]): CssLoaderSnapshot {
  return { status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes };
}

function client(
  descriptors: readonly ThemeExtensionDescriptor[] = [DESCRIPTOR],
  source = SOURCE,
): ThemeExtensionClient {
  return {
    list: vi.fn(async () => descriptors),
    load: vi.fn(async (catalogId, version) => {
      const selected = descriptors.find((descriptor) => (
        descriptor.catalogId === catalogId && descriptor.version === version
      )) ?? DESCRIPTOR;
      return { ...selected, catalogId, version, source };
    }),
  };
}

async function settle(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("evaluateThemeExtensionBundle", () => {
  it("accepts only the exact frozen ABI-v1 CommonJS export", () => {
    const extension = evaluateThemeExtensionBundle(SOURCE);
    expect(extension.abiVersion).toBe(1);
    expect(Object.isFrozen(extension)).toBe(true);
  });

  it.each([
    "module.exports = { abiVersion: 1, mount() { return () => {}; } };",
    "module.exports = Object.freeze({ abiVersion: 2, mount() { return () => {}; } });",
    "module.exports = Object.freeze({ abiVersion: 1, mount() { return () => {}; }, extra: true });",
    "module.exports = Object.freeze({ abiVersion: 1 });",
  ])("rejects invalid exports", (source) => {
    expect(() => evaluateThemeExtensionBundle(source)).toThrow();
  });
});

describe("ThemeExtensionRuntimeHost", () => {
  it("loads lazily only for one exact active descriptor and disposes on deactivation", async () => {
    const extensions = client();
    const host = new ThemeExtensionRuntimeHost({ client: extensions, doc: document });

    host.reconcile(snapshot());
    await settle();
    expect(extensions.load).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.extensionMounted).toBe("1.2.3");

    host.reconcile(snapshot([theme({ enabled: false })]));
    await settle();
    expect(document.documentElement.dataset.extensionMounted).toBeUndefined();
  });

  it.each([
    [[]],
    [[{ ...DESCRIPTOR, cssLoaderName: "Second Theme" }]],
    [[{ ...DESCRIPTOR, version: "1.2.4" }]],
    [[DESCRIPTOR, { ...DESCRIPTOR, catalogId: "second-theme" }]],
  ])("mounts nothing for absent, mismatched or ambiguous descriptors", async (descriptors) => {
    const extensions = client(descriptors);
    const host = new ThemeExtensionRuntimeHost({ client: extensions, doc: document });

    host.reconcile(snapshot());
    await settle();
    expect(extensions.load).not.toHaveBeenCalled();
  });

  it("deduplicates concurrent loads and reconciles verified patch changes", async () => {
    let resolve!: (payload: Awaited<ReturnType<ThemeExtensionClient["load"]>>) => void;
    const extensions = client();
    extensions.load = vi.fn(() => new Promise<ThemeExtensionPayload>((done) => { resolve = done; }));
    const mounts: string[] = [];
    const stops: string[] = [];
    const evaluate = vi.fn((): ThemeExtensionExport => Object.freeze({
      abiVersion: 1,
      mount: ({ theme: activeTheme }: ThemeExtensionMountContext) => {
        const value = activeTheme.patches[0]?.value ?? "none";
        mounts.push(value);
        return () => { stops.push(value); };
      },
    }));
    const host = new ThemeExtensionRuntimeHost({ client: extensions, doc: document, evaluate });

    host.reconcile(snapshot());
    host.reconcile(snapshot());
    await settle();
    expect(extensions.load).toHaveBeenCalledOnce();
    resolve({ ...DESCRIPTOR, source: SOURCE });
    await settle();
    expect(mounts).toEqual(["none"]);

    host.reconcile(snapshot([theme({ patches: [{
      name: "Motion", defaultValue: "Yes", value: "No", options: ["No", "Yes"],
      type: "checkbox", rawType: "checkbox",
    }] })]));
    await settle();
    expect(extensions.load).toHaveBeenCalledOnce();
    expect(stops).toEqual(["none"]);
    expect(mounts).toEqual(["none", "No"]);
  });

  it("does not mount a stale async completion after state changes or unload", async () => {
    let resolve!: (payload: Awaited<ReturnType<ThemeExtensionClient["load"]>>) => void;
    const extensions = client();
    extensions.load = vi.fn(() => new Promise<ThemeExtensionPayload>((done) => { resolve = done; }));
    const mount = vi.fn(() => vi.fn());
    const host = new ThemeExtensionRuntimeHost({
      client: extensions,
      doc: document,
      evaluate: () => Object.freeze({ abiVersion: 1, mount }),
    });

    host.reconcile(snapshot());
    await settle();
    host.reconcile({ status: "missing", themes: [] });
    host.dispose();
    resolve({ ...DESCRIPTOR, source: SOURCE });
    await settle();
    expect(mount).not.toHaveBeenCalled();
  });

  it("disposes a mounted extension exactly once on plugin unload", async () => {
    const stop = vi.fn();
    const host = new ThemeExtensionRuntimeHost({
      client: client(),
      doc: document,
      evaluate: () => Object.freeze({ abiVersion: 1, mount: () => stop }),
    });

    host.reconcile(snapshot());
    await settle();
    host.dispose();
    host.dispose();

    expect(stop).toHaveBeenCalledOnce();
  });

  it("rejects descriptor-mismatched payloads without caching them", async () => {
    const extensions = client();
    extensions.load = vi.fn(async () => ({
      ...DESCRIPTOR,
      sha256: "b".repeat(64),
      source: SOURCE,
    }));
    const logs: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: extensions,
      doc: document,
      log: (code) => logs.push(code),
    });

    host.reconcile(snapshot());
    await settle();
    host.reconcile({ status: "missing", themes: [] });
    host.reconcile(snapshot());
    await settle();

    expect(extensions.load).toHaveBeenCalledTimes(2);
    expect(logs).toEqual(["extension_payload_mismatch", "extension_payload_mismatch"]);
    expect(document.documentElement.dataset.extensionMounted).toBeUndefined();
  });

  it("reloads on descriptor hash replacement and isolates evaluation, mount and dispose failures", async () => {
    const descriptors = [DESCRIPTOR];
    const extensions = client(descriptors);
    const logs: string[] = [];
    const disposer = vi.fn(() => { throw new Error("dispose failed"); });
    const evaluate = vi.fn()
      .mockImplementationOnce(() => Object.freeze({ abiVersion: 1, mount: () => disposer }))
      .mockImplementationOnce(() => { throw new Error("evaluation failed"); })
      .mockImplementationOnce(() => Object.freeze({ abiVersion: 1, mount: () => { throw new Error("mount failed"); } }));
    const host = new ThemeExtensionRuntimeHost({
      client: extensions, doc: document, evaluate, log: (code) => logs.push(code),
    });

    host.reconcile(snapshot());
    await settle();
    descriptors[0] = { ...DESCRIPTOR, sha256: "b".repeat(64) };
    host.refreshDescriptors();
    await settle();
    host.reconcile(snapshot());
    await settle();
    descriptors[0] = { ...DESCRIPTOR, sha256: "c".repeat(64) };
    host.refreshDescriptors();
    await settle();
    host.reconcile(snapshot());
    await settle();

    expect(extensions.load).toHaveBeenCalledTimes(3);
    expect(logs).toEqual(expect.arrayContaining(["extension_dispose_failed", "extension_evaluation_failed", "extension_mount_failed"]));
    expect(logs.join(" ")).not.toContain("example-theme");
  });
});
