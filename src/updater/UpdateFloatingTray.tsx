import { type FC, useLayoutEffect, useRef, useSyncExternalStore } from "react";
import { Focusable, showModal } from "@decky/ui";
import { LuDownload } from "react-icons/lu";

import type { UpdateInfo } from "../api";
import type { Lang } from "../i18n";
import { useFloatingTrayClaimed } from "../components/useFloatingTrayClaim";
import { theme } from "../theme";
import { getUpdaterStrings } from "./strings";
import { UpdateModal } from "./UpdateModal";
import type { UpdateStatus } from "./useUpdate";

interface Props {
  lang: Lang;
  info: UpdateInfo | null;
  status: UpdateStatus;
}

const TRAY_INSET = 16;

let sessionDismissed = false;
const listeners = new Set<() => void>();
const getDismissed = () => sessionDismissed;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function scrollContainer(node: HTMLElement): HTMLElement | null {
  const view = node.ownerDocument.defaultView;
  for (let parent = node.parentElement; parent; parent = parent.parentElement) {
    const overflow = view?.getComputedStyle(parent).overflowY;
    if (overflow === "auto" || overflow === "scroll") return parent;
  }
  return null;
}

// Steam scrolls gamepad focus into view without knowing the sticky card covers the bottom edge.
function useReservedScrollPadding(cardRef: { current: HTMLDivElement | null }): void {
  useLayoutEffect(() => {
    const card = cardRef.current;
    const container = card && scrollContainer(card);
    if (!card || !container) return;
    const previous = container.style.scrollPaddingBottom;
    const reserve = () => {
      container.style.scrollPaddingBottom = `${card.getBoundingClientRect().height + TRAY_INSET * 2}px`;
    };
    const view = card.ownerDocument.defaultView;
    const resize = view && typeof view.ResizeObserver === "function" ? new view.ResizeObserver(reserve) : null;
    resize?.observe(card);
    reserve();
    return () => {
      resize?.disconnect();
      container.style.scrollPaddingBottom = previous;
    };
  }, [cardRef]);
}

function dismiss(): void {
  sessionDismissed = true;
  listeners.forEach((listener) => listener());
}

const VisibleUpdateTray: FC<{ lang: Lang; info: UpdateInfo }> = ({ lang, info }) => {
  const t = getUpdaterStrings(lang).floating;
  const cardRef = useRef<HTMLDivElement>(null);
  const locked = useRef(false);
  useReservedScrollPadding(cardRef);
  const run = async (action: () => void) => {
    if (locked.current) return;
    locked.current = true;
    try {
      await action();
    } finally {
      locked.current = false;
    }
  };
  const update = () => { showModal(<UpdateModal lang={lang} latest={info.latest} notes={info.notes} />); };
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
    cursor: "pointer",
  } as const;

  return (
    <div
      ref={cardRef}
      data-update-tray="card"
      role="status"
      aria-live="polite"
      style={{
        // A fixed card inside the transformed QAM blanks the panel while gamepad focus scrolls it.
        position: "sticky",
        bottom: TRAY_INSET,
        zIndex: 1,
        marginTop: TRAY_INSET,
        boxSizing: "border-box",
        padding: theme.space.md,
        borderRadius: theme.radius.md,
        background: theme.color.surfaceRaised,
        boxShadow: `0 10px 32px rgba(0,0,0,0.42), inset 0 0 0 1px ${theme.color.accent}`,
      }}
    >
      <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>{t.title}</div>
      <div style={{ marginTop: 2, fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {`v${info.current} → v${info.latest}`}
      </div>
      <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.sm, marginTop: theme.space.sm }}>
        <Focusable
          role="button"
          aria-label={t.update}
          style={{ ...actionStyle, flex: 1, minWidth: 0, background: theme.color.accent, color: "#ffffff" }}
          onActivate={() => run(update)}
          onClick={() => run(update)}
        >
          <LuDownload size={16} />
          {t.update}
        </Focusable>
        <Focusable
          role="button"
          aria-label={t.later}
          style={{
            ...actionStyle,
            background: "rgba(255,255,255,0.08)",
            color: theme.color.textPrimary,
            boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          }}
          onActivate={() => run(dismiss)}
          onClick={() => run(dismiss)}
        >
          {t.later}
        </Focusable>
      </Focusable>
    </div>
  );
};

export const UpdateFloatingTray: FC<Props> = ({ lang, info, status }) => {
  const dismissed = useSyncExternalStore(subscribe, getDismissed, getDismissed);
  const claimed = useFloatingTrayClaimed();
  if (info?.has_update !== true || dismissed || claimed || status === "installing" || status === "done") return null;
  return <VisibleUpdateTray lang={lang} info={info} />;
};
