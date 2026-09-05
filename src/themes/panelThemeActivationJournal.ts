import type {
  DurableThemeActivationRecovery,
  ThemeActivationJournal,
} from "./activation";
import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderPatch, CssLoaderPatchType, CssLoaderTheme } from "./cssLoaderTypes";

const PATCH_TYPES = new Set<CssLoaderPatchType>([
  "checkbox",
  "dropdown",
  "slider",
  "none",
  "unsupported",
]);

export interface ThemeActivationJournalHost {
  begin(snapshot: CssLoaderReadySnapshot): Promise<unknown>;
  pending(): Promise<unknown>;
  settle(transaction: string): Promise<unknown>;
  acknowledge(transaction: string): Promise<unknown>;
}

export class ThemeActivationJournalError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "ThemeActivationJournalError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  required: readonly string[],
  optional: readonly string[] = [],
): boolean {
  const keys = Object.keys(value);
  return required.every((key) => keys.includes(key))
    && keys.every((key) => required.includes(key) || optional.includes(key));
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function parsePatch(value: unknown): CssLoaderPatch | null {
  if (!isRecord(value) || !hasExactKeys(value, [
    "name", "defaultValue", "value", "options", "type", "rawType",
  ])) return null;
  if (
    !nonEmptyString(value.name)
    || typeof value.defaultValue !== "string"
    || typeof value.value !== "string"
    || !Array.isArray(value.options)
    || !value.options.every((option) => typeof option === "string")
    || !nonEmptyString(value.type)
    || !PATCH_TYPES.has(value.type as CssLoaderPatchType)
    || !nonEmptyString(value.rawType)
  ) return null;
  return {
    name: value.name,
    defaultValue: value.defaultValue,
    value: value.value,
    options: value.options,
    type: value.type as CssLoaderPatchType,
    rawType: value.rawType,
  };
}

function parseTheme(value: unknown): CssLoaderTheme | null {
  if (!isRecord(value) || !hasExactKeys(value, [
    "id", "name", "displayName", "version", "author", "enabled", "patches",
  ])) return null;
  if (
    typeof value.id !== "string"
    || !nonEmptyString(value.name)
    || typeof value.displayName !== "string"
    || typeof value.version !== "string"
    || typeof value.author !== "string"
    || typeof value.enabled !== "boolean"
    || !Array.isArray(value.patches)
  ) return null;
  const patches = value.patches.map(parsePatch);
  if (!patches.every((patch): patch is CssLoaderPatch => patch !== null)) return null;
  if (new Set(patches.map((patch) => patch.name)).size !== patches.length) return null;
  return {
    id: value.id,
    name: value.name,
    displayName: value.displayName,
    version: value.version,
    author: value.author,
    enabled: value.enabled,
    patches,
  };
}

function parseReadySnapshot(value: unknown): CssLoaderReadySnapshot | null {
  if (!isRecord(value) || !hasExactKeys(
    value,
    ["status", "backendVersion", "themes"],
    ["pluginVersion"],
  )) return null;
  if (
    value.status !== "ready"
    || !Number.isInteger(value.backendVersion)
    || (value.backendVersion as number) < 9
    || (value.pluginVersion !== undefined && typeof value.pluginVersion !== "string")
    || !Array.isArray(value.themes)
  ) return null;
  const themes = value.themes.map(parseTheme);
  if (!themes.every((theme): theme is CssLoaderTheme => theme !== null)) return null;
  if (new Set(themes.map((theme) => theme.name)).size !== themes.length) return null;
  return {
    status: "ready",
    ...(value.pluginVersion === undefined ? {} : { pluginVersion: value.pluginVersion }),
    backendVersion: value.backendVersion as number,
    themes,
  };
}

function responseCode(value: unknown): string | null {
  return isRecord(value) && nonEmptyString(value.code) ? value.code : null;
}

export class PanelThemeActivationJournal implements ThemeActivationJournal {
  constructor(private readonly host: ThemeActivationJournalHost) {}

  async begin(snapshot: CssLoaderReadySnapshot): Promise<string> {
    const response = await this.host.begin(snapshot);
    if (
      !isRecord(response)
      || response.ok !== true
      || response.code !== "prepared"
      || !nonEmptyString(response.transaction)
    ) {
      throw new ThemeActivationJournalError(
        responseCode(response) ?? "malformed_response",
        "Panel could not create a theme activation recovery point",
      );
    }
    return response.transaction;
  }

  async pending(): Promise<DurableThemeActivationRecovery | null> {
    const response = await this.host.pending();
    if (!isRecord(response) || response.ok !== true || response.code !== "ready") {
      throw new ThemeActivationJournalError(
        responseCode(response) ?? "malformed_response",
        "Panel could not inspect theme activation recovery",
      );
    }
    if (response.recovery === null) return null;
    if (!isRecord(response.recovery) || !hasExactKeys(
      response.recovery,
      ["transaction", "snapshot", "recoverable"],
    )) {
      throw new ThemeActivationJournalError("malformed_response", "Panel returned invalid activation recovery");
    }
    const snapshot = parseReadySnapshot(response.recovery.snapshot);
    if (
      !nonEmptyString(response.recovery.transaction)
      || typeof response.recovery.recoverable !== "boolean"
      || !snapshot
    ) {
      throw new ThemeActivationJournalError("malformed_response", "Panel returned invalid activation recovery");
    }
    if (!response.recovery.recoverable) {
      throw new ThemeActivationJournalError(
        "mutation_unsettled",
        "A previous CSS Loader mutation may still be running",
      );
    }
    return { transaction: response.recovery.transaction, snapshot };
  }

  async settle(transaction: string): Promise<void> {
    await this.finish("settle", transaction, "settled");
  }

  async acknowledge(transaction: string): Promise<void> {
    await this.finish("acknowledge", transaction, "acknowledged");
  }

  private async finish(
    operation: "settle" | "acknowledge",
    transaction: string,
    expectedCode: "settled" | "acknowledged",
  ): Promise<void> {
    if (!nonEmptyString(transaction)) {
      throw new ThemeActivationJournalError("invalid_transaction", "Theme activation transaction is invalid");
    }
    const response = await this.host[operation](transaction);
    if (!isRecord(response) || response.ok !== true || response.code !== expectedCode) {
      throw new ThemeActivationJournalError(
        responseCode(response) ?? "malformed_response",
        `Panel could not ${operation} theme activation recovery`,
      );
    }
  }
}

let configuredHost: ThemeActivationJournalHost | undefined;
let configuredLease: symbol | null = null;

function requireConfiguredHost(): ThemeActivationJournalHost {
  if (!configuredHost || !configuredLease) {
    throw new ThemeActivationJournalError("backend_unavailable", "Panel activation journal is unavailable");
  }
  return configuredHost;
}

export function configurePanelThemeActivationJournalHost(
  host: ThemeActivationJournalHost,
): () => void {
  const lease = Symbol("panel-theme-activation-journal-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

export function createPanelThemeActivationJournal(): PanelThemeActivationJournal {
  return new PanelThemeActivationJournal({
    begin: (snapshot) => requireConfiguredHost().begin(snapshot),
    pending: () => requireConfiguredHost().pending(),
    settle: (transaction) => requireConfiguredHost().settle(transaction),
    acknowledge: (transaction) => requireConfiguredHost().acknowledge(transaction),
  });
}
