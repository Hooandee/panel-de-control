import { PanelSection, PanelSectionRow, Spinner, ErrorBoundary } from "@decky/ui";
import { FC, useEffect, useState } from "react";

import { getDevice, DeviceInfo, setUiActive } from "../api";
import { useI18n } from "../i18n";
import { DeviceHeader } from "./DeviceHeader";
import { LearningBanner } from "./LearningBanner";
import { TabBar } from "./TabBar";
import { SECTIONS } from "../sections/registry";
import { resolveActiveSection } from "../sections/nav";
import { useRunningGame } from "../tdp/useRunningGame";
import { useLearningStatus } from "../learning/useLearningStatus";
import { theme } from "../theme";

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
  // Local UI reads for the persistent learning banner. All hooks precede the
  // early returns below (rules-of-hooks; poll hooks blank first render).
  const game = useRunningGame();
  const { status: learning } = useLearningStatus(game?.appid ?? null);

  useEffect(() => {
    getDevice().then(setDevice).catch(() => setFailed(true));
  }, []);

  // Tell the backend the plugin UI (QAM panel) is open while this content is
  // mounted; Decky unmounts it on close → the cleanup fires. Lets the auto-TDP loop
  // raise its floor so the CPU-bound menu render stays fluid. Degrades if the RPC
  // is absent/unreachable (try/catch on the promise).
  useEffect(() => {
    setUiActive(true).catch(() => {});
    return () => {
      setUiActive(false).catch(() => {});
    };
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
      {/* Shell chrome grouped in one row with an explicit gap so the three cards
          (device / learning / tabs) breathe instead of touching. A null
          LearningBanner collapses its slot — no double gap. */}
      <PanelSectionRow>
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginBottom: 6 }}>
          <DeviceHeader device={device} />
          <LearningBanner
            gameName={game?.name ?? null}
            status={learning}
            onOpenSettings={() => setActiveId("settings")}
          />
          <TabBar
            tabs={SECTIONS.map((s) => ({ id: s.id, icon: s.icon, label: t(s.labelKey) }))}
            activeId={active?.id ?? activeId}
            onSelect={setActiveId}
          />
        </div>
      </PanelSectionRow>
      {Active && (
        <ErrorBoundary>
          <Active />
        </ErrorBoundary>
      )}
    </PanelSection>
  );
};
