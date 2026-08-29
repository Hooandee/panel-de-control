import type {
  CssLoaderErrorCode,
  CssLoaderErrorInfo,
  CssLoaderPatch,
  CssLoaderPatchType,
  CssLoaderSnapshot,
  CssLoaderTheme,
} from "./cssLoaderTypes";
import type { CssLoaderApiInstallSource } from "./types";

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
  installTimeoutMs?: number;
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
    || typeof value.display_name !== "string"
    || typeof value.version !== "string"
    || typeof value.author !== "string"
    || typeof value.enabled !== "boolean"
    || !Array.isArray(value.patches)
  ) {
    return null;
  }
  const patches = value.patches.map(normalizePatch);
  if (patches.some((patch) => patch === null)) return null;
  return {
    id: value.id,
    name: value.name,
    displayName: value.display_name,
    version: value.version,
    author: value.author,
    enabled: value.enabled,
    patches: patches as CssLoaderPatch[],
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
  private readonly installTimeoutMs: number;

  constructor(
    private readonly host: CssLoaderHost,
    options: CssLoaderAdapterOptions = {},
  ) {
    this.minimumBackendVersion = options.minimumBackendVersion ?? 9;
    this.timeoutMs = options.timeoutMs ?? 5_000;
    this.installTimeoutMs = options.installTimeoutMs ?? 30_000;
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
      rawThemes.forEach((rawTheme, index) => {
        const theme = normalizeTheme(rawTheme);
        if (!theme) {
          throw new CssLoaderOperationError(
            "malformed_response",
            `CSS Loader returned an invalid theme at index ${index}`,
          );
        }
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

  private async requireReady(): Promise<CssLoaderSnapshot & { status: "ready" }> {
    const snapshot = await this.inspect();
    if (snapshot.status !== "ready") {
      throw new CssLoaderOperationError(
        snapshot.error?.code ?? "verification_failed",
        snapshot.error?.message ?? `CSS Loader is ${snapshot.status}`,
      );
    }
    return snapshot as CssLoaderSnapshot & { status: "ready" };
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

  async installTheme(
    source: CssLoaderApiInstallSource,
    expectedThemeName: string,
  ): Promise<CssLoaderSnapshot> {
    let url: URL;
    try {
      url = new URL(source.baseUrl);
    } catch {
      throw new CssLoaderOperationError("mutation_failed", "Theme install source is not a valid URL");
    }
    if (
      source.kind !== "css-loader-api"
      || url.protocol !== "https:"
      || !source.themeId.trim()
      || !expectedThemeName.trim()
    ) {
      throw new CssLoaderOperationError("mutation_failed", "Theme install source is not permitted");
    }

    await this.requireReady();
    await this.callMutation(
      "download_theme_from_url",
      [source.themeId, source.baseUrl],
      this.installTimeoutMs,
    );
    const after = await this.requireReady();
    if (!after.themes.some((theme) => theme.name === expectedThemeName)) {
      throw new CssLoaderOperationError(
        "verification_failed",
        `CSS Loader did not register installed theme: ${expectedThemeName}`,
      );
    }
    return after;
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
