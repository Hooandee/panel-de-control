import { describe, expect, it, vi } from "vitest";

import type {
  QuickAccessTabCompositionConfig,
  QuickAccessTabCompositionRegistration,
  QuickAccessTabRegistration,
} from "../deckyInternal";
import type { QamInventoryEntry } from "./composer";
import type { QamLayout } from "./layout";
import { readRenderedQamKeys } from "./renderedKeys";
import {
  getQamRuntimeSnapshot,
  startQamComposerRuntime,
  type QamComposerRuntimeDependencies,
} from "./runtime";
import type { QamViewDescriptor } from "./viewCatalog";

const icon = () => null;
const catalog: QamViewDescriptor[] = [
  {
    token: "pdc:home",
    labelKey: "home.title",
    descriptionKey: "home.subtitle",
    accent: "#000",
    icon,
    target: { kind: "home" },
  },
  {
    token: "pdc:section:hud",
    labelKey: "nav.hud",
    descriptionKey: "nav.hud.desc",
    accent: "#000",
    icon,
    target: { kind: "section", id: "hud" },
  },
];

function layout(pinnedViews: string[], order = pinnedViews): QamLayout {
  return { order, hiddenNative: [], pinnedViews, ownedIds: {} };
}

function setup(initial = layout(["pdc:home"])) {
  let currentLayout = initial;
  let currentCatalog = catalog;
  const layoutListeners = new Set<() => void>();
  const catalogListeners = new Set<() => void>();
  const registrations = new Map<string, { dispose: ReturnType<typeof vi.fn> }>();
  let renderedKeys: string[] | null = null;
  let expectedKeys: string[] | null = null;
  let compositionConfig: QuickAccessTabCompositionConfig | null = null;
  const readbacks: Array<() => void> = [];
  const composition: QuickAccessTabCompositionRegistration = {
    configured: true,
    update: vi.fn((config: QuickAccessTabCompositionConfig) => {
      compositionConfig = config;
      return true;
    }),
    expectedKeys: () => expectedKeys,
    dispose: vi.fn(),
  };
  const deps: QamComposerRuntimeDependencies = {
    getLayout: () => currentLayout,
    saveLayout: vi.fn((next) => { currentLayout = next; }),
    subscribeLayout: (listener) => {
      layoutListeners.add(listener);
      return () => layoutListeners.delete(listener);
    },
    getCatalog: () => currentCatalog,
    subscribeCatalog: (listener) => {
      catalogListeners.add(listener);
      return () => catalogListeners.delete(listener);
    },
    occupiedIds: () => new Set([999]),
    cleanupOwned: vi.fn(() => false),
    registerOwned: vi.fn((_id, descriptor): QuickAccessTabRegistration => {
      const dispose = vi.fn();
      registrations.set(descriptor.token, { dispose });
      return { registered: true, restartRequired: false, reason: "registered", dispose };
    }),
    configure: vi.fn((config) => {
      compositionConfig = config;
      return composition;
    }),
    readRenderedKeys: () => renderedKeys,
    scheduleReadback: (readback) => {
      readbacks.push(readback);
      return () => {
        const index = readbacks.indexOf(readback);
        if (index >= 0) readbacks.splice(index, 1);
      };
    },
  };
  return {
    deps,
    composition,
    registrations,
    setLayout(next: QamLayout) {
      currentLayout = next;
      layoutListeners.forEach((listener) => listener());
    },
    setCatalog(next: QamViewDescriptor[]) {
      currentCatalog = next;
      catalogListeners.forEach((listener) => listener());
    },
    setCompositionReadback(expected: string[], rendered: string[]) {
      expectedKeys = expected;
      renderedKeys = rendered;
    },
    emitInventory(entries = [] as QamInventoryEntry[]) {
      compositionConfig?.onInventory?.(entries);
    },
    flushReadbacks() {
      readbacks.splice(0).forEach((readback) => readback());
    },
  };
}

describe("QAM composer runtime", () => {
  it("keeps shortcut edits live while the hidden QAM retains its previous DOM", () => {
    const harness = setup();
    let hidden = false;
    let rendered = ["5260355", "4", "999"];
    const document = {
      get hidden() { return hidden; },
      querySelectorAll: () => rendered.map((id) => ({ id: `quickaccess_tab_${id}` })),
    } as unknown as Document;
    harness.deps.readRenderedKeys = () => readRenderedQamKeys(document);
    const session = startQamComposerRuntime(harness.deps);
    harness.setCompositionReadback(rendered, rendered);
    harness.emitInventory();
    harness.flushReadbacks();
    expect(getQamRuntimeSnapshot().applied).toBe(true);

    hidden = true;
    const pinned = ["5260355", "4", "5260356", "999"];
    harness.setCompositionReadback(pinned, rendered);
    harness.setLayout(layout(["pdc:home", "pdc:section:hud"]));
    harness.flushReadbacks();
    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: false,
      reason: "awaiting_render",
    });

    harness.setCompositionReadback(["5260356", "4", "999"], rendered);
    harness.setLayout(layout(["pdc:section:hud"]));
    harness.flushReadbacks();
    expect(getQamRuntimeSnapshot().activeTokens).toEqual(["pdc:section:hud"]);

    hidden = false;
    rendered = ["5260356", "4", "999"];
    harness.emitInventory();
    harness.flushReadbacks();
    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: true,
      restartRequired: false,
      reason: "ready",
    });

    rendered = ["4", "5260356", "999"];
    harness.emitInventory();
    harness.flushReadbacks();
    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "rendered_mismatch",
    });
    session.dispose();
  });

  it("waits for the first rendered composition before reporting a live apply", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);

    expect(getQamRuntimeSnapshot()).toMatchObject({
      initialized: true,
      applied: false,
      restartRequired: false,
    });

    harness.setCompositionReadback(
      ["4", "5260355", "999"],
      ["4", "5260355", "999"],
    );
    harness.emitInventory();
    harness.flushReadbacks();

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: true,
      restartRequired: false,
      reason: "ready",
    });
    session.dispose();
  });

  it("registers only pinned views and reconciles layout changes live", () => {
    const harness = setup();
    harness.setCompositionReadback(["999"], ["999"]);
    const session = startQamComposerRuntime(harness.deps);
    harness.flushReadbacks();

    expect(harness.deps.registerOwned).toHaveBeenCalledTimes(1);
    expect(harness.deps.registerOwned).toHaveBeenCalledWith(
      expect.any(Number),
      expect.objectContaining({ token: "pdc:home" }),
      expect.any(AbortSignal),
      expect.any(Function),
    );
    expect(getQamRuntimeSnapshot()).toMatchObject({
      initialized: true,
      applied: true,
      restartRequired: false,
      activeTokens: ["pdc:home"],
    });

    harness.setLayout(layout(
      ["pdc:section:hud"],
      ["native:friends", "pdc:section:hud"],
    ));
    harness.flushReadbacks();

    expect(harness.registrations.get("pdc:home")?.dispose).toHaveBeenCalledOnce();
    expect(harness.deps.registerOwned).toHaveBeenCalledTimes(2);
    expect(harness.composition.update).toHaveBeenLastCalledWith(expect.objectContaining({
      layout: expect.objectContaining({ order: ["native:friends", "pdc:section:hud"] }),
      tokensById: expect.any(Map),
    }));
    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: true,
      activeTokens: ["pdc:section:hud"],
    });

    session.dispose();
    expect(harness.registrations.get("pdc:section:hud")?.dispose).toHaveBeenCalledOnce();
    expect(harness.composition.dispose).toHaveBeenCalledOnce();
  });

  it("removes a pinned custom view when it disappears from the catalog", () => {
    const custom: QamViewDescriptor = {
      ...catalog[1],
      token: "pdc:view:v1",
      label: "Juego",
      target: { kind: "section", id: "view:v1" },
    };
    const harness = setup(layout(["pdc:view:v1"]));
    harness.setCatalog([...catalog, custom]);
    const session = startQamComposerRuntime(harness.deps);

    harness.setCatalog(catalog);

    expect(harness.registrations.get("pdc:view:v1")?.dispose).toHaveBeenCalledOnce();
    expect(getQamRuntimeSnapshot().activeTokens).toEqual([]);
    session.dispose();
  });

  it("does not re-register a custom view when an unrelated layout change rebuilds its icon", () => {
    const custom: QamViewDescriptor = {
      ...catalog[1],
      token: "pdc:view:v1",
      label: "Juego",
      presentationKey: "Juego\u0000gamepad",
      target: { kind: "section", id: "view:v1" },
    };
    const harness = setup(layout(["pdc:view:v1"]));
    harness.setCatalog([...catalog, custom]);
    const session = startQamComposerRuntime(harness.deps);

    harness.setCatalog([
      ...catalog,
      { ...custom, icon: () => null },
    ]);

    expect(harness.deps.registerOwned).toHaveBeenCalledOnce();
    expect(harness.registrations.get("pdc:view:v1")?.dispose).not.toHaveBeenCalled();
    session.dispose();
  });

  it("keeps saved intent and requires reload after a failed live apply", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);
    vi.mocked(harness.composition.update).mockReturnValueOnce(false);

    harness.setLayout(layout(["pdc:home"], ["native:help", "pdc:home"]));

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "composition_update_failed",
    });
    expect(harness.composition.update).toHaveBeenCalledWith(expect.objectContaining({
      layout: expect.objectContaining({ order: ["native:help", "pdc:home"] }),
    }));
    session.dispose();
  });

  it("keeps a reload requirement sticky across later inventory renders", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);
    vi.mocked(harness.composition.update).mockReturnValueOnce(false);
    harness.setLayout(layout(["pdc:home"], ["native:help", "pdc:home"]));

    harness.setCompositionReadback(["999"], ["999"]);
    harness.emitInventory();
    harness.flushReadbacks();

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "composition_update_failed",
    });
    session.dispose();
  });

  it("restores the previous registrations when a replacement cannot be registered", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);
    vi.mocked(harness.deps.registerOwned).mockImplementationOnce(
      (_id, descriptor): QuickAccessTabRegistration => ({
        registered: descriptor.token !== "pdc:section:hud",
        restartRequired: false,
        reason: descriptor.token === "pdc:section:hud" ? "add_failed" : "registered",
        dispose: vi.fn(),
      }),
    );

    harness.setLayout(layout(["pdc:section:hud"]));

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "registration_failed",
      activeTokens: ["pdc:home"],
    });
    session.dispose();
  });

  it("disposes partial restorations when a later rollback registration fails", () => {
    const harness = setup(layout(["pdc:home", "pdc:section:hud"]));
    const session = startQamComposerRuntime(harness.deps);
    const restoredHomeDispose = vi.fn();
    let registrationAttempt = 0;
    vi.mocked(harness.deps.registerOwned).mockImplementation(
      (_id, _descriptor): QuickAccessTabRegistration => {
        registrationAttempt += 1;
        const registered = registrationAttempt === 1 || registrationAttempt === 3;
        return {
          registered,
          restartRequired: false,
          reason: registered ? "registered" : "add_failed",
          dispose: registrationAttempt === 3 ? restoredHomeDispose : vi.fn(),
        };
      },
    );

    harness.setCatalog(catalog.map((descriptor) => ({
      ...descriptor,
      presentationKey: "new-language",
    })));

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "cleanup_failed",
    });
    expect(restoredHomeDispose).toHaveBeenCalledOnce();
    session.dispose();
  });

  it("restores the previous registrations when composition reconciliation fails", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);
    vi.mocked(harness.composition.update).mockReturnValueOnce(false);

    harness.setLayout(layout(["pdc:section:hud"]));

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "composition_update_failed",
      activeTokens: ["pdc:home"],
    });
    session.dispose();
  });

  it("requires reload when the visible QAM order does not match the composed entries", () => {
    const harness = setup();
    const session = startQamComposerRuntime(harness.deps);
    harness.setCompositionReadback(
      ["5260355", "4", "5260357", "5", "999"],
      ["5260355", "4", "5", "5260357", "999"],
    );

    harness.setLayout(layout(
      ["pdc:home"],
      ["pdc:home", "native:4", "pdc:section:hud", "native:5"],
    ));
    harness.flushReadbacks();

    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "rendered_mismatch",
    });
    session.dispose();
  });

  it("does not mutate QAM after stale cleanup reports an unsafe state", () => {
    const harness = setup();
    vi.mocked(harness.deps.cleanupOwned).mockReturnValue(true);

    startQamComposerRuntime(harness.deps);

    expect(harness.deps.configure).not.toHaveBeenCalled();
    expect(harness.deps.registerOwned).not.toHaveBeenCalled();
    expect(getQamRuntimeSnapshot()).toMatchObject({
      applied: false,
      restartRequired: true,
      reason: "cleanup_failed",
    });
  });
});
