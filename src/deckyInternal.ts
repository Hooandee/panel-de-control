import type { ReactNode } from "react";

import {
  QAM_DECKY_TOKEN,
  resolveQamTokens,
  type QamEntryToken,
  type QamLayout,
} from "./qam/layout";
import { composeQamEntries, type QamInventoryEntry } from "./qam/composer";
import { applyQamEntryTransaction } from "./qam/transaction";

export const PDC_QAM_TAB_ID = 0x504443;

const PDC_QAM_TAB_OWNER = "panel-de-control";
const DECKY_PLUGIN_TAB_ID = 999;
const QAM_CLEANUP_FAILED = Symbol.for("panel-de-control.qam-cleanup-failed");
const QAM_RENDER_ADAPTER = Symbol.for("panel-de-control.qam-render-adapter");
const QAM_RENDER_ADAPTER_PROTOCOL = 2;
const failedCleanupHooks = new WeakSet<object>();

interface QuickAccessTabView {
  title: ReactNode;
  content: ReactNode;
  icon: ReactNode;
}

interface DeckyQuickAccessTab extends QuickAccessTabView {
  id: number;
  __pdcOwner?: string;
}

interface RenderedQuickAccessTab {
  decky?: boolean;
  key: unknown;
  panel?: unknown;
  initialVisibility?: boolean;
  qAMVisibilitySetter?: (visible: boolean) => void;
}

type DeckyTabsRenderer = (
  this: DeckyTabsHook,
  existingTabs: RenderedQuickAccessTab[],
  visible: boolean,
) => unknown;

interface WeakArrayReference {
  deref(): RenderedQuickAccessTab[] | undefined;
}

interface RenderedArrayState {
  registry: TabRegistryEntry[];
  visible: boolean;
  nativeTabs: RenderedQuickAccessTab[];
  renderedNativeKeys: Set<string>;
}

interface ActiveQamComposition {
  owner: object;
  config: QuickAccessTabCompositionConfig;
  expectedKeys: string[] | null;
}

interface QamRenderAdapterState {
  protocol: number;
  hook: DeckyTabsHook;
  original: DeckyTabsRenderer;
  wrapper: DeckyTabsRenderer;
  initialRegistry: TabRegistryEntry[];
  arrayStates: WeakMap<object, RenderedArrayState>;
  observedArrays: WeakArrayReference[];
  releaseRequested: boolean;
  rendering: boolean;
  failure: string | null;
  deferFailure: boolean;
  failureListeners: Set<() => void>;
  ownedIds: Set<string>;
  composition: ActiveQamComposition | null;
}

interface DeckyTabsHook {
  tabs: DeckyQuickAccessTab[];
  add(tab: DeckyQuickAccessTab): void;
  removeById(id: number): void;
  render: DeckyTabsRenderer;
  [QAM_CLEANUP_FAILED]?: boolean;
  [QAM_RENDER_ADAPTER]?: QamRenderAdapterState;
}

interface TabRegistryEntry {
  tab: DeckyQuickAccessTab;
  id: number;
  title: ReactNode;
  content: ReactNode;
  icon: ReactNode;
  owner: string | undefined;
}

export interface QuickAccessTabRegistration {
  registered: boolean;
  restartRequired: boolean;
  reason: QuickAccessTabReason;
  dispose(): void;
}

export interface QuickAccessTabCompositionConfig {
  layout: QamLayout;
  tokensById: ReadonlyMap<number, QamEntryToken>;
  onInventory?: (entries: QamInventoryEntry[]) => void;
  onRuntimeFailure?: () => void;
}

export interface QuickAccessTabCompositionRegistration {
  configured: boolean;
  update(config: QuickAccessTabCompositionConfig): boolean;
  expectedKeys(): string[] | null;
  dispose(): void;
}

export type QuickAccessTabReason =
  | "registered"
  | "disabled"
  | "hook_unavailable"
  | "cleanup_failed"
  | "unsafe_renderer"
  | "add_failed"
  | "registry_mismatch"
  | "unexpected_error";

let lastQamTabReason: QuickAccessTabReason | "not_attempted" = "not_attempted";

function unavailableQamTab(
  reason: QuickAccessTabReason,
  restartRequired = false,
): QuickAccessTabRegistration {
  lastQamTabReason = reason;
  return { registered: false, restartRequired, reason, dispose() {} };
}

function tabsHookOf(host: unknown): DeckyTabsHook | null {
  const hook = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
    ?.__TABS_HOOK_INSTANCE as Partial<DeckyTabsHook> | undefined;
  if (
    !hook
    || !Array.isArray(hook.tabs)
    || typeof hook.add !== "function"
    || typeof hook.removeById !== "function"
    || typeof hook.render !== "function"
    || !hook.tabs.some((tab) => tab?.id === DECKY_PLUGIN_TAB_ID)
  ) {
    return null;
  }
  return hook as DeckyTabsHook;
}

function tabRegistryOf(host: unknown): DeckyQuickAccessTab[] | null {
  const hook = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
    ?.__TABS_HOOK_INSTANCE as Partial<DeckyTabsHook> | undefined;
  return Array.isArray(hook?.tabs) ? hook.tabs as DeckyQuickAccessTab[] : null;
}

function matchingQamTabs(hook: DeckyTabsHook, id = PDC_QAM_TAB_ID): DeckyQuickAccessTab[] {
  return hook.tabs.filter((tab) => tab.id === id);
}

function ownsQamTab(tab: DeckyQuickAccessTab): boolean {
  return tab.__pdcOwner === PDC_QAM_TAB_OWNER;
}

function ownedQamTabs(hook: DeckyTabsHook): DeckyQuickAccessTab[] {
  return hook.tabs.filter(ownsQamTab);
}

function snapshotTabRegistry(tabs: DeckyQuickAccessTab[]): TabRegistryEntry[] {
  return tabs.map((tab) => ({
    tab,
    id: tab.id,
    title: tab.title,
    content: tab.content,
    icon: tab.icon,
    owner: tab.__pdcOwner,
  }));
}

function matchesTabRegistry(
  actual: DeckyQuickAccessTab[],
  expected: TabRegistryEntry[],
): boolean {
  try {
    return actual.length === expected.length
      && actual.every((tab, index) => (
        tab === expected[index].tab
        && tab.id === expected[index].id
        && tab.title === expected[index].title
        && tab.content === expected[index].content
        && tab.icon === expected[index].icon
        && tab.__pdcOwner === expected[index].owner
      ));
  } catch {
    return false;
  }
}

function matchesHookRegistry(
  hook: DeckyTabsHook,
  expected: TabRegistryEntry[],
): boolean {
  try {
    return matchesTabRegistry(hook.tabs, expected);
  } catch {
    return false;
  }
}

function sameRegistryEntry(
  actual: TabRegistryEntry,
  expected: TabRegistryEntry,
): boolean {
  return actual.tab === expected.tab
    && actual.id === expected.id
    && actual.title === expected.title
    && actual.content === expected.content
    && actual.icon === expected.icon
    && actual.owner === expected.owner;
}

function uniqueRegistryIds(registry: TabRegistryEntry[]): boolean {
  return new Set(registry.map((entry) => String(entry.id))).size === registry.length;
}

function renderedDeckyTabs(tabs: RenderedQuickAccessTab[]): RenderedQuickAccessTab[] {
  return tabs.filter((tab) => tab.decky === true);
}

function renderedKeysMatchRegistry(
  tabs: RenderedQuickAccessTab[],
  registry: TabRegistryEntry[],
): boolean {
  const rendered = renderedDeckyTabs(tabs);
  return rendered.length === registry.length
    && rendered.every((tab, index) => String(tab.key) === String(registry[index].id));
}

function synchronous(result: unknown): boolean {
  return !result || typeof (result as { then?: unknown }).then !== "function";
}

function generateRenderedRegistry(
  renderer: DeckyTabsRenderer,
  hook: DeckyTabsHook,
  registry: TabRegistryEntry[],
  visible: boolean,
): RenderedQuickAccessTab[] | null {
  const registrySnapshot = snapshotTabRegistry(hook.tabs);
  const probeTabs = registry.map((entry) => Object.freeze({ ...entry.tab }));
  const probeHook = Object.create(hook) as DeckyTabsHook;
  Object.defineProperty(probeHook, "tabs", { value: Object.freeze(probeTabs) });
  Object.defineProperty(probeHook, "render", {
    value() { throw new Error("renderer re-entry"); },
  });
  const syntheticTabs: RenderedQuickAccessTab[] = [];
  try {
    if (!synchronous(renderer.call(probeHook, syntheticTabs, visible))) return null;
  } catch {
    return null;
  }
  if (!matchesHookRegistry(hook, registrySnapshot)) return null;
  if (
    syntheticTabs.length !== registry.length
    || syntheticTabs.some((tab, index) => (
      tab.decky !== true
      || String(tab.key) !== String(registry[index].id)
      || tab.panel == null
    ))
  ) {
    return null;
  }
  return syntheticTabs;
}

function preservesStableRenderedTabs(
  renderer: DeckyTabsRenderer,
  hook: DeckyTabsHook,
): boolean {
  const registrySnapshot = snapshotTabRegistry(hook.tabs);
  const probeHook = Object.create(hook) as DeckyTabsHook;
  Object.defineProperty(probeHook, "tabs", {
    value: Object.freeze(hook.tabs.map((tab) => Object.freeze({ ...tab }))),
  });
  Object.defineProperty(probeHook, "render", {
    value() { throw new Error("renderer re-entry"); },
  });
  const nativeTab = Object.freeze({ key: "pdc-native-probe" });
  const stableTabs: RenderedQuickAccessTab[] = [
    nativeTab,
    ...hook.tabs.map((tab) => ({
      decky: true,
      key: tab.id,
      panel: {},
    })),
  ];
  const stableReferences = [...stableTabs];
  try {
    if (!synchronous(renderer.call(probeHook, stableTabs, false))) return false;
  } catch {
    return false;
  }
  return matchesHookRegistry(hook, registrySnapshot)
    && stableTabs.length === stableReferences.length
    && stableTabs.every((tab, index) => tab === stableReferences[index]);
}

function renderAdapterState(hook: DeckyTabsHook): QamRenderAdapterState | null {
  const state = hook[QAM_RENDER_ADAPTER];
  return state?.protocol === QAM_RENDER_ADAPTER_PROTOCOL
    && state.hook === hook
    && hook.render === state.wrapper
    ? state
    : null;
}

function observeRenderedArray(
  state: QamRenderAdapterState,
  tabs: RenderedQuickAccessTab[],
): boolean {
  const WeakReference = (globalThis as unknown as {
    WeakRef?: new (value: RenderedQuickAccessTab[]) => WeakArrayReference;
  }).WeakRef;
  if (!WeakReference) return false;
  state.observedArrays = state.observedArrays.filter((reference) => reference.deref());
  if (!state.observedArrays.some((reference) => reference.deref() === tabs)) {
    state.observedArrays.push(new WeakReference(tabs));
  }
  return true;
}

function restoreRenderAdapter(state: QamRenderAdapterState): boolean {
  const { hook } = state;
  if (hook.render !== state.wrapper) return false;
  try {
    delete (hook as Partial<DeckyTabsHook>).render;
    delete hook[QAM_RENDER_ADAPTER];
    return hook.render === state.original
      && !Object.prototype.hasOwnProperty.call(hook, QAM_RENDER_ADAPTER);
  } catch {
    return false;
  }
}

function observedArraysReleased(state: QamRenderAdapterState): boolean {
  state.observedArrays = state.observedArrays.filter((reference) => reference.deref());
  return state.observedArrays.every((reference) => {
    const tabs = reference.deref();
    return !tabs || !renderedDeckyTabs(tabs).some(
      (tab) => state.ownedIds.has(String(tab.key)),
    );
  });
}

function registryMatchesRenderedKeys(
  registry: TabRegistryEntry[],
  rendered: RenderedQuickAccessTab[],
): boolean {
  return registry.length === rendered.length
    && registry.every((entry, index) => String(entry.id) === String(rendered[index].key));
}

function registryMatchesRenderedKeySet(
  registry: TabRegistryEntry[],
  rendered: RenderedQuickAccessTab[],
): boolean {
  if (registry.length !== rendered.length) return false;
  const renderedKeys = new Set(rendered.map((entry) => String(entry.key)));
  return registry.every((entry) => renderedKeys.has(String(entry.id)));
}

function previousRegistryForArray(
  state: QamRenderAdapterState,
  existingTabs: RenderedQuickAccessTab[],
  current: TabRegistryEntry[],
): TabRegistryEntry[] | null {
  const stored = state.arrayStates.get(existingTabs as object);
  if (stored) return stored.registry;
  const rendered = renderedDeckyTabs(existingTabs);
  if (rendered.length === 0) return [];
  const matchesInitial = registryMatchesRenderedKeys(state.initialRegistry, rendered);
  const matchesCurrent = registryMatchesRenderedKeys(current, rendered);
  if (matchesInitial && matchesCurrent) {
    const unchanged = current.length === state.initialRegistry.length
      && current.every((entry, index) => sameRegistryEntry(entry, state.initialRegistry[index]));
    return unchanged ? current : null;
  }
  if (matchesInitial) return state.initialRegistry;
  if (matchesCurrent) return current;
  return null;
}

function mergeObservedNativeTabs(
  previous: RenderedArrayState | undefined,
  current: RenderedQuickAccessTab[],
): RenderedQuickAccessTab[] {
  if (!previous) return current;
  const currentByKey = new Map(
    current.map((entry) => [String(entry.key), entry]),
  );
  const retained = previous.nativeTabs.flatMap((entry) => {
    const key = String(entry.key);
    const replacement = currentByKey.get(key);
    if (replacement) return [replacement];
    return previous.renderedNativeKeys.has(key) ? [] : [entry];
  });
  const knownKeys = new Set(retained.map((entry) => String(entry.key)));
  const merged = [...retained];
  current.forEach((entry, index) => {
    const key = String(entry.key);
    if (knownKeys.has(key)) return;
    const nextKnown = current.slice(index + 1).find(
      (candidate) => knownKeys.has(String(candidate.key)),
    );
    if (nextKnown) {
      merged.splice(
        merged.findIndex((candidate) => String(candidate.key) === String(nextKnown.key)),
        0,
        entry,
      );
    } else {
      merged.push(entry);
    }
    knownKeys.add(key);
  });
  return merged;
}

function failRenderAdapter(state: QamRenderAdapterState, reason: string): undefined {
  if (state.failure) return undefined;
  state.failure = reason;
  if (state.deferFailure) return undefined;
  markCleanupFailure(state.hook);
  for (const listener of state.failureListeners) {
    try {
      listener();
    } catch {}
  }
  return undefined;
}

function reconcileAdaptedRender(
  state: QamRenderAdapterState,
  existingTabs: RenderedQuickAccessTab[],
  visible: boolean,
): unknown {
  if (state.failure) return undefined;
  const registry = snapshotTabRegistry(state.hook.tabs);
  if (!uniqueRegistryIds(registry)) {
    return failRenderAdapter(state, "registry_invalid");
  }
  const ownedRegistry = registry.filter((entry) => entry.owner === PDC_QAM_TAB_OWNER);
  ownedRegistry.forEach((entry) => state.ownedIds.add(String(entry.id)));
  if (registry.some((entry) => state.ownedIds.has(String(entry.id)) && entry.owner !== PDC_QAM_TAB_OWNER)) {
    return failRenderAdapter(state, "owner_mismatch");
  }
  if (!observeRenderedArray(state, existingTabs)) {
    return failRenderAdapter(state, "weakref_unavailable");
  }

  const before = [...existingTabs];
  const storedArrayState = state.arrayStates.get(existingTabs as object);
  const nativeTabs = mergeObservedNativeTabs(
    storedArrayState,
    before.filter((tab) => tab.decky !== true),
  );
  const deckyTabs = renderedDeckyTabs(before);
  const previousRegistry = previousRegistryForArray(state, existingTabs, registry);
  if (
    !previousRegistry
    || new Set(deckyTabs.map((tab) => String(tab.key))).size !== deckyTabs.length
    || !registryMatchesRenderedKeySet(previousRegistry, deckyTabs)
    || deckyTabs.some((tab) => tab.panel == null)
  ) {
    return failRenderAdapter(state, "rendered_registry_mismatch");
  }

  const requiresGeneration = registry.some((entry) => {
    const previousIndex = previousRegistry.findIndex(
      (candidate) => String(candidate.id) === String(entry.id),
    );
    return previousIndex < 0 || !sameRegistryEntry(entry, previousRegistry[previousIndex]);
  });
  const generated = requiresGeneration
    ? generateRenderedRegistry(state.original, state.hook, registry, visible)
    : null;
  if (requiresGeneration && !generated) {
    return failRenderAdapter(state, "generation_failed");
  }
  const desiredDeckyTabs = registry.map((entry, index) => {
    const previousIndex = previousRegistry.findIndex(
      (candidate) => String(candidate.id) === String(entry.id),
    );
    if (
      previousIndex >= 0
      && sameRegistryEntry(entry, previousRegistry[previousIndex])
    ) {
      return deckyTabs.find((tab) => String(tab.key) === String(entry.id))!;
    }
    return generated![index];
  });
  const canonicalTabs = [...nativeTabs, ...desiredDeckyTabs];
  existingTabs.splice(0, existingTabs.length, ...canonicalTabs);
  let result: unknown;
  try {
    result = state.original.call(state.hook, existingTabs, visible);
  } catch {
    existingTabs.splice(0, existingTabs.length, ...before);
    return failRenderAdapter(state, "stable_render_threw");
  }
  if (
    !synchronous(result)
    || !matchesHookRegistry(state.hook, registry)
    || !renderedKeysMatchRegistry(existingTabs, registry)
    || existingTabs.length !== canonicalTabs.length
    || !existingTabs.every((tab, index) => tab === canonicalTabs[index])
  ) {
    existingTabs.splice(0, existingTabs.length, ...before);
    return failRenderAdapter(state, "stable_render_mismatch");
  }

  const activeComposition = state.composition;
  if (activeComposition) {
    const { config: composition } = activeComposition;
    const ownedEntries = new Map<QamEntryToken, RenderedQuickAccessTab>();
    for (const entry of ownedRegistry) {
      const token = composition.tokensById.get(entry.id);
      const rendered = desiredDeckyTabs.find(
        (candidate) => String(candidate.key) === String(entry.id),
      );
      if (!token || !rendered || ownedEntries.has(token)) {
        existingTabs.splice(0, existingTabs.length, ...before);
        return failRenderAdapter(state, "composition_mapping_invalid");
      }
      ownedEntries.set(token, rendered);
    }
    const defaults = [
      ...nativeTabs.map((entry) => `native:${String(entry.key)}`),
      ...ownedEntries.keys(),
      QAM_DECKY_TOKEN,
    ];
    const desiredTokens = resolveQamTokens(
      defaults,
      composition.layout,
      QAM_DECKY_TOKEN,
    );
    const composed = composeQamEntries(canonicalTabs, desiredTokens, ownedEntries);
    if (!composed.ok) {
      existingTabs.splice(0, existingTabs.length, ...before);
      return failRenderAdapter(state, `composition_${composed.reason}`);
    }
    const transaction = applyQamEntryTransaction(
      existingTabs,
      composed.entries,
      () => matchesHookRegistry(state.hook, registry),
    );
    if (!transaction.applied) {
      existingTabs.splice(0, existingTabs.length, ...before);
      return failRenderAdapter(state, `composition_${transaction.reason}`);
    }
    if (visible || activeComposition.expectedKeys === null) {
      activeComposition.expectedKeys = composed.entries.map((entry) => String(entry.key));
      try {
        composition.onInventory?.(composed.inventory);
      } catch {}
    }
  }

  state.arrayStates.set(existingTabs as object, {
    registry,
    visible,
    nativeTabs,
    renderedNativeKeys: new Set(
      existingTabs
        .filter((entry) => entry.decky !== true)
        .map((entry) => String(entry.key)),
    ),
  });
  if (
    state.releaseRequested
    && !state.composition
    && ownedRegistry.length === 0
    && observedArraysReleased(state)
  ) {
    if (!restoreRenderAdapter(state)) {
      failRenderAdapter(state, "restore_failed");
    }
  }
  return result;
}

function installRenderAdapter(hook: DeckyTabsHook): QamRenderAdapterState | null {
  const existing = renderAdapterState(hook);
  if (existing) {
    existing.releaseRequested = false;
    return existing;
  }
  if (Object.prototype.hasOwnProperty.call(hook, QAM_RENDER_ADAPTER)) return null;
  if (Object.prototype.hasOwnProperty.call(hook, "render")) return null;
  const original = hook.render;
  if (typeof (globalThis as { WeakRef?: unknown }).WeakRef !== "function") return null;
  if (!preservesStableRenderedTabs(original, hook)) return null;
  const state = {} as QamRenderAdapterState;
  const wrapper: DeckyTabsRenderer = function (existingTabs, visible) {
    if (state.rendering || this !== state.hook) {
      return failRenderAdapter(state, "renderer_reentry");
    }
    state.rendering = true;
    try {
      return reconcileAdaptedRender(state, existingTabs, visible);
    } finally {
      state.rendering = false;
    }
  };
  Object.assign(state, {
    protocol: QAM_RENDER_ADAPTER_PROTOCOL,
    hook,
    original,
    wrapper,
    initialRegistry: snapshotTabRegistry(hook.tabs),
    arrayStates: new WeakMap<object, RenderedArrayState>(),
    observedArrays: [],
    releaseRequested: false,
    rendering: false,
    failure: null,
    deferFailure: false,
    failureListeners: new Set<() => void>(),
    ownedIds: new Set(
      snapshotTabRegistry(hook.tabs)
        .filter((entry) => entry.owner === PDC_QAM_TAB_OWNER)
        .map((entry) => String(entry.id)),
    ),
    composition: null,
  });
  try {
    Object.defineProperty(hook, QAM_RENDER_ADAPTER, {
      configurable: true,
      value: state,
    });
    Object.defineProperty(hook, "render", {
      configurable: true,
      writable: true,
      value: wrapper,
    });
    return renderAdapterState(hook);
  } catch {
    try {
      delete hook[QAM_RENDER_ADAPTER];
      delete (hook as Partial<DeckyTabsHook>).render;
    } catch {}
    return null;
  }
}

function releaseRenderAdapter(hook: DeckyTabsHook): boolean {
  const state = renderAdapterState(hook);
  if (!state) {
    return !Object.prototype.hasOwnProperty.call(hook, QAM_RENDER_ADAPTER);
  }
  if (state.composition) return !state.failure;
  state.releaseRequested = true;
  for (const reference of state.observedArrays) {
    const tabs = reference.deref();
    if (
      tabs
      && renderedDeckyTabs(tabs).some((tab) => state.ownedIds.has(String(tab.key)))
    ) {
      const visible = state.arrayStates.get(tabs as object)?.visible ?? false;
      reconcileAdaptedRender(state, tabs, visible);
      if (state.failure) return false;
    }
  }
  if (!observedArraysReleased(state)) return false;
  if (hook.render === state.original) return true;
  return restoreRenderAdapter(state);
}

function reconcileObservedArrays(
  state: QamRenderAdapterState,
  recoverFailure = false,
): boolean {
  if (state.failure || state.rendering) return false;
  state.observedArrays = state.observedArrays.filter((reference) => reference.deref());
  const snapshots = state.observedArrays.flatMap((reference) => {
    const tabs = reference.deref();
    if (!tabs) return [];
    return [{
      tabs,
      entries: [...tabs],
      arrayState: state.arrayStates.get(tabs as object),
    }];
  });
  state.rendering = true;
  state.deferFailure = recoverFailure;
  try {
    for (const { tabs } of snapshots) {
      const visible = state.arrayStates.get(tabs as object)?.visible ?? false;
      reconcileAdaptedRender(state, tabs, visible);
      if (state.failure) {
        snapshots.forEach(({ tabs: observed, entries, arrayState }) => {
          observed.splice(0, observed.length, ...entries);
          if (arrayState) state.arrayStates.set(observed as object, arrayState);
          else state.arrayStates.delete(observed as object);
        });
        if (recoverFailure) state.failure = null;
        return false;
      }
    }
    return true;
  } finally {
    state.deferFailure = false;
    state.rendering = false;
  }
}

function unavailableQamComposition(): QuickAccessTabCompositionRegistration {
  return {
    configured: false,
    update() { return false; },
    expectedKeys() { return null; },
    dispose() {},
  };
}

export function configureQuickAccessTabComposition(
  config: QuickAccessTabCompositionConfig,
  host: unknown = window,
): QuickAccessTabCompositionRegistration {
  const hook = tabsHookOf(host);
  if (!hook) return unavailableQamComposition();
  const state = installRenderAdapter(hook);
  if (!state || state.failure || state.composition) {
    return unavailableQamComposition();
  }

  const owner = {};
  state.composition = { owner, config, expectedKeys: null };
  state.releaseRequested = false;
  if (config.onRuntimeFailure) state.failureListeners.add(config.onRuntimeFailure);
  if (!reconcileObservedArrays(state)) {
    state.composition = null;
    if (config.onRuntimeFailure) state.failureListeners.delete(config.onRuntimeFailure);
    return unavailableQamComposition();
  }

  let disposed = false;
  return {
    configured: true,
    update(nextConfig) {
      if (disposed || state.failure || state.composition?.owner !== owner) return false;
      const previousConfig = state.composition.config;
      const previousExpectedKeys = state.composition.expectedKeys;
      if (previousConfig.onRuntimeFailure) {
        state.failureListeners.delete(previousConfig.onRuntimeFailure);
      }
      state.composition.config = nextConfig;
      state.composition.expectedKeys = null;
      if (nextConfig.onRuntimeFailure) {
        state.failureListeners.add(nextConfig.onRuntimeFailure);
      }
      if (reconcileObservedArrays(state, true)) return true;
      state.composition.config = previousConfig;
      state.composition.expectedKeys = previousExpectedKeys;
      if (nextConfig.onRuntimeFailure) {
        state.failureListeners.delete(nextConfig.onRuntimeFailure);
      }
      if (previousConfig.onRuntimeFailure) {
        state.failureListeners.add(previousConfig.onRuntimeFailure);
      }
      return false;
    },
    expectedKeys() {
      if (disposed || state.composition?.owner !== owner) return null;
      const keys = state.composition.expectedKeys;
      return keys ? [...keys] : null;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      if (state.composition?.owner !== owner) return;
      const activeConfig = state.composition.config;
      state.composition = null;
      if (activeConfig.onRuntimeFailure) {
        state.failureListeners.delete(activeConfig.onRuntimeFailure);
      }
      if (!reconcileObservedArrays(state)) {
        markCleanupFailure(hook);
        activeConfig.onRuntimeFailure?.();
        return;
      }
      if (ownedQamTabs(hook).length === 0 && !releaseRenderAdapter(hook)) {
        markCleanupFailure(hook);
        activeConfig.onRuntimeFailure?.();
      }
    },
  };
}

function canReconcileTabs(
  hook: DeckyTabsHook,
  desiredTabs: DeckyQuickAccessTab[],
): boolean {
  const adapter = renderAdapterState(hook);
  if (adapter) {
    const desired = snapshotTabRegistry(desiredTabs);
    return !adapter.failure && uniqueRegistryIds(desired);
  }
  if (reconcilesTabsExactly(hook, desiredTabs)) return true;
  const current = snapshotTabRegistry(hook.tabs);
  const desired = snapshotTabRegistry(desiredTabs);
  const currentBase = current.filter((entry) => entry.owner !== PDC_QAM_TAB_OWNER);
  const desiredBase = desired.filter((entry) => entry.owner !== PDC_QAM_TAB_OWNER);
  if (
    !uniqueRegistryIds(current)
    || !uniqueRegistryIds(desired)
    || currentBase.length !== desiredBase.length
    || !currentBase.every((entry, index) => sameRegistryEntry(entry, desiredBase[index]))
  ) {
    return false;
  }
  const installed = installRenderAdapter(hook);
  if (!installed) return false;
  if (generateRenderedRegistry(installed.original, hook, desired, false)) {
    return true;
  }
  releaseRenderAdapter(hook);
  return false;
}

export function quickAccessTabDiagnostics(
  host: unknown = window,
  qamDocument: Document | null = null,
) {
  let hook: { tabs?: unknown } | null = null;
  try {
    const candidate = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
      ?.__TABS_HOOK_INSTANCE;
    if (candidate && typeof candidate === "object") hook = candidate;
  } catch {}

  const tabs = Array.isArray(hook?.tabs) ? hook.tabs : null;
  const registryIds = tabs?.map((tab) => (
    tab && typeof tab === "object" ? (tab as { id?: unknown }).id : undefined
  )) ?? null;
  let adapter: QamRenderAdapterState | null = null;
  try {
    adapter = hook ? renderAdapterState(hook as DeckyTabsHook) : null;
  } catch {}

  let renderedIds: string[] | null = null;
  let roots: Element[] | null = null;
  try {
    if (qamDocument) {
      renderedIds = Array.from(
        qamDocument.querySelectorAll<HTMLElement>("[id^='quickaccess_tab_']"),
        (node) => node.id,
      );
      roots = Array.from(qamDocument.querySelectorAll(".pdc-root"));
    }
  } catch {}

  return {
    hook_available: hook !== null,
    registry_count: registryIds?.length ?? null,
    registry_unique_count: registryIds ? new Set(registryIds).size : null,
    registry_decky_count: registryIds?.filter((id) => id === DECKY_PLUGIN_TAB_ID).length ?? null,
    registry_pdc_count: registryIds?.filter((id) => id === PDC_QAM_TAB_ID).length ?? null,
    qam_document_available: qamDocument !== null,
    qam_document_hidden: qamDocument?.hidden ?? null,
    rendered_count: renderedIds?.length ?? null,
    rendered_unique_count: renderedIds ? new Set(renderedIds).size : null,
    rendered_decky_count:
      renderedIds?.filter((id) => id === `quickaccess_tab_${DECKY_PLUGIN_TAB_ID}`).length ?? null,
    rendered_pdc_count:
      renderedIds?.filter((id) => id === `quickaccess_tab_${PDC_QAM_TAB_ID}`).length ?? null,
    panel_root_count: roots?.length ?? null,
    visible_panel_root_count: roots?.filter((node) => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }).length ?? null,
    render_adapter_active: adapter !== null,
    render_adapter_failure: adapter?.failure ?? null,
    render_adapter_observed_arrays: adapter?.observedArrays.filter(
      (reference) => reference.deref(),
    ).length ?? 0,
    registration_reason: lastQamTabReason,
  };
}

function reconcilesTabsExactly(
  hook: DeckyTabsHook,
  desiredTabs: DeckyQuickAccessTab[],
): boolean {
  const nativeTab = Object.freeze({ key: "pdc-native-probe" });
  const renderedTabs: RenderedQuickAccessTab[] = [
    nativeTab,
    ...hook.tabs.map((tab) => ({ decky: true, key: tab.id })),
  ];
  const probeTabs = desiredTabs.map((tab) => Object.freeze({ ...tab }));
  if (new Set(probeTabs.map((tab) => tab.id)).size !== probeTabs.length) return false;

  const probeHook = Object.create(hook) as DeckyTabsHook;
  Object.defineProperty(probeHook, "tabs", { value: Object.freeze(probeTabs) });
  Object.defineProperty(probeHook, "render", {
    value() { throw new Error("renderer re-entry"); },
  });
  hook.render.call(probeHook, renderedTabs, false);

  return renderedTabs.length === probeTabs.length + 1
    && renderedTabs[0] === nativeTab
    && renderedTabs.slice(1).every((tab, index) => (
      tab.decky === true && tab.key === probeTabs[index].id
    ));
}

function removeOwnedQamTab(hook: DeckyTabsHook, id: number): boolean {
  const matching = matchingQamTabs(hook, id);
  if (matching.some((tab) => !ownsQamTab(tab))) return false;
  if (matching.length > 0) {
    const registrySnapshot = snapshotTabRegistry(hook.tabs);
    const remaining = hook.tabs.filter((tab) => tab.id !== id);
    const remainingSnapshot = snapshotTabRegistry(remaining);
    if (!canReconcileTabs(hook, remaining)) return false;
    if (!matchesHookRegistry(hook, registrySnapshot)) return false;
    hook.removeById(id);
    if (!matchesHookRegistry(hook, remainingSnapshot)) return false;
  }
  return ownedQamTabs(hook).length > 0 || releaseRenderAdapter(hook);
}

function removeAllOwnedQamTabs(hook: DeckyTabsHook): boolean {
  const ids = ownedQamTabs(hook).map((tab) => tab.id);
  for (const id of ids) {
    if (!removeOwnedQamTab(hook, id)) return false;
  }
  return releaseRenderAdapter(hook);
}

function cleanupFailedRegistration(
  hook: DeckyTabsHook,
  previousTabs: TabRegistryEntry[],
  id: number,
): boolean {
  try {
    const cleaned = removeOwnedQamTab(hook, id);
    return !cleaned || !matchesHookRegistry(hook, previousTabs);
  } catch {
    return true;
  }
}

function markCleanupFailure(hook: object): void {
  failedCleanupHooks.add(hook);
  try {
    Object.defineProperty(hook, QAM_CLEANUP_FAILED, {
      configurable: true,
      value: true,
    });
  } catch {}
  lastQamTabReason = "cleanup_failed";
}

function hasCleanupFailure(host: unknown): boolean {
  const hook = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
    ?.__TABS_HOOK_INSTANCE;
  return !!hook
    && typeof hook === "object"
    && (
      failedCleanupHooks.has(hook)
      || (hook as { [QAM_CLEANUP_FAILED]?: boolean })[QAM_CLEANUP_FAILED] === true
    );
}

function unavailableAfterMutation(
  reason: QuickAccessTabReason,
  hook: DeckyTabsHook,
  restartRequired: boolean,
): QuickAccessTabRegistration {
  if (restartRequired) markCleanupFailure(hook);
  return unavailableQamTab(reason, restartRequired);
}

export function cleanupOwnedQuickAccessTabs(host: unknown = window): boolean {
  lastQamTabReason = "disabled";
  let hook: DeckyTabsHook | null = null;
  try {
    if (hasCleanupFailure(host)) {
      lastQamTabReason = "cleanup_failed";
      return true;
    }
    const registry = tabRegistryOf(host);
    if (registry && !registry.some((tab) => tab.id === DECKY_PLUGIN_TAB_ID)) {
      const candidate = (host as { __TABS_HOOK_INSTANCE?: unknown } | null)
        ?.__TABS_HOOK_INSTANCE;
      if (candidate && typeof candidate === "object") markCleanupFailure(candidate);
      else lastQamTabReason = "cleanup_failed";
      return true;
    }
    hook = tabsHookOf(host);
    if (!hook) return false;
    if (!ownedQamTabs(hook).length) {
      const restartRequired = !releaseRenderAdapter(hook);
      if (restartRequired) markCleanupFailure(hook);
      return restartRequired;
    }
    const restartRequired = !removeAllOwnedQamTabs(hook);
    if (restartRequired) markCleanupFailure(hook);
    return restartRequired;
  } catch {
    if (hook) markCleanupFailure(hook);
    else lastQamTabReason = "cleanup_failed";
    return true;
  }
}

export function occupiedQuickAccessTabIds(host: unknown = window): ReadonlySet<number> {
  const registry = tabRegistryOf(host);
  if (!registry) return new Set<number>();
  return new Set(
    registry
      .filter((tab) => !ownsQamTab(tab))
      .map((tab) => tab.id),
  );
}

export function registerOwnedQuickAccessTab(
  id: number,
  view: QuickAccessTabView,
  host: unknown = window,
  onRuntimeFailure?: () => void,
): QuickAccessTabRegistration {
  let registryMutationAttempted = false;
  let hook: DeckyTabsHook | null = null;
  try {
    hook = tabsHookOf(host);
    if (!hook) return unavailableQamTab("hook_unavailable");
    registryMutationAttempted = matchingQamTabs(hook, id).some(ownsQamTab);
    if (!removeOwnedQamTab(hook, id)) {
      return unavailableAfterMutation(
        "cleanup_failed",
        hook,
        registryMutationAttempted,
      );
    }
    const previousTabs = [...hook.tabs];
    const previousSnapshot = snapshotTabRegistry(previousTabs);

    const tab: DeckyQuickAccessTab = {
      ...view,
      id,
      __pdcOwner: PDC_QAM_TAB_OWNER,
    };
    const expectedTabs = [...previousTabs, tab];
    const expectedSnapshot = [
      ...previousSnapshot,
      ...snapshotTabRegistry([tab]),
    ];
    let rendererSafe = false;
    try {
      rendererSafe = canReconcileTabs(hook, expectedTabs);
    } catch {
      return unavailableAfterMutation(
        "unsafe_renderer",
        hook,
        !matchesHookRegistry(hook, previousSnapshot),
      );
    }
    const probeMutatedRegistry = !matchesHookRegistry(hook, previousSnapshot);
    if (!rendererSafe || probeMutatedRegistry) {
      return unavailableAfterMutation("unsafe_renderer", hook, probeMutatedRegistry);
    }
    registryMutationAttempted = true;
    const activeAdapter = renderAdapterState(hook);
    try {
      hook.add(tab);
    } catch {
      return unavailableAfterMutation(
        "add_failed",
        hook,
        cleanupFailedRegistration(hook, previousSnapshot, id),
      );
    }
    if (activeAdapter?.failure) {
      return unavailableAfterMutation(
        "add_failed",
        hook,
        cleanupFailedRegistration(hook, previousSnapshot, id),
      );
    }
    if (!matchesHookRegistry(hook, expectedSnapshot)) {
      return unavailableAfterMutation(
        "registry_mismatch",
        hook,
        cleanupFailedRegistration(hook, previousSnapshot, id),
      );
    }
    lastQamTabReason = "registered";

    const registeredHook = hook;
    const registeredAdapter = renderAdapterState(hook);
    if (onRuntimeFailure) registeredAdapter?.failureListeners.add(onRuntimeFailure);
    let disposed = false;
    return {
      registered: true,
      restartRequired: false,
      reason: "registered",
      dispose() {
        if (disposed) return;
        disposed = true;
        try {
          if (!registeredHook.tabs.includes(tab)) {
            if (
              !matchingQamTabs(registeredHook, id).some(ownsQamTab)
              && !releaseRenderAdapter(registeredHook)
            ) {
              markCleanupFailure(registeredHook);
              onRuntimeFailure?.();
            }
            return;
          }
          if (
            tab.id !== id
            || !ownsQamTab(tab)
            || !removeOwnedQamTab(registeredHook, id)
          ) {
            markCleanupFailure(registeredHook);
          }
        } catch {
          markCleanupFailure(registeredHook);
        } finally {
          if (onRuntimeFailure) {
            registeredAdapter?.failureListeners.delete(onRuntimeFailure);
          }
        }
      },
    };
  } catch {
    if (hook && registryMutationAttempted) markCleanupFailure(hook);
    return unavailableQamTab("unexpected_error", registryMutationAttempted);
  }
}

export function registerQuickAccessTab(
  view: QuickAccessTabView,
  host: unknown = window,
  onRuntimeFailure?: () => void,
): QuickAccessTabRegistration {
  return registerOwnedQuickAccessTab(PDC_QAM_TAB_ID, view, host, onRuntimeFailure);
}

type PluginListEntry = string | { name?: string; version?: string };

interface DeckyState {
  publicState?(): Partial<Record<"installedPlugins" | "disabledPlugins", PluginListEntry[]>>;
  setActivePlugin?(name: string): void;
}

interface DeckyHost {
  DeckyPluginLoader?: { deckyState?: DeckyState };
  DeckyBackend?: { call?(method: string, ...args: unknown[]): Promise<unknown> };
}

function pluginNames(kind: "installedPlugins" | "disabledPlugins"): string[] {
  try {
    const state = (window as unknown as DeckyHost).DeckyPluginLoader?.deckyState?.publicState?.();
    return (state?.[kind] ?? [])
      .map((plugin) => typeof plugin === "string" ? plugin : plugin.name)
      .filter((name): name is string => typeof name === "string");
  } catch {
    return [];
  }
}

export interface DeckyPluginInfo {
  name: string;
  version?: string;
  disabled: boolean;
}

function normalizePluginEntry(
  plugin: PluginListEntry,
  collection: "installedPlugins" | "disabledPlugins",
  index: number,
): Omit<DeckyPluginInfo, "disabled"> {
  const name = typeof plugin === "string" ? plugin : plugin?.name;
  const version = typeof plugin === "string" ? undefined : plugin?.version;
  if (!name?.trim() || (version !== undefined && typeof version !== "string")) {
    throw new Error(`Decky ${collection} entry ${index} is invalid`);
  }
  return { name, ...(version ? { version } : {}) };
}

function readPluginInventory(host: unknown): DeckyPluginInfo[] {
  const state = (host as DeckyHost | null)?.DeckyPluginLoader?.deckyState?.publicState?.();
  const installed = state?.installedPlugins;
  const disabled = state?.disabledPlugins;
  if (!Array.isArray(installed) || !Array.isArray(disabled)) {
    throw new Error("Decky plugin inventory unavailable");
  }
  const byName = new Map<string, DeckyPluginInfo>();
  for (const [index, plugin] of installed.entries()) {
    const { name, version } = normalizePluginEntry(plugin, "installedPlugins", index);
    byName.set(name, { name, ...(version ? { version } : {}), disabled: false });
  }
  for (const [index, plugin] of disabled.entries()) {
    const { name, version } = normalizePluginEntry(plugin, "disabledPlugins", index);
    const existing = byName.get(name);
    byName.set(name, {
      name,
      ...(version ? { version } : existing?.version ? { version: existing.version } : {}),
      disabled: true,
    });
  }
  return [...byName.values()];
}

export function strictPluginInventory(host: unknown = window): DeckyPluginInfo[] {
  return readPluginInventory(host);
}

export function pluginInventory(host: unknown = window): DeckyPluginInfo[] {
  try {
    return readPluginInventory(host);
  } catch {
    return [];
  }
}

export function installedPlugins(): string[] {
  return pluginNames("installedPlugins");
}

export function disabledPlugins(): string[] {
  return pluginNames("disabledPlugins");
}

export async function callBackend(method: string, ...args: unknown[]): Promise<unknown> {
  const backend = (window as unknown as DeckyHost).DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  return backend.call(method, ...args);
}

export async function callLegacyPluginBackend(
  pluginName: string,
  method: string,
  kwargs: Readonly<Record<string, unknown>>,
  host: unknown = window,
): Promise<unknown> {
  const backend = (host as DeckyHost | null)?.DeckyBackend;
  if (typeof backend?.call !== "function") throw new Error("DeckyBackend unavailable");
  const response = await backend.call(
    "loader/call_legacy_plugin_method",
    pluginName,
    method,
    kwargs,
  );
  if (
    typeof response !== "object"
    || response === null
    || typeof (response as { success?: unknown }).success !== "boolean"
    || !Object.prototype.hasOwnProperty.call(response, "result")
  ) {
    throw new Error("Decky returned an invalid legacy response");
  }
  const result = (response as { success: boolean; result: unknown }).result;
  if (!(response as { success: boolean }).success) {
    throw new Error(typeof result === "string" ? result : `Decky rejected ${pluginName}.${method}`);
  }
  return result;
}

// Make a plugin the active QAM plugin. No-op (user lands on the Decky plugin list)
// if the setter is gone.
export function setActivePlugin(name: string): void {
  try {
    (window as unknown as DeckyHost).DeckyPluginLoader?.deckyState?.setActivePlugin?.(name);
  } catch {}
}
