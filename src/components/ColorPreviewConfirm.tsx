import { FC, useLayoutEffect, useRef, useState } from "react";
import { Focusable } from "@decky/ui";
import { LuCheck, LuUndo2 } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  seconds: number;
  saving: boolean;
  onSave: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
}

interface TrayPosition {
  left: number;
  width: number;
  bottom: number;
}

const PANEL_INSET = 16;
const POSITION_POLL_MS = 100;

function scrollViewport(anchor: HTMLElement): HTMLElement | null {
  const qamContent = anchor.closest<HTMLElement>("[id^='quickaccess_content_']");
  if (qamContent) return qamContent;
  const view = anchor.ownerDocument.defaultView;
  for (let node = anchor.parentElement; node; node = node.parentElement) {
    const overflow = view?.getComputedStyle(node).overflowY || node.style.overflowY;
    if (overflow === "auto" || overflow === "scroll") return node;
  }
  return null;
}

function trayPosition(anchor: HTMLElement): TrayPosition {
  const view = anchor.ownerDocument.defaultView ?? window;
  const viewport = scrollViewport(anchor)?.getBoundingClientRect();
  const left = viewport?.left ?? 0;
  const width = viewport?.width ?? view.innerWidth;
  const bottom = viewport ? view.innerHeight - viewport.bottom : 0;
  return {
    left: left + PANEL_INSET,
    width: Math.max(0, width - PANEL_INSET * 2),
    bottom: Math.max(0, bottom) + PANEL_INSET,
  };
}

export const ColorPreviewConfirm: FC<Props> = ({ seconds, saving, onSave, onDiscard }) => {
  const { t } = useI18n();
  const anchorRef = useRef<HTMLSpanElement>(null);
  const locked = useRef(false);
  const [position, setPosition] = useState<TrayPosition>({
    left: PANEL_INSET,
    width: Math.max(0, window.innerWidth - PANEL_INSET * 2),
    bottom: PANEL_INSET,
  });

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const view = anchor.ownerDocument.defaultView ?? window;
    const viewport = scrollViewport(anchor);
    const update = () => setPosition((current) => {
      const next = trayPosition(anchor);
      return current.left === next.left
        && current.width === next.width
        && current.bottom === next.bottom
        ? current
        : next;
    });
    const resize = viewport && typeof view.ResizeObserver === "function"
      ? new view.ResizeObserver(update)
      : null;
    if (resize && viewport) resize.observe(viewport);
    view.addEventListener("resize", update);
    // QAM slides with transforms, which do not notify ResizeObserver.
    const poll = view.setInterval(update, POSITION_POLL_MS);
    update();
    return () => {
      resize?.disconnect();
      view.removeEventListener("resize", update);
      view.clearInterval(poll);
    };
  }, []);

  const actionStyle = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    minHeight: 38,
    padding: "8px",
    borderRadius: theme.radius.sm,
    fontSize: theme.font.caption,
    fontWeight: 700,
    whiteSpace: "nowrap",
    cursor: saving ? "default" : "pointer",
    opacity: saving ? 0.55 : 1,
  } as const;
  const run = async (action: () => void | Promise<void>) => {
    if (saving || locked.current) return;
    locked.current = true;
    try {
      await action();
    } finally {
      locked.current = false;
    }
  };

  return (
    <>
      <span ref={anchorRef} aria-hidden style={{ display: "none" }} />
      <div
        role="status"
        aria-live="polite"
        style={{
          position: "fixed",
          left: position.left,
          bottom: position.bottom,
          zIndex: 1000,
          width: position.width,
          boxSizing: "border-box",
          padding: theme.space.md,
          borderRadius: theme.radius.md,
          background: theme.color.surfaceRaised,
          boxShadow: `0 10px 32px rgba(0,0,0,0.42), inset 0 0 0 1px ${theme.color.warn}`,
        }}
      >
        <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          {t("display.confirm.title")}
        </div>
        <div style={{ marginTop: 2, fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("display.confirm.desc", { s: seconds })}
        </div>
        <div style={{ display: "flex", gap: theme.space.sm, marginTop: theme.space.sm }}>
          <Focusable
            role="button"
            aria-label={saving ? t("display.confirm.saving") : t("display.confirm.save")}
            aria-disabled={saving}
            style={{
              ...actionStyle,
              flex: 1,
              minWidth: 0,
              background: theme.color.accent,
              color: "#ffffff",
            }}
            onActivate={() => run(onSave)}
            onClick={() => run(onSave)}
          >
            <LuCheck size={16} />
            {saving ? t("display.confirm.saving") : t("display.confirm.save")}
          </Focusable>
          <Focusable
            role="button"
            aria-label={t("display.confirm.discard")}
            aria-disabled={saving}
            style={{
              ...actionStyle,
              background: "rgba(255,255,255,0.08)",
              color: theme.color.textPrimary,
              boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
            }}
            onActivate={() => run(onDiscard)}
            onClick={() => run(onDiscard)}
          >
            <LuUndo2 size={15} />
            {t("display.confirm.discard")}
          </Focusable>
        </div>
      </div>
    </>
  );
};
