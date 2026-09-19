import { ErrorBoundary, Focusable, getFocusNavController, PanelSection, PanelSectionRow } from "@decky/ui";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { DeviceInfo, LearningStatus } from "../api";
import { PINNED_TAB } from "../customize/manifest";
import { useI18n } from "../i18n";
import { resolveShellState } from "../sections/shellNavigation";
import { setShellMode, type ShellMode, useShellMode } from "../sections/shellMode";
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
  initialMode?: ShellMode;
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

function focusShellDestination(surface: HTMLElement, mode: ShellMode, activeId: string | null): void {
  const controls = 'button,input,select,textarea,[role="button"],[tabindex="0"]';
  const eligible = (element: HTMLElement) => element.getClientRects().length > 0
    && !element.closest('[hidden],[aria-hidden="true"],[aria-disabled="true"],:disabled')
    && (!element.matches('[tabindex="0"]') || element.matches('button,input,select,textarea,[role="button"]') || !element.querySelector(controls));
  const cards = Array.from(surface.querySelectorAll<HTMLElement>('[data-testid="dashboard-card"]')).filter(eligible);
  const body = surface.querySelector('[data-testid="section-body"]');
  const firstControl = (root: Element | null) => Array.from(root?.querySelectorAll<HTMLElement>(controls) ?? []).find(eligible);
  const target = mode === "home"
    ? cards.find((card) => card.dataset.sectionId === activeId) ?? cards[0]
    : firstControl(body) ?? firstControl(surface);
  if (!target) return;
  try {
    const controller = getFocusNavController();
    if (typeof controller?.FocusElement === "function") {
      controller.FocusElement(target);
      return;
    }
  } catch {
    // Steam's focus controller can disappear while the QAM is reconciling.
  }
  target.focus({ preventScroll: true });
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
  initialMode,
  onSelectSection,
}: ControlCenterShellProps) {
  const { t } = useI18n();
  const shellSurface = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<{ mode: ShellMode; previousFocus: Element | null } | null>(null);
  const storedMode = useShellMode();
  const [entryMode, setEntryMode] = useState<ShellMode | undefined>(initialMode);
  const ids = sections.map((section) => section.id);
  const resolved = resolveShellState(entryMode ?? storedMode, activeId, ids, showHome);
  const active = resolved.activeId
    ? sections.find((section) => section.id === resolved.activeId)
    : undefined;
  const Active = active?.Component;
  const learningScope = resolved.mode === "home" ? [] : active?.learningTags ?? [];

  useLayoutEffect(() => {
    if (!entryMode) return;
    if (storedMode !== entryMode) setShellMode(entryMode);
    setEntryMode(undefined);
  }, [entryMode, storedMode]);

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
    const request = pendingFocus.current?.mode === resolved.mode ? pendingFocus.current : null;
    if (!sectionViewKey && !request) return;
    pendingFocus.current = null;
    const surface = shellSurface.current;
    const doc = surface?.ownerDocument;
    const view = doc?.defaultView;
    if (!surface || !doc || !view) return;
    const reset = () => {
      if (sectionViewKey && surface.isConnected) resetNearestVerticalScroller(surface);
    };
    reset();
    let cancelled = false;
    const frame = view.requestAnimationFrame(() => {
      if (cancelled || !surface.isConnected) return;
      reset();
      if (!request || doc.visibilityState === "hidden") return;
      const currentFocus = doc.querySelector(".gpfocus");
      if (currentFocus && currentFocus !== request.previousFocus && !surface.contains(currentFocus)) return;
      focusShellDestination(surface, resolved.mode, resolved.activeId);
    });
    return () => {
      cancelled = true;
      view.cancelAnimationFrame(frame);
    };
  }, [sectionViewKey, resolved.mode, resolved.activeId]);

  useShoulderNav(
    resolved.mode === "home" ? [] : ids,
    resolved.activeId ?? "",
    onSelectSection,
  );

  const navigate = (mode: ShellMode) => {
    pendingFocus.current = { mode, previousFocus: shellSurface.current?.ownerDocument.querySelector(".gpfocus") ?? null };
    setShellMode(mode);
  };
  const goHome = () => navigate("home");
  const leaveDetail = () => navigate(showHome ? "home" : "tabs");
  const openDetail = (id: string) => {
    onSelectSection(id);
    navigate("detail");
  };
  const openSettings = () => {
    onSelectSection(PINNED_TAB);
    if (resolved.mode === "home") navigate("detail");
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
          onCancel={resolved.mode === "detail" || (showHome && resolved.mode === "tabs") ? (event) => {
            event.stopPropagation();
            leaveDetail();
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
                  trailing={showDeviceHeader ? <DeviceHeader device={device} presentation={showHome ? "compact" : "full"} fullWidth={!showHome} /> : undefined}
                />
              ) : null}
              {resolved.mode === "detail" ? (
                <ShellHeader
                  onBack={leaveDetail}
                  backLabel={showHome ? undefined : t("customize.home.tabs")}
                  trailing={showDeviceHeader ? <DeviceHeader device={device} presentation="compact" /> : undefined}
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
