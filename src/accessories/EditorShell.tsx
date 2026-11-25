import { DialogButton, Focusable, NavEntryPositionPreferences } from "@decky/ui";
import { FC, ReactNode, RefObject, useCallback, useLayoutEffect, useRef, useState } from "react";

import { iconChipStyle } from "../components/chipStyle";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { PANEL_H, PANEL_W } from "./pixelFrames";

const MIN_PITCH = 3;
const MAX_PITCH = 14;

/**
 * A stable handler that always runs the latest render's function. Steam keeps the gamepad
 * handlers a Focusable had when it registered, so a plain closure would act on old state.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useLive<A extends any[], R>(fn: (...args: A) => R): (...args: A) => R {
  const latest = useRef(fn);
  latest.current = fn;
  return useCallback((...args: A) => latest.current(...args), []);
}

/** Largest whole LED pitch whose 64×54 matrix fits the element, following its size live. */
export function useFitPitch(area: RefObject<HTMLElement | null>): number {
  const [pitch, setPitch] = useState(5);
  useLayoutEffect(() => {
    const element = area.current;
    if (!element) return undefined;
    const measure = () => {
      const { clientWidth: w, clientHeight: h } = element;
      if (!w || !h) return;
      setPitch(Math.max(MIN_PITCH, Math.min(MAX_PITCH, Math.floor(Math.min(w / PANEL_W, h / PANEL_H)))));
    };
    measure();
    // The editor lives in Steam's main window, so its ResizeObserver is the one to use.
    const Observer = (element.ownerDocument.defaultView as (Window & { ResizeObserver?: typeof ResizeObserver }) | null)?.ResizeObserver;
    if (!Observer) return undefined;
    const observer = new Observer(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [area]);
  return pitch;
}

/** Equal-width chip with the icon over its name: tools, helpers and speeds. */
export const Chip: FC<{ active: boolean; label: string; icon?: ReactNode; onPick: () => void }> = ({ active, label, icon, onPick }) => (
  <DialogButton onClick={onPick} aria-label={label} style={{ ...iconChipStyle(active), minWidth: 0, width: "auto" }}>
    {icon && <span style={{ display: "flex", fontSize: 16 }}>{icon}</span>}
    <span style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
  </DialogButton>
);

// Stacked rows keep the column: Steam would otherwise enter each row at its first chip.
export const ChipRow: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="row" navEntryPreferPosition={NavEntryPositionPreferences.MAINTAIN_X} style={{ display: "flex", gap: theme.space.xs }}>{children}</Focusable>
);

// Never `disabled`: Steam drops gamepad focus when the focused control becomes disabled.
export const IconButton: FC<{ label: string; onPress: () => void; disabled?: boolean; children: ReactNode }> = ({ label, onPress, disabled, children }) => (
  <DialogButton onClick={() => { if (!disabled) onPress(); }} aria-label={label} aria-disabled={disabled}
    style={{ minWidth: 0, width: 40, height: 34, padding: 0, display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto",
      opacity: disabled ? 0.4 : 1 }}>
    {children}
  </DialogButton>
);

/** A titled group inside the inspector column. */
export const InspectorGroup: FC<{ label: string; children: ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
    <span style={theme.sectionLabel}>{label}</span>
    {children}
  </div>
);

interface Props {
  icon: ReactNode;
  title: string;
  /** Drawn at the largest pitch that fits; the matrix keeps its 64×54 aspect. */
  stage: (pitch: number) => ReactNode;
  /** One fixed-height strip under the matrix (timeline, hint). */
  stageFooter?: ReactNode;
  inspector: ReactNode;
  primaryLabel: string;
  primaryIcon: ReactNode;
  primaryBusy?: boolean;
  onPrimary: () => void;
  onClose: () => void;
  notice?: ReactNode;
}

/**
 * Layout shared by the drawing and layout editors: the panel on the left at the largest size
 * that fits, a scrolling inspector on the right and the actions at the bottom. The height leaves
 * room for the dialog's own padding (12px + 2.25vh a side) and the margins Steam keeps around it.
 */
export const EditorShell: FC<Props> = ({
  icon, title, stage, stageFooter, inspector, primaryLabel, primaryIcon, primaryBusy, onPrimary, onClose, notice,
}) => {
  const { t } = useI18n();
  const area = useRef<HTMLDivElement>(null);
  const pitch = useFitPitch(area);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, boxSizing: "border-box",
      width: "min(1180px, 90vw)", maxWidth: "100%", height: "min(760px, calc(95vh - 165px))", minHeight: 360 }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, color: theme.color.textPrimary, flex: "0 0 auto" }}>
        <span style={{ display: "flex", color: theme.color.accent }}>{icon}</span>
        <span style={{ fontSize: 20, fontWeight: 800 }}>{title}</span>
        <span style={{ fontSize: theme.font.body, color: theme.color.textMuted }}>JSAUX PIXEL</span>
      </div>

      <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.lg, flex: "1 1 0", minHeight: 0 }}>
        <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, flex: "1 1 0", minWidth: 0, minHeight: 0 }}>
          <div ref={area} style={{ flex: "1 1 0", minHeight: 0, minWidth: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {stage(pitch)}
          </div>
          {stageFooter && <div style={{ flex: "0 0 auto" }}>{stageFooter}</div>}
        </Focusable>
        <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", gap: theme.space.lg,
          width: "clamp(220px, 30%, 320px)", flex: "0 0 auto", minHeight: 0, overflowY: "auto", padding: theme.space.xs,
          boxSizing: "border-box" }}>
          {inspector}
        </Focusable>
      </Focusable>

      <Focusable flow-children="row" style={{ display: "flex", alignItems: "center", gap: theme.space.sm, flex: "0 0 auto" }}>
        <div style={{ flex: 1, minWidth: 0, fontSize: theme.font.caption, color: theme.color.warn }}>{notice}</div>
        <DialogButton onClick={onClose} style={{ width: "auto", minWidth: 140 }}>{t("accessories.editor.back")}</DialogButton>
        <DialogButton onClick={() => { if (!primaryBusy) onPrimary(); }} aria-disabled={primaryBusy}
          style={{ opacity: primaryBusy ? 0.6 : 1, width: "auto", minWidth: 220, display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.sm,
            background: theme.color.accent, color: theme.color.onAccent, fontWeight: 800 }}>
          {primaryIcon} {primaryLabel}
        </DialogButton>
      </Focusable>
    </div>
  );
};
