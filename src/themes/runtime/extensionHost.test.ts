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
  type ThemeExtensionMountContextV2,
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

const SOURCE_V2 = `module.exports = Object.freeze({
  abiVersion: 2,
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
  return { status: "ready", themes };
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
  it.each([
    { source: SOURCE, abiVersion: 1 },
    { source: SOURCE_V2, abiVersion: 2 },
  ])(
    "accepts the exact frozen ABI-$abiVersion CommonJS export",
    ({ source, abiVersion }) => {
      const extension = evaluateThemeExtensionBundle(source);
      expect(extension.abiVersion).toBe(abiVersion);
      expect(Object.isFrozen(extension)).toBe(true);
    },
  );

  it.each([
    "module.exports = { abiVersion: 1, mount() { return () => {}; } };",
    "module.exports = Object.freeze({ abiVersion: 3, mount() { return () => {}; } });",
    "module.exports = Object.freeze({ abiVersion: 1, mount() { return () => {}; }, extra: true });",
    "module.exports = Object.freeze({ abiVersion: 1 });",
    "module.exports = Object.freeze({ abiVersion: 1, surface: \"home\", mount() { return () => {}; } });",
  ])("rejects invalid exports", (source) => {
    expect(() => evaluateThemeExtensionBundle(source)).toThrow();
  });
});

describe("evaluateThemeExtensionBundle surfaces", () => {
  it("accepts a keyboard surface declaration", () => {
    const extension = evaluateThemeExtensionBundle(
      "module.exports = Object.freeze({ abiVersion: 1, surface: \"keyboard\", mount() { return () => {}; } });",
    );
    expect(extension.surface).toBe("keyboard");
  });
});

describe("ThemeExtensionRuntimeHost surfaces", () => {
  const HOME = DESCRIPTOR;
  const KEYBOARD: ThemeExtensionDescriptor = {
    catalogId: "keyboard-theme", cssLoaderName: "Keyboard Theme", version: "2.0.0", abiVersion: 1, sha256: "k".repeat(64),
  };
  const SECOND_HOME: ThemeExtensionDescriptor = {
    catalogId: "second-home", cssLoaderName: "Second Home", version: "3.0.0", abiVersion: 1, sha256: "s".repeat(64),
  };
  const homeTheme = theme();
  const keyboardTheme = theme({ id: "Keyboard Theme", name: "Keyboard Theme", displayName: "Keyboard Theme", version: "2.0.0" });
  const secondHomeTheme = theme({ id: "Second Home", name: "Second Home", displayName: "Second Home", version: "3.0.0" });

  function surfaceClient(descriptors: readonly ThemeExtensionDescriptor[]): ThemeExtensionClient {
    return {
      list: vi.fn(async () => descriptors),
      load: vi.fn(async (catalogId) => {
        const descriptor = descriptors.find((item) => item.catalogId === catalogId)!;
        return { ...descriptor, source: catalogId };
      }),
    };
  }

  function recordingEvaluate(mounted: string[], stopped: string[]) {
    return vi.fn((source: string): ThemeExtensionExport => Object.freeze({
      abiVersion: 1 as const,
      ...(source === "keyboard-theme" ? { surface: "keyboard" as const } : {}),
      mount: () => {
        mounted.push(source);
        return () => { stopped.push(source); };
      },
    }));
  }

  it("mounts a home runtime and a keyboard runtime side by side", async () => {
    const mounted: string[] = [];
    const stopped: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, KEYBOARD]), doc: document, evaluate: recordingEvaluate(mounted, stopped),
    });

    host.reconcile(snapshot([homeTheme, keyboardTheme]));
    await settle();
    await settle();

    expect(mounted.sort()).toEqual(["example-theme", "keyboard-theme"]);
    host.dispose();
    expect(stopped.sort()).toEqual(["example-theme", "keyboard-theme"]);
  });

  it("keeps two home runtimes CSS-only", async () => {
    const mounted: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, SECOND_HOME]), doc: document, evaluate: recordingEvaluate(mounted, []),
    });

    host.reconcile(snapshot([homeTheme, secondHomeTheme]));
    await settle();
    await settle();

    expect(mounted).toEqual([]);
    host.dispose();
  });

  const section = (name: string, value: "Yes" | "No") => ({
    name, defaultValue: "Yes", value, options: ["Yes", "No"],
    type: "checkbox" as const, rawType: "checkbox",
  });

  it("mounts both home runtimes when their Hooandee sections do not overlap", async () => {
    const mounted: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, SECOND_HOME]), doc: document, evaluate: recordingEvaluate(mounted, []),
    });

    host.reconcile(snapshot([
      { ...homeTheme, patches: [section("Estilizar Inicio", "No"), section("Estilizar Descargas", "Yes")] },
      { ...secondHomeTheme, patches: [section("Estilizar Inicio", "Yes"), section("Estilizar Descargas", "No")] },
    ]));
    await settle();
    await settle();

    expect(mounted.sort()).toEqual(["example-theme", "second-home"]);
    host.dispose();
  });

  it("mounts only the Home owner while another section is claimed twice", async () => {
    const mounted: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, SECOND_HOME]), doc: document, evaluate: recordingEvaluate(mounted, []),
    });

    host.reconcile(snapshot([
      { ...homeTheme, patches: [section("Estilizar Inicio", "No"), section("Estilizar Descargas", "Yes")] },
      { ...secondHomeTheme, patches: [section("Estilizar Inicio", "Yes"), section("Estilizar Descargas", "Yes")] },
    ]));
    await settle();
    await settle();

    expect(mounted).toEqual(["second-home"]);
    host.dispose();
  });

  it("keeps two home runtimes CSS-only when both claim Home", async () => {
    const mounted: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, SECOND_HOME]), doc: document, evaluate: recordingEvaluate(mounted, []),
    });

    host.reconcile(snapshot([
      { ...homeTheme, patches: [section("Estilizar Inicio", "Yes")] },
      { ...secondHomeTheme, patches: [section("Estilizar Inicio", "Yes")] },
    ]));
    await settle();
    await settle();

    expect(mounted).toEqual([]);
    host.dispose();
  });

  it("remounts a mixed home runtime when its sections change", async () => {
    const mounted: string[] = [];
    const stopped: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, SECOND_HOME]), doc: document, evaluate: recordingEvaluate(mounted, stopped),
    });
    const second = { ...secondHomeTheme, patches: [section("Estilizar Inicio", "No")] };

    host.reconcile(snapshot([{ ...homeTheme, patches: [section("Estilizar Inicio", "Yes")] }, second]));
    await settle();
    await settle();
    host.reconcile(snapshot([{ ...homeTheme, patches: [section("Estilizar Inicio", "No")] }, {
      ...second, patches: [section("Estilizar Inicio", "Yes")],
    }]));
    await settle();
    await settle();

    expect(stopped.sort()).toEqual(["example-theme", "second-home"]);
    expect(mounted.filter((id) => id === "second-home")).toHaveLength(2);
    host.dispose();
  });

  it("adds a keyboard runtime without remounting the home runtime", async () => {
    const mounted: string[] = [];
    const stopped: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: surfaceClient([HOME, KEYBOARD]), doc: document, evaluate: recordingEvaluate(mounted, stopped),
    });

    host.reconcile(snapshot([homeTheme, { ...keyboardTheme, enabled: false }]));
    await settle();
    expect(mounted).toEqual(["example-theme"]);

    host.reconcile(snapshot([homeTheme, keyboardTheme]));
    await settle();
    await settle();

    expect(mounted).toEqual(["example-theme", "keyboard-theme"]);
    expect(stopped).toEqual([]);

    host.reconcile(snapshot([homeTheme, { ...keyboardTheme, enabled: false }]));
    await settle();
    expect(stopped).toEqual(["keyboard-theme"]);
    host.dispose();
  });
});

describe("ThemeExtensionRuntimeHost", () => {
  it("keeps the ABI-v1 mount context exact when QAM access is available", async () => {
    const keys: string[][] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: client(),
      doc: document,
      qam: {
        getDocument: () => document,
        subscribe: () => () => {},
      },
      evaluate: () => Object.freeze({
        abiVersion: 1,
        mount: (context: ThemeExtensionMountContext) => {
          keys.push(Object.keys(context).sort());
          return () => {};
        },
      }),
    });

    host.reconcile(snapshot());
    await settle();

    expect(keys).toEqual([["document", "host", "theme"]]);
    host.dispose();
  });

  it("exposes the live QAM document channel and releases extension subscriptions", async () => {
    const firstQamDocument = document.implementation.createHTMLDocument("QAM 1");
    const secondQamDocument = document.implementation.createHTMLDocument("QAM 2");
    let currentQamDocument: Document | null = firstQamDocument;
    let publishQamDocument!: (doc: Document) => void;
    const unsubscribe = vi.fn();
    const seen: Document[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam: {
        getDocument: () => currentQamDocument,
        subscribe: (listener) => {
          publishQamDocument = listener;
          return unsubscribe;
        },
      },
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          expect(Object.isFrozen(context.qam)).toBe(true);
          const current = context.qam.getDocument();
          if (current) seen.push(current);
          const stop = context.qam.subscribe((doc: Document) => seen.push(doc));
          return stop;
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();
    currentQamDocument = secondQamDocument;
    publishQamDocument(secondQamDocument);
    host.dispose();

    expect(seen).toEqual([firstQamDocument, secondQamDocument]);
    expect(unsubscribe).toHaveBeenCalledOnce();
  });

  it("exposes a frozen, narrowly scoped library action channel to ABI-v2 themes", async () => {
    const library = {
      launch: vi.fn(() => "started" as const),
      openSettings: vi.fn(() => true),
      openController: vi.fn(() => true),
      verticalCapsule: vi.fn(() => "/assets/812140/library_600x900.jpg"),
    };
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam: { getDocument: () => document, subscribe: () => () => {} },
      library,
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          expect(Object.isFrozen(context.library)).toBe(true);
          expect(context.library?.launch(812140)).toBe("started");
          expect(context.library?.openSettings(812140)).toBe(true);
          expect(context.library?.openController(812140)).toBe(true);
          expect(context.library?.verticalCapsule(812140)).toBe("/assets/812140/library_600x900.jpg");
          return () => {};
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();

    expect(library.launch).toHaveBeenCalledWith(812140);
    expect(library.openSettings).toHaveBeenCalledWith(812140);
    expect(library.openController).toHaveBeenCalledWith(812140);
    expect(library.verticalCapsule).toHaveBeenCalledWith(812140);
    host.dispose();
  });

  it("lets ABI-v1 themes move focus but never capture buttons", async () => {
    const navigation = { focus: vi.fn(() => true), capture: vi.fn(() => () => {}) };
    const element = document.createElement("div");
    let seen: unknown;
    const host = new ThemeExtensionRuntimeHost({
      client: client(),
      doc: document,
      navigation,
      evaluate: () => Object.freeze({
        abiVersion: 1,
        mount: (context: ThemeExtensionMountContext) => {
          seen = context.navigation;
          context.navigation?.focus(element);
          return () => {};
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();

    expect(Object.isFrozen(seen)).toBe(true);
    expect(Object.keys(seen as object)).toEqual(["focus"]);
    expect(navigation.focus).toHaveBeenCalledWith(element);
    expect(navigation.capture).not.toHaveBeenCalled();
    host.dispose();
  });

  it("exposes a frozen navigation channel to ABI-v2 themes", async () => {
    const stopCapture = vi.fn();
    const navigation = {
      focus: vi.fn(() => true),
      capture: vi.fn(() => stopCapture),
    };
    const button = document.createElement("button");
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam: { getDocument: () => document, subscribe: () => () => {} },
      navigation,
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          expect(Object.isFrozen(context.navigation)).toBe(true);
          expect(context.navigation?.focus(button)).toBe(true);
          const stop = context.navigation?.capture(() => {});
          stop?.();
          return () => {};
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();

    expect(navigation.focus).toHaveBeenCalledWith(button);
    expect(navigation.capture).toHaveBeenCalledOnce();
    expect(stopCapture).toHaveBeenCalledOnce();
    host.dispose();
  });

  it.each([
    ["mount throws after taking them", "mount"],
    ["the disposer forgets and throws", "dispose"],
    ["the theme simply never releases them", "forget"],
  ])("releases QAM subscriptions and navigation captures when %s", async (_case, failure) => {
    const stopCapture = vi.fn();
    const stopSubscribe = vi.fn();
    const navigation = { focus: vi.fn(() => true), capture: vi.fn(() => stopCapture) };
    const qam = { getDocument: () => document, subscribe: vi.fn(() => stopSubscribe) };
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam,
      navigation,
      log: () => {},
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          context.qam.subscribe(() => {});
          context.navigation?.capture(() => {});
          if (failure === "mount") throw new Error("mount failed");
          return () => { if (failure === "dispose") throw new Error("dispose failed"); };
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();
    if (failure !== "mount") {
      expect(stopCapture).not.toHaveBeenCalled();
      host.dispose();
    }

    expect(stopCapture).toHaveBeenCalledOnce();
    expect(stopSubscribe).toHaveBeenCalledOnce();
    host.dispose();
    expect(stopCapture).toHaveBeenCalledOnce();
  });

  it("releases at once a capture a theme takes after it was unmounted", async () => {
    const stopCapture = vi.fn();
    const navigation = { focus: vi.fn(() => true), capture: vi.fn(() => stopCapture) };
    let late: ThemeExtensionMountContextV2["navigation"];
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam: { getDocument: () => document, subscribe: () => () => {} },
      navigation,
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          late = context.navigation;
          return () => {};
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();
    host.dispose();
    late?.capture(() => {});

    expect(navigation.capture).toHaveBeenCalledOnce();
    expect(stopCapture).toHaveBeenCalledOnce();
  });

  it("does not release twice what the theme already released", async () => {
    const stopCapture = vi.fn();
    const navigation = { focus: vi.fn(() => true), capture: vi.fn(() => stopCapture) };
    const host = new ThemeExtensionRuntimeHost({
      client: client([{ ...DESCRIPTOR, abiVersion: 2 } as ThemeExtensionDescriptor], SOURCE_V2),
      doc: document,
      qam: { getDocument: () => document, subscribe: () => () => {} },
      navigation,
      evaluate: () => Object.freeze({
        abiVersion: 2,
        mount: (context: ThemeExtensionMountContextV2) => {
          const release = context.navigation?.capture(() => {});
          return () => release?.();
        },
      }) as unknown as ThemeExtensionExport,
    });

    host.reconcile(snapshot());
    await settle();
    host.dispose();

    expect(stopCapture).toHaveBeenCalledOnce();
  });

  it("retries a transient descriptor failure when the active inventory is unchanged", async () => {
    const extensions = client();
    extensions.list = vi.fn()
      .mockRejectedValueOnce(new Error("transient RPC failure"))
      .mockResolvedValueOnce([DESCRIPTOR]);
    const logs: string[] = [];
    const host = new ThemeExtensionRuntimeHost({
      client: extensions,
      doc: document,
      log: (code) => logs.push(code),
    });

    host.reconcile(snapshot());
    await settle();
    expect(extensions.list).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.extensionMounted).toBeUndefined();

    host.reconcile(snapshot());
    host.reconcile(snapshot());
    await settle();

    expect(extensions.list).toHaveBeenCalledTimes(2);
    expect(extensions.load).toHaveBeenCalledOnce();
    expect(document.documentElement.dataset.extensionMounted).toBe("1.2.3");
    expect(logs).toEqual(["extension_list_failed"]);
    host.dispose();
  });

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

  it("cleans up a mounted extension when the theme disappears from a ready snapshot", async () => {
    const host = new ThemeExtensionRuntimeHost({ client: client(), doc: document });

    host.reconcile(snapshot());
    await settle();
    expect(document.documentElement.dataset.extensionMounted).toBe("1.2.3");

    host.reconcile(snapshot([]));
    await settle();
    expect(document.documentElement.dataset.extensionMounted).toBeUndefined();
    host.dispose();
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
