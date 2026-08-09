import { ErrorBoundary, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FC } from "react";
import { LuGauge } from "react-icons/lu";

import { I18nProvider, translate } from "./i18n";
import { ControlCenter } from "./components/ControlCenter";
import { startGameWatcher } from "./tdp/gameWatcher";
import { startEcoAmbient } from "./system/ecoAmbient";
import { startValueToast, refreshValueToast } from "./system/valueToast";
import { hydratePrefs, onPrefsHealed } from "./system/pdcStorage";
import { reloadLayout } from "./customize/store";
import { hydrateModules } from "./customize/modules";
import { installGameContextMenu } from "./launch/gameContextMenu";
import { startPluginListLocalizer } from "./pluginListLocalizer";
import { registerQuickAccessTab } from "./deckyInternal";
import { QamPanelGate, canGateQamPanel } from "./components/QamPanelGate";
import {
  getQamShortcutEnabled,
  refreshQamShortcutPreference,
  setQamShortcutRuntime,
} from "./system/qamShortcut";
import { shutdownUiActivity } from "./system/uiActivity";
import { QamShortcutDeckyEntry } from "./components/QamShortcutDeckyEntry";

const LocalizedPluginTitle: FC = () => (
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
  const stopPrefsHealed = onPrefsHealed(() => {
    refreshValueToast();
    reloadLayout();
    refreshQamShortcutPreference();
  });
  void hydratePrefs();
  hydrateModules();

  const stopGameWatcher = startGameWatcher();
  const stopEcoAmbient = startEcoAmbient();
  const stopValueToast = startValueToast();
  const stopContextMenu = installGameContextMenu();
  const stopListLocalizer = startPluginListLocalizer();
  const qamLifecycle = new AbortController();
  const fallbackLifecycle = new AbortController();
  const shortcutEnabled = getQamShortcutEnabled();
  const shortcutSupported = canGateQamPanel(window);
  const qamShortcut = shortcutEnabled && shortcutSupported
    ? registerQuickAccessTab({
      title: <LocalizedPluginTitle />,
      content: <VisiblePluginContent lifecycle={qamLifecycle.signal} />,
      icon: <LuGauge />,
    })
    : null;
  const shortcutRegistered = qamShortcut?.registered === true;
  setQamShortcutRuntime(shortcutEnabled, shortcutRegistered);

  return {
    name: "Panel de Control",
    titleView: <LocalizedPluginTitle />,
    content: shortcutRegistered
      ? (
        <ShortcutDeckyContent
          directLifecycle={qamLifecycle}
          fallbackLifecycle={fallbackLifecycle.signal}
        />
      )
      : <PluginContent />,
    icon: <LuGauge />,
    onDismount() {
      qamLifecycle.abort();
      fallbackLifecycle.abort();
      qamShortcut?.dispose();
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
