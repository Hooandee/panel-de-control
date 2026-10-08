import { parseThemeHealth, type ThemeHealthBackend } from "./themeHealth";
import type { ThemeCleanupHost } from "./themesClient";

export interface ThemeHealthRpcHost {
  health(): Promise<unknown>;
  setAside(disabled: string[]): Promise<unknown>;
  restore(): Promise<unknown>;
}

export class ThemeCleanupError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
    this.name = "ThemeCleanupError";
  }
}

let configuredHost: ThemeHealthRpcHost | undefined;
let configuredLease: symbol | null = null;

export function configureThemeHealthHost(host: ThemeHealthRpcHost): () => void {
  const lease = Symbol("theme-health-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

function requireHost(host?: ThemeHealthRpcHost): ThemeHealthRpcHost {
  const selected = host ?? (configuredLease ? configuredHost : undefined);
  if (!selected) throw new ThemeCleanupError("backend_unavailable", "Theme health backend is unavailable");
  return selected;
}

function answered(value: unknown): Record<string, unknown> {
  const result = typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
  if (!result || result.ok !== true) {
    const code = typeof result?.code === "string" ? result.code : "malformed_response";
    throw new ThemeCleanupError(code, `Theme cleanup was refused (${code})`);
  }
  return result;
}

export async function readThemeHealth(host?: ThemeHealthRpcHost): Promise<ThemeHealthBackend> {
  return parseThemeHealth(await requireHost(host).health());
}

export function createThemeCleanupHost(host?: ThemeHealthRpcHost): ThemeCleanupHost {
  return {
    async setAside(disabled) {
      answered(await requireHost(host).setAside([...disabled]));
    },
    async restore() {
      const result = answered(await requireHost(host).restore());
      const names = result.reenable;
      return Array.isArray(names) ? names.filter((name): name is string => typeof name === "string") : [];
    },
  };
}
