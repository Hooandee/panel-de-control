import {
  PanelSection,
  PanelSectionRow,
  Spinner,
  ErrorBoundary,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaSlidersH } from "react-icons/fa";
import { FC, useEffect, useState } from "react";

import { getDevice, DeviceInfo } from "./api";
import { I18nProvider, useI18n } from "./i18n";
import { DeviceHeader } from "./components/DeviceHeader";
import { LanguageToggle } from "./components/LanguageToggle";

const Content: FC = () => {
  // ALL hooks above any early return (minified "invalid hook" trap otherwise).
  const { t } = useI18n();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getDevice().then(setDevice).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("load.error")}</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!device) return <Spinner />;

  return (
    <PanelSection>
      <PanelSectionRow>
        <DeviceHeader device={device} />
      </PanelSectionRow>
      <LanguageToggle />
    </PanelSection>
  );
};

export default definePlugin(() => ({
  name: "Panel de Control",
  titleView: <div className={staticClasses.Title}>Panel de Control</div>,
  content: (
    <I18nProvider>
      <ErrorBoundary>
        <Content />
      </ErrorBoundary>
    </I18nProvider>
  ),
  icon: <FaSlidersH />,
  onDismount() {
    // no listeners/timers yet
  },
}));
