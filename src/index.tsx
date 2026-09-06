import { ErrorBoundary, findSP, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FC } from "react";
import { LuGauge } from "react-icons/lu";

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
import { onPrefsHealed } from "./system/pdcStorage";
import { reloadLayout } from "./customize/store";
import { hydrateModules } from "./customize/modules";
import { installGameContextMenu } from "./launch/gameContextMenu";
import { startPluginListLocalizer } from "./pluginListLocalizer";
import {
  cleanupOwnedQuickAccessTabs,
  registerQuickAccessTab,
} from "./deckyInternal";
import {
  refreshQamShortcutPreference,
  startQamShortcut,
} from "./system/qamShortcut";
import { shutdownUiActivity } from "./system/uiActivity";
import { StandardDeckyContent } from "./components/StandardDeckyContent";
import { DirectQamShortcut } from "./components/DirectQamShortcut";
import { configureDeckyCssLoaderHost } from "./themes/deckyCssLoaderHost";
import { configurePanelThemeInstallHost } from "./themes/panelThemeInstallHost";
import { configurePanelThemeActivationJournalHost } from "./themes/panelThemeActivationJournal";
import { startThemesRuntime } from "./themes/runtime/start";
import { createProductionThemesDependencies } from "./themes/themesClient";
import { configureThemePublicationCheckHost } from "./themes/remotePublicationClient";
import { getThemesClient } from "./themes/useThemes";
import { configureThemeExtensionRpcHost } from "./themes/themeExtensionClient";

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

const DirectPluginContent: FC<{
  lifecycle: AbortSignal;
}> = ({ lifecycle }) => (
  <I18nProvider>
    <DirectQamShortcut lifecycle={lifecycle}>
      <ControlCenterContent />
    </DirectQamShortcut>
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
  // Restore durable UI prefs into the localStorage cache at plugin scope (so the
  // QAM-closed toast uses the right language), then re-apply the healed values.
  const stopPrefsHealed = onPrefsHealed(() => {
    refreshValueToast();
    reloadLayout();
    refreshQamShortcutPreference();
  });
  // Reconcile the durable module enable/disable set (authoritative backend copy).
  hydrateModules();

  // Persistent current-game watcher: runs at plugin scope (while Steam runs),
  // independent of the QAM being open. It is the single source that reports the
  // running game to the backend so auto-TDP / telemetry / fan auto-apply engage
  // on a game already running after a plugin restart. See tdp/gameWatcher.ts.
  const stopGameWatcher = startGameWatcher();
  // Persistent ambient-dim controller for download mode: also runs at plugin scope
  // so the screen keeps dimming/waking while a game downloads with the QAM closed.
  const stopEcoAmbient = startEcoAmbient();
  const stopValueToast = startValueToast();
  // Add "Launch parameters" to a game's library context menu. Fully guarded: a no-op
  // if it can't hook Steam's menu, so it can never break the shared UI.
  const stopContextMenu = installGameContextMenu();
  // Decky renders the plugin-list row from the (fixed) install name, ignoring the
  // localized title. Relabel that row in place to follow the selected language.
  const stopListLocalizer = startPluginListLocalizer();
  const standardLifecycle = new AbortController();
  const directLifecycle = new AbortController();
  const qamShortcut = startQamShortcut(
    (onRuntimeFailure) => registerQuickAccessTab(
      {
        title: <PluginTitle />,
        content: <DirectPluginContent lifecycle={directLifecycle.signal} />,
        icon: <LuGauge />,
      },
      window,
      onRuntimeFailure,
    ),
    () => cleanupOwnedQuickAccessTabs(window),
  );
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
    icon: <LuGauge />,
    onDismount() {
      standardLifecycle.abort();
      directLifecycle.abort();
      qamShortcut.dispose();
      stopPrefsHealed();
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
