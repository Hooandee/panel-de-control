import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import {
  parseThemePublication,
  type ThemePublicationState,
} from "./remotePublication";

export interface ThemePublicationClient {
  check(snapshot: CssLoaderReadySnapshot, force: boolean): Promise<ThemePublicationState>;
}

export type ThemePublicationCheckHost = (
  force: boolean,
  cssLoaderVersion: string,
  cssLoaderBackend: number,
) => Promise<unknown>;

let configuredCheck: ThemePublicationCheckHost | undefined;
let configuredLease: symbol | null = null;
const STABLE_VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;

export function configureThemePublicationCheckHost(
  check: ThemePublicationCheckHost,
): () => void {
  const lease = Symbol("theme-publication-check-host");
  configuredCheck = check;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredCheck = undefined;
    configuredLease = null;
  };
}

export function createRemotePublicationClient(
  check?: ThemePublicationCheckHost,
): ThemePublicationClient {
  return {
    async check(snapshot, force) {
      const backendVersion = snapshot.backendVersion;
      if (
        typeof snapshot.pluginVersion !== "string"
        || !STABLE_VERSION.test(snapshot.pluginVersion)
        || typeof backendVersion !== "number"
        || !Number.isSafeInteger(backendVersion)
        || backendVersion <= 0
      ) {
        return {
          status: "recoverable-failure",
          code: "invalid_descriptor",
          retryable: false,
        };
      }
      try {
        const selectedCheck = check ?? configuredCheck;
        if (!selectedCheck) throw new Error("Theme publication backend is unavailable");
        return parseThemePublication(await selectedCheck(
          force,
          snapshot.pluginVersion,
          backendVersion,
        ));
      } catch {
        return {
          status: "recoverable-failure",
          code: "invalid_descriptor",
          retryable: true,
        };
      }
    },
  };
}
