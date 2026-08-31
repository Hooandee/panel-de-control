import {
  parseThemePublication,
  type ThemePublicationState,
} from "./remotePublication";

export interface ThemePublicationClient {
  check(force: boolean): Promise<ThemePublicationState>;
}

export type ThemePublicationCheckHost = (force: boolean) => Promise<unknown>;

let configuredCheck: ThemePublicationCheckHost | undefined;
let configuredLease: symbol | null = null;

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
    async check(force) {
      try {
        const selectedCheck = check ?? configuredCheck;
        if (!selectedCheck) throw new Error("Theme publication backend is unavailable");
        return parseThemePublication(await selectedCheck(force));
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
