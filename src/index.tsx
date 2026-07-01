import { ErrorBoundary, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { LuGauge } from "react-icons/lu";

import { I18nProvider } from "./i18n";
import { ControlCenter } from "./components/ControlCenter";
import { startGameWatcher } from "./tdp/gameWatcher";

export default definePlugin(() => {
  // Persistent current-game watcher: runs at plugin scope (while Steam runs),
  // independent of the QAM being open. It is the single source that reports the
  // running game to the backend so auto-TDP / telemetry / fan auto-apply engage
  // on a game already running after a plugin restart. See tdp/gameWatcher.ts.
  const stopGameWatcher = startGameWatcher();

  return {
    name: "Panel de Control",
    titleView: <div className={staticClasses.Title}>Panel de Control</div>,
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
    },
  };
});
