import {
  parseEarlyPublication,
  parseThemePublication,
  type ThemePublicationState,
} from "./remotePublication";

export interface ThemePublicationClient {
  check(force: boolean): Promise<ThemePublicationState>;
}

export type ThemePublicationCheckHost = (force: boolean) => Promise<unknown>;

let configuredCheck: ThemePublicationCheckHost | undefined;
let configuredLease: symbol | null = null;
let configuredEarlyCheck: ThemePublicationCheckHost | undefined;

export function configureThemeEarlyCheckHost(check: ThemePublicationCheckHost): () => void {
  configuredEarlyCheck = check;
  return () => {
    if (configuredEarlyCheck === check) configuredEarlyCheck = undefined;
  };
}

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
  earlyCheck?: ThemePublicationCheckHost,
): ThemePublicationClient {
  return {
    async check(force) {
      try {
        const selectedCheck = check ?? configuredCheck;
        if (!selectedCheck) throw new Error("Theme publication backend is unavailable");
        const selectedEarly = earlyCheck ?? configuredEarlyCheck;
        const [raw, rawEarly] = await Promise.all([
          selectedCheck(force),
          selectedEarly ? selectedEarly(force).catch(() => null) : Promise.resolve(null),
        ]);
        const publication = parseThemePublication(raw);
        if (publication.status !== "published" && publication.status !== "cached") return publication;
        const early = parseEarlyPublication(rawEarly);
        return early.length ? { ...publication, early } : publication;
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
