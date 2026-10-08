import { ErrorBoundary, findSP, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FC } from "react";
import { LuSlidersVertical } from "react-icons/lu";

import {
  acknowledgeThemeActivation,
  acknowledgeThemeInstallRollback,
  beginThemeActivation,
  checkThemeReleases,
  commitThemeInstall,
  discardThemeExtensionReceipt,
  getThemeInstallRecoveries,
  getThemeActivationRecovery,
  listThemeExtensions,
  getThemeHealth,
  setAsideThemeLeftovers,
  restoreThemeCleanup,
  loadThemeExtension,
  prepareRemoteThemeInstall,
  recordThemeFailure,
  recordUiEvent,
  rollbackThemeInstall,
  settleThemeActivation,
} from "./api";
import { I18nProvider, translate } from "./i18n";
import { ControlCenter } from "./components/ControlCenter";
import { ReportingBoundary } from "./components/ReportingBoundary";
import { startFrontendErrorReporting } from "./system/uiDiagnostics";
import { setUiEventSink } from "./system/uiEvents";
import { startGameWatcher } from "./tdp/gameWatcher";
import { startEcoAmbient } from "./system/ecoAmbient";
import { startValueToast, refreshValueToast } from "./system/valueToast";
import { hydratePrefs, onPrefsHealed, prefsHydrated, readString, writeString } from "./system/pdcStorage";
import { reloadLayout } from "./customize/store";
import { hydrateModules } from "./customize/modules";
import { installGameContextMenu } from "./launch/gameContextMenu";
import { startPluginListLocalizer } from "./pluginListLocalizer";
import { startKioskSteamBridgeWhenSupported } from "./kiosk/steamBridge";
import {
  shutdownUiActivity,
  startQamDocumentActivity,
  startSteamOverlayActivity,
} from "./system/uiActivity";
import { StandardDeckyContent } from "./components/StandardDeckyContent";
import { configureDeckyCssLoaderHost } from "./themes/deckyCssLoaderHost";
import { configurePanelThemeInstallHost } from "./themes/panelThemeInstallHost";
import { configurePanelThemeActivationJournalHost } from "./themes/panelThemeActivationJournal";
import { startThemesRuntime } from "./themes/runtime/start";
import { parseSectionHandoffs } from "./themes/sectionOwnership";
import {
  configureSectionHandoffStore,
  configureThemeFailureReporter,
  createProductionThemesDependencies,
} from "./themes/themesClient";
import { configureThemePublicationCheckHost } from "./themes/remotePublicationClient";
import { configureThemeHealthHost } from "./themes/themeCleanupHost";
import { getThemesClient } from "./themes/useThemes";
import { configureThemeExtensionRpcHost } from "./themes/themeExtensionClient";
import { startPluginQamRuntime } from "./qam/pluginRuntime";
import { getQamDocument, onQamDocument } from "./qamDocument";

// Localized header title only; the internal plugin name / install folder stays
// "Panel de Control" (renaming it would break existing installs and the updater).
const PluginTitle: FC = () => (
  <div className={staticClasses.Title}>{translate("app.title")}</div>
);

const ControlCenterContent: FC = () => (
  <ErrorBoundary>
    <ReportingBoundary where="control-center">
      <ControlCenter />
    </ReportingBoundary>
  </ErrorBoundary>
);

const StandardPluginContent: FC<{
  lifecycle: AbortSignal;
}> = ({ lifecycle }) => (
  <I18nProvider>
    <StandardDeckyContent lifecycle={lifecycle}>
      <ControlCenterContent />
    </StandardDeckyContent>
  </I18nProvider>
);

export default definePlugin(() => {
  const deckyHost = window;
  const releaseCssLoaderHost = configureDeckyCssLoaderHost(deckyHost);
  const releaseThemeInstallHost = configurePanelThemeInstallHost({
    prepareRemote: prepareRemoteThemeInstall,
    commit: commitThemeInstall,
    discard: discardThemeExtensionReceipt,
    rollback: rollbackThemeInstall,
    recoveries: getThemeInstallRecoveries,
    acknowledge: acknowledgeThemeInstallRollback,
  });
  const releaseThemeActivationJournalHost = configurePanelThemeActivationJournalHost({
    begin: beginThemeActivation,
    pending: getThemeActivationRecovery,
    settle: settleThemeActivation,
    acknowledge: acknowledgeThemeActivation,
  });
  const releaseThemePublicationHost = configureThemePublicationCheckHost(checkThemeReleases);
  const releaseThemeHealthHost = configureThemeHealthHost({
    health: getThemeHealth,
    setAside: setAsideThemeLeftovers,
    restore: restoreThemeCleanup,
  });
  const releaseThemeExtensionHost = configureThemeExtensionRpcHost({
    list: listThemeExtensions,
    load: loadThemeExtension,
  });
  const releaseThemeFailureReporter = configureThemeFailureReporter(
    ({ operation, code, message }) => recordThemeFailure(operation, code, message),
  );
  const releaseSectionHandoffStore = configureSectionHandoffStore({
    read: () => parseSectionHandoffs(readString("pdc:themeSectionHandoffs")),
    write: (handoffs) => writeString("pdc:themeSectionHandoffs", JSON.stringify(handoffs)),
  });
  const themesClient = getThemesClient(createProductionThemesDependencies());
  let qamRuntime: ReturnType<typeof startPluginQamRuntime> | null = null;
  let dismounted = false;
  let hydrationRetry: number | undefined;
  const hydrationRetryDelays = [500, 1500, 5000];
  const cancelHydrationRetry = () => {
    if (hydrationRetry === undefined) return;
    window.clearTimeout(hydrationRetry);
    hydrationRetry = undefined;
  };
  const startHydratedQam = () => {
    if (dismounted || qamRuntime || !prefsHydrated()) return;
    cancelHydrationRetry();
    qamRuntime = startPluginQamRuntime(deckyHost);
  };
  const hydrateQam = () => {
    void hydratePrefs().then(() => {
      if (dismounted) return;
      startHydratedQam();
      if (qamRuntime) return;
      const delay = hydrationRetryDelays.shift();
      if (delay === undefined) return;
      hydrationRetry = window.setTimeout(() => {
        hydrationRetry = undefined;
        hydrateQam();
      }, delay);
    });
  };
  const stopPrefsHealed = onPrefsHealed(() => {
    refreshValueToast();
    reloadLayout();
    queueMicrotask(() => {
      if (dismounted) return;
      if (qamRuntime) qamRuntime.refresh();
      else startHydratedQam();
    });
  });
  hydrateQam();
  hydrateModules();

  const stopFrontendErrorReporting = startFrontendErrorReporting(window);
  setUiEventSink((area, action, detail, ok) => recordUiEvent(area, action, detail, ok));
  const stopGameWatcher = startGameWatcher();
  const stopSteamOverlayActivity = startSteamOverlayActivity();
  const stopQamDocumentActivity = startQamDocumentActivity();
  const stopEcoAmbient = startEcoAmbient();
  const stopValueToast = startValueToast();
  const stopContextMenu = installGameContextMenu();
  const stopListLocalizer = startPluginListLocalizer();
  const stopKioskSteamBridge = startKioskSteamBridgeWhenSupported();
  const standardLifecycle = new AbortController();
  const stopThemesRuntime = startThemesRuntime({
    client: themesClient,
    getSteamDocument: () => findSP()?.document ?? null,
    getQamDocument,
    subscribeQamDocument: onQamDocument,
  });

  return {
    name: "Panel de Control",
    titleView: <PluginTitle />,
    content: (
      <StandardPluginContent
        lifecycle={standardLifecycle.signal}
      />
    ),
    icon: <LuSlidersVertical />,
    onDismount() {
      dismounted = true;
      cancelHydrationRetry();
      standardLifecycle.abort();
      qamRuntime?.dispose();
      stopPrefsHealed();
      stopQamDocumentActivity();
      stopSteamOverlayActivity();
      shutdownUiActivity();
      stopGameWatcher();
      stopFrontendErrorReporting();
      setUiEventSink(null);
      stopEcoAmbient();
      stopValueToast();
      stopContextMenu();
      stopListLocalizer();
      stopKioskSteamBridge();
      stopThemesRuntime();
      releaseThemeInstallHost();
      releaseThemeActivationJournalHost();
      releaseThemePublicationHost();
      releaseThemeHealthHost();
      releaseThemeExtensionHost();
      releaseThemeFailureReporter();
      releaseSectionHandoffStore();
      releaseCssLoaderHost();
    },
  };
});
