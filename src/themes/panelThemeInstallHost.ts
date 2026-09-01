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
    operation: "commit" | "rollback" | "acknowledge",
    value: string,
  ): Promise<unknown> => requireConfiguredHost()[operation](value);
  return new PanelThemeInstaller({
    prepareRemote: (themeId, expectedVersion) => requireConfiguredHost().prepareRemote(
      themeId,
      expectedVersion,
    ),
    commit: (transaction) => call("commit", transaction),
    rollback: (transaction) => call("rollback", transaction),
    recoveries: () => requireConfiguredHost().recoveries(),
    acknowledge: (transaction) => call("acknowledge", transaction),
  });
}
