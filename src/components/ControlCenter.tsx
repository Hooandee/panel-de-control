import { PanelSection, PanelSectionRow } from "@decky/ui";
import { FC, useCallback, useEffect, useMemo, useRef, useState } from "react";

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
import { visibleIds, pinnedLast } from "../customize/layout";
import { PINNED_TAB } from "../customize/manifest";
import { sectionAvailable } from "../sections/availability";
import { getPresent, usePresentVersion } from "../customize/present";
import { useAccent } from "../system/useAccent";
import { acquireUiActivity } from "../system/uiActivity";
import { useDesktopState } from "../desktop/useDesktop";
import type { QamViewTarget } from "../qam/viewCatalog";
import { useDeviceState } from "../system/useDevice";

export const ControlCenter: FC<{ target?: QamViewTarget }> = ({ target }) => {
  const { t, lang } = useI18n();
  const { device, failed } = useDeviceState();
  const layout = useLayout();
  const disabled = useModules();
  const desktopMode = !!useDesktopState().state?.enabled;
  const views = useViews();
  usePresentVersion();
  const viewComponentCache = useRef(new Map<string, FC>());
  const allSections = useMemo<SectionDef[]>(() => {
    const cache = viewComponentCache.current;
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
  const targetSectionId = target?.kind === "section" ? target.id : null;
  const visibleTabIds = useMemo(() => {
    const visible = visibleIds(allSections.map((s) => s.id), layout.tabs, [PINNED_TAB]);
    if (
      targetSectionId
      && allSections.some((section) => section.id === targetSectionId)
      && !visible.includes(targetSectionId)
    ) {
      visible.splice(Math.max(0, visible.length - 1), 0, targetSectionId);
    }
    return pinnedLast(visible, PINNED_TAB);
  }, [layout, allSections, targetSectionId]);
  const [activeId, setActiveIdState] = useState<string>(() => {
    if (targetSectionId) return targetSectionId;
    const saved = readActiveTab();
    return (saved && visibleTabIds.includes(saved) ? saved : visibleTabIds[0]) ?? SECTIONS[0].id;
  });
  const setActiveId = useCallback((id: string) => {
    writeActiveTab(id);
    setActiveIdState(id);
  }, []);
  const game = useRunningGame();
  const { status: learning } = useLearningStatus(game?.appid ?? null);
  const { hasUpdate } = useUpdate(lang);
  useAccent();

  useEffect(() => acquireUiActivity(), []);

  const isAvailable = (section: SectionDef) => {
    if (isViewTabId(section.id)) return true;
    return sectionAvailable(section.id, {
      device,
      disabled,
      layout,
      desktopMode,
      present: getPresent,
    });
  };
  const orderedTabs = visibleTabIds
    .map((id) => allSections.find((s) => s.id === id))
    .filter((s): s is SectionDef => !!s)
    .filter(isAvailable);
  const resolvedTargetId = targetSectionId
    && orderedTabs.some((section) => section.id === targetSectionId)
    ? targetSectionId
    : null;
  if (failed) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("load.error")}</PanelSectionRow>
      </PanelSection>
    );
  }
  if (!device) return <Loading />;
  if (targetSectionId && !resolvedTargetId) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("customize.qam.destinationUnavailable")}</PanelSectionRow>
      </PanelSection>
    );
  }

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
      initialMode={target?.kind === "home" ? "home" : resolvedTargetId ? "detail" : undefined}
      onSelectSection={setActiveId}
    />
  );
};
