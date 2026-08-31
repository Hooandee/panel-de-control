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
  version?: string;
  disabled: boolean;
}

export interface CssLoaderHost {
  inventory(): readonly CssLoaderPluginInventoryEntry[];
  call(method: string, ...args: unknown[]): Promise<unknown>;
}

export interface CssLoaderAdapterOptions {
  minimumBackendVersion?: number;
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
  private readonly minimumBackendVersion: number;
  private readonly timeoutMs: number;
  private readonly reloadTimeoutMs: number;

  constructor(
    private readonly host: CssLoaderHost,
    options: CssLoaderAdapterOptions = {},
  ) {
    this.minimumBackendVersion = options.minimumBackendVersion ?? 9;
    this.timeoutMs = options.timeoutMs ?? 5_000;
    this.reloadTimeoutMs = options.reloadTimeoutMs ?? 15_000;
  }

  private async callWithTimeout(
    timeoutMs: number,
    method: string,
    ...args: unknown[]
  ): Promise<unknown> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new CssLoaderOperationError(
        "timeout",
        `CSS Loader ${method} timed out`,
      )), timeoutMs);
    });
    try {
      return await Promise.race([this.host.call(method, ...args), timeout]);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }

  private call(method: string, ...args: unknown[]): Promise<unknown> {
    return this.callWithTimeout(this.timeoutMs, method, ...args);
  }

  async inspect(): Promise<CssLoaderSnapshot> {
    let plugin: CssLoaderPluginInventoryEntry | undefined;
    let detectedBackendVersion: number | undefined;
    try {
      plugin = this.host.inventory().find((entry) => entry.name === CSS_LOADER_PLUGIN_NAME);
      if (!plugin) return { status: "missing", themes: [] };
      if (plugin.disabled) {
        return { status: "disabled", pluginVersion: plugin.version, themes: [] };
      }

      const backendVersion = await this.call("get_backend_version");
      if (!Number.isInteger(backendVersion) || (backendVersion as number) < 0) {
        throw new CssLoaderOperationError(
          "malformed_response",
          "CSS Loader returned an invalid backend version",
        );
      }
      detectedBackendVersion = backendVersion as number;
      if ((backendVersion as number) < this.minimumBackendVersion) {
        return {
          status: "incompatible",
          pluginVersion: plugin.version,
          backendVersion: backendVersion as number,
          requiredBackendVersion: this.minimumBackendVersion,
          themes: [],
        };
      }

      const rawThemes = await this.call("get_themes");
      if (!Array.isArray(rawThemes)) {
        throw new CssLoaderOperationError(
          "malformed_response",
          "CSS Loader returned an invalid theme list",
        );
      }
      const themes: CssLoaderTheme[] = [];
      const themeNames = new Set<string>();
      rawThemes.forEach((rawTheme, index) => {
        const theme = normalizeTheme(rawTheme);
        if (!theme || themeNames.has(theme.name)) {
          throw new CssLoaderOperationError(
            "malformed_response",
            `CSS Loader returned an invalid theme at index ${index}`,
          );
        }
        themeNames.add(theme.name);
        themes.push(theme);
      });
      return {
        status: "ready",
        pluginVersion: plugin.version,
        backendVersion: backendVersion as number,
        themes,
      };
    } catch (error) {
      return {
        status: "error",
        pluginVersion: plugin?.version,
        backendVersion: detectedBackendVersion,
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
    const result = await this.callWithTimeout(timeoutMs, method, ...args);
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

  private async resetThemes(): Promise<void> {
    const result = await this.callWithTimeout(this.reloadTimeoutMs, "reset");
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
    if (result.fails.length > 0) {
      const [themeName, reason] = result.fails[0] as [string, string];
      throw new CssLoaderOperationError(
        "mutation_failed",
        `CSS Loader could not reload ${themeName}: ${reason}`,
      );
    }
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

  async reloadTheme(
    expectedThemeName: string,
    expectedVersion: string,
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot> {
    await this.resetThemes();
    const after = await this.requireReady();
    const updated = after.themes.find((theme) => theme.name === expectedThemeName);
    if (!updated || updated.version !== expectedVersion) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not register ${expectedThemeName} v${expectedVersion}`,
      );
    }
    this.verifyInventoryState(before, after, expectedThemeName);
    const previous = before.themes.find((theme) => theme.name === expectedThemeName);
    if (previous) this.verifyCompatibleTargetState(previous, updated);
    return after;
  }

  async restoreThemeSnapshot(expected: CssLoaderReadySnapshot): Promise<CssLoaderReadySnapshot> {
    await this.resetThemes();
    const after = await this.requireReady();
    this.verifyInventoryState(expected, after);
    return after;
  }

  async reconcileRecoveredThemes(
    recoveries: readonly CssLoaderRecoveryExpectation[],
    before: CssLoaderReadySnapshot,
  ): Promise<CssLoaderReadySnapshot> {
    await this.resetThemes();
    const after = await this.requireReady();
    this.verifyInventoryState(before, after, recoveries.map((recovery) => recovery.themeName));
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

  private verifyInventoryState(
    before: CssLoaderReadySnapshot,
    after: CssLoaderReadySnapshot,
    excludedThemeNames: string | readonly string[] = [],
  ): void {
    const excluded = new Set(
      typeof excludedThemeNames === "string" ? [excludedThemeNames] : excludedThemeNames,
    );
    const relevant = (themes: readonly CssLoaderTheme[]) => themes
      .filter((theme) => !excluded.has(theme.name))
      .map((theme) => ({
        name: theme.name,
        version: theme.version,
        enabled: theme.enabled,
        patches: theme.patches.map((patch) => ({ name: patch.name, value: patch.value })),
      }))
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
