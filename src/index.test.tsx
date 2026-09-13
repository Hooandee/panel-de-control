// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const configuredThemeInstallHost = vi.hoisted(() => ({
  current: null as null | Record<string, unknown>,
}));
const qamRuntime = vi.hoisted(() => {
  const dispose = vi.fn();
  const refresh = vi.fn();
  return {
    dispose,
    refresh,
    start: vi.fn<() => { dispose(): void; refresh(): void }>(() => ({ dispose, refresh })),
  };
});
const prefs = vi.hoisted(() => ({
  get: vi.fn<() => Promise<Record<string, string>>>(),
  set: vi.fn<(values: Record<string, string | null>) => Promise<boolean>>(),
}));

vi.mock("@decky/api", () => ({ definePlugin: (factory: unknown) => factory }));
vi.mock("./api", () => ({
  getUiPrefs: prefs.get,
  setUiPrefs: prefs.set,
  acknowledgeThemeActivation: vi.fn(),
  acknowledgeThemeInstallRollback: vi.fn(),
  beginThemeActivation: vi.fn(),
  checkThemeReleases: vi.fn(),
  commitThemeInstall: vi.fn(),
  discardThemeExtensionReceipt: vi.fn(),
  getThemeInstallRecoveries: vi.fn(),
  getThemeActivationRecovery: vi.fn(),
  listThemeExtensions: vi.fn(),
  loadThemeExtension: vi.fn(),
  prepareRemoteThemeInstall: vi.fn(),
  rollbackThemeInstall: vi.fn(),
  settleThemeActivation: vi.fn(),
}));
vi.mock("@decky/ui", () => ({
  ErrorBoundary: ({ children }: { children: ReactNode }) => <>{children}</>,
  staticClasses: { Title: "title" },
}));
vi.mock("react-icons/lu", () => ({ LuGauge: () => null }));
vi.mock("./i18n", () => ({
  I18nProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  translate: (key: string) => key,
}));
vi.mock("./components/ControlCenter", () => ({
  ControlCenter: () => <div data-testid="control-center" />,
}));
vi.mock("./components/QamPanelGate", () => ({
  QamPanelGate: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("./qam/pluginRuntime", () => ({ startPluginQamRuntime: qamRuntime.start }));

vi.mock("./tdp/gameWatcher", () => ({ startGameWatcher: () => () => {} }));
vi.mock("./system/ecoAmbient", () => ({ startEcoAmbient: () => () => {} }));
vi.mock("./system/valueToast", () => ({
  refreshValueToast: vi.fn(),
  startValueToast: () => () => {},
}));
vi.mock("./customize/store", () => ({ reloadLayout: vi.fn() }));
vi.mock("./customize/modules", () => ({ hydrateModules: vi.fn() }));
vi.mock("./launch/gameContextMenu", () => ({ installGameContextMenu: () => () => {} }));
vi.mock("./pluginListLocalizer", () => ({ startPluginListLocalizer: () => () => {} }));
vi.mock("./system/uiActivity", () => ({ shutdownUiActivity: vi.fn() }));
vi.mock("./themes/deckyCssLoaderHost", () => ({ configureDeckyCssLoaderHost: () => () => {} }));
vi.mock("./themes/panelThemeInstallHost", () => ({
  configurePanelThemeInstallHost: (host: Record<string, unknown>) => {
    configuredThemeInstallHost.current = host;
    return () => {};
  },
}));
vi.mock("./themes/panelThemeActivationJournal", () => ({
  configurePanelThemeActivationJournalHost: () => () => {},
}));
vi.mock("./themes/remotePublicationClient", () => ({ configureThemePublicationCheckHost: () => () => {} }));
vi.mock("./themes/themeExtensionClient", () => ({ configureThemeExtensionRpcHost: () => () => {} }));
vi.mock("./themes/runtime/start", () => ({ startThemesRuntime: () => () => {} }));
vi.mock("./themes/themesClient", () => ({ createProductionThemesDependencies: () => ({}) }));
vi.mock("./themes/useThemes", () => ({ getThemesClient: () => ({}) }));

import { discardThemeExtensionReceipt } from "./api";

type PluginInstance = { content: ReactNode; onDismount(): void };
const plugins: PluginInstance[] = [];

async function createPlugin(): Promise<PluginInstance> {
  const { default: factory } = await import("./index");
  const plugin = (factory as unknown as () => PluginInstance)();
  plugins.push(plugin);
  return plugin;
}

describe("QAM plugin surfaces", () => {
  beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
    prefs.get.mockReset().mockResolvedValue({});
    prefs.set.mockReset().mockResolvedValue(true);
  });

  afterEach(() => {
    plugins.splice(0).forEach((plugin) => plugin.onDismount());
    cleanup();
    vi.useRealTimers();
    configuredThemeInstallHost.current = null;
    qamRuntime.start.mockClear();
    qamRuntime.dispose.mockClear();
    qamRuntime.refresh.mockClear();
  });

  it("starts one plugin-scope QAM composer after durable preferences hydrate", async () => {
    let finishHydration: (() => void) | undefined;
    prefs.get.mockReturnValueOnce(new Promise<Record<string, string>>((resolve) => {
      finishHydration = () => resolve({});
    }));
    const plugin = await createPlugin();

    expect(qamRuntime.start).not.toHaveBeenCalled();
    finishHydration?.();
    await waitFor(() => expect(qamRuntime.start).toHaveBeenCalledOnce());

    plugin.onDismount();
    expect(qamRuntime.dispose).toHaveBeenCalledOnce();
  });

  it("preserves durable QAM layout when initial hydration fails and autonomously recovers", async () => {
    vi.useFakeTimers();
    const saved = {
      order: ["pdc:section:hud"],
      hiddenNative: ["native:friends"],
      pinnedViews: ["pdc:section:hud"],
      ownedIds: { "pdc:section:hud": 5260356 },
    };
    prefs.get.mockRejectedValueOnce(new Error("backend not ready"))
      .mockResolvedValue({ "pdc:qamLayout": JSON.stringify(saved) });
    const store = await import("./qam/store");
    const { startQamComposerRuntime } = await import("./qam/runtime");
    qamRuntime.start.mockImplementationOnce(() => startQamComposerRuntime({
      getLayout: store.getQamLayout,
      saveLayout: store.saveQamLayout,
      subscribeLayout: store.subscribeQamLayout,
      subscribeCatalog: () => () => {},
      getCatalog: () => [
        { token: "pdc:home", target: { kind: "home" } as const },
        { token: "pdc:section:hud", target: { kind: "section", id: "hud" } as const },
      ].map((entry) => ({ ...entry, labelKey: "test", descriptionKey: "test", accent: "#000", icon: () => null })),
      occupiedIds: () => new Set(),
      cleanupOwned: () => false,
      registerOwned: () => ({ registered: true, restartRequired: false, reason: "registered", dispose() {} }),
      configure: () => ({ configured: true, update: () => true, expectedKeys: () => null, dispose() {} }),
      readRenderedKeys: () => null,
      scheduleReadback: () => () => {},
    }));

    await createPlugin();
    await vi.advanceTimersByTimeAsync(0);
    expect(prefs.set).not.toHaveBeenCalled();
    expect(qamRuntime.start).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(10_000);
    expect(store.getQamLayout()).toEqual(saved);
    expect(qamRuntime.start).toHaveBeenCalledOnce();
    expect(prefs.get).toHaveBeenCalledTimes(2);
    expect(prefs.set).not.toHaveBeenCalled();
  });

  it("bounds hydration retries and starts once after a later consumer heals preferences", async () => {
    vi.useFakeTimers();
    prefs.get.mockRejectedValue(new Error("backend not ready"));
    await createPlugin();
    await vi.advanceTimersByTimeAsync(60_000);
    const attempts = prefs.get.mock.calls.length;
    expect(attempts).toBeGreaterThan(1);
    expect(attempts).toBeLessThanOrEqual(4);
    expect(qamRuntime.start).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(prefs.get).toHaveBeenCalledTimes(attempts);

    prefs.get.mockResolvedValue({});
    const { hydratePrefs } = await import("./system/pdcStorage");
    await hydratePrefs();
    await vi.advanceTimersByTimeAsync(0);
    await hydratePrefs();
    expect(qamRuntime.start).toHaveBeenCalledOnce();
  });

  it("cancels scheduled retries when the plugin dismounts", async () => {
    vi.useFakeTimers();
    prefs.get.mockRejectedValue(new Error("backend not ready"));
    const plugin = await createPlugin();
    await vi.advanceTimersByTimeAsync(0);
    plugin.onDismount();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(prefs.get).toHaveBeenCalledOnce();
    expect(qamRuntime.start).not.toHaveBeenCalled();
  });

  it("ignores hydration completing after dismount", async () => {
    let finish: ((value: Record<string, string>) => void) | undefined;
    prefs.get.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const plugin = await createPlugin();
    plugin.onDismount();
    finish?.({});
    await (await import("./system/pdcStorage")).hydratePrefs();
    expect(qamRuntime.start).not.toHaveBeenCalled();
  });

  it("keeps a functional ControlCenter in the standard Decky entry", async () => {
    const plugin = await createPlugin();

    render(<>{plugin.content}</>);

    expect(screen.getByTestId("control-center")).toBeTruthy();
  });

  it("wires receipt discard to the scoped theme install host", async () => {
    await createPlugin();

    expect(configuredThemeInstallHost.current?.discard).toBe(discardThemeExtensionReceipt);
  });
});
