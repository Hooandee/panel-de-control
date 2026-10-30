import { Focusable } from "@decky/ui";
import { useEffect, useMemo, useRef, useState, type FC } from "react";
import { LuSmartphone } from "react-icons/lu";

import { useI18n } from "../../i18n";
import { qrPath } from "../../platform/qrCode";
import { theme } from "../../theme";
import type { AmbientRuntime } from "../steam/runtime";
import { Button } from "./primitives";

const POLL_MS = 1000;
const PAGE_KEYS = ["title", "hint", "placeholder", "send", "sent", "none", "expired", "error"] as const;

const Qr: FC<{ text: string }> = ({ text }) => {
  const { size, path } = useMemo(() => qrPath(text), [text]);
  const quiet = 3;
  return (
    <svg role="img" aria-label={text} viewBox={`${-quiet} ${-quiet} ${size + quiet * 2} ${size + quiet * 2}`} shapeRendering="crispEdges"
      style={{ width: "100%", maxWidth: 220, aspectRatio: "1", background: "#fff", borderRadius: 12 }}>
      <path d={path} fill="#000" />
    </svg>
  );
};

type Session = { url: string; endsAt: number } | { error: string } | null;

export const SharePanel: FC<{ runtime: AmbientRuntime; onClose: () => void }> = ({ runtime, onClose }) => {
  const { t, lang } = useI18n();
  const [session, setSession] = useState<Session>(null);
  const [received, setReceived] = useState(0);
  const [now, setNow] = useState(Date.now());
  const generation = useRef(0);

  const open = () => {
    const mine = ++generation.current;
    setSession(null);
    const texts: Record<string, string> = { lang };
    for (const key of PAGE_KEYS) texts[key] = t(`ambient.share.page.${key}`);
    void runtime.startShare(texts).then((result) => {
      if (mine !== generation.current) return;
      setSession("url" in result ? { url: result.url, endsAt: Date.now() + result.expiresIn * 1000 } : result);
    });
  };

  useEffect(() => {
    open();
    return () => { generation.current++; runtime.stopShare(); };
  }, [runtime]);

  const live = session && "url" in session && now < session.endsAt;
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => {
      setNow(Date.now());
      void runtime.pollShare().then(({ added, active }) => {
        if (added) setReceived((count) => count + added);
        if (!active) setNow(Number.POSITIVE_INFINITY);
      });
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runtime, live]);

  const remaining = session && "url" in session ? Math.max(0, Math.round((session.endsAt - now) / 1000)) : 0;
  return (
    <Focusable flow-children="column" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.sm, flex: 1, minHeight: 0, textAlign: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 15, fontWeight: 700, color: theme.color.textPrimary }}>
        <LuSmartphone size={18} style={{ color: theme.color.accent }} /> {t("ambient.share.title")}
      </div>
      {session === null && <span style={{ color: theme.color.textMuted }}>{t("ambient.lib.loading")}</span>}
      {session && "error" in session && <span role="status" style={{ color: theme.color.warn }}>{t(session.error === "no_network" ? "ambient.share.noNetwork" : "ambient.share.failed")}</span>}
      {session && "url" in session && (live
        ? <>
          <Qr text={session.url} />
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, maxWidth: 360 }}>{t("ambient.share.hint")}</span>
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, fontVariantNumeric: "tabular-nums" }}>{session.url}</span>
          <span role="status" style={{ fontSize: theme.font.caption, color: received ? theme.color.accent : theme.color.textMuted }}>
            {received ? t("ambient.queue.added", { n: String(received) }) : t("ambient.share.waiting", { time: `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}` })}
          </span>
        </>
        : <span style={{ color: theme.color.textMuted }}>{t("ambient.share.expired")}</span>)}
      <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.sm }}>
        {session && !live && <Button primary label={t("ambient.share.again")} onActivate={open} />}
        <Button label={t("ambient.share.done")} onActivate={onClose} />
      </Focusable>
    </Focusable>
  );
};
