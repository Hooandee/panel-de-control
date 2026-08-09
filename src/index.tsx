import { ErrorBoundary, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FC } from "react";
import { LuGauge } from "react-icons/lu";

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
import { registerQuickAccessTab, removeOwnedQuickAccessTabs } from "./deckyInternal";
import { QamPanelGate, canGateQamPanel } from "./components/QamPanelGate";
import {
  refreshQamShortcutPreference,
  startQamShortcut,
} from "./system/qamShortcut";
import { shutdownUiActivity } from "./system/uiActivity";
import { QamShortcutDeckyEntry } from "./components/QamShortcutDeckyEntry";

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

const PluginContent: FC = () => (
  <I18nProvider><ControlCenterContent /></I18nProvider>
);

const VisiblePluginContent: FC<{ lifecycle: AbortSignal }> = ({ lifecycle }) => (
  <QamPanelGate
    lifecycle={lifecycle}
    fallback={<div>{translate("settings.qamShortcut.fallback")}</div>}
  >
    <PluginContent />
  </QamPanelGate>
);

const ShortcutDeckyContent: FC<{
  directLifecycle: AbortController;
  fallbackLifecycle: AbortSignal;
}> = ({ directLifecycle, fallbackLifecycle }) => (
  <I18nProvider>
    <QamShortcutDeckyEntry
      lifecycle={directLifecycle}
      fallbackLifecycle={fallbackLifecycle}
    >
      <ControlCenterContent />
    </QamShortcutDeckyEntry>
  </I18nProvider>
);

export default definePlugin(() => {
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
  const qamLifecycle = new AbortController();
  const fallbackLifecycle = new AbortController();
  const qamShortcut = startQamShortcut(
    () => registerQuickAccessTab({
      title: <PluginTitle />,
      content: <VisiblePluginContent lifecycle={qamLifecycle.signal} />,
      icon: <LuGauge />,
    }),
    () => removeOwnedQuickAccessTabs(window),
    () => qamLifecycle.abort(),
    canGateQamPanel(window),
  );

  return {
    name: "Panel de Control",
    titleView: <PluginTitle />,
    content: (
      <ShortcutDeckyContent
        directLifecycle={qamLifecycle}
        fallbackLifecycle={fallbackLifecycle.signal}
      />
    ),
    icon: <LuGauge />,
    onDismount() {
      qamLifecycle.abort();
      fallbackLifecycle.abort();
      qamShortcut.dispose();
      stopPrefsHealed();
      shutdownUiActivity();
      stopGameWatcher();
      stopEcoAmbient();
      stopValueToast();
      stopContextMenu();
      stopListLocalizer();
    },
  };
});
