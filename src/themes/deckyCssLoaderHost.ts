import { callLegacyPluginBackend } from "../deckyInternal";
import type { CssLoaderHost, CssLoaderPluginInventoryEntry } from "./cssLoaderAdapter";

const CSS_LOADER_PLUGIN_NAME = "CSS Loader";

let configuredHost: unknown;
let configuredLease: symbol | null = null;

interface DeckyPluginState {
  publicState?(): {
    installedPlugins?: unknown;
    disabledPlugins?: unknown;
  };
}

interface DeckyPluginHost {
  DeckyPluginLoader?: { deckyState?: DeckyPluginState };
}

function isCssLoaderEntry(value: unknown): boolean {
  if (typeof value === "string") return value === CSS_LOADER_PLUGIN_NAME;
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return (value as { name?: unknown }).name === CSS_LOADER_PLUGIN_NAME;
}

function cssLoaderPluginInventory(host: unknown): CssLoaderPluginInventoryEntry[] {
  const state = (host as DeckyPluginHost | null)?.DeckyPluginLoader?.deckyState?.publicState?.();
  const installed = state?.installedPlugins;
  const disabled = state?.disabledPlugins;
  if (!Array.isArray(installed) || !Array.isArray(disabled)) {
    throw new Error("Decky plugin inventory unavailable");
  }
  const installedCssLoader = installed.some(isCssLoaderEntry);
  const disabledCssLoader = disabled.some(isCssLoaderEntry);
  if (!installedCssLoader && !disabledCssLoader) return [];
  return [{ name: CSS_LOADER_PLUGIN_NAME, disabled: disabledCssLoader }];
}

export function configureDeckyCssLoaderHost(host: unknown): () => void {
  const lease = Symbol("decky-css-loader-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

export function createDeckyCssLoaderHost(host?: unknown): CssLoaderHost {
  const selectedHost = host === undefined
    ? configuredLease
      ? configuredHost
      : window
    : host;
  return {
    inventory: () => cssLoaderPluginInventory(selectedHost),
    call: (method, ...args) => callLegacyPluginBackend(
      CSS_LOADER_PLUGIN_NAME,
      method,
      legacyArguments(method, args),
      selectedHost,
    ),
  };
}

function legacyArguments(method: string, args: readonly unknown[]): Readonly<Record<string, unknown>> {
  switch (method) {
    case "get_themes":
    case "reset":
      if (args.length === 0) return {};
      break;
    case "set_theme_state":
      if (args.length === 4) {
        return { name: args[0], state: args[1], set_deps: args[2], set_deps_value: args[3] };
      }
      break;
    case "delete_theme":
      if (args.length === 1) return { themeName: args[0] };
      break;
    case "set_patch_of_theme":
      if (args.length === 3) return { themeName: args[0], patchName: args[1], value: args[2] };
      break;
    case "set_component_of_theme_patch":
      if (args.length === 4) {
        return { themeName: args[0], patchName: args[1], componentName: args[2], value: args[3] };
      }
      break;
  }
  throw new Error(`Unsupported CSS Loader call shape: ${method}`);
}
