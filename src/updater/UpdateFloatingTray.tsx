import { type FC, useRef, useSyncExternalStore } from "react";
import { Focusable, showModal } from "@decky/ui";
import { LuDownload } from "react-icons/lu";

import type { UpdateInfo } from "../api";
import type { Lang } from "../i18n";
import { useFloatingTrayClaimed } from "../components/useFloatingTrayClaim";
import { stickyTrayStyle, useStickyTray } from "../components/useStickyTray";
import { theme } from "../theme";
import { getUpdaterStrings } from "./strings";
import { UpdateModal } from "./UpdateModal";
import type { UpdateStatus } from "./useUpdate";

interface Props {
  lang: Lang;
  info: UpdateInfo | null;
  status: UpdateStatus;
}

let dismissedVersion: string | null = null;
const listeners = new Set<() => void>();
const getDismissedVersion = () => dismissedVersion;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function dismiss(version: string): void {
  dismissedVersion = version;
  listeners.forEach((listener) => listener());
}

const VisibleUpdateTray: FC<{ lang: Lang; info: UpdateInfo }> = ({ lang, info }) => {
  const t = getUpdaterStrings(lang).floating;
  const cardRef = useRef<HTMLDivElement>(null);
  const locked = useRef(false);
  useStickyTray(cardRef);
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
        ...stickyTrayStyle,
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
          onActivate={() => run(() => dismiss(info.latest))}
          onClick={() => run(() => dismiss(info.latest))}
        >
          {t.later}
        </Focusable>
      </Focusable>
    </div>
  );
};

export const UpdateFloatingTray: FC<Props> = ({ lang, info, status }) => {
  const dismissed = useSyncExternalStore(subscribe, getDismissedVersion, getDismissedVersion);
  const claimed = useFloatingTrayClaimed();
  if (info?.has_update !== true || info.latest === dismissed || claimed || status === "installing" || status === "done") return null;
  return <VisibleUpdateTray lang={lang} info={info} />;
};
