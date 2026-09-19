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
  loadThemeExtension,
  prepareRemoteThemeInstall,
  rollbackThemeInstall,
  settleThemeActivation,
} from "./api";
import { I18nProvider, translate } from "./i18n";
import { ControlCenter } from "./components/ControlCenter";
import { startGameWatcher } from "./tdp/gameWatcher";
import { startEcoAmbient } from "./system/ecoAmbient";
import { startValueToast, refreshValueToast } from "./system/valueToast";
import { hydratePrefs, onPrefsHealed, prefsHydrated } from "./system/pdcStorage";
import { reloadLayout } from "./customize/store";
import { hydrateModules } from "./customize/modules";
import { installGameContextMenu } from "./launch/gameContextMenu";
import { startPluginListLocalizer } from "./pluginListLocalizer";
import {
  shutdownUiActivity,
  startSteamOverlayActivity,
} from "./system/uiActivity";
import { StandardDeckyContent } from "./components/StandardDeckyContent";
import { configureDeckyCssLoaderHost } from "./themes/deckyCssLoaderHost";
import { configurePanelThemeInstallHost } from "./themes/panelThemeInstallHost";
import { configurePanelThemeActivationJournalHost } from "./themes/panelThemeActivationJournal";
import { startThemesRuntime } from "./themes/runtime/start";
import { createProductionThemesDependencies } from "./themes/themesClient";
import { configureThemePublicationCheckHost } from "./themes/remotePublicationClient";
import { getThemesClient } from "./themes/useThemes";
import { configureThemeExtensionRpcHost } from "./themes/themeExtensionClient";
import { startPluginQamRuntime } from "./qam/pluginRuntime";

// Localized header title only; the internal plugin name / install folder stays
// "Panel de Control" (renaming it would break existing installs and the updater).
const PluginTitle: FC = () => (
  <div className={staticClasses.Title}>{translate("app.title")}</div>
);

const ControlCenterContent: FC = () => (
  <ErrorBoundary>
    <ControlCenter />
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
  const releaseThemeExtensionHost = configureThemeExtensionRpcHost({
    list: listThemeExtensions,
    load: loadThemeExtension,
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

  const stopGameWatcher = startGameWatcher();
  const stopSteamOverlayActivity = startSteamOverlayActivity();
  const stopEcoAmbient = startEcoAmbient();
  const stopValueToast = startValueToast();
  const stopContextMenu = installGameContextMenu();
  const stopListLocalizer = startPluginListLocalizer();
  const standardLifecycle = new AbortController();
  const stopThemesRuntime = startThemesRuntime({
    client: themesClient,
    getSteamDocument: () => findSP()?.document ?? null,
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
      stopSteamOverlayActivity();
      shutdownUiActivity();
      stopGameWatcher();
      stopEcoAmbient();
      stopValueToast();
      stopContextMenu();
      stopListLocalizer();
      stopThemesRuntime();
      releaseThemeInstallHost();
      releaseThemeActivationJournalHost();
      releaseThemePublicationHost();
      releaseThemeExtensionHost();
      releaseCssLoaderHost();
    },
  };
});
