import { PanelSection, PanelSectionRow } from "@decky/ui";
import { FC, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getDevice, DeviceInfo } from "../api";
import { useI18n } from "../i18n";
import { ControlCenterShell } from "./ControlCenterShell";
import { Loading } from "./Loading";
import { SECTIONS } from "../sections/registry";
import { SectionDef } from "../sections/types";
import { CustomView } from "../sections/CustomView";
import { useViews } from "../customize/viewStore";
import { viewTabId, isViewTabId, learningTagsForViewBlocks } from "../customize/views";
import { viewIconNode } from "../customize/viewIcons";
import { readActiveTab, writeActiveTab } from "../sections/activeTab";
import { useRunningGame } from "../tdp/useRunningGame";
import { useLearningStatus } from "../learning/useLearningStatus";
import { useUpdate } from "../updater/useUpdate";
import { useLayout } from "../customize/store";
import { useModules } from "../customize/modules";
import { effectiveEnabled } from "../customize/moduleLogic";
import { visibleIds, pinnedLast } from "../customize/layout";
import { PINNED_TAB, POWER_TAB } from "../customize/manifest";
import { sectionHiddenOnDevice, allBlocksHidden } from "../sections/availability";
import { getPresent, usePresentVersion } from "../customize/present";
import { useAccent } from "../system/useAccent";
import { acquireUiActivity } from "../system/uiActivity";
import { useDesktopState } from "../desktop/useDesktop";

export const ControlCenter: FC = () => {
  const { t, lang } = useI18n();
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [failed, setFailed] = useState(false);
  const layout = useLayout();
  const disabled = useModules();
  const desktopMode = !!useDesktopState().state?.enabled;
  const views = useViews();
  usePresentVersion(); // re-evaluate tab emptiness as sections report their real blocks
  // Stable Component per view id so editing a view doesn't remount the active one.
  const viewComponents = useRef(new Map<string, FC>());
  const allSections = useMemo<SectionDef[]>(() => {
    const cache = viewComponents.current;
    const viewSections: SectionDef[] = views.map((v) => {
      let Component = cache.get(v.id);
      if (!Component) {
        Component = () => <CustomView viewId={v.id} />;
        cache.set(v.id, Component);
      }
      return {
        id: viewTabId(v.id),
        icon: (size) => viewIconNode(v.icon, size),
        labelKey: "customize.views.namePlaceholder",
        descriptionKey: "customize.views.cardDesc",
        accent: "#586b78",
        label: v.name,
        learningTags: learningTagsForViewBlocks(v.blocks, desktopMode),
        Component,
      };
    });
    const base = SECTIONS.filter((s) => s.id !== PINNED_TAB);
    const pinned = SECTIONS.filter((s) => s.id === PINNED_TAB);
    return [...base, ...viewSections, ...pinned];
  }, [views, desktopMode]);
  const visibleTabIds = useMemo(
    () => pinnedLast(visibleIds(allSections.map((s) => s.id), layout.tabs, [PINNED_TAB]), PINNED_TAB),
    [layout, allSections],
  );
  // Restore the last active tab (persisted) so a panel remount — Decky remounts on
  // each QAM open, and applying a controller remap reloads the gamepad which makes
  // Steam remount us — doesn't snap back to the first tab. Falls back to the user's
  // first visible tab. A stale/hidden saved id is caught by resolveActiveSection.
  const [activeId, setActiveIdState] = useState<string>(() => {
    const saved = readActiveTab();
    return (saved && visibleTabIds.includes(saved) ? saved : visibleTabIds[0]) ?? SECTIONS[0].id;
  });
  // Memoized so it's a stable prop for TabBar/children — this shell is the one
  // implicated in the QAM render-storm freeze, so avoid churning children.
  const setActiveId = useCallback((id: string) => {
    writeActiveTab(id);
    setActiveIdState(id);
  }, []);
  // Local UI reads for the persistent learning banner. All hooks precede the
  // early returns below (rules-of-hooks; poll hooks blank first render).
  const game = useRunningGame();
  const { status: learning } = useLearningStatus(game?.appid ?? null);
  // One session-guarded update check high in the tree: powers the toast (in the
  // hook) and the alert dot on the Ajustes tab. Calling useUpdate elsewhere
  // (AjustesSection's UpdatePanel) reuses the same session-cached result.
  const { hasUpdate } = useUpdate(lang);
  useAccent(); // re-render the shell when the accent changes

  useEffect(() => {
    getDevice().then(setDevice).catch(() => setFailed(true));
  }, []);

  useEffect(() => acquireUiActivity(), []);

  // Apply the user's tab order + visibility (reusing the memoized id list above).
  // Settings stays pinned; a hidden active tab falls back to the first visible
  // one via resolveActiveSection.
  // Drop tabs that: the device can't use (Mandos on the Steam Deck), whose module
  // the user disabled, or whose blocks are all hidden. Settings is pinned; Potencia
  // too — its master switch being off drops it to monitor-only, never hides it (still
  // hidable explicitly via visibleTabIds above). Computed BEFORE the early returns so
  // useShoulderNav (a hook) always runs; a stale active id falls back via
  // resolveActiveSection.
  const orderedTabs = visibleTabIds
    .map((id) => allSections.find((s) => s.id === id))
    .filter((s): s is SectionDef => !!s)
    .filter((s) => s.id === PINNED_TAB || isViewTabId(s.id) || (s.id === POWER_TAB ? (
      !desktopMode || !allBlocksHidden(s.id, layout.blocks, getPresent(s.id), true)
    ) : (
      !sectionHiddenOnDevice(device, s.id)
      && effectiveEnabled(s.id, disabled)
      && !allBlocksHidden(s.id, layout.blocks, getPresent(s.id))
    )));
  if (failed) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("load.error")}</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!device) return <Loading />;

  return (
    <ControlCenterShell
      device={device}
      gameName={game?.name ?? null}
      learning={learning}
      sections={orderedTabs}
      activeId={activeId}
      showHome={layout.showHome}
      showDeviceHeader={layout.showDeviceHeader}
      hasUpdate={hasUpdate}
      onSelectSection={setActiveId}
    />
  );
};
