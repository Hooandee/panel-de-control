import type {
  CssLoaderErrorCode,
  CssLoaderErrorInfo,
  CssLoaderPatch,
  CssLoaderPatchType,
  CssLoaderSnapshot,
  CssLoaderTheme,
} from "./cssLoaderTypes";

const CSS_LOADER_PLUGIN_NAME = "CSS Loader";
const PATCH_TYPES = new Set(["checkbox", "dropdown", "slider", "none"]);

export interface CssLoaderPluginInventoryEntry {
  name: string;
  disabled: boolean;
}

export interface CssLoaderHost {
  inventory(): readonly CssLoaderPluginInventoryEntry[];
  call(method: string, ...args: unknown[]): Promise<unknown>;
}

export interface CssLoaderAdapterOptions {
  timeoutMs?: number;
  reloadTimeoutMs?: number;
}

export type CssLoaderReadySnapshot = CssLoaderSnapshot & { status: "ready" };

export interface CssLoaderRecoveryExpectation {
  themeName: string;
  previousVersion: string | null;
}

export class CssLoaderOperationError extends Error {
  constructor(readonly code: CssLoaderErrorCode, message: string) {
    super(message);
    this.name = "CssLoaderOperationError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function normalizePatch(value: unknown): CssLoaderPatch | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.name !== "string"
    || !value.name.trim()
    || typeof value.default !== "string"
    || typeof value.value !== "string"
    || typeof value.type !== "string"
    || !stringArray(value.options)
    || !Array.isArray(value.components)
  ) {
    return null;
  }
  const type: CssLoaderPatchType = PATCH_TYPES.has(value.type)
    ? value.type as CssLoaderPatchType
    : "unsupported";
  return {
    name: value.name,
    defaultValue: value.default,
    value: value.value,
    options: value.options,
    type,
    rawType: value.type,
  };
}

function normalizeTheme(value: unknown): CssLoaderTheme | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.id !== "string"
    || typeof value.name !== "string"
    || !value.name.trim()
    || typeof value.display_name !== "string"
    || typeof value.version !== "string"
    || typeof value.author !== "string"
    || typeof value.enabled !== "boolean"
    || !Array.isArray(value.patches)
  ) {
    return null;
  }
  const patches = value.patches.map(normalizePatch);
  if (!patches.every((patch): patch is CssLoaderPatch => patch !== null)) return null;
  const patchNames = new Set(patches.map((patch) => patch.name));
  if (patchNames.size !== patches.length) return null;
  return {
    id: value.id,
    name: value.name,
    displayName: value.display_name,
    version: value.version,
    author: value.author,
    enabled: value.enabled,
    patches,
  };
}

function errorInfo(error: unknown): CssLoaderErrorInfo {
  if (error instanceof CssLoaderOperationError) {
    return { code: error.code, message: error.message };
  }
  return {
    code: "transport",
    message: error instanceof Error ? error.message : "CSS Loader transport failed",
  };
}

export class CssLoaderAdapter {
  private readonly timeoutMs: number;
  private readonly reloadTimeoutMs: number;
  private uncertainMutation: Promise<void> | null = null;

  constructor(
    private readonly host: CssLoaderHost,
    options: CssLoaderAdapterOptions = {},
  ) {
    this.timeoutMs = options.timeoutMs ?? 5_000;
    this.reloadTimeoutMs = options.reloadTimeoutMs ?? 15_000;
  }

  private async callWithTimeout(
    timeoutMs: number,
    method: string,
    ...args: unknown[]
  ): Promise<unknown> {
    return this.awaitWithTimeout(timeoutMs, method, this.host.call(method, ...args));
  }

  private async awaitWithTimeout(
    timeoutMs: number,
    method: string,
    operation: Promise<unknown>,
  ): Promise<unknown> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new CssLoaderOperationError(
        "timeout",
        `CSS Loader ${method} timed out`,
      )), timeoutMs);
    });
    try {
      return await Promise.race([operation, timeout]);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }

  private call(method: string, ...args: unknown[]): Promise<unknown> {
    return this.callWithTimeout(this.timeoutMs, method, ...args);
  }

  private async callMutationWithTimeout(
    timeoutMs: number,
    method: string,
    ...args: unknown[]
  ): Promise<unknown> {
    if (this.uncertainMutation) {
      throw new CssLoaderOperationError(
        "timeout",
        "CSS Loader still has a timed-out mutation pending",
      );
    }
    let settled = false;
    const operation = Promise.resolve().then(() => this.host.call(method, ...args));
    void operation.then(
      () => { settled = true; },
      () => { settled = true; },
    );
    try {
      return await this.awaitWithTimeout(timeoutMs, method, operation);
    } catch (error) {
      if (error instanceof CssLoaderOperationError && error.code === "timeout" && !settled) {
        const pending = operation.then(() => undefined, () => undefined);
        this.uncertainMutation = pending;
        void pending.then(() => {
          if (this.uncertainMutation === pending) this.uncertainMutation = null;
        });
      }
      throw error;
    }
  }

  hasPendingMutation(): boolean {
    return this.uncertainMutation !== null;
  }

  async waitForPendingMutation(): Promise<void> {
    const pending = this.uncertainMutation;
    if (pending) await pending;
  }

  async inspect(): Promise<CssLoaderSnapshot> {
    try {
      const plugin = this.host.inventory().find((entry) => entry.name === CSS_LOADER_PLUGIN_NAME);
      if (!plugin) return { status: "missing", themes: [] };
      if (plugin.disabled) return { status: "disabled", themes: [] };

      const rawThemes = await this.call("get_themes");
      if (!Array.isArray(rawThemes)) {
        throw new CssLoaderOperationError(
          "malformed_response",
          "CSS Loader returned an invalid theme list",
        );
      }
      const byName = new Map<string, CssLoaderTheme>();
      const ambiguous = new Set<string>();
      for (const theme of rawThemes.map(normalizeTheme)) {
        if (!theme || ambiguous.has(theme.name)) continue;
        if (byName.delete(theme.name)) ambiguous.add(theme.name);
        else byName.set(theme.name, theme);
      }
      return { status: "ready", themes: [...byName.values()] };
    } catch (error) {
      return {
        status: "error",
        themes: [],
        error: errorInfo(error),
      };
    }
  }

  async requireReady(): Promise<CssLoaderReadySnapshot> {
    const snapshot = await this.inspect();
    if (snapshot.status !== "ready") {
      throw new CssLoaderOperationError(
        snapshot.error?.code ?? "verification_failed",
        snapshot.error?.message ?? `CSS Loader is ${snapshot.status}`,
      );
    }
    return snapshot as CssLoaderReadySnapshot;
  }

  private async callMutation(
    method: string,
    args: readonly unknown[],
    timeoutMs = this.timeoutMs,
  ): Promise<void> {
    const result = await this.callMutationWithTimeout(timeoutMs, method, ...args);
    if (!isRecord(result) || typeof result.success !== "boolean" || typeof result.message !== "string") {
      throw new CssLoaderOperationError(
        "malformed_response",
        `CSS Loader returned an invalid result for ${method}`,
      );
    }
    if (!result.success) {
      throw new CssLoaderOperationError(
        "mutation_failed",
        result.message || `CSS Loader rejected ${method}`,
      );
    }
  }

  // `fails` also lists third-party folders that were already broken on disk.
  private async resetThemes(protectedThemeNames: ReadonlySet<string>): Promise<ReadonlySet<string>> {
    const result = await this.callMutationWithTimeout(this.reloadTimeoutMs, "reset");
    if (
      !isRecord(result)
      || !Array.isArray(result.fails)
      || result.fails.some((failure) => (
        !Array.isArray(failure)
        || failure.length !== 2
        || failure.some((value) => typeof value !== "string")
      ))
    ) {
      throw new CssLoaderOperationError(
        "malformed_response",
        "CSS Loader returned an invalid result for reset",
      );
    }
    const fails = result.fails as [string, string][];
    const protectedFailure = fails.find(([themeName]) => protectedThemeNames.has(themeName));
    if (protectedFailure) {
      const [themeName, reason] = protectedFailure;
      throw new CssLoaderOperationError(
        "mutation_failed",
        `CSS Loader could not reload ${themeName}: ${reason}`,
      );
    }
    return new Set(fails.map(([themeName]) => themeName));
  }

  async setThemeState(themeName: string, enabled: boolean): Promise<CssLoaderSnapshot> {
    const before = await this.requireReady();
    if (!before.themes.some((theme) => theme.name === themeName)) {
      throw new CssLoaderOperationError("mutation_failed", `CSS Loader theme not found: ${themeName}`);
    }

    await this.callMutation("set_theme_state", [themeName, enabled, false, false]);
    const after = await this.requireReady();
    const updated = after.themes.find((theme) => theme.name === themeName);
    if (!updated || updated.enabled !== enabled) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not confirm ${themeName} as ${enabled ? "enabled" : "disabled"}`,
      );
    }
    return after;
  }

  async deleteTheme(themeName: string): Promise<CssLoaderReadySnapshot> {
    const before = await this.requireReady();
    if (!before.themes.some((theme) => theme.name === themeName)) {
      throw new CssLoaderOperationError("mutation_failed", `CSS Loader theme not found: ${themeName}`);
    }

    await this.callMutation("delete_theme", [themeName], this.reloadTimeoutMs);
    const after = await this.requireReady();
    if (after.themes.some((theme) => theme.name === themeName)) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not confirm the removal of ${themeName}`,
      );
    }
    this.verifyInventoryState(before, after, themeName);
    return after;
  }

  async reloadTheme(
    expectedThemeName: string,
    expectedVersion: string,
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot> {
    const brokenOnDisk = await this.resetThemes(new Set([expectedThemeName]));
    let after = await this.requireReady();
    let updated = after.themes.find((theme) => theme.name === expectedThemeName);
    if (!updated || updated.version !== expectedVersion) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not register ${expectedThemeName} v${expectedVersion}`,
      );
    }
    after = await this.restoreCompatibleSnapshotState(before, after, new Set([expectedThemeName]));
    updated = after.themes.find((theme) => theme.name === expectedThemeName);
    if (!updated || updated.version !== expectedVersion) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not preserve ${expectedThemeName} v${expectedVersion}`,
      );
    }
    this.verifyInventoryState(before, after, [expectedThemeName, ...brokenOnDisk]);
    const previous = before.themes.find((theme) => theme.name === expectedThemeName);
    if (previous) this.verifyCompatibleTargetState(previous, updated);
    return after;
  }

  async restoreThemeSnapshot(
    expected: CssLoaderReadySnapshot,
    restoredThemeNames: readonly string[] = [],
  ): Promise<CssLoaderReadySnapshot> {
    const brokenOnDisk = await this.resetThemes(new Set(restoredThemeNames));
    const current = await this.requireReady();
    const after = await this.restoreCompatibleSnapshotState(expected, current);
    this.verifyInventoryState(expected, after, [...brokenOnDisk]);
    return after;
  }

  async reconcileRecoveredThemes(
    recoveries: readonly CssLoaderRecoveryExpectation[],
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot> {
    const recoveredNames = new Set(recoveries.map((recovery) => recovery.themeName));
    const brokenOnDisk = await this.resetThemes(recoveredNames);
    const current = await this.requireReady();
    const after = await this.restoreCompatibleSnapshotState(before, current, recoveredNames);
    this.verifyInventoryState(before, after, [...recoveredNames, ...brokenOnDisk]);
    for (const recovery of recoveries) {
      const restored = after.themes.find((theme) => theme.name === recovery.themeName);
      if (
        (recovery.previousVersion === null && restored)
        || (recovery.previousVersion !== null && restored?.version !== recovery.previousVersion)
      ) {
        throw new CssLoaderOperationError(
          "verification_failed",
          `CSS Loader did not reconcile the rollback for ${recovery.themeName}`,
        );
      }
      const previous = before.themes.find((theme) => theme.name === recovery.themeName);
      if (previous && restored) this.verifyCompatibleTargetState(previous, restored);
    }
    return after;
  }

  // Reloads CSS Loader (dropping styles that no listed theme owns), turns off every theme outside
  // `keep`, then confirms the kept themes still match `before`.
  async disableAllExcept(
    before: CssLoaderReadySnapshot,
    keep: ReadonlySet<string>,
  ): Promise<CssLoaderReadySnapshot> {
    await this.resetThemes(keep);
    const current = await this.requireReady();
    for (const theme of current.themes) {
      if (theme.enabled && !keep.has(theme.name)) {
        await this.callMutation("set_theme_state", [theme.name, false, false, false]);
      }
    }
    const after = await this.reassertKept(before, keep);
    const stray = after.themes.find((theme) => theme.enabled && !keep.has(theme.name));
    if (stray) {
      throw new CssLoaderOperationError("verification_failed", "CSS Loader kept another theme enabled");
    }
    return after;
  }

  async enableAgain(
    before: CssLoaderReadySnapshot,
    keep: ReadonlySet<string>,
    names: readonly string[],
  ): Promise<CssLoaderReadySnapshot> {
    await this.resetThemes(keep);
    const current = await this.requireReady();
    const present = names.filter((name) => !keep.has(name) && current.themes.some((theme) => theme.name === name));
    for (const name of present) {
      if (!current.themes.find((theme) => theme.name === name)?.enabled) {
        await this.callMutation("set_theme_state", [name, true, false, false]);
      }
    }
    const after = await this.reassertKept(before, keep);
    const missing = present.find((name) => !after.themes.find((theme) => theme.name === name)?.enabled);
    if (missing) {
      throw new CssLoaderOperationError("verification_failed", "CSS Loader did not enable a restored theme");
    }
    return after;
  }

  private async reassertKept(
    before: CssLoaderReadySnapshot,
    keep: ReadonlySet<string>,
  ): Promise<CssLoaderReadySnapshot> {
    const kept = (snapshot: CssLoaderReadySnapshot): CssLoaderReadySnapshot => ({
      ...snapshot,
      themes: snapshot.themes.filter((theme) => keep.has(theme.name)),
    });
    const after = await this.restoreCompatibleSnapshotState(kept(before), await this.requireReady());
    this.verifyInventoryState(kept(before), kept(after));
    return after;
  }

  private async restoreCompatibleSnapshotState(
    expected: CssLoaderReadySnapshot,
    current: CssLoaderReadySnapshot,
    allowedVersionChanges: ReadonlySet<string> = new Set(),
  ): Promise<CssLoaderReadySnapshot> {
    for (const expectedTheme of expected.themes) {
      const currentTheme = current.themes.find((theme) => theme.name === expectedTheme.name);
      if (!currentTheme) continue;
      const restorePatches = currentTheme.version === expectedTheme.version
        || allowedVersionChanges.has(expectedTheme.name);
      for (const expectedPatch of restorePatches ? expectedTheme.patches : []) {
        const currentPatch = currentTheme.patches.find((patch) => patch.name === expectedPatch.name);
        if (
          currentPatch
          && currentPatch.options.includes(expectedPatch.value)
          && currentPatch.value !== expectedPatch.value
        ) {
          await this.callMutation("set_patch_of_theme", [
            expectedTheme.name,
            expectedPatch.name,
            expectedPatch.value,
          ]);
        }
      }
      if (currentTheme.enabled !== expectedTheme.enabled) {
        await this.callMutation("set_theme_state", [
          expectedTheme.name,
          expectedTheme.enabled,
          false,
          false,
        ]);
      }
    }
    return this.requireReady();
  }

  private verifyInventoryState(
    before: CssLoaderReadySnapshot,
    after: CssLoaderReadySnapshot,
    excludedThemeNames: string | readonly string[] = [],
  ): void {
    const excluded = new Set(
      typeof excludedThemeNames === "string" ? [excludedThemeNames] : excludedThemeNames,
    );
    const versions = (themes: readonly CssLoaderTheme[]) => new Map(themes.map((theme) => [theme.name, theme.version]));
    const beforeVersions = versions(before.themes);
    const afterVersions = versions(after.themes);
    const relevant = (themes: readonly CssLoaderTheme[]) => themes
      .filter((theme) => !excluded.has(theme.name))
      .map((theme) => {
        const sameVersion = beforeVersions.get(theme.name) === afterVersions.get(theme.name);
        return {
          name: theme.name,
          enabled: theme.enabled,
          patches: sameVersion
            ? theme.patches.map((patch) => ({ name: patch.name, value: patch.value }))
            : null,
        };
      })
      .sort((left, right) => left.name.localeCompare(right.name));
    if (JSON.stringify(relevant(before.themes)) !== JSON.stringify(relevant(after.themes))) {
      throw new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader changed another theme during reload",
      );
    }
  }

  private verifyCompatibleTargetState(previous: CssLoaderTheme, updated: CssLoaderTheme): void {
    if (previous.enabled !== updated.enabled) {
      throw new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader did not preserve the theme activation state",
      );
    }
    for (const previousPatch of previous.patches) {
      const updatedPatch = updated.patches.find((patch) => patch.name === previousPatch.name);
      if (
        updatedPatch
        && updatedPatch.options.includes(previousPatch.value)
        && updatedPatch.value !== previousPatch.value
      ) {
        throw new CssLoaderOperationError(
          "verification_failed",
          `CSS Loader did not preserve ${previousPatch.name}`,
        );
      }
    }
  }

  async setPatchValue(themeName: string, patchName: string, value: string): Promise<CssLoaderSnapshot> {
    const before = await this.requireReady();
    const theme = before.themes.find((candidate) => candidate.name === themeName);
    const patch = theme?.patches.find((candidate) => candidate.name === patchName);
    if (!theme) {
      throw new CssLoaderOperationError("mutation_failed", `CSS Loader theme not found: ${themeName}`);
    }
    if (!patch || patch.type === "none" || patch.type === "unsupported") {
      throw new CssLoaderOperationError("mutation_failed", `CSS Loader patch is not editable: ${patchName}`);
    }
    if (!patch.options.includes(value)) {
      throw new CssLoaderOperationError(
        "mutation_failed",
        `CSS Loader did not advertise value ${value} for ${patchName}`,
      );
    }

    await this.callMutation("set_patch_of_theme", [themeName, patchName, value]);
    const after = await this.requireReady();
    const updated = after.themes
      .find((candidate) => candidate.name === themeName)
      ?.patches.find((candidate) => candidate.name === patchName);
    if (!updated || updated.value !== value) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not confirm ${patchName} as ${value}`,
      );
    }
    return after;
  }
}

export type { CssLoaderSnapshot, CssLoaderTheme, CssLoaderPatch } from "./cssLoaderTypes";
