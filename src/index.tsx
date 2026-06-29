import { ErrorBoundary, staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { LuGauge } from "react-icons/lu";

import { I18nProvider } from "./i18n";
import { ControlCenter } from "./components/ControlCenter";

export default definePlugin(() => ({
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
    // no global listeners; hooks clean up their own
  },
}));
