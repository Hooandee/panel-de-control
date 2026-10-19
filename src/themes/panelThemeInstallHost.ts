import {
  PanelThemeInstaller,
  ThemeInstallError,
  type ThemeInstallHost,
} from "./panelThemeInstaller";

let configuredHost: ThemeInstallHost | undefined;
let configuredLease: symbol | null = null;
const packageChangeListeners = new Set<() => void>();

export function onThemePackagesChanged(listener: () => void): () => void {
  packageChangeListeners.add(listener);
  return () => {
    packageChangeListeners.delete(listener);
  };
}

function notifyPackagesChanged(): void {
  for (const listener of [...packageChangeListeners]) listener();
}

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
    operation: "commit" | "discard" | "rollback" | "acknowledge",
    value: string,
  ): Promise<unknown> => {
    const result = requireConfiguredHost()[operation](value);
    if (operation === "commit" || operation === "rollback") {
      void result.then(notifyPackagesChanged, notifyPackagesChanged);
    }
    return result;
  };
  return new PanelThemeInstaller({
    prepareRemote: (themeId, expectedVersion) => requireConfiguredHost().prepareRemote(
      themeId,
      expectedVersion,
    ),
    prepareEarly: (archivePath) => requireConfiguredHost().prepareEarly(archivePath),
    commit: (transaction) => call("commit", transaction),
    discard: (catalogId) => call("discard", catalogId),
    rollback: (transaction) => call("rollback", transaction),
    recoveries: () => requireConfiguredHost().recoveries(),
    acknowledge: (transaction) => call("acknowledge", transaction),
  });
}
