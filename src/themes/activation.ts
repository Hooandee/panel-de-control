import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedThemeRelease } from "./remotePublication";

export interface ThemeActivationAdapter {
  inspect(): Promise<CssLoaderSnapshot>;
  setThemeState(name: string, enabled: boolean): Promise<CssLoaderSnapshot>;
  restoreThemeSnapshot(expected: CssLoaderReadySnapshot): Promise<CssLoaderReadySnapshot>;
  hasPendingMutation(): boolean;
  waitForPendingMutation(): Promise<void>;
}

export interface DurableThemeActivationRecovery {
  transaction: string;
  snapshot: CssLoaderReadySnapshot;
}

export interface ThemeActivationJournal {
  begin(snapshot: CssLoaderReadySnapshot): Promise<string>;
  pending(): Promise<DurableThemeActivationRecovery | null>;
  acknowledge(transaction: string): Promise<void>;
}

class MemoryThemeActivationJournal implements ThemeActivationJournal {
  private recovery: DurableThemeActivationRecovery | null = null;

  async begin(snapshot: CssLoaderReadySnapshot): Promise<string> {
    if (this.recovery) throw new Error("A theme activation recovery is already pending");
    const transaction = crypto.randomUUID();
    this.recovery = { transaction, snapshot: structuredClone(snapshot) };
    return transaction;
  }

  async pending(): Promise<DurableThemeActivationRecovery | null> {
    return this.recovery ? structuredClone(this.recovery) : null;
  }

  async acknowledge(transaction: string): Promise<void> {
    if (!this.recovery || this.recovery.transaction !== transaction) {
      throw new Error("Theme activation recovery transaction does not match");
    }
    this.recovery = null;
  }
}

export type ThemeActivationErrorCode =
  | "busy"
  | "not_ready"
  | "unknown_theme"
  | "not_installed"
  | "activation_failed"
  | "deactivation_failed"
  | "rollback_failed";

export class ThemeActivationError extends Error {
  constructor(
    readonly code: ThemeActivationErrorCode,
    message: string,
    readonly restorationFailed = false,
  ) {
    super(message);
    this.name = "ThemeActivationError";
  }
}

function requireReady(snapshot: CssLoaderSnapshot): asserts snapshot is CssLoaderSnapshot & { status: "ready" } {
  if (snapshot.status !== "ready") {
    throw new ThemeActivationError("not_ready", `CSS Loader is ${snapshot.status}`);
  }
}

function catalogByCssLoaderName(catalog: readonly PublishedThemeRelease[]): Map<string, PublishedThemeRelease> {
  return new Map(catalog.map((theme) => [theme.cssLoaderName, theme]));
}

function statesOf(snapshot: CssLoaderSnapshot): Map<string, boolean> {
  return new Map(snapshot.themes.map((theme) => [theme.name, theme.enabled]));
}

function comparableTheme(theme: CssLoaderTheme, expectedEnabled?: boolean) {
  return {
    id: theme.id,
    name: theme.name,
    displayName: theme.displayName,
    version: theme.version,
    author: theme.author,
    enabled: expectedEnabled ?? theme.enabled,
    patches: theme.patches
      .map((patch) => ({
        name: patch.name,
        defaultValue: patch.defaultValue,
        value: patch.value,
        options: patch.options,
        type: patch.type,
        rawType: patch.rawType,
      }))
      .sort((left, right) => left.name.localeCompare(right.name)),
  };
}

function sameSnapshotState(
  initial: CssLoaderReadySnapshot,
  expectedStates: ReadonlyMap<string, boolean>,
  actual: CssLoaderReadySnapshot,
): boolean {
  const comparable = (snapshot: CssLoaderReadySnapshot, useExpectedStates: boolean) => ({
    themes: snapshot.themes
      .map((theme) => comparableTheme(
        theme,
        useExpectedStates ? expectedStates.get(theme.name) : undefined,
      ))
      .sort((left, right) => left.name.localeCompare(right.name)),
  });
  return JSON.stringify(comparable(initial, true)) === JSON.stringify(comparable(actual, false));
}

interface ActivationRecovery {
  transaction: string;
  initial: CssLoaderReadySnapshot;
  status: "needed" | "pending" | "ready";
  snapshot?: CssLoaderReadySnapshot;
  error?: unknown;
}

export class ThemeActivator {
  private running = false;
  private pendingRecovery: ActivationRecovery | null = null;

  constructor(
    private readonly adapter: ThemeActivationAdapter,
    private readonly journal: ThemeActivationJournal = new MemoryThemeActivationJournal(),
  ) {}

  activate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot> {
    if (this.pendingRecovery) {
      return Promise.reject(new ThemeActivationError(
        "rollback_failed",
        "A previous theme activation is still being recovered",
        true,
      ));
    }
    if (this.running) {
      return Promise.reject(new ThemeActivationError("busy", "A theme activation is already running"));
    }
    this.running = true;
    return this.runActivation(themeId, catalog).finally(() => {
      this.running = false;
    });
  }

  deactivate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot> {
    if (this.pendingRecovery) {
      return Promise.reject(new ThemeActivationError(
        "rollback_failed",
        "A previous theme operation is still being recovered",
        true,
      ));
    }
    if (this.running) {
      return Promise.reject(new ThemeActivationError("busy", "A theme operation is already running"));
    }
    this.running = true;
    return this.runDeactivation(themeId, catalog).finally(() => {
      this.running = false;
    });
  }

  private async runActivation(
    themeId: string,
    catalog: readonly PublishedThemeRelease[],
  ): Promise<CssLoaderSnapshot> {
    const target = catalog.find((theme) => theme.catalogId === themeId);
    if (!target) throw new ThemeActivationError("unknown_theme", `Unknown published theme: ${themeId}`);

    const initial = await this.adapter.inspect();
    requireReady(initial);
    if (!initial.themes.some((theme) => theme.name === target.cssLoaderName)) {
      throw new ThemeActivationError("not_installed", `${target.cssLoaderName} is not installed`);
    }

    const catalogEntries = catalogByCssLoaderName(catalog);
    const initialStates = statesOf(initial);
    const conflicts = initial.themes.filter((theme) => {
      const entry = catalogEntries.get(theme.name);
      return theme.enabled
        && theme.name !== target.cssLoaderName
        && entry?.exclusiveGroup !== undefined
      && entry.exclusiveGroup === target.exclusiveGroup;
    });
    const expectedStates = new Map(initialStates);
    conflicts.forEach((conflict) => expectedStates.set(conflict.name, false));
    expectedStates.set(target.cssLoaderName, true);
    const recovery = await this.beginOperation(initial);

    try {
      for (const conflict of conflicts) {
        await this.adapter.setThemeState(conflict.name, false);
      }
      if (!initialStates.get(target.cssLoaderName)) {
        await this.adapter.setThemeState(target.cssLoaderName, true);
      }

      const finalSnapshot = await this.adapter.inspect();
      requireReady(finalSnapshot);
      if (!sameSnapshotState(initial, expectedStates, finalSnapshot)) {
        throw new Error("CSS Loader did not confirm the complete requested theme state");
      }
      await this.completeSuccessfulOperation(recovery);
      return finalSnapshot;
    } catch (activationError) {
      await this.restoreAfterFailure(recovery, "Activation");
      const detail = activationError instanceof Error ? activationError.message : "unknown failure";
      throw new ThemeActivationError("activation_failed", `Theme activation failed: ${detail}`);
    }
  }

  private async runDeactivation(
    themeId: string,
    catalog: readonly PublishedThemeRelease[],
  ): Promise<CssLoaderSnapshot> {
    const target = catalog.find((theme) => theme.catalogId === themeId);
    if (!target) throw new ThemeActivationError("unknown_theme", `Unknown published theme: ${themeId}`);

    const initial = await this.adapter.inspect();
    requireReady(initial);
    const installed = initial.themes.find((theme) => theme.name === target.cssLoaderName);
    if (!installed) throw new ThemeActivationError("not_installed", `${target.cssLoaderName} is not installed`);
    if (!installed.enabled) return initial;

    const initialStates = statesOf(initial);
    const expectedStates = new Map(initialStates);
    expectedStates.set(target.cssLoaderName, false);
    const recovery = await this.beginOperation(initial);
    try {
      await this.adapter.setThemeState(target.cssLoaderName, false);
      const finalSnapshot = await this.adapter.inspect();
      requireReady(finalSnapshot);
      if (!sameSnapshotState(initial, expectedStates, finalSnapshot)) {
        throw new Error("CSS Loader did not confirm the complete requested theme state");
      }
      await this.completeSuccessfulOperation(recovery);
      return finalSnapshot;
    } catch (deactivationError) {
      await this.restoreAfterFailure(recovery, "Deactivation");
      const detail = deactivationError instanceof Error ? deactivationError.message : "unknown failure";
      throw new ThemeActivationError("deactivation_failed", `Theme deactivation failed: ${detail}`);
    }
  }

  async reconcilePendingRecovery(): Promise<CssLoaderReadySnapshot | null> {
    let recovery = this.pendingRecovery;
    if (!recovery) {
      let durable: DurableThemeActivationRecovery | null;
      try {
        durable = await this.journal.pending();
      } catch (error) {
        const detail = error instanceof Error ? `: ${error.message}` : "";
        throw new ThemeActivationError(
          "rollback_failed",
          `Theme activation recovery could not be inspected${detail}`,
          true,
        );
      }
      if (!durable) return null;
      recovery = {
        transaction: durable.transaction,
        initial: durable.snapshot,
        status: "needed",
      };
      this.pendingRecovery = recovery;
    }
    if (recovery.status === "pending") {
      throw new ThemeActivationError(
        "rollback_failed",
        "The previous theme state is still being restored",
        true,
      );
    }
    if (recovery.status === "ready" && recovery.snapshot) {
      const current = await this.adapter.inspect();
      requireReady(current);
      if (this.isFullyRestored(recovery.initial, current)) {
        return this.acknowledgeRecovery(recovery, current);
      }
      recovery.status = "needed";
      recovery.snapshot = undefined;
    }
    try {
      const restored = await this.attemptRecovery(recovery);
      return await this.acknowledgeRecovery(recovery, restored);
    } catch (error) {
      if (this.adapter.hasPendingMutation()) this.beginDeferredRecovery(recovery);
      const detail = error instanceof Error ? `: ${error.message}` : "";
      throw new ThemeActivationError(
        "rollback_failed",
        `The previous theme state could not be restored${detail}`,
        true,
      );
    }
  }

  private async restoreAfterFailure(
    recovery: ActivationRecovery,
    operationName: "Activation" | "Deactivation",
  ): Promise<void> {
    if (this.adapter.hasPendingMutation()) {
      this.beginDeferredRecovery(recovery);
      throw new ThemeActivationError(
        "rollback_failed",
        `${operationName} timed out; recovery is waiting for CSS Loader to settle`,
        true,
      );
    }
    try {
      await this.attemptRecovery(recovery);
      await this.acknowledgeRecovery(recovery, recovery.snapshot!);
    } catch (error) {
      if (this.adapter.hasPendingMutation()) this.beginDeferredRecovery(recovery);
      recovery.error = error;
      throw new ThemeActivationError(
        "rollback_failed",
        `${operationName} failed and the previous theme state could not be restored`,
        true,
      );
    }
  }

  private beginDeferredRecovery(recovery: ActivationRecovery): void {
    recovery.status = "pending";
    void this.performRecovery(recovery.initial)
      .then(
        (snapshot) => {
          recovery.status = "ready";
          recovery.snapshot = snapshot;
          recovery.error = undefined;
        },
        (error: unknown) => {
          recovery.status = "needed";
          recovery.error = error;
        },
      );
  }

  private async attemptRecovery(recovery: ActivationRecovery): Promise<CssLoaderReadySnapshot> {
    recovery.status = "pending";
    try {
      const snapshot = await this.performRecovery(recovery.initial);
      recovery.status = "ready";
      recovery.snapshot = snapshot;
      recovery.error = undefined;
      return snapshot;
    } catch (error) {
      recovery.status = "needed";
      recovery.error = error;
      throw error;
    }
  }

  private async performRecovery(initial: CssLoaderReadySnapshot): Promise<CssLoaderReadySnapshot> {
    await this.adapter.waitForPendingMutation();
    const restored = await this.adapter.restoreThemeSnapshot(initial);
    if (!this.isFullyRestored(initial, restored)) {
      throw new Error("The restored CSS Loader state does not match the activation snapshot");
    }
    return restored;
  }

  private isFullyRestored(
    initial: CssLoaderReadySnapshot,
    candidate: CssLoaderReadySnapshot,
  ): boolean {
    return sameSnapshotState(initial, statesOf(initial), candidate);
  }

  private async beginOperation(initial: CssLoaderReadySnapshot): Promise<ActivationRecovery> {
    try {
      const transaction = await this.journal.begin(initial);
      const recovery: ActivationRecovery = {
        transaction,
        initial: structuredClone(initial),
        status: "needed",
      };
      this.pendingRecovery = recovery;
      return recovery;
    } catch (error) {
      const detail = error instanceof Error ? `: ${error.message}` : "";
      throw new ThemeActivationError(
        "rollback_failed",
        `Theme activation could not create a durable recovery point${detail}`,
        true,
      );
    }
  }

  private async completeSuccessfulOperation(recovery: ActivationRecovery): Promise<void> {
    await this.journal.acknowledge(recovery.transaction);
    if (this.pendingRecovery === recovery) this.pendingRecovery = null;
  }

  private async acknowledgeRecovery(
    recovery: ActivationRecovery,
    snapshot: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot> {
    if (!this.isFullyRestored(recovery.initial, snapshot)) {
      recovery.status = "needed";
      throw new Error("Theme activation recovery verification failed");
    }
    await this.journal.acknowledge(recovery.transaction);
    if (this.pendingRecovery === recovery) this.pendingRecovery = null;
    return snapshot;
  }
}
