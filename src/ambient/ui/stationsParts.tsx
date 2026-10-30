import { Focusable } from "@decky/ui";
import { useLayoutEffect, useRef, useState, type CSSProperties, type FC, type ReactNode } from "react";

import { theme } from "../../theme";

const SHEET: CSSProperties = { display: "flex", flexDirection: "column", gap: 10, padding: theme.space.sm, height: "calc(100vh - 162px)", maxHeight: 628, minHeight: 0, boxSizing: "border-box" };

function scrollingAncestor(node: HTMLElement, view: Window): HTMLElement | null {
  for (let parent = node.parentElement; parent; parent = parent.parentElement) {
    if (/(auto|scroll|hidden)/.test(view.getComputedStyle(parent).overflowY)) return parent;
  }
  return null;
}

export function sheetRoom(node: HTMLElement, scroller: HTMLElement, view: Window): number {
  const style = view.getComputedStyle(scroller);
  const padTop = parseFloat(style.paddingTop) || 0;
  const padBottom = parseFloat(style.paddingBottom) || 0;
  const offset = node.getBoundingClientRect().top + scroller.scrollTop - scroller.getBoundingClientRect().top - padTop;
  return Math.floor(scroller.clientHeight - padTop - padBottom - Math.max(0, offset));
}

/**
 * Fits the dialog exactly: if it overflowed, moving focus would scroll the whole modal and the map with it.
 * Steam pads its dialogs more on larger screens (Legion Go 2), so the viewport estimate only bounds the measured room.
 */
export const Sheet: FC<{ children: ReactNode }> = ({ children }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  useLayoutEffect(() => {
    const node = ref.current;
    const view = node?.ownerDocument.defaultView;
    const scroller = node && view ? scrollingAncestor(node, view) : null;
    if (!node || !view || !scroller) return;
    const fit = () => {
      const room = sheetRoom(node, scroller, view);
      if (room > 0 && room < node.offsetHeight) setHeight(room);
    };
    fit();
    const Observer = view.ResizeObserver;
    if (!Observer) return;
    const observer = new Observer(fit);
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} style={height === null ? SHEET : { ...SHEET, height }}>{children}</div>;
};

export const ROW_HEIGHT = 56;

export const oneLine: CSSProperties = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

export function useMeasuredHeight(): [(node: HTMLDivElement | null) => void, number] {
  const [height, setHeight] = useState(0);
  const observer = useRef<ResizeObserver | null>(null);
  const ref = (node: HTMLDivElement | null) => {
    observer.current?.disconnect();
    observer.current = null;
    const Observer = node?.ownerDocument.defaultView?.ResizeObserver;
    if (!node || !Observer) return;
    observer.current = new Observer(([entry]) => setHeight(Math.floor(entry.contentRect.height)));
    observer.current.observe(node);
  };
  return [ref, height];
}

export const Chip: FC<{ label: string; active: boolean; onActivate: () => void; icon?: ReactNode; subtle?: boolean }> = ({ label, active, onActivate, icon, subtle }) => (
  <Focusable
    onActivate={onActivate}
    onClick={onActivate}
    style={{ "--pdc-focus-radius": "99px", borderRadius: 99, flexShrink: 0, cursor: "pointer", background: "transparent", padding: 0 } as CSSProperties}
  >
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      padding: "6px 12px",
      borderRadius: 99,
      fontSize: 12,
      fontWeight: 600,
      whiteSpace: "nowrap",
      color: active ? theme.color.onAccent : subtle ? theme.color.textMuted : theme.color.textPrimary,
      background: active ? theme.color.accent : subtle ? "transparent" : "rgba(255,255,255,0.05)",
      boxShadow: active ? "none" : `inset 0 0 0 1px ${subtle ? "rgba(255,255,255,0.12)" : theme.color.hairline}`,
    }}>
      {icon}
      {label}
    </span>
  </Focusable>
);

export const Empty: FC<{ text: string }> = ({ text }) => (
  <div style={{ padding: `${theme.space.lg}px ${theme.space.sm}px`, textAlign: "center", fontSize: theme.font.body, color: theme.color.textMuted }}>{text}</div>
);

const DIM = 0.35;

/** The libraries sit over a busy Home; tinting Steam's dialog (glass or solid) keeps their lists readable. */
export const DimDialog: FC = () => {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const dialog = ref.current?.closest<HTMLElement>(".GenericDialogBase");
    if (!dialog) return;
    const previous = dialog.style.boxShadow;
    dialog.style.boxShadow = `inset 0 0 0 100vmax rgba(0,0,0,${DIM})`;
    return () => {
      dialog.style.boxShadow = previous;
    };
  }, []);
  return <span ref={ref} hidden />;
};
