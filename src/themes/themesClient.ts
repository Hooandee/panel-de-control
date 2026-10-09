import { ThemeActivationError, ThemeActivator } from "./activation";
import {
  CssLoaderAdapter,
  CssLoaderOperationError,
  type CssLoaderReadySnapshot,
} from "./cssLoaderAdapter";
import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import { createDeckyCssLoaderHost } from "./deckyCssLoaderHost";
import { createPanelThemeInstaller } from "./panelThemeInstallHost";
import { createPanelThemeActivationJournal } from "./panelThemeActivationJournal";
import { createThemeCleanupHost } from "./themeCleanupHost";
import { ThemeInstallError, type ThemeInstallResult } from "./panelThemeInstaller";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
import {
  createRemotePublicationClient,
  type ThemePublicationClient,
} from "./remotePublicationClient";
import {
  handoffsGivenBy,
  planSectionHandoff,
  planSectionReclaim,
  planSectionRestore,
  SECTION_OFF,
  SECTION_ON,
  sectionHandoffKey,
  sectionKeyOf,
  type SectionHandoffs,
  type SectionPatchRef,
} from "./sectionOwnership";
import { deriveThemeCards } from "./state";
import type { ThemeInstallRequest } from "./types";

export interface ThemesAdapter {
  inspect(): Promise<CssLoaderSnapshot>;
  requireReady(): Promise<CssLoaderReadySnapshot>;
  deleteTheme(themeName: string): Promise<CssLoaderReadySnapshot>;
  reloadTheme(
    expectedThemeName: string,
    expectedVersion: string,
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot>;
  restoreThemeSnapshot(
    expected: CssLoaderReadySnapshot,
    restoredThemeNames?: readonly string[],
  ): Promise<CssLoaderReadySnapshot>;
  reconcileRecoveredThemes(
    recoveries: readonly { themeName: string; previousVersion: string | null }[],
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot>;
  setPatchValue(themeName: string, patchName: string, value: string): Promise<CssLoaderSnapshot>;
  disableAllExcept?(before: CssLoaderReadySnapshot, keep: ReadonlySet<string>): Promise<CssLoaderReadySnapshot>;
  enableAgain?(
    before: CssLoaderReadySnapshot,
    keep: ReadonlySet<string>,
    names: readonly string[],
  ): Promise<CssLoaderReadySnapshot>;
}

export interface ThemeCleanupHost {
  setAside(disabled: readonly string[]): Promise<void>;
  // Moves folders back and returns the themes to enable again; they stay recorded until acknowledged.
  restore(): Promise<readonly string[]>;
  acknowledgeRestore(): Promise<void>;
}

export interface ThemesInstaller {
  prepare(source: ThemeInstallRequest): Promise<ThemeInstallResult>;
  commit(transaction: string): Promise<void>;
  discardReceipt(catalogId: string): Promise<void>;
  rollback(transaction: string): Promise<void>;
  pendingRecoveries(): Promise<readonly {
    transaction: string;
    themeName: string;
    previousVersion: string | null;
  }[]>;
  acknowledgeRollback(transaction: string): Promise<void>;
}

export interface ThemesActivator {
  activate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot>;
  deactivate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot>;
  reconcilePendingRecovery?(): Promise<CssLoaderReadySnapshot | null>;
  takeAbandonedRecovery?(): boolean;
}

export interface SectionHandoffStore {
  read(): SectionHandoffs;
  write(handoffs: SectionHandoffs): void;
}

export interface SectionHandoffNotice {
  owner: string;
  others: string[];
}

export interface ThemeFailureReport {
  operation: ThemesOperation["kind"];
  code: string;
  message: string;
}

export interface ThemesDependencies {
  adapter: ThemesAdapter;
  installer: ThemesInstaller;
  activator: ThemesActivator;
  publication?: ThemePublicationClient;
  reportFailure?: (failure: ThemeFailureReport) => void;
  sectionHandoffs?: SectionHandoffStore;
  cleanup?: ThemeCleanupHost;
  refreshIntervalMs?: number;
  publicationRefreshIntervalMs?: number;
  publicationFailureRetryIntervalMs?: number;
}

export interface ThemeInstallConfirmation {
  version: string;
}

export type ThemesOperation =
  | { kind: "recovering" }
  | { kind: "installing"; themeId: string }
  | { kind: "uninstalling"; themeId: string }
  | { kind: "activating"; themeId: string }
  | { kind: "deactivating"; themeId: string }
  | { kind: "saving"; themeId: string; patchName: string }
  | { kind: "cleaning" }
  | { kind: "restoring" };

export interface ThemesClientSnapshot {
  loading: boolean;
  refreshing: boolean;
  snapshot: CssLoaderSnapshot;
  operation: ThemesOperation | null;
  recoveryBlocked: boolean;
  recoveryKeptCurrent: boolean;
  error: string | null;
  errorCode: string | null;
  sectionHandoff: SectionHandoffNotice | null;
  publication: ThemePublicationState;
}

const BLOCKING_RECOVERY_CODES = new Set([
  "invalid_journal",
  "rollback_failed",
  "rollback_verification_failed",
]);
const ANSWERED_CSS_LOADER_CODES = new Set(["mutation_failed", "verification_failed"]);
const MAX_INSTALL_RECONCILE_FAILURES = 3;

let productionDependencies: ThemesDependencies | undefined;
let failureReporter: ((failure: ThemeFailureReport) => unknown) | undefined;
let sectionHandoffStore: SectionHandoffStore | undefined;

export function configureThemeFailureReporter(
  reporter: (failure: ThemeFailureReport) => unknown,
): () => void {
  failureReporter = reporter;
  return () => {
    if (failureReporter === reporter) failureReporter = undefined;
  };
}

export function configureSectionHandoffStore(store: SectionHandoffStore): () => void {
  sectionHandoffStore = store;
  return () => {
    if (sectionHandoffStore === store) sectionHandoffStore = undefined;
  };
}

export function createProductionThemesDependencies(): ThemesDependencies {
  if (productionDependencies) return productionDependencies;
  const adapter = new CssLoaderAdapter(createDeckyCssLoaderHost());
  productionDependencies = {
    adapter,
    installer: createPanelThemeInstaller(),
    activator: new ThemeActivator(adapter, createPanelThemeActivationJournal()),
    publication: createRemotePublicationClient(),
    reportFailure: (failure) => {
      void Promise.resolve(failureReporter?.(failure)).catch(() => undefined);
    },
    sectionHandoffs: {
      read: () => sectionHandoffStore?.read() ?? {},
      write: (handoffs) => sectionHandoffStore?.write(handoffs),
    },
    cleanup: createThemeCleanupHost(),
  };
  return productionDependencies;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Theme operation failed";
}

function errorCode(error: unknown): string {
  const code = error instanceof Error ? (error as { code?: unknown }).code : undefined;
  return typeof code === "string" && code.length > 0 ? code : "unknown";
}

// Failure messages reach the logs in reports; other themes and profiles can carry personal names.
async function withoutThemeNames<T>(operation: Promise<T>): Promise<T> {
  try {
    return await operation;
  } catch (error) {
    throw new CssLoaderOperationError(
      error instanceof CssLoaderOperationError ? error.code : "transport",
      "CSS Loader could not finish the theme cleanup",
    );
  }
}

function cssLoaderAnsweredWithMismatch(error: unknown): boolean {
  return error instanceof CssLoaderOperationError && ANSWERED_CSS_LOADER_CODES.has(error.code);
}

function blocksThemeRecovery(error: unknown): boolean {
  return (
    error instanceof ThemeInstallError && BLOCKING_RECOVERY_CODES.has(error.code)
  ) || (
    error instanceof ThemeActivationError && error.restorationFailed
  );
}

export class ThemesClient {
  private current: ThemesClientSnapshot = {
    loading: true,
    refreshing: false,
    snapshot: { status: "missing", themes: [] },
    operation: null,
    recoveryBlocked: false,
    recoveryKeptCurrent: false,
    error: null,
    errorCode: null,
    sectionHandoff: null,
    publication: { status: "unchecked" },
  };
  private readonly subscriptions = new Map<symbol, {
    listener: () => void;
    refreshIntervalMs: number;
  }>();
  private requestSequence = 0;
  private operationLocked = false;
  private activeRefreshes = 0;
  private refreshTimer: ReturnType<typeof setInterval> | undefined;
  private refreshTimerIntervalMs: number | undefined;
  private recoveryChecked = false;
  private recoveryPromise: Promise<CssLoaderReadySnapshot | null> | null = null;
  private refreshPromise: Promise<void> | null = null;
  private publicationRequestSequence = 0;
  private publicationPromise: Promise<void> | null = null;
  private publicationResolvedAtMs: number | undefined;
  private installReconcileFailures = 0;
  private pendingSectionHandoff: SectionHandoffNotice | null = null;
  private lastReportedFailure: string | null = null;

  constructor(readonly dependencies: ThemesDependencies) {}

  getSnapshot = (): ThemesClientSnapshot => this.current;

  subscribe = (
    listener: () => void,
    refreshIntervalMs = this.dependencies.refreshIntervalMs ?? 10_000,
  ): (() => void) => {
    const firstConsumer = this.subscriptions.size === 0;
    const lease = Symbol("themes-client-subscriber");
    this.subscriptions.set(lease, {
      listener,
      refreshIntervalMs: Math.max(1, refreshIntervalMs),
    });
    this.reconcileRefreshTimer();
    if (firstConsumer) {
      if (this.activeRefreshes === 0) void this.refresh();
    }
    return () => {
      this.subscriptions.delete(lease);
      this.reconcileRefreshTimer();
      if (
        this.subscriptions.size === 0
        && this.dependencies.publication
        && this.current.publication.status !== "checking"
      ) {
        this.current = { ...this.current, publication: { status: "unchecked" } };
      }
    };
  };

  refresh = (): Promise<void> => {
    if (this.refreshPromise) return this.refreshPromise;
    if (this.operationLocked) return Promise.resolve();
    const running = this.performRefresh();
    this.refreshPromise = running;
    const release = () => {
      if (this.refreshPromise === running) this.refreshPromise = null;
    };
    void running.then(release, release);
    return running;
  };

  private performRefresh = async (): Promise<void> => {
    const ownsRecoveryLock = !this.recoveryChecked;
    this.update({ refreshing: true });
    if (ownsRecoveryLock) {
      this.operationLocked = true;
      this.update({ operation: { kind: "recovering" }, error: null });
    }
    this.activeRefreshes += 1;
    this.startPublicationCheck(false);
    const request = ++this.requestSequence;
    let recoveryError: unknown;
    let recoveryLockReleased = false;
    try {
      let recovered: CssLoaderReadySnapshot | null = null;
      try {
        recovered = await this.reconcilePendingRecovery();
      } catch (error) {
        recoveryError = error;
      } finally {
        if (ownsRecoveryLock) {
          this.operationLocked = false;
          recoveryLockReleased = true;
          if (request === this.requestSequence) this.update({ operation: null });
        }
      }
      const snapshot = recovered ?? await this.dependencies.adapter.inspect();
      if (request === this.requestSequence) {
        this.update({
          snapshot,
          recoveryBlocked: recoveryError === undefined
            ? false
            : this.current.recoveryBlocked || blocksThemeRecovery(recoveryError),
          ...this.failurePatch("recovering", recoveryError),
        });
      }
    } catch (inspectionError) {
      if (request === this.requestSequence) {
        this.update({
          snapshot: {
            status: "error",
            themes: [],
            error: { code: "transport", message: errorMessage(inspectionError) },
          },
          recoveryBlocked: recoveryError === undefined
            ? this.current.recoveryBlocked
            : this.current.recoveryBlocked || blocksThemeRecovery(recoveryError),
          ...(recoveryError === undefined
            ? { error: errorMessage(inspectionError), errorCode: errorCode(inspectionError) }
            : this.failurePatch("recovering", recoveryError)),
        });
      }
    } finally {
      this.activeRefreshes -= 1;
      if (ownsRecoveryLock && !recoveryLockReleased) this.operationLocked = false;
      if (request === this.requestSequence) {
        this.update({
          loading: false,
          refreshing: false,
          ...(ownsRecoveryLock && !recoveryLockReleased ? { operation: null } : {}),
        });
      } else if (this.activeRefreshes === 0) {
        this.update({ refreshing: false });
      }
    }
  };

  activate = (themeId: string): Promise<boolean> => {
    const themes = this.currentPublicationThemes();
    const target = themes.find((theme) => theme.catalogId === themeId);
    if (this.current.snapshot.status !== "ready" || target?.compatibility !== "compatible") {
      return Promise.resolve(false);
    }
    return this.mutate(
      { kind: "activating", themeId },
      async () => this.handOffSections(
        await this.reclaimSections(
          await this.dependencies.activator.activate(themeId, themes),
          target.cssLoaderName,
        ),
        target.cssLoaderName,
      ),
    );
  };

  deactivate = (themeId: string): Promise<boolean> => {
    const themes = this.currentPublicationThemes();
    if (this.current.snapshot.status !== "ready" || !themes.some((theme) => theme.catalogId === themeId)) {
      return Promise.resolve(false);
    }
    const leaving = themes.find((theme) => theme.catalogId === themeId)!.cssLoaderName;
    return this.mutate(
      { kind: "deactivating", themeId },
      async () => this.restoreSections(
        await this.dependencies.activator.deactivate(themeId, themes),
        leaving,
      ),
    );
  };

  install = (
    themeId: string,
    confirmation?: ThemeInstallConfirmation,
  ): Promise<boolean> => {
    const card = deriveThemeCards(this.current.publication, this.current.snapshot)
      .find((candidate) => candidate.id === themeId);
    if (this.current.snapshot.status !== "ready" || !card?.targetVersion || !card.installable) {
      return Promise.resolve(false);
    }
    if (confirmation && confirmation.version !== card.targetVersion) return Promise.resolve(false);
    const source: ThemeInstallRequest = {
      kind: "official-remote",
      channelId: "panel-pages-v1",
      catalogId: card.release.catalogId,
      expectedVersion: card.targetVersion,
    };
    const expectedVersion = card.targetVersion;
    return this.mutate(
      { kind: "installing", themeId },
      async () => {
        const before = await this.dependencies.adapter.requireReady();
        this.recoveryChecked = false;
        const installed = await this.dependencies.installer.prepare(source);
        try {
          if (
            installed.themeId !== card.release.catalogId
            || installed.themeName !== card.release.cssLoaderName
            || installed.version !== expectedVersion
          ) {
            throw new ThemeInstallError(
              "identity_mismatch",
              "Installed theme package does not match the catalog",
            );
          }
          const verified = await this.dependencies.adapter.reloadTheme(
            card.release.cssLoaderName,
            expectedVersion,
            before,
          );
          await this.dependencies.installer.commit(installed.transaction);
          this.recoveryChecked = true;
          return verified;
        } catch (installError) {
          this.recoveryChecked = false;
          try {
            await this.dependencies.installer.rollback(installed.transaction);
          } catch (rollbackError) {
            throw new ThemeInstallError(
              "rollback_failed",
              `Theme installation rollback failed: ${errorMessage(rollbackError)}`,
            );
          }
          try {
            await this.dependencies.adapter.restoreThemeSnapshot(before, [card.release.cssLoaderName]);
          } catch (restoreError) {
            throw new ThemeInstallError(
              "rollback_verification_failed",
              `Theme rollback could not be verified: ${errorMessage(restoreError)}`,
            );
          }
          await this.dependencies.installer.acknowledgeRollback(installed.transaction);
          this.recoveryChecked = true;
          throw installError;
        }
      },
    );
  };

  uninstall = (themeId: string): Promise<boolean> => {
    const card = deriveThemeCards(this.current.publication, this.current.snapshot)
      .find((candidate) => candidate.id === themeId);
    if (this.current.snapshot.status !== "ready" || !card?.installed) {
      return Promise.resolve(false);
    }
    return this.mutate(
      { kind: "uninstalling", themeId },
      async () => {
        const after = await this.dependencies.adapter.deleteTheme(card.release.cssLoaderName);
        try {
          await this.dependencies.installer.discardReceipt(card.release.catalogId);
        } catch {}
        return this.restoreSections(after, card.release.cssLoaderName);
      },
    );
  };

  refreshPublication = (force = true): Promise<void> => {
    if (this.publicationPromise) return this.publicationPromise;
    if (!this.dependencies.publication) return Promise.resolve();
    return this.startPublicationCheck(force);
  };

  private startPublicationCheck(force: boolean): Promise<void> {
    if (!this.dependencies.publication) return Promise.resolve();
    const now = Date.now();
    const freshnessWindow = Math.max(
      1,
      this.dependencies.publicationRefreshIntervalMs ?? 15 * 60 * 1_000,
    );
    const failureRetryWindow = Math.max(
      1,
      this.dependencies.publicationFailureRetryIntervalMs ?? 30_000,
    );
    const retryableFailure = (
      this.current.publication.status === "temporarily-unavailable"
      || this.current.publication.status === "recoverable-failure"
      || this.current.publication.status === "cached"
    ) && this.current.publication.retryable;
    if (
      !force
      && this.current.publication.status !== "unchecked"
      && this.publicationResolvedAtMs !== undefined
      && now - this.publicationResolvedAtMs < (
        retryableFailure ? failureRetryWindow : freshnessWindow
      )
    ) return Promise.resolve();
    if (this.publicationPromise) return this.publicationPromise;
    const request = ++this.publicationRequestSequence;
    this.update({ publication: { status: "checking" } });
    const running = this.dependencies.publication.check(force).then((publication) => {
      if (request === this.publicationRequestSequence) {
        this.publicationResolvedAtMs = Date.now();
        this.update({ publication });
      }
    }).catch(() => {
      if (request === this.publicationRequestSequence) {
        this.publicationResolvedAtMs = Date.now();
        this.update({
          publication: {
            status: "recoverable-failure",
            code: "invalid_descriptor",
            retryable: true,
          },
        });
      }
    });
    this.publicationPromise = running;
    const release = () => {
      if (this.publicationPromise === running) this.publicationPromise = null;
    };
    void running.then(release, release);
    return running;
  }

  setPatch = (themeId: string, patchName: string, value: string): Promise<boolean> => {
    const entry = this.currentPublicationThemes().find((theme) => theme.catalogId === themeId);
    if (!entry) return Promise.resolve(false);
    return this.mutate(
      { kind: "saving", themeId, patchName },
      async () => {
        const after = await this.dependencies.adapter.setPatchValue(entry.cssLoaderName, patchName, value);
        if (sectionKeyOf(patchName) === null) return after;
        this.forgetHandoffs([{ themeName: entry.cssLoaderName, patchName }]);
        return this.handOffSections(after, entry.cssLoaderName, patchName);
      },
    );
  };

  // Without CSS Loader running nothing can be turned off or reloaded, but its folders can still be
  // set aside and the styles it left behind removed from the Steam windows the caller can reach.
  // `keepActive` names the one Hooandee theme to leave on when several are; the others go off
  // through the same path as their own Deactivate button, before CSS Loader reloads.
  cleanUp = (
    keep: readonly string[],
    removeLeftoverStyles?: () => void,
    keepActive?: string,
  ): Promise<boolean> => this.mutate({ kind: "cleaning" }, async () => {
    const { adapter, cleanup } = this.dependencies;
    if (!adapter.disableAllExcept || !cleanup) {
      throw new CssLoaderOperationError("transport", "Theme cleanup is unavailable");
    }
    const current = await adapter.inspect();
    if (current.status === "missing" || current.status === "disabled") {
      await cleanup.setAside([]);
      removeLeftoverStyles?.();
      return current;
    }
    const kept = new Set([...keep, ...this.hooandeeThemeNames()]);
    if (keepActive !== undefined) await this.deactivateOursExcept(current, keepActive);
    const before = await adapter.requireReady();
    await cleanup.setAside(before.themes.filter((theme) => theme.enabled && !kept.has(theme.name)).map((theme) => theme.name));
    const after = await withoutThemeNames(adapter.disableAllExcept(before, kept));
    if (!after.themes.some((theme) => theme.enabled)) removeLeftoverStyles?.();
    return after;
  });

  undoCleanup = (keep: readonly string[]): Promise<boolean> => this.mutate({ kind: "restoring" }, async () => {
    const { adapter, cleanup } = this.dependencies;
    if (!adapter.enableAgain || !cleanup) {
      throw new CssLoaderOperationError("transport", "Theme cleanup is unavailable");
    }
    const current = await adapter.inspect();
    if (current.status === "missing" || current.status === "disabled") {
      await cleanup.restore();
      return current;
    }
    const kept = new Set([...keep, ...this.hooandeeThemeNames()]);
    const before = await adapter.requireReady();
    const after = await withoutThemeNames(adapter.enableAgain(before, kept, await cleanup.restore()));
    await cleanup.acknowledgeRestore();
    return after;
  });

  private async deactivateOursExcept(snapshot: CssLoaderSnapshot, keepActive: string): Promise<void> {
    if (!snapshot.themes.some((theme) => theme.name === keepActive && theme.enabled)) {
      throw new CssLoaderOperationError("verification_failed", "The theme chosen to stay active is no longer active");
    }
    const catalog = this.currentPublicationThemes();
    for (const theme of snapshot.themes) {
      if (!theme.enabled || theme.name === keepActive) continue;
      const release = catalog.find((entry) => entry.cssLoaderName === theme.name);
      if (release) {
        await this.restoreSections(await this.dependencies.activator.deactivate(release.catalogId, catalog), theme.name);
      }
    }
  }

  private hooandeeThemeNames(): ReadonlySet<string> {
    return new Set(this.currentPublicationThemes().map((theme) => theme.cssLoaderName));
  }

  private readHandoffs(): SectionHandoffs {
    return this.dependencies.sectionHandoffs?.read() ?? {};
  }

  private writeHandoffs(handoffs: SectionHandoffs): void {
    this.dependencies.sectionHandoffs?.write(handoffs);
  }

  private forgetHandoffs(refs: readonly SectionPatchRef[]): void {
    const handoffs = { ...this.readHandoffs() };
    const keys = refs.map(sectionHandoffKey).filter((key) => key in handoffs);
    keys.forEach((key) => delete handoffs[key]);
    if (keys.length > 0) this.writeHandoffs(handoffs);
  }

  private async applySectionValues(
    snapshot: CssLoaderSnapshot,
    refs: readonly SectionPatchRef[],
    value: typeof SECTION_ON | typeof SECTION_OFF,
  ): Promise<{ snapshot: CssLoaderSnapshot; applied: SectionPatchRef[] }> {
    let current = snapshot;
    const applied: SectionPatchRef[] = [];
    for (const ref of refs) {
      try {
        current = await this.dependencies.adapter.setPatchValue(ref.themeName, ref.patchName, value);
        applied.push(ref);
      } catch (error) {
        this.report("saving", error, "section_handoff_failed");
      }
    }
    return { snapshot: current, applied };
  }

  private async handOffSections(
    snapshot: CssLoaderSnapshot,
    ownerName: string,
    onlyPatchName?: string,
  ): Promise<CssLoaderSnapshot> {
    if (snapshot.status !== "ready") return snapshot;
    const plan = planSectionHandoff(snapshot.themes, ownerName, this.hooandeeThemeNames(), onlyPatchName);
    if (plan.length === 0) return snapshot;
    const { snapshot: after, applied } = await this.applySectionValues(snapshot, plan, SECTION_OFF);
    if (applied.length > 0) {
      const handoffs = { ...this.readHandoffs() };
      for (const ref of applied) handoffs[sectionHandoffKey(ref)] = ownerName;
      this.writeHandoffs(handoffs);
      const displayName = (name: string) => after.themes.find((theme) => theme.name === name)?.displayName ?? name;
      this.pendingSectionHandoff = {
        owner: displayName(ownerName),
        others: [...new Set(applied.map((ref) => displayName(ref.themeName)))],
      };
    }
    return after;
  }

  private async reclaimSections(snapshot: CssLoaderSnapshot, themeName: string): Promise<CssLoaderSnapshot> {
    const handoffs = this.readHandoffs();
    const given = handoffsGivenBy(handoffs, themeName);
    if (given.length === 0 || snapshot.status !== "ready") return snapshot;
    const plan = planSectionReclaim(snapshot.themes, handoffs, themeName);
    const { snapshot: after } = await this.applySectionValues(snapshot, plan, SECTION_ON);
    this.forgetHandoffs(given);
    return after;
  }

  private async restoreSections(snapshot: CssLoaderSnapshot, leavingOwner: string): Promise<CssLoaderSnapshot> {
    const handoffs = this.readHandoffs();
    const owned = Object.keys(handoffs).filter((key) => handoffs[key] === leavingOwner);
    if (owned.length === 0 || snapshot.status !== "ready") return snapshot;
    const plan = planSectionRestore(snapshot.themes, handoffs, leavingOwner);
    const { snapshot: after } = await this.applySectionValues(snapshot, plan, SECTION_ON);
    const remaining = { ...handoffs };
    owned.forEach((key) => delete remaining[key]);
    this.writeHandoffs(remaining);
    return after;
  }

  private currentPublicationThemes(): readonly PublishedThemeRelease[] {
    return this.current.publication.status === "published" || this.current.publication.status === "cached"
      ? this.current.publication.themes
      : [];
  }

  private publishSnapshot(request: number, snapshot: CssLoaderSnapshot): void {
    if (request !== this.requestSequence) return;
    const sectionHandoff = this.pendingSectionHandoff;
    this.pendingSectionHandoff = null;
    this.update({ snapshot, error: null, errorCode: null, sectionHandoff });
  }

  private reconcileRefreshTimer(): void {
    const interval = this.subscriptions.size === 0
      ? undefined
      : Math.min(...[...this.subscriptions.values()].map((entry) => entry.refreshIntervalMs));
    if (interval === this.refreshTimerIntervalMs) return;
    if (this.refreshTimer !== undefined) clearInterval(this.refreshTimer);
    this.refreshTimer = undefined;
    this.refreshTimerIntervalMs = interval;
    if (interval !== undefined) {
      this.refreshTimer = setInterval(() => void this.refresh(), interval);
    }
  }

  private async reconcilePendingRecovery(): Promise<CssLoaderReadySnapshot | null> {
    if (this.recoveryPromise) return this.recoveryPromise;
    this.recoveryPromise = this.runPendingRecovery();
    try {
      return await this.recoveryPromise;
    } finally {
      this.recoveryPromise = null;
    }
  }

  private async runPendingRecovery(): Promise<CssLoaderReadySnapshot | null> {
    const activationRecovery = await this.dependencies.activator.reconcilePendingRecovery?.() ?? null;
    if (this.dependencies.activator.takeAbandonedRecovery?.()) this.update({ recoveryKeptCurrent: true });
    if (this.recoveryChecked) return activationRecovery;
    const recoveries = await this.dependencies.installer.pendingRecoveries();
    if (recoveries.length === 0) {
      this.recoveryChecked = true;
      return activationRecovery;
    }
    const before = activationRecovery ?? await this.dependencies.adapter.requireReady();
    let reconciled: CssLoaderReadySnapshot;
    try {
      reconciled = await this.dependencies.adapter.reconcileRecoveredThemes(recoveries, before);
    } catch (error) {
      if (!cssLoaderAnsweredWithMismatch(error)) throw error;
      this.installReconcileFailures += 1;
      if (this.installReconcileFailures < MAX_INSTALL_RECONCILE_FAILURES) throw error;
      this.report("recovering", error, "released_after_mismatch");
      reconciled = await this.dependencies.adapter.requireReady();
      this.update({ recoveryKeptCurrent: true });
    }
    for (const recovery of recoveries) {
      await this.dependencies.installer.acknowledgeRollback(recovery.transaction);
    }
    this.installReconcileFailures = 0;
    this.recoveryChecked = true;
    return reconciled;
  }

  private async mutate(
    operation: ThemesOperation,
    run: () => Promise<CssLoaderSnapshot>,
  ): Promise<boolean> {
    if (this.operationLocked || this.current.recoveryBlocked) return false;
    this.operationLocked = true;
    const request = ++this.requestSequence;
    this.pendingSectionHandoff = null;
    this.update({
      loading: false,
      operation,
      error: null,
      errorCode: null,
      recoveryKeptCurrent: false,
      sectionHandoff: null,
    });
    try {
      await this.reconcilePendingRecovery();
      this.publishSnapshot(request, await run());
      return true;
    } catch (operationError) {
      let reconciled: CssLoaderSnapshot;
      try {
        reconciled = await this.dependencies.adapter.inspect();
      } catch (inspectionError) {
        reconciled = {
          status: "error",
          themes: [],
          error: { code: "transport", message: errorMessage(inspectionError) },
        };
      }
      if (request === this.requestSequence) {
        this.update({
          snapshot: reconciled,
          recoveryBlocked: this.current.recoveryBlocked || blocksThemeRecovery(operationError),
          ...this.failurePatch(operation.kind, operationError),
        });
      }
      return false;
    } finally {
      this.operationLocked = false;
      if (request === this.requestSequence) this.update({ operation: null });
    }
  }

  private failurePatch(
    operation: ThemesOperation["kind"],
    error: unknown,
  ): Pick<ThemesClientSnapshot, "error" | "errorCode"> {
    if (error === undefined) {
      this.lastReportedFailure = null;
      return { error: null, errorCode: null };
    }
    this.report(operation, error);
    return { error: errorMessage(error), errorCode: errorCode(error) };
  }

  private report(operation: ThemesOperation["kind"], error: unknown, code = errorCode(error)): void {
    const failure: ThemeFailureReport = {
      operation,
      code,
      message: errorMessage(error),
    };
    const key = JSON.stringify(failure);
    if (key === this.lastReportedFailure) return;
    this.lastReportedFailure = key;
    try {
      this.dependencies.reportFailure?.(failure);
    } catch {}
  }

  private update(patch: Partial<ThemesClientSnapshot>): void {
    this.current = { ...this.current, ...patch };
    this.subscriptions.forEach(({ listener }) => listener());
  }
}
