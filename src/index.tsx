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

// Localized header title only; the internal plugin name / install folder stays
// "Panel de Control" (renaming it would break existing installs and the updater).
const PluginTitle: FC = () => (
  <div className={staticClasses.Title}>{translate("app.title")}</div>
);

export default definePlugin(() => {
  // Restore durable UI prefs into the localStorage cache at plugin scope (so the
  // QAM-closed toast uses the right language), then re-apply the healed values.
  onPrefsHealed(() => {
    refreshValueToast();
    reloadLayout();
  });
  void hydratePrefs();
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

  return {
    name: "Panel de Control",
    titleView: <PluginTitle />,
    content: (
      <I18nProvider>
        <ErrorBoundary>
          <ControlCenter />
        </ErrorBoundary>
      </I18nProvider>
    ),
    icon: <LuGauge />,
    onDismount() {
      stopGameWatcher();
      stopEcoAmbient();
      stopValueToast();
    },
  };
});
