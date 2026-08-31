import {
  PanelThemeInstaller,
  ThemeInstallError,
  type ThemeInstallHost,
} from "./panelThemeInstaller";

let configuredHost: ThemeInstallHost | undefined;
let configuredLease: symbol | null = null;

function requireConfiguredHost(): ThemeInstallHost {
  if (!configuredLease || !configuredHost) {
    throw new ThemeInstallError("backend_unavailable", "Panel theme installer is unavailable");
  }
  return configuredHost;
}

export function configurePanelThemeInstallHost(host: ThemeInstallHost): () => void {
  const lease = Symbol("panel-theme-install-host");
  configuredHost = host;
  configuredLease = lease;
  return () => {
    if (configuredLease !== lease) return;
    configuredHost = undefined;
    configuredLease = null;
  };
}

export function createPanelThemeInstaller(): PanelThemeInstaller {
  const call = (
    operation: "prepare" | "commit" | "rollback" | "acknowledge",
    value: string,
  ): Promise<unknown> => requireConfiguredHost()[operation](value);
  return new PanelThemeInstaller({
    prepare: (themeId) => call("prepare", themeId),
    prepareRemote: (themeId, expectedVersion) => requireConfiguredHost().prepareRemote?.(
      themeId,
      expectedVersion,
    ) ?? Promise.reject(
      new ThemeInstallError("backend_unavailable", "Remote theme installer is unavailable"),
    ),
    commit: (transaction) => call("commit", transaction),
    rollback: (transaction) => call("rollback", transaction),
    recoveries: () => requireConfiguredHost().recoveries(),
    acknowledge: (transaction) => call("acknowledge", transaction),
  });
}
