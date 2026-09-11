import { ErrorBoundary, Focusable, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useLayoutEffect, useRef } from "react";

import type { DeviceInfo, LearningStatus } from "../api";
import { PINNED_TAB } from "../customize/manifest";
import { useI18n } from "../i18n";
import { resolveShellState } from "../sections/shellNavigation";
import { setShellMode, useShellMode } from "../sections/shellMode";
import type { SectionDef } from "../sections/types";
import { useShoulderNav } from "../sections/useShoulderNav";
import { theme } from "../theme";
import { AlertDot } from "../updater/AlertDot";
import { Dashboard } from "./Dashboard";
import { DeviceHeader } from "./DeviceHeader";
import { FocusRoot } from "./FocusRoot";
import { LearningBanner } from "./LearningBanner";
import { ShellHeader } from "./ShellHeader";
import { TabsModeHeader } from "./TabsModeHeader";

export interface ControlCenterShellProps {
  device: DeviceInfo;
  gameName: string | null;
  learning: LearningStatus | null;
  sections: SectionDef[];
  activeId: string;
  showHome: boolean;
  showDeviceHeader: boolean;
  hasUpdate: boolean;
  onSelectSection: (id: string) => void;
}

function resetNearestVerticalScroller(element: HTMLElement | null): void {
  if (!element) return;
  const qamViewport = element.closest<HTMLElement>("[id^='quickaccess_content_']");
  if (qamViewport) {
    qamViewport.scrollTop = 0;
    return;
  }
  const view = element.ownerDocument.defaultView;
  for (let current = element.parentElement; current; current = current.parentElement) {
    const overflowY = view?.getComputedStyle(current).overflowY || current.style.overflowY;
    const canScroll = current.scrollTop > 0 || current.scrollHeight > current.clientHeight;
    if ((overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") && canScroll) {
      current.scrollTop = 0;
      return;
    }
  }
}

export function ControlCenterShell({
  device,
  gameName,
  learning,
  sections,
  activeId,
  showHome,
  showDeviceHeader,
  hasUpdate,
  onSelectSection,
}: ControlCenterShellProps) {
  const { t } = useI18n();
  const shellSurface = useRef<HTMLDivElement>(null);
  const storedMode = useShellMode();
  const ids = sections.map((section) => section.id);
  const resolved = resolveShellState(storedMode, activeId, ids, showHome);
  const active = resolved.activeId
    ? sections.find((section) => section.id === resolved.activeId)
    : undefined;
  const Active = active?.Component;
  const learningScope = resolved.mode === "home" ? [] : active?.learningTags ?? [];

  useEffect(() => {
    if (storedMode !== resolved.mode) setShellMode(resolved.mode);
    if (resolved.activeId && resolved.activeId !== activeId) {
      onSelectSection(resolved.activeId);
    }
  }, [activeId, onSelectSection, resolved.activeId, resolved.mode, storedMode]);

  const sectionViewKey = resolved.mode === "home"
    ? null
    : `${resolved.mode}:${resolved.activeId ?? ""}`;

  useLayoutEffect(() => {
    if (!sectionViewKey) return;
    const surface = shellSurface.current;
    if (!surface) return;
    const view = surface.ownerDocument.defaultView;
    const reset = () => {
      if (surface.isConnected) resetNearestVerticalScroller(surface);
    };
    reset();
    const frame = view?.requestAnimationFrame(reset);
    return () => {
      if (frame !== undefined) view?.cancelAnimationFrame(frame);
    };
  }, [sectionViewKey]);

  useShoulderNav(
    resolved.mode === "home" ? [] : ids,
    resolved.activeId ?? "",
    onSelectSection,
  );

  const goHome = () => setShellMode("home");
  const openDetail = (id: string) => {
    onSelectSection(id);
    setShellMode("detail");
  };
  const openSettings = () => {
    onSelectSection(PINNED_TAB);
    if (resolved.mode === "home") setShellMode("detail");
  };
  const tabsModeItems = sections.map((section) => ({
    id: section.id,
    icon: section.icon(section.id === resolved.activeId ? 17 : 13),
    label: section.label || t(section.labelKey),
    accent: section.accent,
    badge: section.id === PINNED_TAB ? <AlertDot show={hasUpdate} /> : undefined,
  }));

  return (
    <PanelSection>
      <FocusRoot publishDocument>
        <Focusable
          ref={shellSurface}
          data-testid="shell-surface"
          onCancel={showHome && resolved.mode !== "home" ? (event) => {
            event.stopPropagation();
            goHome();
          } : undefined}
        >
          <PanelSectionRow>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: theme.space.section,
                marginBottom: theme.space.card,
              }}
            >
              {showDeviceHeader && resolved.mode === "home" ? <DeviceHeader device={device} /> : null}
              {resolved.mode === "tabs" ? (
                <TabsModeHeader
                  items={tabsModeItems}
                  activeId={resolved.activeId ?? activeId}
                  showBack={showHome}
                  onBack={goHome}
                  onSelect={onSelectSection}
                  trailing={showDeviceHeader ? <DeviceHeader device={device} /> : undefined}
                />
              ) : null}
              {resolved.mode === "detail" ? (
                <ShellHeader
                  onBack={goHome}
                  trailing={showDeviceHeader ? <DeviceHeader device={device} /> : undefined}
                />
              ) : null}
              <LearningBanner
                gameName={gameName}
                status={learning}
                onOpenSettings={openSettings}
                scope={learningScope}
              />
              {resolved.mode === "home" ? (
                <div data-testid="dashboard">
                  <Dashboard
                    sections={sections}
                    activeId={resolved.activeId}
                    settingsBadge={<AlertDot show={hasUpdate} />}
                    onOpenSection={openDetail}
                  />
                </div>
              ) : null}
            </div>
          </PanelSectionRow>
          {resolved.mode !== "home" && active && Active ? (
            <ErrorBoundary key={active.id}>
              <div data-testid="section-body" style={{ paddingBottom: theme.space.lg }}>
                <Active />
              </div>
            </ErrorBoundary>
          ) : null}
        </Focusable>
      </FocusRoot>
    </PanelSection>
  );
}
