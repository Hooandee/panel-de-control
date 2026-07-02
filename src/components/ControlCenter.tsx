import { PanelSection, PanelSectionRow, Spinner, ErrorBoundary } from "@decky/ui";
import { FC, useEffect, useMemo, useState } from "react";

import { getDevice, DeviceInfo, setUiActive } from "../api";
import { useI18n } from "../i18n";
import { DeviceHeader } from "./DeviceHeader";
import { LearningBanner } from "./LearningBanner";
import { TabBar } from "./TabBar";
import { SECTIONS } from "../sections/registry";
import { resolveActiveSection } from "../sections/nav";
import { useRunningGame } from "../tdp/useRunningGame";
import { useLearningStatus } from "../learning/useLearningStatus";
import { useUpdate } from "../updater/useUpdate";
import { AlertDot } from "../updater/AlertDot";
import { useLayout } from "../customize/store";
import { visibleIds } from "../customize/layout";
import { PINNED_TAB } from "../customize/manifest";
import { theme } from "../theme";

/**
 * The control-center shell: persistent chrome (device header + language flags +
 * tab bar) wrapping the active section. Loads the device once; each section owns
 * its own state. A per-section ErrorBoundary keeps one section's crash from
 * blanking the whole panel.
 */
export const ControlCenter: FC = () => {
  const { t, lang } = useI18n();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [failed, setFailed] = useState(false);
  const layout = useLayout();
  // The user's visible tabs in their saved order (Settings always kept). One
  // memoized computation feeds both the initial-tab pick and the rendered tab
  // list (the shell re-renders on every poll tick, so avoid recomputing it).
  const visibleTabIds = useMemo(
    () => visibleIds(SECTIONS.map((s) => s.id), layout.tabs, [PINNED_TAB]),
    [layout],
  );
  // Open on the user's FIRST VISIBLE tab (their reordering), not the code default.
  // Lazy init reads the layout once per mount; Decky remounts the panel on each
  // QAM open, so a saved reorder takes effect the next time it opens.
  const [activeId, setActiveId] = useState<string>(() => visibleTabIds[0] ?? SECTIONS[0].id);
  // Local UI reads for the persistent learning banner. All hooks precede the
  // early returns below (rules-of-hooks; poll hooks blank first render).
  const game = useRunningGame();
  const { status: learning } = useLearningStatus(game?.appid ?? null);
  // One session-guarded update check high in the tree: powers the toast (in the
  // hook) and the alert dot on the Ajustes tab. Calling useUpdate elsewhere
  // (AjustesSection's UpdatePanel) reuses the same session-cached result.
  const { hasUpdate } = useUpdate(lang);

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

  // Apply the user's tab order + visibility (reusing the memoized id list above).
  // Settings stays pinned; a hidden active tab falls back to the first visible
  // one via resolveActiveSection.
  const orderedTabs = visibleTabIds
    .map((id) => SECTIONS.find((s) => s.id === id))
    .filter((s): s is (typeof SECTIONS)[number] => !!s);
  const active = resolveActiveSection(orderedTabs, activeId);
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
            tabs={orderedTabs.map((s) => ({
              id: s.id,
              icon: s.icon,
              label: t(s.labelKey),
              // Red dot on the tab that leads to the updater (Ajustes) when an
              // update is available.
              badge: s.id === PINNED_TAB ? <AlertDot show={hasUpdate} /> : undefined,
            }))}
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
