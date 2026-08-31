import { ThemeActivator } from "./activation";
import { CssLoaderAdapter, type CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import { createDeckyCssLoaderHost } from "./deckyCssLoaderHost";
import { createPanelThemeInstaller } from "./panelThemeInstallHost";
import { ThemeInstallError, type ThemeInstallResult } from "./panelThemeInstaller";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
import {
  createRemotePublicationClient,
  type ThemePublicationClient,
} from "./remotePublicationClient";
import { deriveThemeCards } from "./state";
import type { ThemeInstallRequest } from "./types";

export interface ThemesAdapter {
  inspect(): Promise<CssLoaderSnapshot>;
  requireReady(): Promise<CssLoaderReadySnapshot>;
  reloadTheme(
    expectedThemeName: string,
    expectedVersion: string,
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot>;
  restoreThemeSnapshot(expected: CssLoaderReadySnapshot): Promise<CssLoaderReadySnapshot>;
  reconcileRecoveredThemes(
    recoveries: readonly { themeName: string; previousVersion: string | null }[],
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot>;
  setPatchValue(themeName: string, patchName: string, value: string): Promise<CssLoaderSnapshot>;
}

export interface ThemesInstaller {
  prepare(source: ThemeInstallRequest): Promise<ThemeInstallResult>;
  commit(transaction: string): Promise<void>;
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
}

export interface ThemesDependencies {
  adapter: ThemesAdapter;
  installer: ThemesInstaller;
  activator: ThemesActivator;
  publication?: ThemePublicationClient;
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
  | { kind: "activating"; themeId: string }
  | { kind: "deactivating"; themeId: string }
  | { kind: "saving"; themeId: string; patchName: string };

export interface ThemesClientSnapshot {
  loading: boolean;
  refreshing: boolean;
  snapshot: CssLoaderSnapshot;
  operation: ThemesOperation | null;
  recoveryBlocked: boolean;
  error: string | null;
  publication: ThemePublicationState;
}

let productionDependencies: ThemesDependencies | undefined;
const BLOCKING_RECOVERY_CODES = new Set([
  "invalid_journal",
  "rollback_failed",
  "rollback_verification_failed",
]);

export const REQUIRED_CSS_LOADER_BACKEND_VERSION = 9;

export function createProductionThemesDependencies(): ThemesDependencies {
  if (productionDependencies) return productionDependencies;
  const adapter = new CssLoaderAdapter(createDeckyCssLoaderHost(), {
    minimumBackendVersion: REQUIRED_CSS_LOADER_BACKEND_VERSION,
  });
  productionDependencies = {
    adapter,
    installer: createPanelThemeInstaller(),
    activator: new ThemeActivator(adapter),
    publication: createRemotePublicationClient(),
  };
  return productionDependencies;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Theme operation failed";
}

function blocksThemeRecovery(error: unknown): boolean {
  return error instanceof ThemeInstallError && BLOCKING_RECOVERY_CODES.has(error.code);
}

export class ThemesClient {
  private current: ThemesClientSnapshot = {
    loading: true,
    refreshing: false,
    snapshot: { status: "missing", themes: [] },
    operation: null,
    recoveryBlocked: false,
    error: null,
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
          error: recoveryError === undefined ? null : errorMessage(recoveryError),
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
          error: errorMessage(recoveryError ?? inspectionError),
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
    if (this.current.snapshot.status !== "ready" || !themes.some((theme) => theme.catalogId === themeId)) {
      return Promise.resolve(false);
    }
    return this.mutate(
      { kind: "activating", themeId },
      () => this.dependencies.activator.activate(themeId, themes),
    );
  };

  deactivate = (themeId: string): Promise<boolean> => {
    const themes = this.currentPublicationThemes();
    if (this.current.snapshot.status !== "ready" || !themes.some((theme) => theme.catalogId === themeId)) {
      return Promise.resolve(false);
    }
    return this.mutate(
      { kind: "deactivating", themeId },
      () => this.dependencies.activator.deactivate(themeId, themes),
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
            await this.dependencies.adapter.restoreThemeSnapshot(before);
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
      () => this.dependencies.adapter.setPatchValue(entry.cssLoaderName, patchName, value),
    );
  };

  private currentPublicationThemes(): readonly PublishedThemeRelease[] {
    return this.current.publication.status === "published" || this.current.publication.status === "cached"
      ? this.current.publication.themes
      : [];
  }

  private publishSnapshot(request: number, snapshot: CssLoaderSnapshot): void {
    if (request !== this.requestSequence) return;
    this.update({ snapshot, error: null });
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
    if (this.recoveryChecked) return null;
    if (this.recoveryPromise) return this.recoveryPromise;
    this.recoveryPromise = this.runPendingRecovery();
    try {
      return await this.recoveryPromise;
    } finally {
      this.recoveryPromise = null;
    }
  }

  private async runPendingRecovery(): Promise<CssLoaderReadySnapshot | null> {
    const recoveries = await this.dependencies.installer.pendingRecoveries();
    if (recoveries.length === 0) {
      this.recoveryChecked = true;
      return null;
    }
    const before = await this.dependencies.adapter.requireReady();
    const reconciled = await this.dependencies.adapter.reconcileRecoveredThemes(recoveries, before);
    for (const recovery of recoveries) {
      await this.dependencies.installer.acknowledgeRollback(recovery.transaction);
    }
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
    this.update({ loading: false, operation, error: null });
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
          error: errorMessage(operationError),
        });
      }
      return false;
    } finally {
      this.operationLocked = false;
      if (request === this.requestSequence) this.update({ operation: null });
    }
  }

  private update(patch: Partial<ThemesClientSnapshot>): void {
    this.current = { ...this.current, ...patch };
    this.subscriptions.forEach(({ listener }) => listener());
  }
}
