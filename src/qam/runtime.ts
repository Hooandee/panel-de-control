import type {
  QuickAccessTabCompositionConfig,
  QuickAccessTabCompositionRegistration,
  QuickAccessTabRegistration,
} from "../deckyInternal";
import type { QamInventoryEntry } from "./composer";
import type { QamEntryToken, QamLayout } from "./layout";
import { assignOwnedIds } from "./ownedIds";
import type { QamViewDescriptor } from "./viewCatalog";

export type QamRuntimeReason =
  | "ready"
  | "cleanup_failed"
  | "id_allocation_failed"
  | "composition_unavailable"
  | "registration_failed"
  | "composition_update_failed"
  | "awaiting_render"
  | "rendered_mismatch"
  | "runtime_failure";

export interface QamRuntimeSnapshot {
  initialized: boolean;
  applied: boolean;
  restartRequired: boolean;
  reason: QamRuntimeReason;
  activeTokens: QamEntryToken[];
  inventory: QamInventoryEntry[];
}

export interface QamComposerRuntimeDependencies {
  getLayout(): QamLayout;
  saveLayout(layout: QamLayout): void;
  subscribeLayout(listener: () => void): () => void;
  getCatalog(): QamViewDescriptor[];
  subscribeCatalog(listener: () => void): () => void;
  occupiedIds(): ReadonlySet<number>;
  cleanupOwned(): boolean;
  registerOwned(
    id: number,
    descriptor: QamViewDescriptor,
    lifecycle: AbortSignal,
    onRuntimeFailure: () => void,
  ): QuickAccessTabRegistration;
  configure(config: QuickAccessTabCompositionConfig): QuickAccessTabCompositionRegistration;
  readRenderedKeys(): string[] | null;
  scheduleReadback(readback: () => void): () => void;
}

export interface QamComposerSession {
  refresh(): void;
  dispose(): void;
}

interface ActiveRegistration {
  descriptor: QamViewDescriptor;
  id: number;
  lifecycle: AbortController;
  registration: QuickAccessTabRegistration;
}

const listeners = new Set<() => void>();
let snapshot: QamRuntimeSnapshot = {
  initialized: false,
  applied: false,
  restartRequired: false,
  reason: "ready",
  activeTokens: [],
  inventory: [],
};

export function getQamRuntimeSnapshot(): QamRuntimeSnapshot {
  return snapshot;
}

export function subscribeQamRuntime(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function publish(next: QamRuntimeSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function sameTarget(a: QamViewDescriptor, b: QamViewDescriptor): boolean {
  return a.target.kind === b.target.kind
    && (a.target.kind === "home" || (
      b.target.kind === "section" && a.target.id === b.target.id
    ));
}

function sameRegistrationView(a: QamViewDescriptor, b: QamViewDescriptor): boolean {
  return a.labelKey === b.labelKey
    && a.label === b.label
    && a.presentationKey === b.presentationKey
    && sameTarget(a, b);
}

function sameKeys(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((key, index) => key === b[index]);
}

export function startQamComposerRuntime(
  deps: QamComposerRuntimeDependencies,
): QamComposerSession {
  let disposed = false;
  let reconciling = false;
  let composition: QuickAccessTabCompositionRegistration | null = null;
  let cancelReadback: (() => void) | null = null;
  let verifiedKeys: string[] | null = null;
  let inventory: QamInventoryEntry[] = [];
  const active = new Map<QamEntryToken, ActiveRegistration>();
  const unsubscribers: Array<() => void> = [];

  const fail = (reason: QamRuntimeReason) => {
    cancelReadback?.();
    cancelReadback = null;
    publish({
      initialized: true,
      applied: false,
      restartRequired: true,
      reason,
      activeTokens: [...active.keys()],
      inventory,
    });
  };
  const onRuntimeFailure = () => {
    if (!disposed) fail("runtime_failure");
  };
  const publishPendingReadback = () => {
    publish({
      initialized: true,
      applied: false,
      restartRequired: false,
      reason: "awaiting_render",
      activeTokens: [...active.keys()],
      inventory,
    });
  };
  const scheduleCompositionReadback = () => {
    cancelReadback?.();
    cancelReadback = null;
    const expectedKeys = composition?.expectedKeys() ?? null;
    const previouslyVerified = expectedKeys !== null
      && verifiedKeys !== null
      && sameKeys(expectedKeys, verifiedKeys);
    if (!previouslyVerified) publishPendingReadback();
    if (!expectedKeys) return;
    cancelReadback = deps.scheduleReadback(() => {
      cancelReadback = null;
      if (disposed || snapshot.restartRequired) return;
      const renderedKeys = deps.readRenderedKeys();
      if (!renderedKeys) {
        if (!previouslyVerified) publishPendingReadback();
      } else if (!sameKeys(renderedKeys, expectedKeys)) {
        fail("rendered_mismatch");
      } else {
        verifiedKeys = [...expectedKeys];
        publish({
          initialized: true,
          applied: true,
          restartRequired: false,
          reason: "ready",
          activeTokens: [...active.keys()],
          inventory,
        });
      }
    });
  };
  const onInventory = (next: QamInventoryEntry[]) => {
    inventory = [...next];
    if (snapshot.initialized && !disposed) {
      const restartRequired = snapshot.restartRequired;
      publish({ ...snapshot, inventory });
      if (!restartRequired) scheduleCompositionReadback();
    }
  };

  const register = (
    descriptor: QamViewDescriptor,
    id: number,
  ): ActiveRegistration | null => {
    const lifecycle = new AbortController();
    const registration = deps.registerOwned(
      id,
      descriptor,
      lifecycle.signal,
      onRuntimeFailure,
    );
    if (!registration.registered) {
      lifecycle.abort();
      registration.dispose();
      return null;
    }
    return { descriptor, id, lifecycle, registration };
  };

  const restoreActive = (
    previous: ReadonlyMap<QamEntryToken, ActiveRegistration>,
  ): boolean => {
    for (const [token, current] of active) {
      if (previous.get(token) === current) continue;
      current.lifecycle.abort();
      current.registration.dispose();
      active.delete(token);
    }
    const restored = new Map<QamEntryToken, ActiveRegistration>();
    const recreated: ActiveRegistration[] = [];
    for (const [token, previousRegistration] of previous) {
      const unchanged = active.get(token);
      if (unchanged === previousRegistration) {
        restored.set(token, unchanged);
        continue;
      }
      const replacement = register(
        previousRegistration.descriptor,
        previousRegistration.id,
      );
      if (!replacement) {
        recreated.forEach((registration) => {
          registration.lifecycle.abort();
          registration.registration.dispose();
        });
        return false;
      }
      recreated.push(replacement);
      restored.set(token, replacement);
    }
    active.clear();
    restored.forEach((registration, token) => active.set(token, registration));
    return true;
  };

  let lastCompositionConfig: QuickAccessTabCompositionConfig | null = null;

  const reconcile = () => {
    if (disposed || reconciling || snapshot.restartRequired) return;
    reconciling = true;
    try {
      let layout = deps.getLayout();
      const catalog = deps.getCatalog();
      const descriptors = new Map(catalog.map((entry) => [entry.token, entry]));
      const desired = layout.pinnedViews
        .map((token) => descriptors.get(token))
        .filter((entry): entry is QamViewDescriptor => !!entry);
      let ownedIds: Record<QamEntryToken, number>;
      try {
        ownedIds = assignOwnedIds(
          desired.map((entry) => entry.token),
          layout.ownedIds,
          deps.occupiedIds(),
        );
      } catch {
        fail("id_allocation_failed");
        return;
      }
      if (JSON.stringify(ownedIds) !== JSON.stringify(layout.ownedIds)) {
        layout = { ...layout, ownedIds };
        deps.saveLayout(layout);
      }

      const tokensById = new Map<number, QamEntryToken>();
      desired.forEach((entry) => tokensById.set(ownedIds[entry.token], entry.token));
      const compositionConfig: QuickAccessTabCompositionConfig = {
        layout,
        tokensById,
        onInventory,
        onRuntimeFailure,
      };
      if (!composition) {
        composition = deps.configure(compositionConfig);
        if (!composition.configured) {
          fail("composition_unavailable");
          return;
        }
      }

      const previousActive = new Map(active);
      const desiredTokens = new Set(desired.map((entry) => entry.token));
      for (const [token, current] of active) {
        const next = descriptors.get(token);
        if (
          desiredTokens.has(token)
          && next
          && ownedIds[token] === current.id
          && sameRegistrationView(current.descriptor, next)
        ) continue;
        current.lifecycle.abort();
        current.registration.dispose();
        active.delete(token);
      }

      for (const descriptor of desired) {
        if (active.has(descriptor.token)) continue;
        const registration = register(descriptor, ownedIds[descriptor.token]);
        if (!registration) {
          fail(restoreActive(previousActive) ? "registration_failed" : "cleanup_failed");
          return;
        }
        active.set(descriptor.token, registration);
      }

      if (!composition.update(compositionConfig)) {
        const registrationsRestored = restoreActive(previousActive);
        const compositionRestored = !lastCompositionConfig
          || composition.update(lastCompositionConfig);
        fail(
          registrationsRestored && compositionRestored
            ? "composition_update_failed"
            : "cleanup_failed",
        );
        return;
      }
      lastCompositionConfig = compositionConfig;
      scheduleCompositionReadback();
    } finally {
      reconciling = false;
    }
  };

  if (deps.cleanupOwned()) {
    fail("cleanup_failed");
  } else {
    publish({
      initialized: false,
      applied: false,
      restartRequired: false,
      reason: "ready",
      activeTokens: [],
      inventory: [],
    });
    reconcile();
    unsubscribers.push(deps.subscribeLayout(reconcile), deps.subscribeCatalog(reconcile));
  }

  return {
    refresh: reconcile,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancelReadback?.();
      cancelReadback = null;
      unsubscribers.forEach((unsubscribe) => unsubscribe());
      for (const current of active.values()) {
        current.lifecycle.abort();
        current.registration.dispose();
      }
      active.clear();
      composition?.dispose();
    },
  };
}
