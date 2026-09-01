import { callLegacyPluginBackend, strictPluginInventory } from "../deckyInternal";
import type { CssLoaderHost } from "./cssLoaderAdapter";

const CSS_LOADER_PLUGIN_NAME = "CSS Loader";

let configuredHost: unknown;
let configuredLease: symbol | null = null;

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
    inventory: () => strictPluginInventory(selectedHost),
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
    case "get_backend_version":
    case "get_themes":
    case "reset":
      if (args.length === 0) return {};
      break;
    case "set_theme_state":
      if (args.length === 4) {
        return { name: args[0], state: args[1], set_deps: args[2], set_deps_value: args[3] };
      }
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
