// @vitest-environment happy-dom
import { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const registeredView = vi.hoisted(() => ({ content: null as ReactNode }));
const configuredThemeInstallHost = vi.hoisted(() => ({
  current: null as null | Record<string, unknown>,
}));

vi.mock("@decky/api", () => ({ definePlugin: (factory: unknown) => factory }));
vi.mock("./api", () => ({
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
vi.mock("./deckyInternal", () => ({
  registerQuickAccessTab: (view: { content: ReactNode }) => {
    registeredView.content = view.content;
    return { registered: true, restartRequired: false, reason: "registered", dispose() {} };
  },
  cleanupOwnedQuickAccessTabs: vi.fn(() => false),
}));
vi.mock("./system/qamShortcut", () => ({
  refreshQamShortcutPreference: vi.fn(),
  startQamShortcut: (register: () => unknown) => {
    register();
    return { ready: Promise.resolve(), dispose() {} };
  },
}));

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
vi.mock("./system/pdcStorage", () => ({ onPrefsHealed: () => () => {} }));
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
import createPlugin from "./index";

describe("QAM plugin surfaces", () => {
  afterEach(() => {
    cleanup();
    registeredView.content = null;
    configuredThemeInstallHost.current = null;
  });

  it("registers a functional ControlCenter in the direct QAM entry", () => {
    (createPlugin as unknown as () => { content: ReactNode })();

    render(<>{registeredView.content}</>);

    expect(screen.getByTestId("control-center")).toBeTruthy();
  });

  it("keeps a functional ControlCenter in the standard Decky entry", () => {
    const plugin = (createPlugin as unknown as () => { content: ReactNode })();

    render(<>{plugin.content}</>);

    expect(screen.getByTestId("control-center")).toBeTruthy();
  });

  it("wires receipt discard to the scoped theme install host", () => {
    (createPlugin as unknown as () => { content: ReactNode })();

    expect(configuredThemeInstallHost.current?.discard).toBe(discardThemeExtensionReceipt);
  });
});
