import { PanelSection, PanelSectionRow, Spinner, ErrorBoundary } from "@decky/ui";
import { FC, useEffect, useState } from "react";

import { getDevice, DeviceInfo } from "../api";
import { useI18n } from "../i18n";
import { DeviceHeader } from "./DeviceHeader";
import { TabBar } from "./TabBar";
import { SECTIONS } from "../sections/registry";
import { resolveActiveSection } from "../sections/nav";

/**
 * The control-center shell: persistent chrome (device header + language flags +
 * tab bar) wrapping the active section. Loads the device once; each section owns
 * its own state. A per-section ErrorBoundary keeps one section's crash from
 * blanking the whole panel.
 */
export const ControlCenter: FC = () => {
  const { t } = useI18n();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [failed, setFailed] = useState(false);
  const [activeId, setActiveId] = useState<string>(SECTIONS[0].id);

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

  const active = resolveActiveSection(SECTIONS, activeId);
  const Active = active?.Component;

  return (
    <PanelSection>
      <PanelSectionRow>
        <DeviceHeader device={device} />
      </PanelSectionRow>
      <PanelSectionRow>
        <TabBar
          tabs={SECTIONS.map((s) => ({ id: s.id, icon: s.icon, label: t(s.labelKey) }))}
          activeId={active?.id ?? activeId}
          onSelect={setActiveId}
        />
      </PanelSectionRow>
      {Active && (
        <ErrorBoundary>
          <Active />
        </ErrorBoundary>
      )}
    </PanelSection>
  );
};
